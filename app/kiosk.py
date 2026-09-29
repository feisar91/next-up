import secrets

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app import audit, db
from app.models import Location, QueueEntry
from app.opening_hours import reopens_text
from app.sockets import broadcast_queue, kiosk_barbers, queue_state
from app.web_app import manifest_response

kiosk_bp = Blueprint("kiosk", __name__)

# The "You're checked in" details, carried across the redirect after a check-in.
CONFIRMATION_SESSION_KEY = "kiosk_confirmation"


def _get_authorized_location(location_slug, token):
    location = Location.query.filter_by(slug=location_slug, active=True).first()
    if not location or not secrets.compare_digest(token, location.kiosk_token):
        abort(404)
    return location


@kiosk_bp.route("/kiosk/<location_slug>/<token>", methods=["GET", "POST"])
def check_in(location_slug, token):
    location = _get_authorized_location(location_slug, token)
    barbers = kiosk_barbers(location)

    if request.method == "POST":
        _check_in(location, barbers)
        # Post/Redirect/Get: the confirmation is a plain GET, so a reload during it
        # (a deploy, the store opening or closing) can't submit the check-in again.
        return redirect(url_for("kiosk.check_in", location_slug=location.slug, token=token))

    # Shown once: reloading the confirmation goes back to the check-in form.
    confirmation = session.pop(CONFIRMATION_SESSION_KEY, None)
    return render_template(
        "kiosk.html",
        location=location,
        token=token,
        barbers=barbers,
        confirmation=confirmation,
        reopens=reopens_text(location),
    )


@kiosk_bp.route("/kiosk/<location_slug>/<token>/manifest.webmanifest")
def web_app_manifest(location_slug, token):
    """Lets the shop tablet add this kiosk to its home screen and open it full-screen.
    The start URL carries the token, so this is protected the same way as the page."""
    location = _get_authorized_location(location_slug, token)
    kiosk_url = url_for("kiosk.check_in", location_slug=location.slug, token=token)
    return manifest_response(
        # Without the token, so a reinstall after regenerating the link replaces the old app.
        app_id=f"/kiosk/{location.slug}",
        name=f"Next Up Check-In - {location.name}",
        short_name="Check-In",
        start_url=kiosk_url,
        scope=kiosk_url,
        display="fullscreen",
    )


def _check_in(location, barbers):
    """Add the submitted customer to the queue, unless the store is closed (a
    kiosk page from before closing can still submit) or no name was given."""
    customer_name = request.form.get("customer_name", "").strip()
    if location.closed or not customer_name:
        return

    # Only accept a barber the kiosk actually offered; anything else (hidden,
    # off duty, or a tampered form) falls back to "no preference".
    preferred_barber_id = request.form.get("preferred_barber_id", "")
    preferred_barber = next((b for b in barbers if str(b.id) == preferred_barber_id), None)

    entry = QueueEntry(
        location_id=location.id,
        customer_name=customer_name,
        preferred_barber_id=preferred_barber.id if preferred_barber else None,
        status=QueueEntry.STATUS_WAITING,
    )
    db.session.add(entry)
    db.session.commit()

    broadcast_queue(location)
    detail = f" (prefers {preferred_barber.name})" if preferred_barber else ""
    audit.record("queue.checkin", f"{customer_name} checked in at {location.name}{detail}")

    position = len(queue_state(location)["waiting"])
    session[CONFIRMATION_SESSION_KEY] = {"name": customer_name, "position": position}
