"""Clear customers left in a queue overnight.

Nobody taps Complete or Remove for the last customers of some days, so they'd
greet the next morning's barbers and inflate wait-time metrics. A background
thread checks every QUEUE_CLEANUP_CHECK_SECONDS for entries checked in before
today (shop time) that are still waiting or in the chair: waiting ones become
no-shows, and ones in the chair are marked done - they almost certainly got
their cut - with completed_at equal to called_at, so metrics count the cut but
not a made-up time in the chair (QueueEntry.has_chair_time).

The same thread also ends shop announcements at midnight (app/announcements.py).
"""
import threading
from collections import defaultdict
from datetime import datetime, time, timezone

from app import audit, db, socketio
from app.announcements import clear_expired_announcements
from app.models import QueueEntry, utcnow
from app.settings import get_timezone

_started = False
_start_lock = threading.Lock()


def _plural(count, noun):
    return f"{count} {noun}{'' if count == 1 else 's'}"


def clear_leftover_entries(now=None):
    """Returns the number of entries cleared."""
    from app.sockets import broadcast_queue

    now = now or utcnow()
    tz = get_timezone()
    start_of_today = datetime.combine(now.astimezone(tz).date(), time(0), tzinfo=tz).astimezone(timezone.utc)
    leftovers = (
        QueueEntry.query.filter(
            QueueEntry.status.in_([QueueEntry.STATUS_WAITING, QueueEntry.STATUS_IN_PROGRESS]),
            QueueEntry.checked_in_at < start_of_today,
        )
        .order_by(QueueEntry.id)
        .all()
    )
    if not leftovers:
        return 0

    by_location = defaultdict(list)
    for entry in leftovers:
        by_location[entry.location].append(entry)
        if entry.status == QueueEntry.STATUS_WAITING:
            # removed_at stays empty: it only times the Undo offer, which doesn't apply here.
            entry.status = QueueEntry.STATUS_CANCELLED
        else:
            entry.status = QueueEntry.STATUS_DONE
            entry.completed_at = entry.called_at or entry.checked_in_at
    db.session.commit()

    for location, entries in by_location.items():
        broadcast_queue(location)
        # Counted after the change above: cancelled ones were waiting, done ones were in the chair.
        waiting = sum(1 for e in entries if e.status == QueueEntry.STATUS_CANCELLED)
        in_chair = len(entries) - waiting
        details = []
        if waiting:
            details.append(f"{waiting} waiting marked as no-show{'' if waiting == 1 else 's'}")
        if in_chair:
            details.append(f"{in_chair} in the chair marked done")
        audit.record(
            "queue.auto_clear",
            f"Cleared {_plural(len(entries), 'customer')} left in the {location.name} queue "
            f"from before today: " + ", ".join(details),
            automatic=True,
        )
    return len(leftovers)


def start_queue_cleanup_checks(app):
    """Start the background check once per process (see app/background.py)."""
    global _started
    interval = app.config["QUEUE_CLEANUP_CHECK_SECONDS"]
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
                clear_leftover_entries()
            except Exception:
                app.logger.exception("Clearing leftover queue entries failed")
                db.session.rollback()
            try:
                clear_expired_announcements()
            except Exception:
                app.logger.exception("Clearing expired announcements failed")
                db.session.rollback()
            finally:
                db.session.remove()
