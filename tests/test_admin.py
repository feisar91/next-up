from datetime import datetime, timedelta, timezone

from app import db
from app.models import Barber, Location, QueueEntry
from tests.conftest import display_url, kiosk_url, login


def test_edit_barber_requires_admin(client, barber, other_location_barber):
    login(client, barber["username"], barber["password"])
    resp = client.get(f"/admin/barbers/{other_location_barber['id']}/edit")
    assert resp.status_code == 403


def test_edit_barber_requires_login(client, barber):
    resp = client.get(f"/admin/barbers/{barber['id']}/edit")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_admin_can_update_barber_attributes(app, client, admin_barber, barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])

    resp = client.post(
        f"/admin/barbers/{barber['id']}/edit",
        data={
            "name": "Alexandra",
            "username": "alexandra",
            "default_location_id": locations["riverside"],
            "is_admin": "on",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.name == "Alexandra"
        assert updated.username == "alexandra"
        assert updated.default_location_id == locations["riverside"]
        assert updated.is_admin is True


def test_admin_can_clear_barbers_default_location(app, client, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])

    client.post(
        f"/admin/barbers/{barber['id']}/edit",
        data={"name": "Alex", "username": "alex", "default_location_id": ""},
        follow_redirects=True,
    )

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.default_location_id is None


def test_edit_barber_rejects_duplicate_username(app, client, admin_barber, barber, other_location_barber):
    login(client, admin_barber["username"], admin_barber["password"])

    resp = client.post(
        f"/admin/barbers/{barber['id']}/edit",
        data={"name": "Alex", "username": other_location_barber["username"], "default_location_id": ""},
        follow_redirects=True,
    )
    assert b"already taken" in resp.data

    with app.app_context():
        unchanged = db.session.get(Barber, barber["id"])
        assert unchanged.username == "alex"


def test_edit_barber_keeping_own_username_is_allowed(app, client, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])

    resp = client.post(
        f"/admin/barbers/{barber['id']}/edit",
        data={"name": "Alex Updated", "username": "alex", "default_location_id": ""},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.name == "Alex Updated"


def test_admin_overview_tabulates_locations_and_barbers(client, admin_barber, barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/")
    assert resp.status_code == 200
    assert b"<table" in resp.data
    assert b"Main Street" in resp.data
    assert b"Alex" in resp.data


def test_metrics_requires_admin(client, barber):
    login(client, barber["username"], barber["password"])
    resp = client.get("/admin/metrics")
    assert resp.status_code == 403


def test_metrics_page_loads_for_admin(client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/metrics")
    assert resp.status_code == 200
    assert b"Cuts per day" in resp.data
    assert b"Cuts by barber" in resp.data
    assert b"Cuts by location" in resp.data


def test_metrics_reflects_completed_cuts(app, client, admin_barber, barber, locations):
    client.post(kiosk_url(app, "main-street"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry = QueueEntry.query.filter_by(customer_name="Jamie").first()
        entry_id = entry.id
    client.post(f"/staff/main-street/call/{entry_id}")
    client.post(f"/staff/main-street/complete/{entry_id}")

    client.post("/logout")
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/metrics")
    assert resp.status_code == 200
    assert b">1<" in resp.data  # total cuts stat tile


def test_metrics_day_range_filter_rejects_invalid_value(client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/metrics?days=9999")
    assert resp.status_code == 200
    assert b"Last 14 days" in resp.data  # falls back to the default


def test_metrics_averages_wait_and_service_time(app, client, admin_barber, barber, locations):
    with app.app_context():
        now = datetime.now(timezone.utc)
        entry = QueueEntry(
            location_id=locations["main-street"],
            customer_name="Timed Customer",
            status=QueueEntry.STATUS_DONE,
            checked_in_at=now - timedelta(minutes=15),
            called_at=now - timedelta(minutes=10),
            completed_at=now,
            called_by_barber_id=barber["id"],
        )
        db.session.add(entry)
        db.session.commit()

    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/metrics")
    assert resp.status_code == 200
    assert b"5.0" in resp.data  # exactly 5 min wait
    assert b"10.0" in resp.data  # exactly 10 min in chair


def test_toggle_location_active_requires_admin(client, barber, locations):
    login(client, barber["username"], barber["password"])
    resp = client.post(f"/admin/locations/{locations['main-street']}/toggle-active")
    assert resp.status_code == 403


def test_admin_can_remove_and_restore_a_location(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])

    resp = client.post(
        f"/admin/locations/{locations['riverside']}/toggle-active", follow_redirects=True
    )
    assert resp.status_code == 200
    with app.app_context():
        loc = db.session.get(Location, locations["riverside"])
        assert loc.active is False

    resp = client.post(
        f"/admin/locations/{locations['riverside']}/toggle-active", follow_redirects=True
    )
    assert resp.status_code == 200
    with app.app_context():
        loc = db.session.get(Location, locations["riverside"])
        assert loc.active is True


def test_removed_location_kiosk_and_display_urls_404(app, client, admin_barber, locations):
    kiosk_link = kiosk_url(app, "riverside")
    display_link = display_url(app, "riverside")

    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['riverside']}/toggle-active")

    assert client.get(kiosk_link).status_code == 404
    assert client.get(display_link).status_code == 404


def test_removed_location_excluded_from_location_picker(app, client, admin_barber, barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['riverside']}/toggle-active")
    client.get("/admin/")  # consume the "has been removed" flash so it doesn't leak into the next assertion
    client.post("/logout")

    resp = login(client, barber["username"], barber["password"])
    assert b"Riverside" not in resp.data


def test_removed_default_location_is_not_offered_as_one_click_continue(
    app, client, admin_barber, barber, locations
):
    # barber's default is Main Street (see conftest); remove it and make sure the
    # picker doesn't still offer a dead one-click "Continue to Main Street".
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['main-street']}/toggle-active")
    client.post("/logout")

    resp = login(client, barber["username"], barber["password"])
    assert b"Continue to Main Street" not in resp.data


def test_removing_a_location_does_not_delete_its_historical_queue_entries(
    app, client, admin_barber, barber, locations
):
    client.post(kiosk_url(app, "riverside"), data={"customer_name": "Jamie", "preferred_barber_id": ""})

    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['riverside']}/toggle-active")

    with app.app_context():
        assert QueueEntry.query.filter_by(customer_name="Jamie").count() == 1


def test_device_links_tab_excludes_removed_locations(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['riverside']}/toggle-active")

    resp = client.get("/admin/")
    assert b"Riverside" in resp.data  # still listed (as Inactive) in Locations tab
    with app.app_context():
        loc = db.session.get(Location, locations["riverside"])
        assert loc.kiosk_token.encode() not in resp.data


def test_delete_barber_requires_admin(client, barber, other_location_barber):
    login(client, barber["username"], barber["password"])
    resp = client.post(f"/admin/barbers/{other_location_barber['id']}/delete")
    assert resp.status_code == 403


def test_cannot_delete_an_active_barber(app, client, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post(f"/admin/barbers/{barber['id']}/delete", follow_redirects=True)
    assert b"Deactivate" in resp.data

    with app.app_context():
        assert db.session.get(Barber, barber["id"]) is not None


def test_admin_can_delete_a_deactivated_barber(app, client, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/barbers/{barber['id']}/toggle-active")

    resp = client.post(f"/admin/barbers/{barber['id']}/delete", follow_redirects=True)
    assert resp.status_code == 200
    assert b"permanently deleted" in resp.data

    with app.app_context():
        assert db.session.get(Barber, barber["id"]) is None


def test_deleting_a_barber_keeps_their_queue_history_but_clears_the_name_link(
    app, client, admin_barber, barber, locations
):
    client.post(
        kiosk_url(app, "main-street"),
        data={"customer_name": "Jamie", "preferred_barber_id": barber["id"]},
    )
    login(client, barber["username"], barber["password"])

    with app.app_context():
        entry = QueueEntry.query.filter_by(customer_name="Jamie").first()
        entry_id = entry.id
    client.post(f"/staff/main-street/call/{entry_id}")
    client.post("/logout")

    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/barbers/{barber['id']}/toggle-active")
    client.post(f"/admin/barbers/{barber['id']}/delete")

    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        assert entry is not None
        assert entry.preferred_barber_id is None
        assert entry.called_by_barber_id is None


def test_delete_location_requires_admin(client, barber, locations):
    login(client, barber["username"], barber["password"])
    resp = client.post(f"/admin/locations/{locations['riverside']}/delete")
    assert resp.status_code == 403


def test_cannot_delete_an_active_location(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post(
        f"/admin/locations/{locations['riverside']}/delete", follow_redirects=True
    )
    assert b"Remove" in resp.data

    with app.app_context():
        assert db.session.get(Location, locations["riverside"]) is not None


def test_admin_can_delete_a_removed_location_with_no_history(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['riverside']}/toggle-active")

    resp = client.post(
        f"/admin/locations/{locations['riverside']}/delete", follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"permanently deleted" in resp.data

    with app.app_context():
        assert db.session.get(Location, locations["riverside"]) is None


def test_cannot_delete_a_removed_location_with_history(app, client, admin_barber, locations):
    client.post(kiosk_url(app, "riverside"), data={"customer_name": "Jamie", "preferred_barber_id": ""})

    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['riverside']}/toggle-active")

    resp = client.post(
        f"/admin/locations/{locations['riverside']}/delete", follow_redirects=True
    )
    assert b"historical check-in records" in resp.data

    with app.app_context():
        assert db.session.get(Location, locations["riverside"]) is not None
        assert QueueEntry.query.filter_by(customer_name="Jamie").count() == 1


def test_deleting_a_location_clears_barbers_who_pointed_to_it(app, client, admin_barber, barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/locations/{locations['main-street']}/toggle-active")
    client.post(f"/admin/locations/{locations['main-street']}/delete")

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.default_location_id is None


def test_create_barber_requires_matching_confirm_password(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post(
        "/admin/barbers",
        data={
            "name": "New Guy",
            "username": "newguy",
            "password": "temp12345",
            "confirm_password": "different",
        },
        follow_redirects=True,
    )
    assert b"do not match" in resp.data

    with app.app_context():
        assert Barber.query.filter_by(username="newguy").first() is None


def test_create_barber_forces_password_change_on_first_login(app, client, admin_barber, locations):
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(
        "/admin/barbers",
        data={
            "name": "New Guy",
            "username": "newguy",
            "password": "temp12345",
            "confirm_password": "temp12345",
        },
    )
    client.post("/logout")

    resp = login(client, "newguy", "temp12345")
    assert b"Set a New Password" in resp.data

    with app.app_context():
        created = Barber.query.filter_by(username="newguy").first()
        assert created.must_change_password is True


def test_reset_barber_password_requires_admin(client, barber, other_location_barber):
    login(client, barber["username"], barber["password"])
    resp = client.post(f"/admin/barbers/{other_location_barber['id']}/reset-password")
    assert resp.status_code == 403


def test_reset_barber_password_requires_matching_confirmation(app, client, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post(
        f"/admin/barbers/{barber['id']}/reset-password",
        data={"password": "newtemp123", "confirm_password": "nope"},
        follow_redirects=True,
    )
    assert b"do not match" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.must_change_password is False


def test_admin_can_reset_a_barbers_password(app, client, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post(
        f"/admin/barbers/{barber['id']}/reset-password",
        data={"password": "newtemp123", "confirm_password": "newtemp123"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Temporary password set" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.must_change_password is True
        assert updated.check_password("newtemp123")
        assert not updated.check_password(barber["password"])


def test_admin_cannot_reset_their_own_password_via_admin_screen(app, client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post(
        f"/admin/barbers/{admin_barber['id']}/reset-password",
        data={"password": "newtemp123", "confirm_password": "newtemp123"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Use your profile page" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, admin_barber["id"])
        assert updated.check_password(admin_barber["password"])


def test_admin_cannot_deactivate_their_own_account(app, client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post(f"/admin/barbers/{admin_barber['id']}/toggle-active", follow_redirects=True)
    assert resp.status_code == 200
    assert b"deactivate your own account" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, admin_barber["id"])
        assert updated.active is True


def test_admin_barbers_tab_hides_self_actions(client, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.get("/admin/#barbers")
    rows_html = resp.data.decode()

    own_row_start = rows_html.index(admin_barber["username"])
    other_row_start = rows_html.index(barber["username"])

    own_row = rows_html[own_row_start:rows_html.index("</tr>", own_row_start)]
    other_row = rows_html[other_row_start:rows_html.index("</tr>", other_row_start)]

    assert "Deactivate" not in own_row
    assert "Reset Password" not in own_row
    assert "Deactivate" in other_row
    assert "Reset Password" in other_row
    # The kiosk switch is available on every row, including the admin's own.
    assert "toggle-kiosk" in own_row
    assert "toggle-kiosk" in other_row


def test_admin_cannot_remove_their_own_admin_access(app, client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])

    response = client.post(
        f"/admin/barbers/{admin_barber['id']}/edit",
        data={"name": "Morgan Admin", "username": "morgan"},
        follow_redirects=True,
    )

    assert "You can&#39;t remove your own admin access. Another admin can." in response.data.decode()
    assert db.session.get(Barber, admin_barber["id"]).is_admin is True


def test_own_edit_page_locks_the_admin_box_but_still_saves(app, client, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])

    html = client.get(f"/admin/barbers/{admin_barber['id']}/edit").data.decode()
    assert "checked disabled" in html
    assert '<input type="hidden" name="is_admin" value="on">' in html

    client.post(
        f"/admin/barbers/{admin_barber['id']}/edit",
        data={"name": "Morgan", "username": "morgan", "is_admin": "on"},
    )
    admin = db.session.get(Barber, admin_barber["id"])
    assert (admin.name, admin.is_admin) == ("Morgan", True)


def test_admin_can_remove_another_admins_access(app, client, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])
    db.session.get(Barber, barber["id"]).is_admin = True
    db.session.commit()

    client.post(f"/admin/barbers/{barber['id']}/edit", data={"name": "Alex", "username": "alex"})

    assert db.session.get(Barber, barber["id"]).is_admin is False


def test_usernames_differing_only_in_capitals_are_taken(app, client, admin_barber, barber, other_location_barber):
    login(client, admin_barber["username"], admin_barber["password"])

    response = client.post(
        "/admin/barbers",
        data={"name": "Alex Two", "username": "ALEX", "password": "password123", "confirm_password": "password123"},
        follow_redirects=True,
    )
    assert "Username &#39;ALEX&#39; is already taken." in response.data.decode()

    response = client.post(
        f"/admin/barbers/{other_location_barber['id']}/edit",
        data={"name": "Sam", "username": "Alex"},
        follow_redirects=True,
    )
    assert "Username &#39;Alex&#39; is already taken." in response.data.decode()

    # Changing the capitals of your own username is fine.
    client.post(f"/admin/barbers/{barber['id']}/edit", data={"name": "Alex", "username": "Alex"})
    assert db.session.get(Barber, barber["id"]).username == "Alex"
