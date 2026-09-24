from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import audit, db
from app.authz import admin_required
from app.login_sessions import end_all_sessions, logged_in_barbers
from app.models import Barber, Location, QueueEntry
from app.settings import get_timezone_name, set_timezone_name, timezone_choices
from app.sockets import broadcast_barbers, broadcast_queue, device_status, disconnect_devices
from app.staff import clear_on_duty, set_on_duty

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

ACTIVITY_LOG_LIMIT = 100


@admin_bp.route("/")
@login_required
@admin_required
def overview():
    locations = Location.query.order_by(Location.name).all()
    active_locations = [location for location in locations if location.active]
    barbers = Barber.query.order_by(Barber.name).all()
    return render_template(
        "admin/overview.html",
        locations=locations,
        active_locations=active_locations,
        barbers=barbers,
        logged_in=logged_in_barbers(),
        device_statuses={location.id: device_status(location) for location in active_locations},
        activity=audit.recent(ACTIVITY_LOG_LIMIT),
        activity_limit=ACTIVITY_LOG_LIMIT,
        timezone_name=get_timezone_name(),
        timezone_choices=timezone_choices(),
    )


@admin_bp.route("/settings", methods=["POST"])
@login_required
@admin_required
def update_settings():
    tz_name = request.form.get("timezone", "").strip()
    if tz_name not in timezone_choices():
        flash("Choose a timezone from the list.", "error")
    else:
        previous = get_timezone_name()
        set_timezone_name(tz_name)
        if tz_name != previous:
            audit.record("settings.timezone", f"Changed the timezone from {previous} to {tz_name}")
        flash(f"Timezone set to {tz_name}.", "success")
    return redirect(url_for("admin.overview", _anchor="settings"))


@admin_bp.route("/locations", methods=["POST"])
@login_required
@admin_required
def create_location():
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip().lower()
    address = request.form.get("address", "").strip()

    if not name or not slug:
        flash("Location name and slug are required.", "error")
    elif Location.query.filter_by(slug=slug).first():
        flash(f"Slug '{slug}' is already in use.", "error")
    else:
        db.session.add(Location(name=name, slug=slug, address=address))
        db.session.commit()
        audit.record("location.create", f"Created location {name} ({slug})")
        flash(f"Location '{name}' created.", "success")

    return redirect(url_for("admin.overview", _anchor="locations"))


