from datetime import datetime, timedelta

from app import audit, db
from app.models import AdminAction, Barber, QueueEntry
from app.settings import get_timezone
from tests.conftest import kiosk_url, login


def _entries():
    """Log entries oldest first, without the login/logout entries that nearly
    every test's setup produces (those have their own tests below)."""
    return AdminAction.query.filter(~AdminAction.action.like("session.%")).order_by(AdminAction.id)


def _summaries(app):
    with app.app_context():
        return [a.summary for a in _entries().all()]


def _categories(app):
    with app.app_context():
        return [(a.action, a.category) for a in _entries().all()]


def _last(app):
    with app.app_context():
        entry = _entries().all()[-1]
        return entry.actor_name, entry.action, entry.summary


def _session_entries(app):
    with app.app_context():
        return [
            (a.actor_name, a.action, a.summary, a.category)
            for a in AdminAction.query.filter(AdminAction.action.like("session.%")).order_by(AdminAction.id)
        ]


def test_creating_a_barber_is_logged_with_who_did_it(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    client.post(
        "/admin/barbers",
        data={"name": "Jo", "username": "jo", "password": "temp-pass-1", "confirm_password": "temp-pass-1"},
    )
    assert _last(app) == ("Morgan Admin", "barber.create", "Created barber Jo (jo), hidden from the kiosk")


def test_edit_logs_each_change(app, client, admin_barber, barber, locations):
    login(client, "morgan", "password123")
    client.post(
        f"/admin/barbers/{barber['id']}/edit",
        data={"name": "Alexander", "username": "alex", "default_location_id": locations["kings-meadows"], "is_admin": "on"},
    )
    assert _last(app)[2] == (
        "Edited Alexander: name Alex to Alexander; default location Launceston to Kings Meadows; granted admin access"
    )


def test_edit_without_changes_is_not_logged(app, client, admin_barber, barber, locations):
    login(client, "morgan", "password123")
    client.post(
        f"/admin/barbers/{barber['id']}/edit",
        data={"name": "Alex", "username": "alex", "default_location_id": locations["launceston"]},
    )
    assert _summaries(app) == []


def test_barber_actions_are_logged(app, client, admin_barber, barber, locations):
    login(client, "morgan", "password123")
    client.post(f"/admin/barbers/{barber['id']}/reset-password",
                data={"password": "temp-pass-1", "confirm_password": "temp-pass-1"})
    client.post(f"/admin/barbers/{barber['id']}/toggle-kiosk")
    client.post(f"/admin/barbers/{barber['id']}/login", data={"location_id": locations["launceston"]})
    client.post(f"/admin/barbers/{barber['id']}/logout")
    client.post(f"/admin/barbers/{barber['id']}/toggle-active")
    client.post(f"/admin/barbers/{barber['id']}/delete")

    assert _summaries(app) == [
        "Reset the password for Alex and logged them out",
        "Hid Alex from the check-in kiosk",
        "Logged in Alex at Launceston (on duty, no device)",
        "Logged out Alex and took them off duty",
        "Deactivated Alex",
        "Deleted Alex (alex)",
    ]


def test_refused_actions_are_not_logged(app, client, admin_barber, barber):
    login(client, "morgan", "password123")
    client.post(f"/admin/barbers/{barber['id']}/delete")  # still active, so refused
    client.post(f"/admin/barbers/{admin_barber['id']}/toggle-active")  # can't deactivate yourself
    assert _summaries(app) == []


def test_location_and_settings_actions_are_logged(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    client.post("/admin/locations", data={"name": "Hobart", "slug": "hobart"})
    client.post(f"/admin/locations/{locations['launceston']}/regenerate-kiosk-token")
    client.post(f"/admin/locations/{locations['launceston']}/regenerate-display-token")
    client.post(f"/admin/locations/{locations['kings-meadows']}/toggle-active")
    client.post(f"/admin/locations/{locations['kings-meadows']}/delete")
    client.post("/admin/settings", data={"timezone": "Australia/Melbourne"})

    assert _summaries(app) == [
        "Created location Hobart (hobart)",
        "Regenerated the kiosk link for Launceston",
        "Regenerated the TV display link for Launceston",
        "Removed location Kings Meadows",
        "Deleted location Kings Meadows",
        "Changed the timezone from Australia/Hobart to Australia/Melbourne",
    ]


def test_cli_password_reset_is_logged_as_command_line(app, admin_barber):
    app.test_cli_runner().invoke(args=["reset-admin-password", "--username", "morgan"])
    assert _last(app) == (
        "Command line", "barber.reset_password", "Reset the password for Morgan Admin from the command line"
    )


def test_store_close_and_open_is_logged(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    client.post("/staff/launceston/store", data={"closed": "1"})
    client.post("/staff/launceston/store", data={"closed": "0"})

    assert _summaries(app) == [
        "Closed Launceston to new check-ins",
        "Opened Launceston to new check-ins",
    ]
    assert _categories(app) == [
        ("location.close", "barber"),
        ("location.open", "barber"),
    ]


def test_store_status_unchanged_is_not_logged(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    client.post("/staff/launceston/store", data={"closed": "0"})  # already open
    assert _summaries(app) == []


def test_customer_checkin_is_logged_as_customer(app, client, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})

    assert _summaries(app) == ["Jamie checked in at Launceston"]
    assert _categories(app) == [("queue.checkin", "customer")]
    with app.app_context():
        entry = AdminAction.query.one()
        assert entry.actor_name == "Customer"
        assert entry.actor_id is None


def test_queue_actions_are_logged_as_barber_events(app, client, barber, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry_id = QueueEntry.query.filter_by(customer_name="Jamie").first().id
    client.post(f"/staff/launceston/call/{entry_id}")
    client.post(f"/staff/launceston/complete/{entry_id}")
    client.post(f"/staff/launceston/undo/{entry_id}")

    assert _summaries(app)[1:] == [
        "Called Jamie to the chair at Launceston",
        "Completed Jamie at Launceston",
        "Undid completing Jamie at Launceston",
    ]
    assert [cat for _, cat in _categories(app)[1:]] == ["barber", "barber", "barber"]


def test_removing_a_customer_is_logged(app, client, barber, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])
    with app.app_context():
        entry_id = QueueEntry.query.filter_by(customer_name="Jamie").first().id

    client.post(f"/staff/launceston/remove/{entry_id}")

    assert _last(app)[1:] == ("queue.remove", "Removed Jamie from the queue at Launceston (no-show)")


def test_break_toggle_is_logged_as_barber_event(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.post("/staff/launceston/break", data={"on_break": "1"})
    client.post("/staff/launceston/break", data={"on_break": "1"})  # no change, shouldn't log again
    client.post("/staff/launceston/break", data={"on_break": "0"})

    assert _summaries(app) == [
        "Alex went on break at Launceston",
        "Alex came back from break at Launceston",
    ]


def test_barber_login_and_logout_are_logged(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.post("/logout")

    assert _session_entries(app) == [
        ("Alex", "session.login", "Alex logged in", "barber"),
        ("Alex", "session.location", "Alex started working at Launceston", "barber"),
        ("Alex", "session.logout", "Alex logged out and went off duty at Launceston", "barber"),
    ]


def test_logout_before_choosing_a_location_is_logged(app, client, barber):
    login(client, barber["username"], barber["password"])
    client.post("/logout")

    assert [summary for _, _, summary, _ in _session_entries(app)] == ["Alex logged in", "Alex logged out"]


def test_choosing_and_switching_location_is_logged(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.get("/staff/launceston")  # reloading the dashboard isn't a change
    client.get("/staff/kings-meadows")

    assert [entry for entry in _session_entries(app) if entry[1] == "session.location"] == [
        ("Alex", "session.location", "Alex started working at Launceston", "barber"),
        ("Alex", "session.location", "Alex moved from Launceston to Kings Meadows", "barber"),
    ]


def test_failed_login_is_logged_as_security_with_unknown_actor(app, client, barber):
    login(client, barber["username"], "wrong-password")
    login(client, "nobody", "wrong-password")

    assert _session_entries(app) == [
        ("Unknown", "session.login_failed", "Failed login for 'alex' from 127.0.0.1", "security"),
        ("Unknown", "session.login_failed", "Failed login for 'nobody' from 127.0.0.1", "security"),
    ]
    with app.app_context():
        assert AdminAction.query.filter_by(action="session.login_failed").first().actor_id is None


def test_lockout_is_logged_once_when_it_starts(app, client, barber):
    for _ in range(app.config["LOGIN_MAX_FAILURES_PER_USER"]):
        login(client, barber["username"], "wrong-password")
    login(client, barber["username"], "wrong-password")  # refused while locked out
    login(client, barber["username"], barber["password"])  # refused too, even with the right password

    actions = [action for _, action, _, _ in _session_entries(app)]
    assert actions.count("session.login_failed") == app.config["LOGIN_MAX_FAILURES_PER_USER"]
    assert actions[-1] == "session.lockout"
    assert _session_entries(app)[-1] == (
        "Unknown",
        "session.lockout",
        f"Locked out logins for 'alex' from 127.0.0.1 for {app.config['LOGIN_LOCKOUT_MINUTES']} minutes "
        "after too many failed attempts",
        "security",
    )


def test_barber_profile_change_is_logged(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    client.post(
        "/staff/profile",
        data={"form_name": "profile", "name": "Alexander", "default_location_id": locations["kings-meadows"]},
    )
    client.post(  # saving again without changes isn't logged
        "/staff/profile",
        data={"form_name": "profile", "name": "Alexander", "default_location_id": locations["kings-meadows"]},
    )

    assert _categories(app) == [("barber.edit_own_profile", "barber")]
    assert _summaries(app) == [
        "Alexander updated their profile: name Alex to Alexander; default location Launceston to Kings Meadows"
    ]


def test_barber_changing_their_own_password_is_logged(app, client, barber):
    login(client, barber["username"], barber["password"])
    client.post(
        "/staff/profile",
        data={
            "form_name": "change_password",
            "current_password": "wrong",
            "password": "new-password-1",
            "confirm_password": "new-password-1",
        },
    )  # refused, so not logged
    client.post(
        "/staff/profile",
        data={
            "form_name": "change_password",
            "current_password": barber["password"],
            "password": "new-password-1",
            "confirm_password": "new-password-1",
        },
    )

    assert _last(app) == ("Alex", "barber.change_own_password", "Alex changed their password")
    assert _categories(app) == [("barber.change_own_password", "barber")]


def test_forced_password_change_is_logged(app, client, barber):
    with app.app_context():
        db.session.get(Barber, barber["id"]).must_change_password = True
        db.session.commit()
    login(client, barber["username"], barber["password"])
    client.post("/change-password", data={"password": "new-password-1", "confirm_password": "new-password-1"})

    assert _last(app) == (
        "Alex", "barber.change_own_password", "Alex set a new password after being asked to change it"
    )


def test_action_label_falls_back_to_the_raw_code():
    assert audit.action_label("queue.checkin") == "Customer checked in"
    assert audit.action_label("unknown.code") == "unknown.code"


def test_record_without_request_context_is_cli_category(app):
    with app.app_context():
        audit.record("barber.reset_password", "test from a script")
        entry = AdminAction.query.order_by(AdminAction.id.desc()).first()
        assert entry.category == "cli"
        assert entry.actor_name == "Command line"


def test_activity_tab_filters_by_category(app, client, admin_barber, locations):
    client.post(kiosk_url(app, "launceston"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, "morgan", "password123")
    client.post("/admin/locations", data={"name": "Hobart", "slug": "hobart"})

    resp = client.get("/admin/?activity_category=customer")
    assert b"Jamie checked in at Launceston" in resp.data
    assert b"Created location Hobart" not in resp.data


def test_activity_tab_filters_by_event_type(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    client.post("/admin/locations", data={"name": "Hobart", "slug": "hobart"})
    client.post(f"/admin/locations/{locations['kings-meadows']}/toggle-active")

    resp = client.get("/admin/?activity_action=location.create")
    assert b"Created location Hobart" in resp.data
    assert b"Removed location Kings Meadows" not in resp.data


def test_activity_tab_filters_by_who(app, client, admin_barber, barber, locations):
    login(client, "morgan", "password123")
    client.post(f"/admin/barbers/{barber['id']}/toggle-kiosk")
    client.post("/logout")
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.post("/staff/launceston/break", data={"on_break": "1"})
    client.post("/logout")
    login(client, "morgan", "password123")

    resp = client.get("/admin/?activity_who=Alex")
    assert b"Alex went on break at Launceston" in resp.data
    assert b"Hid Alex from the check-in kiosk" not in resp.data


def test_activity_tab_filters_by_date_range(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    client.post("/admin/locations", data={"name": "Hobart", "slug": "hobart"})

    # The filter works in shop time, so "tomorrow" must be too, not the server's UTC date.
    tomorrow = (datetime.now(get_timezone()).date() + timedelta(days=1)).isoformat()
    resp = client.get(f"/admin/?activity_from={tomorrow}")
    assert b"Created location Hobart" not in resp.data

    resp = client.get(f"/admin/?activity_to={tomorrow}")
    assert b"Created location Hobart" in resp.data


def test_log_keeps_the_actors_name_after_they_are_deleted(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    client.post("/admin/locations", data={"name": "Hobart", "slug": "hobart"})
    with app.app_context():
        db.session.delete(db.session.get(Barber, admin_barber["id"]))
        db.session.commit()
    assert _last(app)[0] == "Morgan Admin"


def test_activity_tab_lists_entries_newest_first(app, client, admin_barber, barber):
    login(client, "morgan", "password123")
    client.post(f"/admin/barbers/{barber['id']}/toggle-kiosk")
    client.post(f"/admin/barbers/{barber['id']}/toggle-kiosk")

    html = client.get("/admin/").data.decode()
    tab = html[html.index('data-tab-panel="activity"'):]
    assert tab.index("Showed Alex on the check-in kiosk") < tab.index("Hid Alex from the check-in kiosk")
    assert "Morgan Admin" in tab


def test_activity_refresh_link_keeps_the_applied_filters(client, admin_barber):
    login(client, "morgan", "password123")

    html = client.get("/admin/?activity_category=security&activity_who=Unknown").data.decode()
    assert 'href="/admin/?activity_category=security&amp;activity_who=Unknown#activity"' in html

    html = client.get("/admin/").data.decode()
    assert 'href="/admin/#activity" class="btn btn-secondary" title="Show the latest activity" data-reload>Refresh</a>' in html
