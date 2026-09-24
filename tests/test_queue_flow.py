from app import db
from app.models import QueueEntry
from tests.conftest import kiosk_url, login


def test_checkin_adds_waiting_entry(app, client, locations):
    resp = client.post(
        kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""}
    )
    assert resp.status_code == 200

    with app.app_context():
        entries = QueueEntry.query.all()
        assert len(entries) == 1
        assert entries[0].customer_name == "Jamie"
        assert entries[0].status == QueueEntry.STATUS_WAITING


def test_checkin_requires_name(app, client, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "", "preferred_barber_id": ""})

    with app.app_context():
        assert QueueEntry.query.count() == 0


def test_checkin_unknown_location_404s(client):
    resp = client.get("/kiosk/nowhere/some-token")
    assert resp.status_code == 404


def test_checkin_wrong_token_404s(app, client, locations):
    resp = client.get("/kiosk/launceston/wrong-token")
    assert resp.status_code == 404


def test_barber_can_call_and_complete_own_location_customer(app, client, locations, barber):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry = QueueEntry.query.filter_by(customer_name="Jamie").first()
        entry_id = entry.id

    resp = client.post(f"/staff/launceston/call/{entry_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        assert entry.status == QueueEntry.STATUS_IN_PROGRESS
        assert entry.called_by_barber_id == barber["id"]

    resp = client.post(f"/staff/launceston/complete/{entry_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        assert entry.status == QueueEntry.STATUS_DONE


def test_barber_can_remove_waiting_customer(app, client, locations, barber):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry_id = QueueEntry.query.filter_by(customer_name="Jamie").first().id

    client.post(f"/staff/launceston/remove/{entry_id}", follow_redirects=True)

    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        assert entry.status == QueueEntry.STATUS_CANCELLED


def test_dashboard_renders_waiting_customers(app, client, locations, barber):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    resp = client.get("/staff/launceston")
    assert resp.status_code == 200
    assert b"Jamie" in resp.data
    assert b"#1" in resp.data


def test_dashboard_renders_customer_in_chair(app, client, locations, barber):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry_id = QueueEntry.query.filter_by(customer_name="Jamie").first().id
    client.post(f"/staff/launceston/call/{entry_id}")

    resp = client.get("/staff/launceston")
    assert resp.status_code == 200
    assert b"Jamie" in resp.data
    assert b"Alex" in resp.data  # the barber who called them to the chair


def test_queue_position_ordering(app, client, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "First", "preferred_barber_id": ""})
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Second", "preferred_barber_id": ""})

    with app.app_context():
        entries = (
            QueueEntry.query.filter_by(status=QueueEntry.STATUS_WAITING)
            .order_by(QueueEntry.checked_in_at.asc())
            .all()
        )
        assert [e.customer_name for e in entries] == ["First", "Second"]
