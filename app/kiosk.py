import secrets

from flask import Blueprint, abort, redirect, render_template, request, session, url_for

from app import audit, db
from app.announcements import current_announcement
from app.branding import get_brand
from app.models import Location, QueueEntry, utcnow
from app.opening_hours import reopens_text
from app.sockets import broadcast_queue, kiosk_barbers, queue_state
from app.web_app import manifest_response

kiosk_bp = Blueprint("kiosk", __name__)

# The "You're checked in" details, carried across the redirect after a check-in.
CONFIRMATION_SESSION_KEY = "kiosk_confirmation"

# Most people one check-in can add ("Add another person" on the kiosk). The
# kiosk is public, so this also caps how much of the queue one tap can fill.
MAX_GROUP_SIZE = 6


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
        max_group_size=MAX_GROUP_SIZE,
        reopens=reopens_text(location),
        announcement=current_announcement(location),
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
        name=f"{get_brand().name} Check-In - {location.name}",
        short_name="Check-In",
        start_url=kiosk_url,
        scope=kiosk_url,
        display="fullscreen",
    )


def _check_in(location, barbers):
    """Add the submitted customers to the queue, unless the store is closed (a
    kiosk page from before closing can still submit) or no name was given.

    A group (a parent with their kids) sends one `customer_name` per person and
    gets consecutive places, each person a separate entry. They share one
    preferred barber."""
    names = [n.strip() for n in request.form.getlist("customer_name") if n.strip()][:MAX_GROUP_SIZE]
    if location.closed or not names:
        return

    # Only accept a barber the kiosk actually offered; anything else (hidden,
    # off duty, or a tampered form) falls back to "no preference".
    preferred_barber_id = request.form.get("preferred_barber_id", "")
    preferred_barber = next((b for b in barbers if str(b.id) == preferred_barber_id), None)

    # One check-in time for the whole group; the queue orders ties by id, so
    # flush each entry to give them ids in the order the names were entered.
    checked_in_at = utcnow()
    entries = []
    for name in names:
        entry = QueueEntry(
            location_id=location.id,
            customer_name=name,
            preferred_barber_id=preferred_barber.id if preferred_barber else None,
            status=QueueEntry.STATUS_WAITING,
            checked_in_at=checked_in_at,
        )
        db.session.add(entry)
        db.session.flush()
        entries.append(entry)
    db.session.commit()

    broadcast_queue(location)
    detail = f" (prefers {preferred_barber.name})" if preferred_barber else ""
    for i, name in enumerate(names):
        others = names[:i] + names[i + 1 :]
        with_others = f" with {_join_names(others)}" if others else ""
        audit.record("queue.checkin", f"{name} checked in at {location.name}{with_others}{detail}")

    waiting_ids = [e["id"] for e in queue_state(location)["waiting"]]
    session[CONFIRMATION_SESSION_KEY] = {
        "people": [{"name": e.customer_name, "position": waiting_ids.index(e.id) + 1} for e in entries]
    }


def _join_names(names):
    """'Mia', 'Mia and Leo', 'Jamie, Mia and Leo'."""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"
