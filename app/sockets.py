import secrets
import threading
from collections import Counter
from datetime import timedelta

from flask import current_app, request
from flask_login import current_user
from flask_socketio import join_room

from app import db, socketio
from app.models import Barber, Location, QueueEntry, utcnow

DEVICE_KINDS = ("kiosk", "display")
# How long after Complete / Remove a barber can undo it, and how many recently
# finished customers the staff dashboard lists.
UNDO_WINDOW = timedelta(minutes=10)
RECENT_LIMIT = 5
# A screen that dropped off this recently still counts as online: kiosks briefly
# disconnect on every check-in (the page reloads), and that shouldn't read as "Offline".
RECONNECT_GRACE = timedelta(seconds=60)

# Socket.IO session id -> (location_id, "kiosk" | "display") for every connected
# shop screen. In-memory is fine because the app runs as a single process (see
# README); after a restart the screens reconnect within seconds.
_device_connections = {}
_device_lock = threading.Lock()


def location_room(slug):
    """Every screen at a location: on-duty barber updates."""
    return f"location-{slug}"


def staff_room(slug):
    """Logged-in staff: the queue with customers' full names."""
    return f"location-{slug}-staff"


def display_room(slug):
    """The shop TV: the queue with shortened names ("Jordan S."), since the whole
    shop can read it. The kiosk joins neither queue room; it doesn't show the queue."""
    return f"location-{slug}-display"


def queue_state(location, short_names=False):
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
        "waiting": [e.to_dict(short_name=short_names) for e in waiting],
        "in_progress": [e.to_dict(short_name=short_names) for e in in_progress],
    }


def recently_finished(location):
    """Customers completed or removed within UNDO_WINDOW, newest first, for the
    staff dashboard's Undo list. `undo_seconds` is relative rather than a
    timestamp so a tablet with a wrong clock still hides the row on time."""
    now = utcnow()
    cutoff = now - UNDO_WINDOW
    entries = QueueEntry.query.filter(
        QueueEntry.location_id == location.id,
        db.or_(
            db.and_(QueueEntry.status == QueueEntry.STATUS_DONE, QueueEntry.completed_at >= cutoff),
            db.and_(QueueEntry.status == QueueEntry.STATUS_CANCELLED, QueueEntry.removed_at >= cutoff),
        ),
    ).all()
    entries.sort(key=lambda e: e.finished_at, reverse=True)
    return [
        {**e.to_dict(), "undo_seconds": int((e.finished_at + UNDO_WINDOW - now).total_seconds())}
        for e in entries[:RECENT_LIMIT]
    ]


def staff_queue_state(location):
    """The queue as staff see it: full names plus the recently finished list."""
    return {**queue_state(location), "recent": recently_finished(location)}


def broadcast_queue(location):
    socketio.emit("queue_update", staff_queue_state(location), to=staff_room(location.slug))
    socketio.emit("queue_update", queue_state(location, short_names=True), to=display_room(location.slug))


def kiosk_barbers(location):
    """Barbers a customer can pick as their preferred barber at this location."""
    return (
        Barber.query.filter_by(
            on_duty_location_id=location.id, active=True, show_on_kiosk=True, on_break=False
        )
        .order_by(Barber.name)
        .all()
    )


def on_duty_state(location):
    return {
        "location": location.slug,
        "barbers": [{"id": b.id, "name": b.name} for b in kiosk_barbers(location)],
    }


def broadcast_barbers(location):
    socketio.emit("barbers_update", on_duty_state(location), to=location_room(location.slug))


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
    device_kind = None
    if token and secrets.compare_digest(token, location.display_token):
        device_kind = "display"
    elif token and secrets.compare_digest(token, location.kiosk_token):
        device_kind = "kiosk"
    if not (device_kind or current_user.is_authenticated):
        return

    if device_kind:
        _track_device(location, device_kind)
    join_room(location_room(slug))
    if device_kind == "display":
        join_room(display_room(slug))
    elif not device_kind:
        join_room(staff_room(slug))
    broadcast_queue(location)
    broadcast_barbers(location)
    # Returned as the join acknowledgement: screens compare it with the version
    # they were loaded with and reload after a deploy (app/static/js/app-version.js).
    return {"version": current_app.config["APP_VERSION"]}


def _mark_seen(location_id, kind):
    location = db.session.get(Location, location_id)
    if location:
        setattr(location, f"{kind}_last_seen_at", utcnow())
        db.session.commit()


def _track_device(location, kind):
    with _device_lock:
        _device_connections[request.sid] = (location.id, kind)
    _mark_seen(location.id, kind)


@socketio.on("disconnect")
def handle_disconnect(*args):
    with _device_lock:
        device = _device_connections.pop(request.sid, None)
    if device:
        _mark_seen(*device)


def device_status(location):
    """{"kiosk": {...}, "display": {...}} for the admin Device Links tab. Each has
    state "online" / "offline" / "never", the number of screens connected, and
    last_seen (when it last connected or dropped off)."""
    with _device_lock:
        counts = Counter(
            kind for location_id, kind in _device_connections.values() if location_id == location.id
        )
    status = {}
    for kind in DEVICE_KINDS:
        last_seen = getattr(location, f"{kind}_last_seen_at")
        if last_seen is not None and last_seen.tzinfo is None:  # SQLite (tests) drops tzinfo
            last_seen = last_seen.replace(tzinfo=utcnow().tzinfo)
        if counts[kind]:
            state = "online"
        elif last_seen is None:
            state = "never"
        elif utcnow() - last_seen < RECONNECT_GRACE:
            state = "online"
        else:
            state = "offline"
        status[kind] = {"state": state, "count": counts[kind], "last_seen": last_seen}
    return status


def disconnect_devices(location, kinds=DEVICE_KINDS):
    """Drop the live connection of this location's kiosk and/or TV screens, e.g.
    after its link is regenerated. They try to reconnect, and their join fails
    unless their token is still valid, so a leaked old link stops receiving updates."""
    with _device_lock:
        sids = [
            sid
            for sid, (location_id, kind) in _device_connections.items()
            if location_id == location.id and kind in kinds
        ]
    for sid in sids:
        socketio.server.disconnect(sid, namespace="/")
