from pathlib import Path

from app import db
from app.models import Location
from tests.conftest import display_url, kiosk_url, login


def assert_hidden_banner(resp, message):
    assert resp.status_code == 200
    assert b'id="connection-banner"' in resp.data
    assert b'role="status" hidden' in resp.data
    assert message.encode() in resp.data
    assert b"js/connection-status.js" in resp.data


def test_display_page_includes_a_hidden_connection_lost_banner(app, client, locations):
    assert_hidden_banner(client.get(display_url(app, "main-street")), "Connection lost - reconnecting")


def test_kiosk_page_includes_a_hidden_connection_lost_banner(app, client, locations):
    assert_hidden_banner(
        client.get(kiosk_url(app, "main-street")), "Connection lost - check-in is paused until it&#39;s back"
    )


def test_closed_kiosk_still_includes_the_banner(app, client, locations):
    with app.app_context():
        Location.query.filter_by(slug="main-street").first().closed = True
        db.session.commit()
    assert_hidden_banner(client.get(kiosk_url(app, "main-street")), "Connection lost")


def test_staff_dashboard_includes_a_hidden_connection_lost_banner(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    assert_hidden_banner(client.get("/staff/main-street"), "the queue isn&#39;t updating")


def test_screens_watch_their_connection():
    for script in ("kiosk.js", "display.js", "staff.js"):
        assert "watchConnection(socket" in Path(f"app/static/js/{script}").read_text()
