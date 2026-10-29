from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app import audit, db
from app.announcements import MAX_LENGTH as ANNOUNCEMENT_MAX_LENGTH
from app.announcements import current_announcement, set_announcement
from app.models import MIN_PASSWORD_LENGTH, Location, QueueEntry
from app.opening_hours import schedule_note, set_store_closed
from app.branding import get_brand
from app.web_app import manifest_response
from app.sockets import (
    UNDO_WINDOW,
    broadcast_barbers,
    broadcast_queue,
    broadcast_store_status,
    kiosk_status,
    staff_queue_state,
)

staff_bp = Blueprint("staff", __name__)

ACTIVE_LOCATION_SESSION_KEY = "active_location_id"


def _get_location_or_404(location_slug):
    location = Location.query.filter_by(slug=location_slug, active=True).first()
    if not location:
        abort(404)
    return location


def set_on_duty(barber, location):
    """Mark a barber as working at `location`, so the kiosk's preferred-barber
    list picks them up live. Broadcasts to both the old and new location rooms
    so the outgoing location's kiosk drops them and the new one adds them.
    Returns whether anything changed."""
    if barber.on_duty_location_id == location.id:
        return False
    previous_location = barber.on_duty_location
    barber.on_duty_location_id = location.id
    barber.on_duty_since = datetime.now(timezone.utc)
    db.session.commit()
    if previous_location:
        broadcast_barbers(previous_location)
    broadcast_barbers(location)
    return True


def _work_at(location):
    """Put the logged-in barber on duty at `location`, logging it when that's a
    change (a first pick after logging in, or a move from another shop)."""
    previous = current_user.on_duty_location
    if not set_on_duty(current_user, location):
        return
    if previous:
        summary = f"{current_user.name} moved from {previous.name} to {location.name}"
    else:
        summary = f"{current_user.name} started working at {location.name}"
    audit.record("session.location", summary, category=audit.CATEGORY_BARBER)


def clear_on_duty(barber):
    location = barber.on_duty_location
    if not location:
        return
    barber.on_duty_location_id = None
    barber.on_duty_since = None
    barber.on_break = False
    db.session.commit()
    broadcast_barbers(location)


@staff_bp.route("/staff/app.webmanifest")
def web_app_manifest():
    """Lets barbers add the staff pages to their home screen (see app/web_app.py)."""
    return manifest_response(
        app_id="/staff",
        name=f"{get_brand().name} Staff",
        short_name=get_brand().name,
        start_url=url_for("staff.landing"),
        scope="/",
        display="standalone",
    )


@staff_bp.route("/staff")
@login_required
def landing():
    """Send a barber to the location they're already working at this session,
    or to the picker if they haven't chosen one since logging in."""
    location_id = session.get(ACTIVE_LOCATION_SESSION_KEY)
    location = Location.query.filter_by(id=location_id, active=True).first() if location_id else None
    if location:
        return redirect(url_for("staff.dashboard", location_slug=location.slug))
    # A new install has no locations yet: send the admin to set the shop up.
    if current_user.is_admin and not Location.query.filter_by(active=True).first():
        return redirect(url_for("admin.overview"))
    return redirect(url_for("staff.choose_location"))


@staff_bp.route("/staff/choose-location", methods=["GET", "POST"])
@login_required
def choose_location():
    locations = Location.query.filter_by(active=True).order_by(Location.name).all()

    if request.method == "POST":
        location = Location.query.filter_by(
            id=request.form.get("location_id", type=int), active=True
        ).first()
        if not location:
            abort(404)
        session[ACTIVE_LOCATION_SESSION_KEY] = location.id
        return redirect(url_for("staff.dashboard", location_slug=location.slug))

    default_location = current_user.default_location if current_user.default_location and current_user.default_location.active else None
    other_locations = [loc for loc in locations if loc != default_location]
    return render_template(
        "choose_location.html",
        default_location=default_location,
        other_locations=other_locations if default_location else locations,
    )


