from datetime import timedelta
from unittest.mock import patch

from app import db, sockets, socketio
from app.models import Location, utcnow
from app.sockets import kiosk_status
from tests.conftest import login

NOTE = b'id="kiosk-offline-note"'


def _location(slug="main-street"):
    return Location.query.filter_by(slug=slug).first()


def _connect_kiosk(app, slug="main-street"):
    with app.app_context():
        token = _location(slug).kiosk_token
    client = socketio.test_client(app, flask_test_client=app.test_client())
    client.emit("join", {"location": slug, "token": token}, callback=True)
    return client


def _kiosk_last_seen(app, ago):
    with app.app_context():
        _location().kiosk_last_seen_at = utcnow() - ago
        db.session.commit()


def _status(app):
    with app.app_context():
        return kiosk_status(_location())


# (room, payload) of each kiosk_status sent. Checked on socketio.emit rather than with
# a logged-in staff test client, which flakes (see the note in test_sockets.py).
def _kiosk_statuses(mock_emit):
    return [(c.kwargs["to"], c.args[1]) for c in mock_emit.call_args_list if c.args[0] == "kiosk_status"]


def test_kiosk_that_never_connected_is_not_reported_offline(app, locations):
    assert _status(app) == {"location": "main-street", "offline": False, "offline_in": None}


def test_connected_kiosk_is_not_offline(app, locations):
    kiosk = _connect_kiosk(app)
    assert _status(app) == {"location": "main-street", "offline": False, "offline_in": None}
    kiosk.disconnect()


def test_kiosk_that_just_dropped_off_gets_the_reconnect_grace(app, locations):
    _connect_kiosk(app).disconnect()
    status = _status(app)
    assert status["offline"] is False
    assert 5 <= status["offline_in"] <= 10


def test_kiosk_gone_longer_than_the_grace_is_offline(app, locations):
    _connect_kiosk(app).disconnect()
    _kiosk_last_seen(app, sockets.RECONNECT_GRACE + timedelta(seconds=1))
    assert _status(app)["offline"] is True


def test_kiosk_gone_for_a_while_is_offline(app, locations):
    _connect_kiosk(app).disconnect()
    _kiosk_last_seen(app, timedelta(minutes=5))
    assert _status(app) == {"location": "main-street", "offline": True, "offline_in": None}


def test_kiosks_get_the_grace_again_after_a_restart(app, locations):
    _kiosk_last_seen(app, timedelta(hours=3))
    sockets._process_started_at = utcnow()
    status = _status(app)
    assert status["offline"] is False
    assert 55 <= status["offline_in"] <= 60
    with app.app_context():
        assert sockets.device_status(_location())["kiosk"]["state"] == "unknown"


def test_dashboard_warns_when_the_kiosk_is_offline(app, client, locations, barber):
    _kiosk_last_seen(app, timedelta(minutes=5))
    login(client, barber["username"], barber["password"])
    resp = client.get("/staff/main-street")
    assert NOTE + b' role="status" >' in resp.data
    assert b"The kiosk isn't connected" in resp.data


def test_dashboard_hides_the_warning_while_the_kiosk_is_connected(app, client, locations, barber):
    kiosk = _connect_kiosk(app)
    login(client, barber["username"], barber["password"])
    resp = client.get("/staff/main-street")
    assert NOTE + b' role="status" hidden>' in resp.data
    kiosk.disconnect()


def test_no_kiosk_warning_while_the_store_is_closed(app, client, locations, barber):
    _kiosk_last_seen(app, timedelta(minutes=5))
    with app.app_context():
        _location().closed = True
        db.session.commit()
    login(client, barber["username"], barber["password"])
    assert NOTE not in client.get("/staff/main-street").data


def test_staff_hear_when_the_kiosk_connects_and_drops_off(app, locations):
    with patch.object(socketio, "emit") as mock_emit:
        kiosk = _connect_kiosk(app)
        kiosk.disconnect()

    (joined_room, joined), (dropped_room, dropped) = _kiosk_statuses(mock_emit)
    assert joined_room == dropped_room == "location-main-street-staff"
    assert joined == {"location": "main-street", "offline": False, "offline_in": None}
    assert dropped["offline"] is False and dropped["offline_in"] > 0


def test_tv_disconnecting_sends_no_kiosk_status(app, locations):
    with app.app_context():
        token = _location().display_token
    tv = socketio.test_client(app, flask_test_client=app.test_client())
    tv.emit("join", {"location": "main-street", "token": token}, callback=True)

    with patch.object(socketio, "emit") as mock_emit:
        tv.disconnect()
    assert _kiosk_statuses(mock_emit) == []
