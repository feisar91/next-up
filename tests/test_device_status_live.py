"""The admin Device Links tab's live status lines (app/static/js/device-status.js)."""
from datetime import timedelta
from unittest.mock import patch

from flask_login import login_user

from app import db, socketio, sockets
from app.models import Barber, Location, utcnow
from app.sockets import ADMIN_DEVICES_ROOM, device_status_update, handle_watch_devices
from tests.conftest import login


def _location(slug="main-street"):
    return Location.query.filter_by(slug=slug).first()


def _connect(app, kind, slug="main-street"):
    with app.app_context():
        location = _location(slug)
        token = location.display_token if kind == "display" else location.kiosk_token
    client = socketio.test_client(app, flask_test_client=app.test_client())
    client.emit("join", {"location": slug, "token": token}, callback=True)
    return client


def _device_updates(mock_emit):
    return [
        (c.kwargs["to"], c.args[1]) for c in mock_emit.call_args_list if c.args[0] == "device_status"
    ]


# Called directly under a logged-in request context rather than through a logged-in
# socketio.test_client, which flakes (see the note in test_sockets.py).
def _watch_as(app, barber_id):
    with app.test_request_context():
        login_user(db.session.get(Barber, barber_id))
        with patch("app.sockets.join_room") as mock_join_room:
            ack = handle_watch_devices()
        return ack, [c.args[0] for c in mock_join_room.call_args_list]


def test_admin_page_gets_every_location_and_joins_the_admin_room(app, locations, admin_barber):
    ack, rooms = _watch_as(app, admin_barber["id"])
    assert rooms == [ADMIN_DEVICES_ROOM]
    assert sorted(update["location_id"] for update in ack) == sorted(locations.values())
    first = ack[0]
    assert "Never connected" in first["kiosk"]["html"]
    assert first["kiosk"]["offline_in"] is None


def test_barbers_cannot_watch_device_status(app, locations, barber):
    ack, rooms = _watch_as(app, barber["id"])
    assert ack is None
    assert rooms == []


def test_screens_connecting_and_dropping_off_are_pushed_to_admins(app, locations):
    with patch.object(socketio, "emit") as mock_emit:
        tv = _connect(app, "display")
        tv.disconnect()

    (joined_room, joined), (dropped_room, dropped) = _device_updates(mock_emit)
    assert joined_room == dropped_room == ADMIN_DEVICES_ROOM
    assert joined["location_id"] == locations["main-street"]
    assert "Online" in joined["display"]["html"] and joined["display"]["offline_in"] is None
    assert "Never connected" in joined["kiosk"]["html"]
    # Still online during the reconnect grace, with how long until it isn't.
    assert "Online" in dropped["display"]["html"]
    assert 5 <= dropped["display"]["offline_in"] <= 10


def test_status_after_the_grace_reads_offline(app, locations):
    _connect(app, "kiosk").disconnect()
    with app.app_context():
        location = _location()
        location.kiosk_last_seen_at = utcnow() - sockets.RECONNECT_GRACE - timedelta(seconds=1)
        db.session.commit()
        update = device_status_update(location)
    assert "Offline since" in update["kiosk"]["html"]
    assert update["kiosk"]["offline_in"] is None


def test_device_links_tab_has_live_slots(app, client, locations, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    html = client.get("/admin/").data.decode()
    main_street = locations["main-street"]
    assert f'id="device-status-{main_street}-kiosk"' in html
    assert f'id="device-status-{main_street}-display"' in html
    assert "js/device-status.js" in html