@staff_bp.route("/staff/profile", methods=["GET", "POST"])
@login_required
def profile():
    locations = Location.query.filter_by(active=True).order_by(Location.name).all()

    if request.method == "POST":
        if request.form.get("form_name") == "change_password":
            current_password = request.form.get("current_password", "")
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not current_user.check_password(current_password):
                flash("Current password is incorrect.", "error")
            elif len(password) < MIN_PASSWORD_LENGTH:
                flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
            elif password != confirm_password:
                flash("New passwords do not match.", "error")
            else:
                current_user.set_password(password)
                db.session.commit()
                # Log out any other phones/browsers still signed in with the old password.
                from app.login_sessions import end_all_sessions

                end_all_sessions(current_user, keep_current=True)
                audit.record(
                    "barber.change_own_password",
                    f"{current_user.name} changed their password",
                    category=audit.CATEGORY_BARBER,
                )
                flash("Password updated.", "success")
            return redirect(url_for("staff.profile"))

        name = request.form.get("name", "").strip()
        if not name:
            flash("Display name can't be empty.", "error")
            return redirect(url_for("staff.profile"))

        name_changed = name != current_user.name
        location_id = request.form.get("default_location_id") or None
        location_id = int(location_id) if location_id else None
        changes = audit.barber_changes(
            current_user, name, current_user.username, location_id, current_user.is_admin
        )
        current_user.name = name
        current_user.default_location_id = location_id
        db.session.commit()
        if changes:
            audit.record(
                "barber.edit_own_profile",
                f"{name} updated their profile: " + "; ".join(changes),
                category=audit.CATEGORY_BARBER,
            )
        # The name shows on the kiosk's barber list and on queue entries.
        if name_changed and current_user.on_duty_location:
            broadcast_barbers(current_user.on_duty_location)
            broadcast_queue(current_user.on_duty_location)
        flash("Profile updated.", "success")
        return redirect(url_for("staff.profile"))

    return render_template("profile.html", locations=locations)


