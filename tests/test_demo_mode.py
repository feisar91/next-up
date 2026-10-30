"""The public demo (DEMO_MODE): hourly resets, turned-off actions and the word filter."""
import html
from datetime import datetime, timedelta, timezone

import pytest
from flask import g

from app import create_app, db
from app.branding import get_brand
from app.demo import DemoError
from app.demo_mode import BLOCKED_WORD, LAST_RESET_KEY, TURNED_OFF, last_scheduled_reset, next_reset, reset_demo, reset_due
from app.models import Barber, Location, LoginSession, QueueEntry, Setting
from app.word_filter import contains_blocked_word
from config import TestConfig
from tests.conftest import login

PASSWORD = "demo-password"


class DemoTestConfig(TestConfig):
    DEMO_MODE = True


@pytest.fixture()
def demo_app():
    app = create_app(DemoTestConfig)

    def reset_login_cache():  # as in conftest's app fixture
        g.pop("_login_user", None)
        g.pop("csrf_token", None)

    app.before_request_funcs.setdefault(None, []).insert(0, reset_login_cache)
    with app.app_context():
        db.create_all()
        reset_demo()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def demo_client(demo_app):
    return demo_app.test_client()


def _page(response):
    return html.unescape(response.data.decode())


def _location(slug="harbour-lane"):
    return Location.query.filter_by(slug=slug).one()


def _barber(username):
    return Barber.query.filter_by(username=username).one()


def _kiosk(slug="harbour-lane"):
    location = _location(slug)
    return f"/kiosk/{slug}/{location.kiosk_token}"


# Word filter -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["fuck", "Fuck off", "f u c k", "f.u.c.k", "fuuuuck", "sh1t", "$hit", "SHITHEAD", "fück", "ｆｕｃｋ",
     "cunts", "You twat", "dickhead", "2 girls 1 cup", "s&m", "🖕", "asssss", "motherfucker"],
)
def test_word_filter_catches_offensive_text(text):
    assert contains_blocked_word(text)


@pytest.mark.parametrize(
    "text",
    ["Jordan Smith", "Cassidy", "Hancock", "Dickson", "Yoshitaka", "Scunthorpe", "Butt", "Alan Cumming",
     "Matt Bass", "Shiitake", "Classes", "Closing at 4 pm on Friday", "EFTPOS is down - cash only today", ""],
)
def test_word_filter_leaves_ordinary_names_and_notices_alone(text):
    assert not contains_blocked_word(text)


# Resets ------------------------------------------------------------------------


def test_reset_puts_the_demo_back_and_keeps_device_links(demo_app, demo_client):
    location = _location()
    kiosk_token, display_token = location.kiosk_token, location.display_token
    login(demo_client, "marco", PASSWORD)
    demo_client.post(_kiosk(), data={"customer_name": "Visitor Added"})
    db.session.add(Location(name="Visitor Shop", slug="visitor-shop"))
    db.session.commit()
    assert QueueEntry.query.filter_by(customer_name="Visitor Added").count() == 1

    reset_demo()

    assert QueueEntry.query.filter_by(customer_name="Visitor Added").count() == 0
    assert Location.query.filter_by(slug="visitor-shop").count() == 0
    assert LoginSession.query.count() == 0
    location = _location()
    assert (location.kiosk_token, location.display_token) == (kiosk_token, display_token)
    assert demo_client.get("/staff/harbour-lane").status_code == 302  # logged out


def test_reset_keeps_every_location_open_around_the_clock(demo_app):
    assert all(not location.auto_hours and not location.closed for location in Location.query)


def test_reset_refuses_a_database_the_demo_did_not_make(demo_app):
    db.session.delete(db.session.get(Setting, LAST_RESET_KEY))
    db.session.commit()

    with pytest.raises(DemoError, match="didn't create"):
        reset_demo()
    assert _barber("dana")


def test_reset_refuses_when_demo_mode_is_off(app, barber):
    with pytest.raises(DemoError, match="Demo mode is off"):
        reset_demo()
    assert Barber.query.count() == 1


