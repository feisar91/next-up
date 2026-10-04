from datetime import timedelta

from app import db, sockets, socketio
from app.models import Location, utcnow
from app.sockets import device_status
from tests.conftest import login


def _location(app, slug="launceston"):
    with app.app_context():
        return Location.query.filter_by(slug=slug).first()


def _connect(app, kind, slug="launceston"):
    location = _location(app, slug)
    token = location.display_token if kind == "display" else location.kiosk_token
    client = socketio.test_client(app, flask_test_client=app.test_client())
    client.emit("join", {"location": slug, "token": token}, callback=True)
    return client


def _status(app, slug="launceston"):
    with app.app_context():
        return device_status(Location.query.filter_by(slug=slug).first())


def test_screens_start_as_never_connected(app, locations):
    status = _status(app)
    assert status["kiosk"]["state"] == "never"
    assert status["display"]["state"] == "never"


def test_connected_tv_and_kiosk_show_online(app, locations):
    tv = _connect(app, "display")
    kiosk = _connect(app, "kiosk")

    status = _status(app)
    assert status["display"] == {
        "state": "online",
        "count": 1,
        "last_seen": status["display"]["last_seen"],
        "offline_in": None,
    }
    assert status["kiosk"]["state"] == "online"
    assert _status(app, "kings-meadows")["display"]["state"] == "never"

    tv.disconnect()
    kiosk.disconnect()


def test_screen_that_just_dropped_off_still_counts_as_online(app, locations):
    _connect(app, "display").disconnect()
    assert _status(app)["display"]["state"] == "online"


def test_screen_gone_for_a_while_shows_offline_since(app, locations):
    _connect(app, "display").disconnect()
    with app.app_context():
        location = Location.query.filter_by(slug="launceston").first()
        location.display_last_seen_at = utcnow() - timedelta(minutes=5)
        db.session.commit()

    status = _status(app)["display"]
    assert status["state"] == "offline"
    assert status["last_seen"] is not None


def _restart(app, seen_ago):
    """As if the app had just started, with the TV last seen seen_ago before that."""
    with app.app_context():
        Location.query.filter_by(slug="launceston").first().display_last_seen_at = utcnow() - seen_ago
        db.session.commit()
    sockets._process_started_at = utcnow()


def test_screen_not_back_since_a_restart_is_unknown(app, locations):
    _restart(app, timedelta(hours=3))
    status = _status(app)["display"]
    assert status["state"] == "unknown"
    assert 55 <= status["offline_in"] <= 60
    assert _status(app, "kings-meadows")["display"]["state"] == "never"


def test_unknown_screen_turns_offline_when_the_startup_grace_ends(app, locations):
    _restart(app, timedelta(hours=3))
    sockets._process_started_at -= sockets.STARTUP_GRACE
    assert _status(app)["display"]["state"] == "offline"


def test_screen_that_reconnects_after_a_restart_is_online(app, locations):
    _restart(app, timedelta(hours=3))
    tv = _connect(app, "display")
    assert _status(app)["display"]["state"] == "online"
    tv.disconnect()


def test_screen_that_drops_off_after_a_restart_gets_only_the_reconnect_grace(app, locations):
    _restart(app, timedelta(hours=3))
    _connect(app, "display").disconnect()
    status = _status(app)["display"]
    assert status["state"] == "online"
    assert status["offline_in"] <= sockets.RECONNECT_GRACE.total_seconds()


def test_device_links_tab_shows_unknown_after_a_restart(app, client, locations, admin_barber):
    _restart(app, timedelta(hours=3))
    login(client, "morgan", "password123")
    html = client.get("/admin/").data.decode()
    tab = html[html.index('data-tab-panel="device-links"'):html.index('data-tab-panel="barbers"')]
    assert "Unknown (waiting for the screen to connect)" in tab


def test_two_screens_on_one_link_are_counted(app, locations):
    first, second = _connect(app, "display"), _connect(app, "display")
    assert _status(app)["display"]["count"] == 2
    first.disconnect()
    second.disconnect()


def test_staff_dashboards_are_not_counted_as_screens(app, locations, barber):
    staff_client = app.test_client()
    login(staff_client, "alex", "password123")
    sio = socketio.test_client(app, flask_test_client=staff_client)
    sio.emit("join", {"location": "launceston"}, callback=True)

    status = _status(app)
    assert status["kiosk"]["state"] == "never" and status["display"]["state"] == "never"
    sio.disconnect()


def test_device_links_tab_shows_status(app, client, locations, admin_barber):
    tv = _connect(app, "display")
    _connect(app, "display")
    login(client, "morgan", "password123")

    html = client.get("/admin/").data.decode()
    tab = html[html.index('data-tab-panel="device-links"'):html.index('data-tab-panel="barbers"')]
    assert "Online (2 screens)" in tab
    assert "More than one screen is using this TV display link" in tab
    assert "Never connected" in tab
    tv.disconnect()


def test_regenerating_a_link_disconnects_screens_on_the_old_one(app, client, locations, admin_barber):
    tv = _connect(app, "display")
    kiosk = _connect(app, "kiosk")
    login(client, "morgan", "password123")

    client.post(f"/admin/locations/{locations['launceston']}/regenerate-display-token")

    assert not tv.is_connected()
    assert kiosk.is_connected()
    kiosk.disconnect()


def test_removing_a_location_disconnects_its_screens(app, client, locations, admin_barber):
    tv = _connect(app, "display")
    login(client, "morgan", "password123")

    client.post(f"/admin/locations/{locations['launceston']}/toggle-active")

    assert not tv.is_connected()
