from unittest.mock import patch

from flask_login import login_user

from app import db, socketio
from app.models import Barber, Location
from app.sockets import handle_join


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

        mock_join_room.assert_called_once_with("location-riverside")
        emitted_events = [call.args[0] for call in mock_emit.call_args_list]
        assert emitted_events == ["queue_update", "barbers_update"]


def test_unauthenticated_request_context_join_gets_nothing(app, locations):
    with app.test_request_context():
        with patch("app.sockets.join_room") as mock_join_room, patch.object(
            socketio, "emit"
        ) as mock_emit:
            handle_join({"location": "riverside"})

        mock_join_room.assert_not_called()
        mock_emit.assert_not_called()
