from app import db, socketio
from app.auth import SETUP_CLAIM_KEY
from app.models import AdminAction, Barber, Location, QueueEntry, Setting, utcnow
from tests.conftest import login


def _create_first_admin(client, **overrides):
    data = {"name": "Sam Owner", "username": "sam", "password": "my-password-1", "confirm_password": "my-password-1"}
    data.update(overrides)
    return client.post("/setup", data=data, follow_redirects=True)


def _devices_step(html):
    start = html.index('data-step="devices"')
    return html[html.rindex("<li", 0, start) : html.index("</li>", start)]


def test_a_new_install_sends_everyone_to_setup(client):
    for url in ("/", "/login"):
        resp = client.get(url)
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/setup")
    html = client.get("/setup").data.decode()
    assert "Create the admin login for your shop" in html


def test_owner_creates_the_first_admin_and_lands_on_getting_started(app, client):
    resp = _create_first_admin(client)

    html = resp.data.decode()
    assert resp.request.path == "/admin/"
    assert "Getting Started" in html
    assert 'href="#locations">Add your first location</a>' in html
    admin = Barber.query.one()
    assert (admin.name, admin.username, admin.is_admin, admin.must_change_password) == ("Sam Owner", "sam", True, False)
    assert admin.check_password("my-password-1")
    assert Location.query.count() == 0
    entry = AdminAction.query.filter_by(action="setup.first_admin").one()
    assert (entry.actor_name, entry.summary) == ("Sam Owner", "Created the first admin login, Sam Owner (sam)")


def test_setup_checks_the_password(app, client):
    assert b"at least 8 characters" in _create_first_admin(client, password="short", confirm_password="short").data
    assert b"do not match" in _create_first_admin(client, confirm_password="something-else").data
    assert b"Enter your name and a username" in _create_first_admin(client, username=" ").data
    html = _create_first_admin(client, password="short", confirm_password="short").data.decode()
    assert 'value="Sam Owner"' in html  # what they typed is kept
    assert Barber.query.count() == 0


def test_setup_is_closed_once_any_login_exists(app, client, barber):
    assert client.get("/setup").headers["Location"].endswith("/login")
    _create_first_admin(client)
    assert Barber.query.filter_by(username="sam").first() is None


def test_setup_can_only_be_claimed_once(app, client):
    # Two setup forms submitted at the same moment: the claim row's primary key
    # lets only the first one through.
    db.session.add(Setting(key=SETUP_CLAIM_KEY, value="someone"))
    db.session.commit()

    resp = _create_first_admin(client)
    assert b"Setup has already been completed" in resp.data
    assert Barber.query.count() == 0


def test_bootstrap_only_points_to_the_browser(app, monkeypatch):
    monkeypatch.delenv("ADMIN_PASSWORD", raising=False)
    result = app.test_cli_runner().invoke(args=["bootstrap"])

    assert result.exit_code == 0, result.output
    assert "Open the app in your browser" in result.output
    assert Barber.query.count() == 0


def test_bootstrap_creates_an_admin_from_admin_password(app, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "first-run-pass")
    result = app.test_cli_runner().invoke(args=["bootstrap"])

    assert result.exit_code == 0, result.output
    assert "first-run-pass" not in result.output
    admin = Barber.query.one()
    assert (admin.username, admin.is_admin, admin.must_change_password) == ("admin", True, True)
    assert admin.check_password("first-run-pass")
    assert Location.query.count() == 0


def test_bootstrap_refuses_a_short_admin_password(app, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "short")
    result = app.test_cli_runner().invoke(args=["bootstrap"])
    assert result.exit_code != 0
    assert Barber.query.count() == 0


def test_bootstrap_does_nothing_once_a_login_exists(app, monkeypatch, barber):
    monkeypatch.setenv("ADMIN_PASSWORD", "first-run-pass")
    result = app.test_cli_runner().invoke(args=["bootstrap"])
    assert result.output == ""
    assert Barber.query.count() == 1


