from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app import db
from app.models import MIN_PASSWORD_LENGTH, Location, QueueEntry
from app.sockets import broadcast_barbers, broadcast_queue, queue_state

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
    so the outgoing location's kiosk drops them and the new one adds them."""
    if barber.on_duty_location_id == location.id:
        return
    previous_location = barber.on_duty_location
    barber.on_duty_location_id = location.id
    db.session.commit()
    if previous_location:
        broadcast_barbers(previous_location)
    broadcast_barbers(location)


def clear_on_duty(barber):
    location = barber.on_duty_location
    if not location:
        return
    barber.on_duty_location_id = None
    db.session.commit()
    broadcast_barbers(location)


@staff_bp.route("/staff")
@login_required
def landing():
    """Send a barber to the location they're already working at this session,
    or to the picker if they haven't chosen one since logging in."""
    location_id = session.get(ACTIVE_LOCATION_SESSION_KEY)
    location = Location.query.filter_by(id=location_id, active=True).first() if location_id else None
    if location:
        return redirect(url_for("staff.dashboard", location_slug=location.slug))
    return redirect(url_for("staff.choose_location"))


@staff_bp.route("/staff/choose-location", methods=["GET", "POST"])
@login_required
def choose_location():
    locations = Location.query.filter_by(active=True).order_by(Location.name).all()

    if request.method == "POST":
        location = Location.query.filter_by(
            id=request.form.get("location_id"), active=True
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
                flash("Password updated.", "success")
            return redirect(url_for("staff.profile"))

        if request.form.get("form_name") == "display_name":
            name = request.form.get("name", "").strip()
            if not name:
                flash("Display name can't be empty.", "error")
            else:
                current_user.name = name
                db.session.commit()
                # The name shows on the kiosk's barber list and on queue entries.
                if current_user.on_duty_location:
                    broadcast_barbers(current_user.on_duty_location)
                    broadcast_queue(current_user.on_duty_location)
                flash("Display name updated.", "success")
            return redirect(url_for("staff.profile"))

        location_id = request.form.get("default_location_id") or None
        current_user.default_location_id = int(location_id) if location_id else None
        db.session.commit()
        flash("Default location updated.", "success")
        return redirect(url_for("staff.profile"))

    return render_template("profile.html", locations=locations)


@staff_bp.route("/staff/<location_slug>")
@login_required
def dashboard(location_slug):
    location = _get_location_or_404(location_slug)
    session[ACTIVE_LOCATION_SESSION_KEY] = location.id
    set_on_duty(current_user, location)
    state = queue_state(location)
    return render_template("staff_dashboard.html", location=location, state=state)


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
    return redirect(url_for("staff.dashboard", location_slug=location.slug))


@staff_bp.route("/staff/<location_slug>/remove/<int:entry_id>", methods=["POST"])
@login_required
def remove_customer(location_slug, entry_id):
    location = _get_location_or_404(location_slug)
    entry = QueueEntry.query.filter_by(
        id=entry_id, location_id=location.id, status=QueueEntry.STATUS_WAITING
    ).first_or_404()

    entry.status = QueueEntry.STATUS_CANCELLED
    db.session.commit()

    broadcast_queue(location)
    return redirect(url_for("staff.dashboard", location_slug=location.slug))
