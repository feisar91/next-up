import re
from pathlib import Path
from unittest.mock import patch

from app import compute_app_version, socketio
from app.sockets import handle_join
from tests.conftest import display_url, kiosk_url


def test_version_is_a_stable_fingerprint():
    first = compute_app_version()
    assert re.fullmatch(r"[0-9a-f]{12}", first)
    assert compute_app_version() == first


def test_static_urls_carry_the_version(app, client, locations):
    version = app.config["APP_VERSION"]
    html = client.get(kiosk_url(app, "launceston")).data.decode()

    assert f"js/kiosk.js?v={version}" in html
    assert f"css/brand.css?v={version}" in html


def test_kiosk_and_display_know_their_version_and_load_the_checker(app, client, locations):
    version = app.config["APP_VERSION"]
    for url in (kiosk_url(app, "launceston"), display_url(app, "launceston")):
        html = client.get(url).data.decode()
        assert f'window.APP_VERSION = "{version}"' in html
        assert "js/app-version.js" in html


def test_join_acknowledgement_returns_the_server_version(app, client, locations):
    from app.models import Location

    with app.app_context():
        token = Location.query.filter_by(slug="launceston").first().display_token

    sio_client = socketio.test_client(app, flask_test_client=client)
    ack = sio_client.emit("join", {"location": "launceston", "token": token}, callback=True)
    sio_client.disconnect()

    assert ack == {"version": app.config["APP_VERSION"]}


def test_unauthorised_join_gets_no_version(app, locations):
    with app.test_request_context(), patch("app.sockets.join_room"), patch.object(socketio, "emit"):
        assert handle_join({"location": "launceston", "token": "wrong"}) is None


def test_screens_pass_the_ack_to_the_version_check():
    for script in ("kiosk.js", "display.js", "staff.js"):
        assert "checkAppVersion(ack" in Path(f"app/static/js/{script}").read_text()