@staff_bp.route("/staff/<location_slug>")
@login_required
def dashboard(location_slug):
    location = _get_location_or_404(location_slug)
    session[ACTIVE_LOCATION_SESSION_KEY] = location.id
    _work_at(location)
    state = staff_queue_state(location)
    return render_template(
        "staff_dashboard.html",
        location=location,
        state=state,
        schedule_note=schedule_note(location),
        kiosk_offline=kiosk_status(location)["offline"],
        announcement=current_announcement(location),
        announcement_max_length=ANNOUNCEMENT_MAX_LENGTH,
        undo_minutes=int(UNDO_WINDOW.total_seconds() // 60),
    )


@staff_bp.route("/staff/<location_slug>/store", methods=["POST"])
@login_required
def set_store_status(location_slug):
    """Close the store to new check-ins (e.g. no barbers rostered) or reopen it.
    The kiosk enforces this server-side too, in case a stale page still POSTs a
    check-in. The form sends the state it wants, same reasoning as set_break."""
    location = _get_location_or_404(location_slug)
    closed = request.form.get("closed") == "1"
    if closed != location.closed:
        set_store_closed(location, closed)
        broadcast_store_status(location)
        audit.record(
            "location.close" if closed else "location.open",
            f"{'Closed' if closed else 'Opened'} {location.name} to new check-ins",
            category=audit.CATEGORY_BARBER,
        )
    return redirect(url_for("staff.dashboard", location_slug=location.slug))


@staff_bp.route("/staff/<location_slug>/announcement", methods=["POST"])
@login_required
def set_location_announcement(location_slug):
    """Set the announcement on this shop's TV and kiosk until midnight; empty text clears it."""
    location = _get_location_or_404(location_slug)
    set_announcement(location, request.form.get("announcement", ""), category=audit.CATEGORY_BARBER)
    return redirect(url_for("staff.dashboard", location_slug=location.slug))


@staff_bp.route("/staff/<location_slug>/break", methods=["POST"])
@login_required
def set_break(location_slug):
    """Take yourself off (or back onto) the kiosk without logging out. The form
    sends the state it wants rather than toggling, so a stale page on a second
    device can't flip it the wrong way."""
    location = _get_location_or_404(location_slug)
    _work_at(location)
    on_break = request.form.get("on_break") == "1"
    changed = on_break != current_user.on_break
    current_user.on_break = on_break
    db.session.commit()
    broadcast_barbers(location)
    if changed:
        audit.record(
            "barber.break_start" if on_break else "barber.break_end",
            f"{current_user.name} {'went on break' if on_break else 'came back from break'} at {location.name}",
            category=audit.CATEGORY_BARBER,
        )
    return redirect(url_for("staff.dashboard", location_slug=location.slug))


@staff_bp.route("/staff/<location_slug>/call/<int:entry_id>", methods=["POST"])
@login_required
def call_customer(location_slug, entry_id):
    location = _get_location_or_404(location_slug)
    entry = QueueEntry.query.filter_by(
        id=entry_id, location_id=location.id, status=QueueEntry.STATUS_WAITING
    ).first_or_404()

    entry.status = QueueEntry.STATUS_IN_PROGRESS
    entry.called_at = datetime.now(timezone.utc)
    entry.called_by_barber_id = current_user.id
    db.session.commit()

    broadcast_queue(location)
    audit.record(
        "queue.call",
        f"Called {entry.customer_name} to the chair at {location.name}",
        category=audit.CATEGORY_BARBER,
    )
    return redirect(url_for("staff.dashboard", location_slug=location.slug))


@staff_bp.route("/staff/<location_slug>/complete/<int:entry_id>", methods=["POST"])
@login_required
def complete_customer(location_slug, entry_id):
    location = _get_location_or_404(location_slug)
    entry = QueueEntry.query.filter_by(
        id=entry_id, location_id=location.id, status=QueueEntry.STATUS_IN_PROGRESS
    ).first_or_404()

    entry.status = QueueEntry.STATUS_DONE
    entry.completed_at = datetime.now(timezone.utc)
    db.session.commit()

    broadcast_queue(location)
    audit.record(
        "queue.complete",
        f"Completed {entry.customer_name} at {location.name}",
        category=audit.CATEGORY_BARBER,
    )
    return redirect(url_for("staff.dashboard", location_slug=location.slug))


@staff_bp.route("/staff/<location_slug>/remove/<int:entry_id>", methods=["POST"])
@login_required
def remove_customer(location_slug, entry_id):
    location = _get_location_or_404(location_slug)
    entry = QueueEntry.query.filter_by(
        id=entry_id, location_id=location.id, status=QueueEntry.STATUS_WAITING
    ).first_or_404()

    entry.status = QueueEntry.STATUS_CANCELLED
    entry.removed_at = datetime.now(timezone.utc)
    db.session.commit()

    broadcast_queue(location)
    audit.record(
        "queue.remove",
        f"Removed {entry.customer_name} from the queue at {location.name} (no-show)",
        category=audit.CATEGORY_BARBER,
    )
    return redirect(url_for("staff.dashboard", location_slug=location.slug))


@staff_bp.route("/staff/<location_slug>/undo/<int:entry_id>", methods=["POST"])
@login_required
def undo_finish(location_slug, entry_id):
    """Undo an accidental Complete (back in the chair) or Remove (back in the
    queue, in their original place since it's ordered by check-in time)."""
    location = _get_location_or_404(location_slug)
    entry = QueueEntry.query.filter(
        QueueEntry.id == entry_id,
        QueueEntry.location_id == location.id,
        QueueEntry.status.in_([QueueEntry.STATUS_DONE, QueueEntry.STATUS_CANCELLED]),
    ).first_or_404()

    finished_at = entry.finished_at
    if finished_at is None or datetime.now(timezone.utc) - finished_at > UNDO_WINDOW:
        minutes = int(UNDO_WINDOW.total_seconds() // 60)
        flash(f"Too late to undo: {entry.customer_name} finished more than {minutes} minutes ago.", "error")
        return redirect(url_for("staff.dashboard", location_slug=location.slug))

    undone_complete = entry.status == QueueEntry.STATUS_DONE
    if undone_complete:
        entry.status = QueueEntry.STATUS_IN_PROGRESS
        entry.completed_at = None
    else:
        entry.status = QueueEntry.STATUS_WAITING
        entry.removed_at = None
    db.session.commit()

    broadcast_queue(location)
    audit.record(
        "queue.undo",
        f"Undid {'completing' if undone_complete else 'removing'} {entry.customer_name} at {location.name}",
        category=audit.CATEGORY_BARBER,
    )
    return redirect(url_for("staff.dashboard", location_slug=location.slug))