def test_resets_are_due_on_the_hour(demo_app):
    reset_at = datetime(2026, 10, 29, 3, 0, 5, tzinfo=timezone.utc)
    reset_demo(now=reset_at)

    assert not reset_due(now=reset_at + timedelta(minutes=59))
    assert reset_due(now=datetime(2026, 10, 29, 4, 0, 0, tzinfo=timezone.utc))
    assert last_scheduled_reset(reset_at) == datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc)
    assert next_reset(reset_at) == datetime(2026, 10, 29, 4, 0, tzinfo=timezone.utc)


def test_resets_follow_demo_reset_minutes(demo_app):
    demo_app.config["DEMO_RESET_MINUTES"] = 120
    assert next_reset(datetime(2026, 10, 29, 3, 30, tzinfo=timezone.utc)) == datetime(
        2026, 10, 29, 4, 0, tzinfo=timezone.utc
    )


def test_bootstrap_loads_a_fresh_demo(demo_app):
    _barber("marco").name = "Renamed"
    db.session.commit()

    result = demo_app.test_cli_runner().invoke(args=["bootstrap"])

    assert result.exit_code == 0, result.output
    assert "fresh copy of the demo" in result.output
    assert _barber("marco").name == "Marco"


def test_bootstrap_won_t_erase_a_real_shop(app, barber):
    app.config["DEMO_MODE"] = True
    result = app.test_cli_runner().invoke(args=["bootstrap"])

    assert result.exit_code != 0
    assert "didn't create" in result.output
    assert Barber.query.count() == 1


def test_demo_reset_command_needs_demo_mode(app):
    result = app.test_cli_runner().invoke(args=["demo-reset"])

    assert result.exit_code != 0
    assert "Demo mode is off" in result.output


# Pages ---------------------------------------------------------------------------


def test_login_page_offers_one_click_logins_and_screen_links(demo_app, demo_client):
    page = demo_client.get("/login").data.decode()

    assert "Dana Wells, the owner" in page
    assert 'name="username" value="marco"' in page
    assert _kiosk() in page
    assert f"/display/harbour-lane/{_location().display_token}" in page
    assert "demo-banner" in page


def test_one_click_login_works(demo_app, demo_client):
    response = demo_client.post("/login", data={"username": "dana", "password": PASSWORD})
    assert response.status_code == 302
    assert "/login" not in response.headers["Location"]


def test_home_page_goes_to_the_demo_login_page(demo_app, demo_client):
    response = demo_client.get("/")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


def test_demo_login_page_has_the_username_form_too(demo_app, demo_client):
    page = demo_client.get("/login").data.decode()
    assert 'id="username"' in page and 'id="password"' in page


def test_kiosk_and_tv_show_the_demo_label(demo_app, demo_client):
    location = _location()
    for url in (_kiosk(), f"/display/harbour-lane/{location.display_token}"):
        assert "demo-banner-screen" in demo_client.get(url).data.decode()


def test_no_demo_banner_outside_demo_mode(app, client, locations):
    assert "demo-banner" not in client.get("/login").data.decode()
    assert "demo-banner" not in client.get(f"/kiosk/main-street/{db.session.get(Location, locations['main-street']).kiosk_token}").data.decode()


def test_setup_page_is_closed(demo_app, demo_client):
    response = demo_client.get("/setup")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")


# Turned-off actions --------------------------------------------------------------


def _admin_client(demo_app):
    client = demo_app.test_client()
    login(client, "dana", PASSWORD)
    return client


@pytest.mark.parametrize(
    "path",
    ["/admin/branding", "/admin/branding/logo", "/admin/branding/logo/remove"],
)
def test_branding_is_turned_off(demo_app, path):
    client = _admin_client(demo_app)
    response = client.post(path, data={"name": "Someone Else", "dark": "#000000", "accent": "#0d9488"},
                           follow_redirects=True)
    assert TURNED_OFF in _page(response)
    assert get_brand().name == "Harbour Lane Barbers"