@admin_bp.route("/barbers", methods=["POST"])
@login_required
@admin_required
def create_barber():
    name = request.form.get("name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    default_location_id = request.form.get("default_location_id") or None
    is_admin = bool(request.form.get("is_admin"))
    show_on_kiosk = bool(request.form.get("show_on_kiosk"))

    if not all([name, username, password]):
        flash("Name, username and password are all required.", "error")
    elif password != confirm_password:
        flash("Temporary passwords do not match.", "error")
    elif Barber.query.filter_by(username=username).first():
        flash(f"Username '{username}' is already taken.", "error")
    else:
        barber = Barber(
            name=name,
            username=username,
            default_location_id=int(default_location_id) if default_location_id else None,
            is_admin=is_admin,
            show_on_kiosk=show_on_kiosk,
            must_change_password=True,
        )
        barber.set_password(password)
        db.session.add(barber)
        db.session.commit()
        audit.record(
            "barber.create",
            f"Created {'admin' if is_admin else 'barber'} {name} ({username})"
            + ("" if show_on_kiosk else ", hidden from the kiosk"),
        )
        flash(f"Barber '{name}' created.", "success")

    return redirect(url_for("admin.overview", _anchor="barbers"))


@admin_bp.route("/barbers/<int:barber_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_barber(barber_id):
    barber = db.get_or_404(Barber, barber_id)
    locations = Location.query.filter_by(active=True).order_by(Location.name).all()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        username = request.form.get("username", "").strip()
        default_location_id = request.form.get("default_location_id") or None
        is_admin = bool(request.form.get("is_admin"))

        existing = Barber.query.filter_by(username=username).first()

        if not name or not username:
            flash("Name and username are required.", "error")
        elif existing and existing.id != barber.id:
            flash(f"Username '{username}' is already taken.", "error")
        else:
            new_location_id = int(default_location_id) if default_location_id else None
            changes = _barber_changes(barber, name, username, new_location_id, is_admin)
            barber.name = name
            barber.username = username
            barber.default_location_id = new_location_id
            barber.is_admin = is_admin
            db.session.commit()
            if changes:
                audit.record("barber.edit", f"Edited {name}: " + "; ".join(changes))
            # The name shows on the kiosk's barber list and on queue entries.
            if barber.on_duty_location:
                broadcast_barbers(barber.on_duty_location)
                broadcast_queue(barber.on_duty_location)
            flash(f"Barber '{name}' updated.", "success")
            return redirect(url_for("admin.overview", _anchor="barbers"))

    return render_template("admin/edit_barber.html", barber=barber, locations=locations)


def _barber_changes(barber, name, username, default_location_id, is_admin):
    """Human-readable list of what an edit changes, for the activity log."""
    changes = []
    if name != barber.name:
        changes.append(f"name {barber.name} to {name}")
    if username != barber.username:
        changes.append(f"username {barber.username} to {username}")
    if default_location_id != barber.default_location_id:
        new_location = db.session.get(Location, default_location_id) if default_location_id else None
        old_name = barber.default_location.name if barber.default_location else "none"
        changes.append(f"default location {old_name} to {new_location.name if new_location else 'none'}")
    if is_admin != barber.is_admin:
        changes.append("granted admin access" if is_admin else "removed admin access")
    return changes


@admin_bp.route("/barbers/<int:barber_id>/reset-password", methods=["GET", "POST"])
@login_required
@admin_required
def reset_barber_password(barber_id):
    barber = db.get_or_404(Barber, barber_id)

    if barber.id == current_user.id:
        flash("Use your profile page to change your own password.", "error")
        return redirect(url_for("admin.overview", _anchor="barbers"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not password:
            flash("Enter a temporary password.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            barber.set_password(password)
            barber.must_change_password = True
            db.session.commit()
            end_all_sessions(barber)
            audit.record("barber.reset_password", f"Reset the password for {barber.name} and logged them out")
            flash(
                f"Temporary password set for '{barber.name}' - they'll be asked to choose "
                "their own password on next login.",
                "success",
            )
            return redirect(url_for("admin.overview", _anchor="barbers"))

    return render_template("admin/reset_password.html", barber=barber)


@admin_bp.route("/barbers/<int:barber_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def toggle_barber_active(barber_id):
    barber = db.get_or_404(Barber, barber_id)

    if barber.id == current_user.id:
        flash("You can't deactivate your own account.", "error")
        return redirect(url_for("admin.overview", _anchor="barbers"))

    barber.active = not barber.active
    db.session.commit()
    if not barber.active:
        clear_on_duty(barber)
        end_all_sessions(barber)
    audit.record(
        "barber.activate" if barber.active else "barber.deactivate",
        f"{'Activated' if barber.active else 'Deactivated'} {barber.name}",
    )
    flash(f"Barber '{barber.name}' is now {'active' if barber.active else 'inactive'}.", "success")
    return redirect(url_for("admin.overview", _anchor="barbers"))


@admin_bp.route("/barbers/<int:barber_id>/logout", methods=["POST"])
@login_required
@admin_required
def force_logout_barber(barber_id):
    barber = db.get_or_404(Barber, barber_id)

    if barber.id == current_user.id:
        flash("Use Log out in the menu to end your own session.", "error")
        return redirect(url_for("admin.overview", _anchor="barbers"))

    end_all_sessions(barber)
    clear_on_duty(barber)
    audit.record("barber.logout", f"Logged out {barber.name} and took them off duty")
    flash(f"'{barber.name}' has been logged out and taken off duty.", "success")
    return redirect(url_for("admin.overview", _anchor="barbers"))


@admin_bp.route("/barbers/<int:barber_id>/login", methods=["POST"])
@login_required
@admin_required
def put_barber_on_duty(barber_id):
    """Mark a barber as working at a shop without them logging in on a device
    (e.g. they forgot their phone), so customers can pick them on the kiosk.
    They stay on duty until logged out from here or they log in and out themselves."""
    barber = db.get_or_404(Barber, barber_id)
    location = Location.query.filter_by(id=request.form.get("location_id"), active=True).first()

    if not barber.active:
        flash(f"Activate '{barber.name}' before logging them in.", "error")
    elif not location:
        flash("Choose a location to log them in at.", "error")
    else:
        set_on_duty(barber, location)
        audit.record("barber.login", f"Logged in {barber.name} at {location.name} (on duty, no device)")
        flash(f"'{barber.name}' is now on duty at {location.name}.", "success")
    return redirect(url_for("admin.overview", _anchor="barbers"))


@admin_bp.route("/barbers/<int:barber_id>/toggle-kiosk", methods=["POST"])
@login_required
@admin_required
def toggle_barber_kiosk(barber_id):
    barber = db.get_or_404(Barber, barber_id)
    barber.show_on_kiosk = not barber.show_on_kiosk
    db.session.commit()
    if barber.on_duty_location:
        broadcast_barbers(barber.on_duty_location)
    audit.record(
        "barber.kiosk_visibility",
        f"{'Showed' if barber.show_on_kiosk else 'Hid'} {barber.name} {'on' if barber.show_on_kiosk else 'from'} the check-in kiosk",
    )
    flash(
        f"'{barber.name}' is now {'shown on' if barber.show_on_kiosk else 'hidden from'} the check-in kiosk.",
        "success",
    )
    return redirect(url_for("admin.overview", _anchor="barbers"))


@admin_bp.route("/barbers/<int:barber_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_barber(barber_id):
    barber = db.get_or_404(Barber, barber_id)
    if barber.active:
        flash(f"Deactivate '{barber.name}' before deleting them.", "error")
        return redirect(url_for("admin.overview", _anchor="barbers"))

    # Their past check-ins stay on record for metrics - just drop the name link
    # rather than deleting the QueueEntry rows themselves.
    QueueEntry.query.filter_by(preferred_barber_id=barber.id).update({"preferred_barber_id": None})
    QueueEntry.query.filter_by(called_by_barber_id=barber.id).update({"called_by_barber_id": None})

    name, username = barber.name, barber.username
    db.session.delete(barber)
    db.session.commit()
    audit.record("barber.delete", f"Deleted {name} ({username})")
    flash(f"Barber '{name}' has been permanently deleted.", "success")
    return redirect(url_for("admin.overview", _anchor="barbers"))


@admin_bp.route("/locations/<int:location_id>/toggle-active", methods=["POST"])
@login_required
@admin_required
def toggle_location_active(location_id):
    location = db.get_or_404(Location, location_id)
    location.active = not location.active
    db.session.commit()
    if not location.active:
        disconnect_devices(location)
    audit.record(
        "location.restore" if location.active else "location.remove",
        f"{'Restored' if location.active else 'Removed'} location {location.name}",
    )
    flash(
        f"Location '{location.name}' has been {'restored' if location.active else 'removed'}. "
        + (
            "Its kiosk and TV display links are working again."
            if location.active
            else "Its kiosk and TV display links have stopped working, and it no longer appears on the location picker."
        ),
        "success",
    )
    return redirect(url_for("admin.overview", _anchor="locations"))


@admin_bp.route("/locations/<int:location_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_location(location_id):
    location = db.get_or_404(Location, location_id)
    if location.active:
        flash(f"Remove '{location.name}' before deleting it.", "error")
        return redirect(url_for("admin.overview", _anchor="locations"))

    if QueueEntry.query.filter_by(location_id=location.id).first():
        flash(
            f"Can't delete '{location.name}' - it has historical check-in records. "
            "Locations with history can be removed but not deleted, to keep past metrics accurate.",
            "error",
        )
        return redirect(url_for("admin.overview", _anchor="locations"))

    Barber.query.filter_by(default_location_id=location.id).update({"default_location_id": None})
    Barber.query.filter_by(on_duty_location_id=location.id).update({"on_duty_location_id": None})

    name = location.name
    db.session.delete(location)
    db.session.commit()
    audit.record("location.delete", f"Deleted location {name}")
    flash(f"Location '{name}' has been permanently deleted.", "success")
    return redirect(url_for("admin.overview", _anchor="locations"))


@admin_bp.route("/locations/<int:location_id>/regenerate-kiosk-token", methods=["POST"])
@login_required
@admin_required
def regenerate_kiosk_token(location_id):
    location = db.get_or_404(Location, location_id)
    location.regenerate_kiosk_token()
    db.session.commit()
    disconnect_devices(location, kinds=("kiosk",))
    audit.record("location.regenerate_kiosk_link", f"Regenerated the kiosk link for {location.name}")
    flash(
        f"Kiosk link for '{location.name}' has been reset - update the tablet with the new link.",
        "success",
    )
    return redirect(url_for("admin.overview", _anchor="device-links"))


@admin_bp.route("/locations/<int:location_id>/regenerate-display-token", methods=["POST"])
@login_required
@admin_required
def regenerate_display_token(location_id):
    location = db.get_or_404(Location, location_id)
    location.regenerate_display_token()
    db.session.commit()
    disconnect_devices(location, kinds=("display",))
    audit.record("location.regenerate_display_link", f"Regenerated the TV display link for {location.name}")
    flash(
        f"TV display link for '{location.name}' has been reset - update the TV with the new link.",
        "success",
    )
    return redirect(url_for("admin.overview", _anchor="device-links"))
