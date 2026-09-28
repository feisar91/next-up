from datetime import timedelta

from app import db, socketio
from app.models import QueueEntry, utcnow
from app.sockets import UNDO_WINDOW, staff_queue_state
from tests.conftest import kiosk_url, login


def _check_in(app, client, name):
    client.post(kiosk_url(app, "mainstreet"), data={"customer_name": name, "preferred_barber_id": ""})
    with app.app_context():
        return QueueEntry.query.filter_by(customer_name=name).one().id


def _entry(app, entry_id):
    with app.app_context():
        return db.session.get(QueueEntry, entry_id)


def _logged_in(client, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/mainstreet")


def test_undo_complete_puts_the_customer_back_in_the_chair(app, client, locations, barber):
    entry_id = _check_in(app, client, "Jordan")
    _logged_in(client, barber)
    client.post(f"/staff/mainstreet/call/{entry_id}")
    client.post(f"/staff/mainstreet/complete/{entry_id}")

    resp = client.post(f"/staff/mainstreet/undo/{entry_id}")

    assert resp.status_code == 302
    entry = _entry(app, entry_id)
    assert entry.status == QueueEntry.STATUS_IN_PROGRESS
    assert entry.completed_at is None
    assert entry.called_by_barber_id == barber["id"]


def test_undo_remove_puts_the_customer_back_in_their_place(app, client, locations, barber):
    first = _check_in(app, client, "First")
    second = _check_in(app, client, "Second")
    _logged_in(client, barber)
    client.post(f"/staff/mainstreet/remove/{first}")
    assert _entry(app, first).removed_at is not None

    client.post(f"/staff/mainstreet/undo/{first}")

    entry = _entry(app, first)
    assert entry.status == QueueEntry.STATUS_WAITING
    assert entry.removed_at is None
    with app.app_context():
        from app.models import Location

        state = staff_queue_state(Location.query.filter_by(slug="mainstreet").one())
    assert [e["id"] for e in state["waiting"]] == [first, second]


def test_undo_is_refused_after_the_window(app, client, locations, barber):
    entry_id = _check_in(app, client, "Jordan")
    _logged_in(client, barber)
    client.post(f"/staff/mainstreet/remove/{entry_id}")
    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        entry.removed_at = utcnow() - UNDO_WINDOW - timedelta(seconds=1)
        db.session.commit()

    resp = client.post(f"/staff/mainstreet/undo/{entry_id}", follow_redirects=True)

    assert b"Too late to undo" in resp.data
    assert _entry(app, entry_id).status == QueueEntry.STATUS_CANCELLED


def test_undo_does_not_touch_customers_still_in_the_queue(app, client, locations, barber):
    entry_id = _check_in(app, client, "Jordan")
    _logged_in(client, barber)

    assert client.post(f"/staff/mainstreet/undo/{entry_id}").status_code == 404
    assert _entry(app, entry_id).status == QueueEntry.STATUS_WAITING


def test_undo_is_limited_to_the_entrys_location(app, client, locations, barber):
    entry_id = _check_in(app, client, "Jordan")
    _logged_in(client, barber)
    client.post(f"/staff/mainstreet/remove/{entry_id}")

    assert client.post(f"/staff/riverside/undo/{entry_id}").status_code == 404
    assert _entry(app, entry_id).status == QueueEntry.STATUS_CANCELLED


def test_undo_requires_login(app, client, locations):
    entry_id = _check_in(app, client, "Jordan")
    resp = client.post(f"/staff/mainstreet/undo/{entry_id}")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_removals_from_before_this_feature_cannot_be_undone(app, client, locations, barber):
    # Rows cancelled before removed_at existed have no time, so no Undo.
    entry_id = _check_in(app, client, "Jordan")
    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        entry.status = QueueEntry.STATUS_CANCELLED
        db.session.commit()
    _logged_in(client, barber)

    client.post(f"/staff/mainstreet/undo/{entry_id}")
    assert _entry(app, entry_id).status == QueueEntry.STATUS_CANCELLED


def test_dashboard_lists_recently_finished_newest_first(app, client, locations, barber):
    done = _check_in(app, client, "Done Customer")
    removed = _check_in(app, client, "Removed Customer")
    _logged_in(client, barber)
    client.post(f"/staff/mainstreet/call/{done}")
    client.post(f"/staff/mainstreet/complete/{done}")
    client.post(f"/staff/mainstreet/remove/{removed}")

    html = client.get("/staff/mainstreet").data.decode()
    recent = html[html.index('id="recent-list"'):]
    assert recent.index("Removed Customer") < recent.index("Done Customer")
    assert "Completed with Alex" in recent
    assert "Removed from the queue" in recent
    assert f"/staff/mainstreet/undo/{done}" in recent


def test_recently_finished_card_is_hidden_when_empty(app, client, locations, barber):
    _logged_in(client, barber)
    html = client.get("/staff/mainstreet").data.decode()
    assert '<div class="card staff-section" id="recent-card" hidden>' in html


def test_recently_finished_drops_old_entries_and_caps_the_list(app, client, locations, barber):
    _logged_in(client, barber)
    ids = [_check_in(app, client, f"Customer {i}") for i in range(7)]
    for entry_id in ids:
        client.post(f"/staff/mainstreet/remove/{entry_id}")
    with app.app_context():
        from app.models import Location

        old = db.session.get(QueueEntry, ids[-1])
        old.removed_at = utcnow() - UNDO_WINDOW - timedelta(seconds=1)
        db.session.commit()
        recent = staff_queue_state(Location.query.filter_by(slug="mainstreet").one())["recent"]

    assert len(recent) == 5
    assert ids[-1] not in [e["id"] for e in recent]
    assert all(0 < e["undo_seconds"] <= UNDO_WINDOW.total_seconds() for e in recent)


def test_display_never_receives_the_recently_finished_list(app, client, locations, barber):
    from app.models import Location

    entry_id = _check_in(app, client, "Jordan Smith")
    _logged_in(client, barber)
    client.post(f"/staff/mainstreet/remove/{entry_id}")
    with app.app_context():
        display_token = Location.query.filter_by(slug="mainstreet").one().display_token

    sio_client = socketio.test_client(app, flask_test_client=app.test_client())
    sio_client.emit("join", {"location": "mainstreet", "token": display_token})
    updates = [e["args"][0] for e in sio_client.get_received() if e["name"] == "queue_update"]

    assert updates and all("recent" not in u for u in updates)
    sio_client.disconnect()