@pytest.mark.parametrize(
    "action, data",
    [
        ("edit", {"name": "Hacked", "username": "marco"}),
        ("reset-password", {"password": "newpassword1", "confirm_password": "newpassword1"}),
        ("toggle-active", {}),
        ("logout", {}),
        ("delete", {}),
    ],
)
def test_demo_logins_can_t_be_changed(demo_app, action, data):
    client = _admin_client(demo_app)
    marco = _barber("marco")

    response = client.post(f"/admin/barbers/{marco.id}/{action}", data=data, follow_redirects=True)

    assert TURNED_OFF in _page(response)
    db.session.expire_all()
    marco = _barber("marco")
    assert marco.name == "Marco" and marco.active and marco.check_password(PASSWORD)


def test_logins_a_visitor_adds_can_be_changed(demo_app):
    client = _admin_client(demo_app)
    client.post("/admin/barbers", data={"name": "Visitor", "username": "visitor", "password": "password123",
                                        "confirm_password": "password123"})
    visitor = _barber("visitor")

    response = client.post(f"/admin/barbers/{visitor.id}/toggle-active", follow_redirects=True)

    assert TURNED_OFF not in _page(response)
    db.session.expire_all()
    assert not _barber("visitor").active


def test_demo_logins_can_t_change_their_own_password(demo_app, demo_client):
    login(demo_client, "marco", PASSWORD)
    response = demo_client.post(
        "/staff/profile",
        data={"form_name": "change_password", "current_password": PASSWORD, "password": "newpassword1",
              "confirm_password": "newpassword1"},
        follow_redirects=True,
    )
    assert TURNED_OFF in _page(response)
    db.session.expire_all()
    assert _barber("marco").check_password(PASSWORD)


@pytest.mark.parametrize("action", ["toggle-active", "regenerate-kiosk-token", "regenerate-display-token"])
def test_demo_locations_can_t_be_removed_or_relinked(demo_app, action):
    client = _admin_client(demo_app)
    location = _location()
    tokens = (location.kiosk_token, location.display_token)

    response = client.post(f"/admin/locations/{location.id}/{action}", follow_redirects=True)

    assert TURNED_OFF in _page(response)
    db.session.expire_all()
    location = _location()
    assert location.active and (location.kiosk_token, location.display_token) == tokens


def test_everyday_actions_still_work(demo_app):
    client = _admin_client(demo_app)
    location = _location()
    client.post(f"/admin/locations/{location.id}/announcement", data={"announcement": "Free coffee today"})
    db.session.expire_all()
    assert _location().announcement == "Free coffee today"


# Blocked words -------------------------------------------------------------------


def test_kiosk_turns_away_a_blocked_name(demo_app, demo_client):
    before = QueueEntry.query.count()

    response = demo_client.post(_kiosk(), data={"customer_name": ["Jordan", "Fuck Face"]}, follow_redirects=True)

    assert BLOCKED_WORD in _page(response)
    assert QueueEntry.query.count() == before
    # Shown once only.
    assert BLOCKED_WORD not in _page(demo_client.get(_kiosk()))


def test_kiosk_accepts_an_ordinary_name(demo_app, demo_client):
    demo_client.post(_kiosk(), data={"customer_name": "Sam Cassidy"})
    assert QueueEntry.query.filter_by(customer_name="Sam Cassidy").count() == 1


def test_staff_announcement_with_a_blocked_word_is_refused(demo_app, demo_client):
    login(demo_client, "marco", PASSWORD)
    previous = _location().announcement

    response = demo_client.post(
        "/staff/harbour-lane/announcement",
        data={"announcement": "this place is sh1t"},
        headers={"Referer": "http://localhost/staff/harbour-lane"},
        follow_redirects=True,
    )

    assert BLOCKED_WORD in _page(response)
    db.session.expire_all()
    assert _location().announcement == previous


def test_new_login_names_are_checked_too(demo_app):
    client = _admin_client(demo_app)
    client.post("/admin/barbers", data={"name": "Big Wanker", "username": "bw", "password": "password123",
                                        "confirm_password": "password123"})
    assert Barber.query.filter_by(username="bw").count() == 0


def test_passwords_are_not_checked(demo_app):
    client = _admin_client(demo_app)
    client.post("/admin/barbers", data={"name": "Visitor", "username": "visitor", "password": "shitshitshit",
                                        "confirm_password": "shitshitshit"})
    assert Barber.query.filter_by(username="visitor").count() == 1
