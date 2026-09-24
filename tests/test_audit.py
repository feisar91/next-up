from app import db
from app.models import AdminAction, Barber
from tests.conftest import login


def _summaries(app):
    with app.app_context():
        return [a.summary for a in AdminAction.query.order_by(AdminAction.id).all()]


def _last(app):
    with app.app_context():
        entry = AdminAction.query.order_by(AdminAction.id.desc()).first()
        return entry.actor_name, entry.action, entry.summary


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