def test_seed_demo_fills_an_empty_database(app, client):
    result = app.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code == 0, result.output
    assert {location.slug for location in Location.query} == {"harbour-lane", "station-street"}
    assert QueueEntry.query.filter_by(status=QueueEntry.STATUS_WAITING).count() >= 5
    assert QueueEntry.query.filter_by(status=QueueEntry.STATUS_DONE).count() > 200

    login(client, "dana", "demo-password")
    for url in ("/admin/", "/admin/metrics", "/staff/harbour-lane"):
        assert client.get(url).status_code == 200, url


def test_seed_demo_refuses_a_database_in_use(app, barber):
    result = app.test_cli_runner().invoke(args=["seed-demo"])
    assert result.exit_code != 0
    assert "empty database" in result.output
    assert Location.query.count() == 2  # just the fixture's
    assert QueueEntry.query.count() == 0


def test_checklist_ticks_off_steps(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    html = client.get("/admin/").data.decode()
    assert '<li class="is-done" data-step="location"' in html
    assert '<li class="" data-step="branding"' in html


def test_checklist_can_be_hidden(app, client):
    _create_first_admin(client)
    client.post("/admin/setup/hide")
    assert "Getting Started" not in client.get("/admin/").data.decode()


def test_devices_step_needs_both_a_kiosk_and_a_tv(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    location = db.session.get(Location, locations["main-street"])
    location.kiosk_last_seen_at = utcnow()
    db.session.commit()

    step = _devices_step(client.get("/admin/").data.decode())
    assert 'class=""' in step
    assert 'data-kiosk-seen="true" data-display-seen="false"' in step

    db.session.get(Location, locations["riverside"]).display_last_seen_at = utcnow()
    db.session.commit()
    step = _devices_step(client.get("/admin/").data.decode())
    assert 'class="is-done"' in step


def test_device_updates_say_whether_a_screen_has_ever_connected(app, client, admin_barber, locations):
    from app.sockets import device_status_update

    with app.test_request_context():
        update = device_status_update(db.session.get(Location, locations["main-street"]))
    assert update["kiosk"]["state"] == update["display"]["state"] == "never"

    with app.app_context():
        display_token = db.session.get(Location, locations["main-street"]).display_token
    tv = socketio.test_client(app)
    tv.emit("join", {"location": "main-street", "token": display_token})
    with app.test_request_context():
        update = device_status_update(db.session.get(Location, locations["main-street"]))
    tv.disconnect()
    assert update["display"]["state"] == "online"


def test_device_status_script_ticks_the_checklist():
    from pathlib import Path

    script = Path("app/static/js/device-status.js").read_text()
    assert 'data-step="devices"' in script and "kioskSeen" in script and "displaySeen" in script


def test_checklist_disappears_when_everything_is_done(app, client, admin_barber, barber, locations):
    login(client, "morgan", "password123")
    client.post("/admin/branding", data={"name": "Fade Street", "dark": "#1f2933", "accent": "#0d9488"})
    client.post("/admin/settings", data={"timezone": "Europe/London"})
    location = db.session.get(Location, locations["main-street"])
    location.kiosk_last_seen_at = location.display_last_seen_at = utcnow()
    db.session.commit()
    assert "Getting Started" not in client.get("/admin/").data.decode()


def test_barber_with_no_locations_is_told_to_ask_an_admin(app, client):
    barber = Barber(name="Alex", username="alex")
    barber.set_password("password123")
    db.session.add(barber)
    db.session.commit()

    html = login(client, "alex", "password123").data.decode()
    assert "No locations are set up yet." in html
    assert "Ask your admin" in html


def test_location_link_name_is_made_from_the_name(app, client, admin_barber):
    login(client, "morgan", "password123")
    client.post("/admin/locations", data={"name": "  Main St. (North) ", "slug": ""})
    assert Location.query.filter_by(slug="main-st-north").one().name == "Main St. (North)"


def test_location_link_name_is_tidied(app, client, admin_barber):
    login(client, "morgan", "password123")
    client.post("/admin/locations", data={"name": "Riverside", "slug": "River Side!"})
    assert Location.query.filter_by(slug="river-side").count() == 1


def test_timezone_defaults_to_the_env_setting(app):
    from app.settings import get_timezone_name

    app.config["DEFAULT_TIMEZONE"] = "Europe/London"
    assert get_timezone_name() == "Europe/London"
    app.config["DEFAULT_TIMEZONE"] = "Not/AZone"
    assert get_timezone_name() == "UTC"
