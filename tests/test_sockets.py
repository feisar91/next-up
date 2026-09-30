from unittest.mock import patch

import pytest
from flask_login import login_user

from app import db, socketio
from app.models import Barber, Location, shorten_name
from app.sockets import handle_join, queue_state
from tests.conftest import kiosk_url


def _get_tokens(app, slug):
    with app.app_context():
        location = Location.query.filter_by(slug=slug).first()
        return location.kiosk_token, location.display_token


def test_join_with_valid_display_token_receives_queue_state(app, client, locations):
    _, display_token = _get_tokens(app, "mainstreet")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "mainstreet", "token": display_token})
    received = sio_client.get_received()

    assert any(evt["name"] == "queue_update" for evt in received)
    sio_client.disconnect()


def _check_in(client, app, name):
    client.post(kiosk_url(app, "mainstreet"), data={"customer_name": name, "preferred_barber_id": ""})


def _queue_updates(received):
    return [evt["args"][0] for evt in received if evt["name"] == "queue_update"]


def test_display_receives_shortened_customer_names(app, client, locations):
    _check_in(client, app, "Jordan Smith")
    _, display_token = _get_tokens(app, "mainstreet")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "mainstreet", "token": display_token})
    updates = _queue_updates(sio_client.get_received())

    assert updates
    assert [e["customer_name"] for e in updates[-1]["waiting"]] == ["Jordan S."]
    sio_client.disconnect()


def test_kiosk_does_not_receive_the_queue(app, client, locations):
    _check_in(client, app, "Jordan Smith")
    kiosk_token, _ = _get_tokens(app, "mainstreet")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "mainstreet", "token": kiosk_token})
    received = sio_client.get_received()

    assert _queue_updates(received) == []
    assert any(evt["name"] == "barbers_update" for evt in received)
    sio_client.disconnect()


def test_staff_queue_state_keeps_full_names(app, client, locations):
    _check_in(client, app, "Jordan Smith")
    with app.app_context():
        location = Location.query.filter_by(slug="mainstreet").first()
        assert queue_state(location)["waiting"][0]["customer_name"] == "Jordan Smith"
        assert queue_state(location, short_names=True)["waiting"][0]["customer_name"] == "Jordan S."


@pytest.mark.parametrize(
    "full, short",
    [
        ("Jordan Smith", "Jordan S."),
        ("jordan smith", "jordan S."),
        ("  Jordan   van der Berg ", "Jordan B."),
        ("Jordan", "Jordan"),
        ("Jordan O'Brien", "Jordan O."),
        ("Jordan (J)", "Jordan J."),
        ("Jordan 2", "Jordan"),
        ("", ""),
    ],
)
def test_shorten_name(full, short):
    assert shorten_name(full) == short


def test_join_with_wrong_token_gets_nothing(app, client, locations):
    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "mainstreet", "token": "not-the-real-token"})
    received = sio_client.get_received()

    assert received == []
    sio_client.disconnect()


def test_join_with_no_token_and_no_session_gets_nothing(app, client, locations):
    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "mainstreet"})
    received = sio_client.get_received()

    assert received == []
    sio_client.disconnect()


def test_join_unknown_location_gets_nothing(app, client, locations):
    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "nowhere", "token": "anything"})
    received = sio_client.get_received()

    assert received == []
    sio_client.disconnect()


# The scenarios above go through the real Socket.IO transport (socketio.test_client),
# which is reliable for these since they don't depend on a Flask-Login session. The
# "authenticated staff, no token" branch does depend on one, and Flask-SocketIO's
# threading-mode test client doesn't cleanly isolate Flask-Login sessions across
# back-to-back test_client() instances in the same process (confirmed: this exact
# scenario passes in isolation and in the live app, but flakes when preceded by another
# socketio.test_client() call in the same pytest run) - so this exercises handle_join's
# authorization logic directly under a real authenticated request context instead.
def test_authenticated_staff_can_join_without_a_token(app, locations, barber):
    with app.test_request_context():
        b = db.session.get(Barber, barber["id"])
        login_user(b)

        with patch("app.sockets.join_room") as mock_join_room, patch.object(
            socketio, "emit"
        ) as mock_emit:
            handle_join({"location": "riverside"})

        joined = [call.args[0] for call in mock_join_room.call_args_list]
        assert joined == ["location-riverside", "location-riverside-staff"]
        emitted = [(call.args[0], call.kwargs["to"]) for call in mock_emit.call_args_list]
        assert emitted == [
            ("queue_update", "location-riverside-staff"),
            ("queue_update", "location-riverside-display"),
            ("barbers_update", "location-riverside"),
            ("store_status", "location-riverside"),
            ("announcement", "location-riverside"),
            ("kiosk_status", "location-riverside-staff"),
        ]


def test_unauthenticated_request_context_join_gets_nothing(app, locations):
    with app.test_request_context():
        with patch("app.sockets.join_room") as mock_join_room, patch.object(
            socketio, "emit"
        ) as mock_emit:
            handle_join({"location": "riverside"})

        mock_join_room.assert_not_called()
        mock_emit.assert_not_called()
