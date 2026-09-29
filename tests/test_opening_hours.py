from datetime import date, datetime, time, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import db, opening_hours, socketio
from app.models import AdminAction, Location, OpeningHours, SpecialHours, as_utc
from app.opening_hours import (
    apply_all_schedules,
    describe_when,
    next_automatic_change,
    reopens_text,
    scheduled_open,
    set_store_closed,
    start_opening_hours_checks,
)
from tests.conftest import kiosk_url, login

HOBART = ZoneInfo("Australia/Hobart")
MONDAY = date(2026, 11, 16)  # clear of the October daylight-saving change


def at(day, hour, minute=0):
    """A Hobart local time on `day` (a date) as a UTC datetime, like utcnow()."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=HOBART).astimezone(timezone.utc)


def monday(hour, minute=0, weeks_ahead=0, days_ahead=0):
    return at(date.fromordinal(MONDAY.toordinal() + weeks_ahead * 7 + days_ahead), hour, minute)


def _set_hours(app, slug="launceston", days=range(0, 6), opens=time(9), closes=time(17, 30), auto=True, cutoff=0):
    """Mon-Sat 9:00-5:30 by default, Sunday closed."""
    with app.app_context():
        location = Location.query.filter_by(slug=slug).one()
        location.opening_hours = [OpeningHours(weekday=d, opens_at=opens, closes_at=closes) for d in days]
        location.auto_hours = auto
        location.checkin_cutoff_minutes = cutoff
        db.session.commit()


def _location(slug="launceston"):
    return Location.query.filter_by(slug=slug).one()


def _add_special(app, day, opens=None, closes=None, slug="launceston"):
    with app.app_context():
        location = _location(slug)
        location.special_hours.append(SpecialHours(date=day, opens_at=opens, closes_at=closes))
        db.session.commit()


def _set_closed(app, closed, slug="launceston"):
    with app.app_context():
        _location(slug).closed = closed
        db.session.commit()


def _auto_entries(app):
    with app.app_context():
        return [
            (a.actor_name, a.action, a.summary, a.category)
            for a in AdminAction.query.filter(AdminAction.action.like("location.%")).order_by(AdminAction.id)
        ]


# --- The schedule itself ---


def test_open_between_opening_and_closing_time(app, locations):
    _set_hours(app)
    with app.app_context():
        location = _location()
        assert not scheduled_open(location, monday(8, 59))
        assert scheduled_open(location, monday(9))
        assert scheduled_open(location, monday(17, 29))
        assert not scheduled_open(location, monday(17, 30))
        assert not scheduled_open(location, monday(12, days_ahead=6))  # Sunday has no hours


def test_cutoff_closes_check_ins_early(app, locations):
    _set_hours(app, cutoff=30)
    with app.app_context():
        assert scheduled_open(_location(), monday(16, 59))
        assert not scheduled_open(_location(), monday(17))


def test_special_hours_replace_the_weekly_hours(app, locations):
    _set_hours(app)
    _add_special(app, MONDAY)  # closed all day
    _add_special(app, date(2026, 11, 17), opens=time(9), closes=time(14))
    with app.app_context():
        assert not scheduled_open(_location(), monday(12))
        assert scheduled_open(_location(), monday(13, days_ahead=1))
        assert not scheduled_open(_location(), monday(15, days_ahead=1))


def test_describe_when(app):
    with app.app_context():
        now = monday(8)
        assert describe_when(monday(9), now) == "at 9:00 am"
        assert describe_when(monday(0, days_ahead=1), now) == "at midnight"
        assert describe_when(monday(9, days_ahead=1), now) == "Tuesday at 9:00 am"
        assert describe_when(monday(17, 30, days_ahead=5), now) == "Saturday at 5:30 pm"
        assert describe_when(monday(9, weeks_ahead=1), now) == "Monday 23 Nov at 9:00 am"


def test_next_automatic_change(app, locations):
    _set_hours(app)
    with app.app_context():
        location = _location()
        location.closed = False
        assert next_automatic_change(location, monday(10)) == monday(17, 30)
        location.closed = True
        assert next_automatic_change(location, monday(18)) == monday(9, days_ahead=1)
        # Saturday evening: Sunday has no hours, so it's Monday.
        assert next_automatic_change(location, monday(18, days_ahead=5)) == monday(9, weeks_ahead=1)
        location.auto_hours = False
        assert next_automatic_change(location, monday(18)) is None


# --- The background check ---


def test_schedule_opens_and_closes_the_store(app, locations):
    _set_hours(app)
    _set_closed(app, True)

    with app.app_context():
        assert [loc.slug for loc in apply_all_schedules(monday(9))] == ["launceston"]
        assert _location().closed is False
        assert apply_all_schedules(monday(12)) == []  # already open
        apply_all_schedules(monday(17, 30))
        assert _location().closed is True

    assert _auto_entries(app) == [
        ("Automatic", "location.open", "Opened Launceston to new check-ins (opening hours)", "automatic"),
        ("Automatic", "location.close", "Closed Launceston to new check-ins (opening hours)", "automatic"),
    ]


def test_schedule_tells_the_kiosk(app, client, locations):
    _set_hours(app)
    _set_closed(app, True)
    with app.app_context():
        token = _location().kiosk_token
    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "launceston", "token": token})
    sio_client.get_received()

    with app.app_context():
        apply_all_schedules(monday(9))

    updates = [evt["args"][0] for evt in sio_client.get_received() if evt["name"] == "store_status"]
    assert updates == [{"location": "launceston", "closed": False}]
    sio_client.disconnect()


def test_locations_without_automatic_hours_are_left_alone(app, locations):
    _set_hours(app, auto=False)
    _set_closed(app, True)
    with app.app_context():
        assert apply_all_schedules(monday(12)) == []
        assert _location().closed is True


# --- Manual Open/Close ---


def test_closing_early_holds_until_closing_time_then_stays_closed(app, locations):
    _set_hours(app)
    with app.app_context():
        location = _location()
        set_store_closed(location, True, monday(15))
        assert as_utc(location.manual_until) == monday(17, 30)

        assert apply_all_schedules(monday(16)) == []
        assert location.closed is True
        apply_all_schedules(monday(17, 31))
        assert location.closed is True
        assert location.manual_until is None

        apply_all_schedules(monday(9, days_ahead=1))
        assert location.closed is False


def test_opening_late_by_hand_closes_again_at_midnight(app, locations):
    _set_hours(app)
    _set_closed(app, True)
    with app.app_context():
        location = _location()
        set_store_closed(location, False, monday(18))
        assert as_utc(location.manual_until) == monday(0, days_ahead=1)

        apply_all_schedules(monday(23, 30))
        assert location.closed is False
        apply_all_schedules(monday(0, 1, days_ahead=1))
        assert location.closed is True


def test_manual_change_that_matches_the_schedule_sets_no_hold(app, locations):
    _set_hours(app)
    _set_closed(app, True)
    with app.app_context():
        location = _location()
        set_store_closed(location, False, monday(10))
        assert location.manual_until is None


def test_staff_close_button_holds_against_the_schedule(app, client, barber, locations):
    _set_hours(app)
    login(client, barber["username"], barber["password"])
    with patch("app.opening_hours.utcnow", return_value=monday(15)):
        client.post("/staff/launceston/store", data={"closed": "1"})
        html = client.get("/staff/launceston").data.decode()

    assert "Opens automatically Tuesday at 9:00 am." in html
    with app.app_context():
        assert as_utc(_location().manual_until) == monday(17, 30)


# --- Screens ---


def test_closed_kiosk_says_when_it_reopens(app, client, locations):
    _set_hours(app)
    _set_closed(app, True)
    with patch("app.opening_hours.utcnow", return_value=monday(18)):
        html = client.get(kiosk_url(app, "launceston")).data.decode()
    assert "Back Tuesday at 9:00 am." in html


def test_closed_kiosk_without_automatic_hours_keeps_the_generic_message(app, client, locations):
    _set_closed(app, True)
    html = client.get(kiosk_url(app, "launceston")).data.decode()
    assert "Please check back later." in html
    with app.app_context():
        assert reopens_text(_location(), monday(18)) is None


def test_staff_card_says_when_the_store_closes(app, client, barber, locations):
    _set_hours(app)
    login(client, barber["username"], barber["password"])
    with patch("app.opening_hours.utcnow", return_value=monday(10)):
        html = client.get("/staff/launceston").data.decode()
    assert "Closes to check-ins automatically at 5:30 pm." in html


# --- Admin page ---


def _weekly_form(days=range(0, 6), opens="09:00", closes="17:30", auto=True, cutoff="0"):
    form = {"checkin_cutoff_minutes": cutoff}
    if auto:
        form["auto_hours"] = "on"
    for weekday in range(7):
        form[f"opens_{weekday}"] = opens
        form[f"closes_{weekday}"] = closes
        if weekday in days:
            form[f"open_{weekday}"] = "on"
    return form


def test_admin_saves_weekly_hours(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    url = f"/admin/locations/{locations['launceston']}/hours"
    assert client.get(url).status_code == 200

    with patch("app.opening_hours.utcnow", return_value=monday(10)):
        resp = client.post(url, data=_weekly_form(cutoff="15"), follow_redirects=True)
    assert b"Opening hours for Launceston saved." in resp.data

    with app.app_context():
        location = _location()
        assert location.auto_hours is True
        assert location.checkin_cutoff_minutes == 15
        assert sorted(h.weekday for h in location.opening_hours) == [0, 1, 2, 3, 4, 5]
        entry = AdminAction.query.filter_by(action="location.hours").one()
        assert entry.summary == (
            "Changed opening hours for Launceston: turned on automatic opening; "
            "Mon closed to 9:00 am-5:30 pm; Tue closed to 9:00 am-5:30 pm; Wed closed to 9:00 am-5:30 pm; "
            "Thu closed to 9:00 am-5:30 pm; Fri closed to 9:00 am-5:30 pm; Sat closed to 9:00 am-5:30 pm; "
            "check-in cutoff 0 to 15 minutes"
        )


def test_turning_on_automatic_hours_applies_them_straight_away(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    with patch("app.opening_hours.utcnow", return_value=monday(20)):
        client.post(f"/admin/locations/{locations['launceston']}/hours", data=_weekly_form())
    with app.app_context():
        assert _location().closed is True
        assert AdminAction.query.filter_by(action="location.close", category="automatic").count() == 1


def test_saving_unchanged_hours_is_not_logged(app, client, admin_barber, locations):
    _set_hours(app, auto=False)
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['launceston']}/hours", data=_weekly_form(auto=False))
    with app.app_context():
        assert AdminAction.query.filter_by(action="location.hours").count() == 0


def test_admin_hours_validation(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    url = f"/admin/locations/{locations['launceston']}/hours"

    resp = client.post(url, data=_weekly_form(opens="17:00", closes="09:00"))
    assert b"Closing time must be after opening time for Monday." in resp.data
    assert b'value="17:00"' in resp.data  # what was typed is kept

    resp = client.post(url, data=_weekly_form(cutoff="999"))
    assert b"The check-in cutoff must be between 0 and 240 minutes." in resp.data

    resp = client.post(url, data=_weekly_form(days=[]))
    assert b"Set opening hours for at least one day" in resp.data

    with app.app_context():
        assert _location().auto_hours is False
        assert _location().opening_hours == []
        assert AdminAction.query.filter(AdminAction.action.like("location.%")).count() == 0


def test_admin_adds_and_removes_special_hours(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    base = f"/admin/locations/{locations['launceston']}/special-hours"

    with patch("app.admin.datetime") as fake_datetime:
        fake_datetime.now.return_value = monday(8).astimezone(HOBART)
        client.post(base, data={"date": "2026-12-24", "opens": "09:00", "closes": "14:00", "note": "Christmas Eve"})
        client.post(base, data={"date": "2026-12-25", "closed_all_day": "on"})
        client.post(base, data={"date": "2026-11-01", "closed_all_day": "on"})  # in the past, refused

    with app.app_context():
        specials = _location().special_hours
        assert [(s.date, s.opens_at, s.closes_at) for s in specials] == [
            (date(2026, 12, 24), time(9), time(14)),
            (date(2026, 12, 25), None, None),
        ]
        christmas_id = specials[1].id

    client.post(f"{base}/{christmas_id}/delete")
    with app.app_context():
        assert [s.date for s in _location().special_hours] == [date(2026, 12, 24)]
        assert [a.summary for a in AdminAction.query.filter(AdminAction.action.like("location.special%"))] == [
            "Set Launceston to 9:00 am-2:00 pm on Thu 24 Dec 2026 (Christmas Eve)",
            "Set Launceston to closed on Fri 25 Dec 2026",
            "Removed the special hours for Launceston on Fri 25 Dec 2026",
        ]


def test_locations_tab_links_to_opening_hours(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    html = client.get("/admin/").data.decode()
    assert f'href="/admin/locations/{locations["launceston"]}/hours"' in html
    assert "<td>Manual</td>" in html


def test_deleting_a_location_deletes_its_hours(app, client, admin_barber, locations):
    _set_hours(app, slug="kings-meadows")
    _add_special(app, MONDAY, slug="kings-meadows")
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['kings-meadows']}/toggle-active")
    client.post(f"/admin/locations/{locations['kings-meadows']}/delete")
    with app.app_context():
        assert Location.query.filter_by(slug="kings-meadows").first() is None
        assert OpeningHours.query.count() == 0
        assert SpecialHours.query.count() == 0


def test_check_thread_does_not_start_when_disabled(app):
    with patch.object(socketio, "start_background_task") as start:
        start_opening_hours_checks(app)  # TestConfig sets OPENING_HOURS_CHECK_SECONDS = 0
    start.assert_not_called()
    assert opening_hours._started is False
