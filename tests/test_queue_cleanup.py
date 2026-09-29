import csv
import io
from datetime import timedelta
from unittest.mock import patch

from app import db, queue_cleanup, socketio
from app.metrics import compute_metrics, visits_csv
from app.models import AdminAction, Location, QueueEntry, utcnow
from app.queue_cleanup import clear_leftover_entries, start_queue_cleanup_checks
from app.settings import get_timezone
from app.sockets import staff_queue_state
from tests.conftest import login


def _entry(location_id, name, status, checked_in_at, called_at=None, completed_at=None):
    entry = QueueEntry(
        location_id=location_id,
        customer_name=name,
        status=status,
        checked_in_at=checked_in_at,
        called_at=called_at,
        completed_at=completed_at,
    )
    db.session.add(entry)
    return entry


def _yesterdays_leftovers(locations):
    """Two waiting and one in the chair from yesterday, plus one of each from today."""
    yesterday = utcnow() - timedelta(days=1)
    mainstreet = locations["mainstreet"]
    _entry(mainstreet, "Jamie", QueueEntry.STATUS_WAITING, yesterday)
    _entry(mainstreet, "Sam", QueueEntry.STATUS_WAITING, yesterday)
    _entry(mainstreet, "Robin", QueueEntry.STATUS_IN_PROGRESS, yesterday, called_at=yesterday + timedelta(minutes=10))
    _entry(mainstreet, "Today Waiting", QueueEntry.STATUS_WAITING, utcnow())
    _entry(mainstreet, "Today Chair", QueueEntry.STATUS_IN_PROGRESS, utcnow(), called_at=utcnow())
    db.session.commit()


def _status(name):
    return QueueEntry.query.filter_by(customer_name=name).one()


def test_leftovers_from_before_today_are_cleared(app, locations):
    with app.app_context():
        _yesterdays_leftovers(locations)
        assert clear_leftover_entries() == 3

        assert _status("Jamie").status == QueueEntry.STATUS_CANCELLED
        assert _status("Jamie").removed_at is None  # never offered for Undo
        robin = _status("Robin")
        assert robin.status == QueueEntry.STATUS_DONE
        assert robin.completed_at == robin.called_at
        assert not robin.has_chair_time

        assert _status("Today Waiting").status == QueueEntry.STATUS_WAITING
        assert _status("Today Chair").status == QueueEntry.STATUS_IN_PROGRESS

        assert clear_leftover_entries() == 0  # nothing left to do


def test_clearing_is_logged_once_per_location(app, locations):
    with app.app_context():
        _yesterdays_leftovers(locations)
        clear_leftover_entries()
        entries = AdminAction.query.filter_by(action="queue.auto_clear").all()
        assert [(e.actor_name, e.category, e.summary) for e in entries] == [
            (
                "Automatic",
                "automatic",
                "Cleared 3 customers left in the Main Street queue from before today: "
                "2 waiting marked as no-shows, 1 in the chair marked done",
            )
        ]


def test_cleared_entries_leave_the_staff_screens(app, client, barber, locations):
    with app.app_context():
        _yesterdays_leftovers(locations)
    login(client, barber["username"], barber["password"])
    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "mainstreet"})
    sio_client.get_received()

    with app.app_context():
        clear_leftover_entries()
        state = staff_queue_state(Location.query.filter_by(slug="mainstreet").one())

    assert [e["customer_name"] for e in state["waiting"]] == ["Today Waiting"]
    assert [e["customer_name"] for e in state["in_progress"]] == ["Today Chair"]
    assert state["recent"] == []  # not offered for Undo
    updates = [evt["args"][0] for evt in sio_client.get_received() if evt["name"] == "queue_update"]
    assert updates and [e["customer_name"] for e in updates[-1]["waiting"]] == ["Today Waiting"]
    sio_client.disconnect()


def test_cleared_cuts_count_but_add_no_time_in_the_chair(app, locations):
    with app.app_context():
        two_days_ago = utcnow() - timedelta(days=2)
        _entry(
            locations["mainstreet"],
            "Timed",
            QueueEntry.STATUS_DONE,
            two_days_ago,
            called_at=two_days_ago,
            completed_at=two_days_ago + timedelta(minutes=20),
        )
        _yesterdays_leftovers(locations)
        clear_leftover_entries()

        metrics = compute_metrics(7, get_timezone())
        assert metrics["total_cuts"] == 2  # Timed, plus Robin cleared from the chair
        assert metrics["avg_service_minutes"] == 20  # Robin adds no chair time

        rows = list(csv.DictReader(io.StringIO(visits_csv(7, get_timezone()).lstrip("\ufeff"))))
        robin = next(row for row in rows if row["Customer"] == "Robin")
        assert robin["Time in chair (min)"] == ""


def test_check_thread_does_not_start_when_disabled(app):
    with patch.object(socketio, "start_background_task") as start:
        start_queue_cleanup_checks(app)  # TestConfig sets QUEUE_CLEANUP_CHECK_SECONDS = 0
    start.assert_not_called()
    assert queue_cleanup._started is False
