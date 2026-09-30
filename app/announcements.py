"""Shop announcements: one line of text per location, shown on its TV and kiosk,
e.g. "EFTPOS is down - cash only today". Barbers set it from the staff dashboard
and admins from the Locations tab. It's for the day it's set: every announcement
ends at local midnight (announcement_until), and the queue-cleanup thread clears
expired ones so screens left open overnight drop it too.
"""
from datetime import datetime, time, timedelta, timezone

from app import audit, db
from app.models import Location, utcnow
from app.settings import get_timezone

MAX_LENGTH = 140


def clean_text(text):
    """One line (runs of whitespace, including new lines, collapsed), at most MAX_LENGTH."""
    return " ".join((text or "").split())[:MAX_LENGTH]


def _aware(value):
    if value.tzinfo is None:  # SQLite (tests) drops tzinfo
        return value.replace(tzinfo=timezone.utc)
    return value


def current_announcement(location, now=None):
    """The announcement to show, or None if there isn't one or it has ended."""
    if not location.announcement:
        return None
    if location.announcement_until and _aware(location.announcement_until) <= (now or utcnow()):
        return None
    return location.announcement


def set_announcement(location, text, category=audit.CATEGORY_ADMIN, now=None):
    """Save (or, for empty text, clear) the announcement, tell the screens and log
    it. Returns the cleaned text, or None if cleared."""
    from app.sockets import broadcast_announcement

    now = now or utcnow()
    text = clean_text(text) or None
    if text == current_announcement(location, now):
        return text

    location.announcement = text
    if text:
        tz = get_timezone()
        midnight = datetime.combine(now.astimezone(tz).date() + timedelta(days=1), time(0), tzinfo=tz)
        location.announcement_until = midnight.astimezone(timezone.utc)
    else:
        location.announcement_until = None
    db.session.commit()
    broadcast_announcement(location)
    if text:
        audit.record(
            "location.announcement_set", f'Set the {location.name} announcement: "{text}"', category=category
        )
    else:
        audit.record("location.announcement_clear", f"Cleared the {location.name} announcement", category=category)
    return text


def clear_expired_announcements(now=None):
    """Clear announcements past their midnight. Returns how many were cleared."""
    from app.sockets import broadcast_announcement

    now = now or utcnow()
    expired = [
        location
        for location in Location.query.filter(Location.announcement.isnot(None)).order_by(Location.id)
        if current_announcement(location, now) is None
    ]
    for location in expired:
        location.announcement = None
        location.announcement_until = None
    db.session.commit()

    for location in expired:
        broadcast_announcement(location)
        audit.record(
            "location.announcement_expire",
            f"Cleared the {location.name} announcement at midnight",
            automatic=True,
        )
    return len(expired)
