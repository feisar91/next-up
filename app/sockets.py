import secrets

from flask_login import current_user
from flask_socketio import join_room

from app import socketio
from app.models import Barber, Location, QueueEntry


def queue_state(location):
    waiting = (
        QueueEntry.query.filter_by(location_id=location.id, status=QueueEntry.STATUS_WAITING)
        .order_by(QueueEntry.checked_in_at.asc())
        .all()
    )
    in_progress = (
        QueueEntry.query.filter_by(location_id=location.id, status=QueueEntry.STATUS_IN_PROGRESS)
        .order_by(QueueEntry.called_at.asc())
        .all()
    )
    return {
        "location": location.slug,
        "waiting": [e.to_dict() for e in waiting],
        "in_progress": [e.to_dict() for e in in_progress],
    }


def broadcast_queue(location):
    socketio.emit("queue_update", queue_state(location), to=f"location-{location.slug}")


def kiosk_barbers(location):
    """Barbers a customer can pick as their preferred barber at this location."""
    return (
        Barber.query.filter_by(on_duty_location_id=location.id, active=True, show_on_kiosk=True)
        .order_by(Barber.name)
        .all()
    )


def on_duty_state(location):
    return {
        "location": location.slug,
        "barbers": [{"id": b.id, "name": b.name} for b in kiosk_barbers(location)],
    }


def broadcast_barbers(location):
    socketio.emit("barbers_update", on_duty_state(location), to=f"location-{location.slug}")


@socketio.on("join")
def handle_join(data):
    slug = (data or {}).get("location")
    token = (data or {}).get("token")
    if not slug:
        return

    location = Location.query.filter_by(slug=slug, active=True).first()
    if not location:
        return

    # Three ways to prove you're allowed to watch this location's live room:
    # the TV display's bearer token, the kiosk's bearer token (it needs the
    # on-duty barber roster, not the queue), or an authenticated staff session
    # (any logged-in barber/admin - matches the staff dashboard's own access
    # model, which already lets any barber work any location).
    has_valid_token = bool(token) and (
        secrets.compare_digest(token, location.display_token)
        or secrets.compare_digest(token, location.kiosk_token)
    )
    if not (has_valid_token or current_user.is_authenticated):
        return

    join_room(f"location-{slug}")
    socketio.emit("queue_update", queue_state(location), to=f"location-{slug}")
    socketio.emit("barbers_update", on_duty_state(location), to=f"location-{slug}")
