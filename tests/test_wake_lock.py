from app import db
from app.models import Location
from tests.conftest import display_url, kiosk_url, login


def assert_keeps_screen_awake(resp):
    assert resp.status_code == 200
    assert b"js/wake-lock.js" in resp.data


def test_display_keeps_the_screen_awake(app, client, locations):
    assert_keeps_screen_awake(client.get(display_url(app, "mainstreet")))


def test_kiosk_keeps_the_screen_awake(app, client, locations):
    assert_keeps_screen_awake(client.get(kiosk_url(app, "mainstreet")))


def test_closed_kiosk_still_keeps_the_screen_awake(app, client, locations):
    with app.app_context():
        Location.query.filter_by(slug="mainstreet").first().closed = True
        db.session.commit()
    assert_keeps_screen_awake(client.get(kiosk_url(app, "mainstreet")))


def test_staff_dashboard_lets_phones_sleep(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    resp = client.get("/staff/mainstreet")
    assert resp.status_code == 200
    assert b"js/wake-lock.js" not in resp.data
