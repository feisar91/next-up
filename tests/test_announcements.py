from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import audit, db, socketio
from app.announcements import MAX_LENGTH, clean_text, clear_expired_announcements, set_announcement
from app.models import AdminAction, Location, utcnow
from tests.conftest import display_url, kiosk_url, login

HOBART = ZoneInfo("Australia/Hobart")
# 11:30 pm in Hobart; the announcement should end half an hour later.
LATE_EVENING = datetime(2026, 9, 30, 23, 30, tzinfo=HOBART).astimezone(timezone.utc)
MIDNIGHT = datetime(2026, 10, 1, 0, 0, tzinfo=HOBART).astimezone(timezone.utc)


def _location(slug="mainstreet"):
    return Location.query.filter_by(slug=slug).first()


def _logged(app, action_prefix="location.announcement"):
    with app.app_context():
        return [
            (a.action, a.summary, a.category)
            for a in AdminAction.query.filter(AdminAction.action.like(f"{action_prefix}%")).order_by(AdminAction.id)
        ]


def _set_directly(app, text, until):
    with app.app_context():
        location = _location()
        location.announcement = text
        location.announcement_until = until
        db.session.commit()


def test_clean_text_makes_one_short_line():
    assert clean_text("  EFTPOS is down\n\ncash   only  ") == "EFTPOS is down cash only"
    assert clean_text("x" * 500) == "x" * MAX_LENGTH
    assert clean_text(None) == ""


def test_barber_sets_the_announcement_until_midnight(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    with patch("app.announcements.utcnow", return_value=LATE_EVENING):
        client.post("/staff/mainstreet/announcement", data={"announcement": "  EFTPOS is down - cash only  "})

    with app.app_context():
        location = _location()
        assert location.announcement == "EFTPOS is down - cash only"
        assert location.announcement_until.replace(tzinfo=timezone.utc) == MIDNIGHT
    assert _logged(app) == [
        (
            "location.announcement_set",
            'Set the Main Street announcement: "EFTPOS is down - cash only"',
            audit.CATEGORY_BARBER,
        )
    ]


def test_announcement_shows_on_the_tv_kiosk_and_dashboard(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.post("/staff/mainstreet/announcement", data={"announcement": "Kids' cuts $20 today"})

    for url in (display_url(app, "mainstreet"), kiosk_url(app, "mainstreet"), "/staff/mainstreet"):
        body = client.get(url).data
        assert b"Kids&#39; cuts $20 today" in body, url
    assert b'id="announcement" >' in client.get(display_url(app, "mainstreet")).data
    # Only on this location's screens.
    assert b"Kids&#39; cuts" not in client.get(display_url(app, "riverside")).data


def test_screens_without_an_announcement_hide_it(app, client, locations):
    assert b'id="announcement" hidden>' in client.get(display_url(app, "mainstreet")).data
    assert b'id="announcement" hidden>' in client.get(kiosk_url(app, "mainstreet")).data


def test_announcement_text_is_escaped(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.post("/staff/mainstreet/announcement", data={"announcement": "<script>alert(1)</script>"})
    body = client.get(display_url(app, "mainstreet")).data
    assert b"<script>alert(1)</script>" not in body
    assert b"&lt;script&gt;alert(1)&lt;/script&gt;" in body


def test_empty_text_clears_it(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.post("/staff/mainstreet/announcement", data={"announcement": "Back at 2 pm"})
    client.post("/staff/mainstreet/announcement", data={"announcement": "   "})

    with app.app_context():
        assert _location().announcement is None
        assert _location().announcement_until is None
    assert _logged(app)[-1] == (
        "location.announcement_clear",
        "Cleared the Main Street announcement",
        audit.CATEGORY_BARBER,
    )
    assert b"Back at 2 pm" not in client.get(display_url(app, "mainstreet")).data


def test_saving_the_same_text_again_is_not_logged_twice(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.post("/staff/mainstreet/announcement", data={"announcement": "Back at 2 pm"})
    client.post("/staff/mainstreet/announcement", data={"announcement": "Back at 2 pm "})
    assert len(_logged(app)) == 1


def test_admin_sets_an_announcement_from_the_locations_tab(app, client, locations, admin_barber):
    login(client, "morgan", "password123")
    resp = client.post(
        f"/admin/locations/{locations['riverside']}/announcement",
        data={"announcement": "Closing at 3 pm today"},
        follow_redirects=True,
    )
    assert b"until midnight" in resp.data
    assert b'value="Closing at 3 pm today"' in client.get("/admin/").data
    with app.app_context():
        assert _location("riverside").announcement == "Closing at 3 pm today"
    assert _logged(app) == [
        (
            "location.announcement_set",
            'Set the Riverside announcement: "Closing at 3 pm today"',
            audit.CATEGORY_ADMIN,
        )
    ]


def test_barbers_cannot_use_the_admin_route(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.post(f"/admin/locations/{locations['mainstreet']}/announcement", data={"announcement": "Hi"})
    with app.app_context():
        assert _location().announcement is None


def test_expired_announcement_is_not_shown(app, client, locations):
    _set_directly(app, "Yesterday's news", utcnow() - timedelta(minutes=1))
    assert b"Yesterday" not in client.get(display_url(app, "mainstreet")).data
    assert b"Yesterday" not in client.get(kiosk_url(app, "mainstreet")).data


def test_midnight_clears_expired_announcements_only(app, locations):
    _set_directly(app, "Yesterday's news", utcnow() - timedelta(minutes=1))
    with app.app_context():
        other = _location("riverside")
        other.announcement = "Still today"
        other.announcement_until = utcnow() + timedelta(hours=1)
        db.session.commit()

        with patch.object(socketio, "emit") as mock_emit:
            assert clear_expired_announcements() == 1
            assert clear_expired_announcements() == 0  # nothing left to do

        assert _location().announcement is None
        assert _location("riverside").announcement == "Still today"
    assert [(c.args[0], c.args[1], c.kwargs["to"]) for c in mock_emit.call_args_list] == [
        ("announcement", {"location": "mainstreet", "text": None}, "location-mainstreet")
    ]
    assert _logged(app) == [
        ("location.announcement_expire", "Cleared the Main Street announcement at midnight", audit.CATEGORY_AUTOMATIC)
    ]


def test_setting_it_tells_every_screen_at_the_location(app, locations):
    with app.app_context(), patch.object(socketio, "emit") as mock_emit:
        set_announcement(_location(), "Card only today")
    assert [(c.args[0], c.args[1], c.kwargs["to"]) for c in mock_emit.call_args_list] == [
        ("announcement", {"location": "mainstreet", "text": "Card only today"}, "location-mainstreet")
    ]


def test_kiosk_confirmation_screen_has_no_announcement(app, client, locations):
    _set_directly(app, "Card only today", utcnow() + timedelta(hours=1))
    client.post(kiosk_url(app, "mainstreet"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    body = client.get(kiosk_url(app, "mainstreet")).data
    assert b"You're checked in" in body
    assert b"Card only today" not in body
