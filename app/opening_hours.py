"""Open and close each store automatically on its opening hours.

A location with auto_hours on is open to check-ins from each day's opening time
until its closing time less checkin_cutoff_minutes. SpecialHours (a holiday, a
short day) replaces the weekly OpeningHours for its date. A background thread
checks every OPENING_HOURS_CHECK_SECONDS and flips Location.closed to match.

A barber's manual Open/Close that disagrees with the schedule holds until the
next scheduled change or local midnight, whichever comes first
(Location.manual_until): closing early isn't undone by the schedule, and a
store opened late by hand doesn't keep taking check-ins all night.

Functions take `now` (timezone-aware) so they can be tested at fixed times.
"""
import threading
from datetime import datetime, time, timedelta, timezone

from app import audit, db, socketio
from app.models import Location, as_utc, utcnow
from app.settings import get_timezone

# How far ahead to look for the next opening or closing.
LOOKAHEAD_DAYS = 14
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

_started = False
_start_lock = threading.Lock()


def format_clock(value):
    """'9:00 am' for a time or datetime, the same style as the local_time filter."""
    return f"{value.hour % 12 or 12}:{value:%M} {'am' if value.hour < 12 else 'pm'}"


def hours_on(location, day):
    """(opens_at, closes_at) for a local date, or None if closed all day."""
    special = next((s for s in location.special_hours if s.date == day), None)
    if special:
        return None if special.closed_all_day else (special.opens_at, special.closes_at)
    regular = next((h for h in location.opening_hours if h.weekday == day.weekday()), None)
    return (regular.opens_at, regular.closes_at) if regular else None


def checkin_window(location, day, tz):
    """When check-ins are open on `day`: (opens, closes) as local datetimes with the
    cutoff taken off closing time, or None if that leaves no time at all."""
    hours = hours_on(location, day)
    if not hours:
        return None
    opens = datetime.combine(day, hours[0], tzinfo=tz)
    closes = datetime.combine(day, hours[1], tzinfo=tz) - timedelta(minutes=location.checkin_cutoff_minutes)
    return (opens, closes) if closes > opens else None


def _windows(location, start):
    tz = get_timezone()
    first_day = start.astimezone(tz).date()
    for offset in range(LOOKAHEAD_DAYS + 1):
        window = checkin_window(location, first_day + timedelta(days=offset), tz)
        if window:
            yield window


def scheduled_open(location, now):
    """Whether the schedule has check-ins open at `now`."""
    tz = get_timezone()
    window = checkin_window(location, now.astimezone(tz).date(), tz)
    return bool(window) and window[0] <= now < window[1]


def next_change(location, now):
    """The next scheduled opening or closing after `now`, or None."""
    for opens, closes in _windows(location, now):
        for edge in (opens, closes):
            if edge > now:
                return edge
    return None


def _manual_hold(location, now):
    """When the current manual Open/Close stops holding, or None if none is."""
    until = as_utc(location.manual_until)
    return until if until and until > now else None


def next_automatic_change(location, now):
    """When the schedule will next flip this location's open/closed state (allowing
    for a manual hold), or None if automatic hours are off or nothing is due."""
    if not location.auto_hours:
        return None
    start = _manual_hold(location, now) or now
    if scheduled_open(location, start) == location.closed:
        return start  # the schedule disagrees with the current state once any hold ends
    for opens, closes in _windows(location, start):
        edge = opens if location.closed else closes
        if edge > start:
            return edge
    return None


def describe_when(moment, now):
    """'at 9:00 am' (today), 'at midnight', 'Tuesday at 9:00 am' (within the week) or
    'Tuesday 6 Oct at 9:00 am'. Never 'tomorrow', which would be wrong on a
    kiosk screen left open past midnight."""
    tz = get_timezone()
    local = moment.astimezone(tz)
    days = (local.date() - now.astimezone(tz).date()).days
    if days == 1 and local.time() == time(0, 0):
        return "at midnight"
    clock = f"at {format_clock(local)}"
    if days <= 0:
        return clock
    weekday = WEEKDAY_NAMES[local.weekday()]
    if days < 7:
        return f"{weekday} {clock}"
    return f"{weekday} {local.day} {local:%b} {clock}"


def schedule_note(location, now=None):
    """One line for the staff dashboard's store card about the next automatic change."""
    now = now or utcnow()
    change = next_automatic_change(location, now)
    if not change:
        return None
    when = describe_when(change, now)
    if _manual_hold(location, now):
        # Opened or closed by hand against the schedule: say so, or a late opening's
        # "at midnight" (when the hold ends) reads like a default.
        if location.closed:
            return f"Closed manually. Opens automatically {when}."
        return f"Opened manually. Closes automatically {when}."
    return f"Opens automatically {when}." if location.closed else f"Closes to check-ins automatically {when}."


def reopens_text(location, now=None):
    """'Back Tuesday at 9:00 am' for a closed kiosk, or None if there's no scheduled reopening."""
    now = now or utcnow()
    if not location.closed:
        return None
    change = next_automatic_change(location, now)
    return f"Back {describe_when(change, now)}" if change else None


def set_store_closed(location, closed, now=None):
    """A barber opening or closing the store by hand. When that disagrees with the
    schedule it holds until the next scheduled change, or midnight if sooner."""
    now = now or utcnow()
    location.closed = closed
    location.manual_until = None
    if location.auto_hours and closed == scheduled_open(location, now):
        tz = get_timezone()
        midnight = datetime.combine(now.astimezone(tz).date() + timedelta(days=1), time(0, 0), tzinfo=tz)
        change = next_change(location, now)
        until = min(change, midnight) if change else midnight
        # Stored as UTC: SQLite (tests) drops the offset and as_utc() assumes UTC.
        location.manual_until = until.astimezone(timezone.utc)
    db.session.commit()


def apply_schedule(location, now=None):
    """Open or close `location` to match its schedule. Returns the new `closed`
    value if it changed, else None."""
    from app.sockets import broadcast_store_status

    now = now or utcnow()
    if not (location.auto_hours and location.active):
        return None
    if location.manual_until is not None:
        if _manual_hold(location, now):
            return None
        location.manual_until = None
        db.session.commit()

    closed = not scheduled_open(location, now)
    if closed == location.closed:
        return None
    location.closed = closed
    db.session.commit()
    broadcast_store_status(location)
    audit.record(
        "location.close" if closed else "location.open",
        f"{'Closed' if closed else 'Opened'} {location.name} to new check-ins (opening hours)",
        automatic=True,
    )
    return closed


def apply_all_schedules(now=None):
    """Returns the locations whose open/closed state changed."""
    now = now or utcnow()
    changed = []
    for location in Location.query.filter_by(active=True, auto_hours=True).order_by(Location.id).all():
        if apply_schedule(location, now) is not None:
            changed.append(location)
    return changed


def start_opening_hours_checks(app):
    """Start the background check once per process (see app/background.py)."""
    global _started
    interval = app.config["OPENING_HOURS_CHECK_SECONDS"]
    if _started or not interval:
        return
    with _start_lock:
        if _started:
            return
        _started = True
    socketio.start_background_task(_run, app, interval)


def _run(app, interval):
    while True:
        socketio.sleep(interval)
        with app.app_context():
            try:
                apply_all_schedules()
            except Exception:
                app.logger.exception("Applying opening hours failed")
                db.session.rollback()
            finally:
                db.session.remove()
