from app import db
from app.models import Barber, QueueEntry
from tests.conftest import kiosk_url, login


def test_staff_dashboard_requires_login(client, locations):
    resp = client.get("/staff/mainstreet")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_login_with_bad_credentials_shows_error(client, barber):
    resp = login(client, barber["username"], "wrong-password")
    assert b"Incorrect username or password" in resp.data


def test_login_lands_on_location_picker(client, barber):
    resp = login(client, barber["username"], barber["password"])
    assert resp.status_code == 200
    assert b"Where are you working today" in resp.data


def test_location_picker_highlights_default_location(client, barber):
    resp = login(client, barber["username"], barber["password"])
    assert b"Continue to Main Street" in resp.data


def test_barber_without_default_sees_plain_location_list(client, floating_barber, locations):
    resp = login(client, floating_barber["username"], floating_barber["password"])
    assert b"Continue to" not in resp.data
    assert b"Main Street" in resp.data and b"Riverside" in resp.data


def test_choosing_a_location_reaches_its_dashboard(client, barber, locations):
    login(client, barber["username"], barber["password"])
    resp = client.post(
        "/staff/choose-location", data={"location_id": locations["riverside"]}, follow_redirects=True
    )
    assert resp.status_code == 200
    assert b"Riverside" in resp.data


def test_any_active_barber_can_access_any_location_dashboard(app, client, locations, barber, other_location_barber):
    # Barbers pick their working location at login rather than being locked to one account-wide location.
    login(client, barber["username"], barber["password"])
    resp = client.get("/staff/riverside")
    assert resp.status_code == 200


def test_any_active_barber_can_act_on_any_location_queue_entry(app, client, locations, barber, other_location_barber):
    client.post(kiosk_url(app, "riverside"), data={"customer_name": "Jamie", "preferred_barber_id": ""})
    with app.app_context():
        entry_id = QueueEntry.query.filter_by(customer_name="Jamie").first().id

    login(client, barber["username"], barber["password"])
    resp = client.post(f"/staff/riverside/call/{entry_id}", follow_redirects=True)
    assert resp.status_code == 200

    with app.app_context():
        entry = db.session.get(QueueEntry, entry_id)
        assert entry.status == QueueEntry.STATUS_IN_PROGRESS
        assert entry.called_by_barber_id == barber["id"]


def test_admin_panel_forbidden_for_non_admin(client, barber):
    login(client, barber["username"], barber["password"])
    resp = client.get("/admin/")
    assert resp.status_code == 403


def test_profile_updates_default_location(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    resp = client.post(
        "/staff/profile",
        data={"form_name": "profile", "name": "Alex", "default_location_id": locations["riverside"]},
        follow_redirects=True,
    )
    assert resp.status_code == 200

    with app.app_context():
        barber_obj = db.session.get(Barber, barber["id"])
        assert barber_obj.default_location_id == locations["riverside"]


def test_profile_can_clear_default_location(app, client, barber):
    login(client, barber["username"], barber["password"])
    client.post(
        "/staff/profile",
        data={"form_name": "profile", "name": "Alex", "default_location_id": ""},
        follow_redirects=True,
    )

    with app.app_context():
        barber_obj = db.session.get(Barber, barber["id"])
        assert barber_obj.default_location_id is None


def test_profile_saves_name_and_default_location_together(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    resp = client.post(
        "/staff/profile",
        data={"form_name": "profile", "name": "Alexander", "default_location_id": locations["riverside"]},
        follow_redirects=True,
    )

    assert b"Profile updated." in resp.data
    with app.app_context():
        barber_obj = db.session.get(Barber, barber["id"])
        assert barber_obj.name == "Alexander"
        assert barber_obj.default_location_id == locations["riverside"]


def test_profile_blank_name_saves_nothing(app, client, barber, locations):
    login(client, barber["username"], barber["password"])
    client.post(
        "/staff/profile",
        data={"form_name": "profile", "name": "  ", "default_location_id": locations["riverside"]},
    )

    with app.app_context():
        barber_obj = db.session.get(Barber, barber["id"])
        assert barber_obj.name == "Alex"
        assert barber_obj.default_location_id == locations["mainstreet"]


def test_profile_self_service_password_change(app, client, barber):
    login(client, barber["username"], barber["password"])
    resp = client.post(
        "/staff/profile",
        data={
            "form_name": "change_password",
            "current_password": barber["password"],
            "password": "newpassword123",
            "confirm_password": "newpassword123",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    assert b"Password updated" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.check_password("newpassword123")
        assert not updated.check_password(barber["password"])


def test_profile_password_change_rejects_wrong_current_password(app, client, barber):
    login(client, barber["username"], barber["password"])
    resp = client.post(
        "/staff/profile",
        data={
            "form_name": "change_password",
            "current_password": "wrong-password",
            "password": "newpassword123",
            "confirm_password": "newpassword123",
        },
        follow_redirects=True,
    )
    assert b"Current password is incorrect" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.check_password(barber["password"])


def test_profile_password_change_rejects_mismatched_confirmation(client, barber):
    login(client, barber["username"], barber["password"])
    resp = client.post(
        "/staff/profile",
        data={
            "form_name": "change_password",
            "current_password": barber["password"],
            "password": "newpassword123",
            "confirm_password": "different456",
        },
        follow_redirects=True,
    )
    assert b"do not match" in resp.data


def test_profile_password_change_rejects_too_short_password(client, barber):
    login(client, barber["username"], barber["password"])
    resp = client.post(
        "/staff/profile",
        data={
            "form_name": "change_password",
            "current_password": barber["password"],
            "password": "short",
            "confirm_password": "short",
        },
        follow_redirects=True,
    )
    assert b"at least 8 characters" in resp.data


def _force_password_change(app, barber_id):
    with app.app_context():
        b = db.session.get(Barber, barber_id)
        b.must_change_password = True
        db.session.commit()


def test_forced_password_change_redirects_before_reaching_staff_area(app, client, barber):
    _force_password_change(app, barber["id"])

    resp = login(client, barber["username"], barber["password"])
    assert b"Set a New Password" in resp.data

    resp = client.get("/staff/choose-location", follow_redirects=True)
    assert b"Set a New Password" in resp.data


def test_completing_forced_password_change_clears_the_flag_and_unlocks_the_app(app, client, barber):
    _force_password_change(app, barber["id"])
    login(client, barber["username"], barber["password"])

    resp = client.post(
        "/change-password",
        data={"password": "newpassword123", "confirm_password": "newpassword123"},
        follow_redirects=True,
    )
    assert b"Where are you working today" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.must_change_password is False
        assert updated.check_password("newpassword123")


def test_change_password_rejects_mismatched_confirmation(app, client, barber):
    _force_password_change(app, barber["id"])
    login(client, barber["username"], barber["password"])

    resp = client.post(
        "/change-password",
        data={"password": "newpassword123", "confirm_password": "different456"},
        follow_redirects=True,
    )
    assert b"do not match" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.must_change_password is True


def test_change_password_rejects_too_short_password(app, client, barber):
    _force_password_change(app, barber["id"])
    login(client, barber["username"], barber["password"])

    resp = client.post(
        "/change-password",
        data={"password": "short", "confirm_password": "short"},
        follow_redirects=True,
    )
    assert b"at least 8 characters" in resp.data


def test_logo_links_to_staff_landing_when_authenticated(client, barber):
    login(client, barber["username"], barber["password"])
    resp = client.get("/staff/choose-location")
    assert b'href="/staff" class="brand-link"' in resp.data


def test_logo_links_to_index_when_anonymous(client):
    resp = client.get("/login")
    assert b'href="/" class="brand-link"' in resp.data


def test_admin_can_change_their_display_name(app, client, admin_barber):
    from app import db
    from app.models import Barber

    login(client, admin_barber["username"], admin_barber["password"])
    resp = client.post(
        "/staff/profile", data={"form_name": "profile", "name": "  Morgan  "}, follow_redirects=True
    )

    assert b"Profile updated." in resp.data
    with app.app_context():
        assert db.session.get(Barber, admin_barber["id"]).name == "Morgan"


def test_display_name_cannot_be_blank(app, client, admin_barber):
    from app import db
    from app.models import Barber

    login(client, admin_barber["username"], admin_barber["password"])
    client.post("/staff/profile", data={"form_name": "profile", "name": "   "})

    with app.app_context():
        assert db.session.get(Barber, admin_barber["id"]).name == "Morgan Admin"


def test_barber_can_change_their_display_name(app, client, barber):
    from app import db
    from app.models import Barber

    login(client, barber["username"], barber["password"])
    resp = client.post(
        "/staff/profile", data={"form_name": "profile", "name": "Alexander"}, follow_redirects=True
    )

    assert b"Profile updated." in resp.data
    with app.app_context():
        assert db.session.get(Barber, barber["id"]).name == "Alexander"


def test_nav_has_a_queue_link_marked_current_on_the_dashboard(client, locations, barber):
    login(client, barber["username"], barber["password"])

    dashboard = client.get("/staff/mainstreet").data.decode()
    assert '<a href="/staff" aria-current="page">Queue</a>' in dashboard

    profile = client.get("/staff/profile").data.decode()
    assert '<a href="/staff">Queue</a>' in profile
    assert 'aria-current="page">Profile</a>' in profile


def test_queue_link_returns_to_the_current_location(client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/riverside")
    client.get("/staff/profile")

    resp = client.get("/staff")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/staff/riverside")


def test_home_page_shows_log_in_when_logged_out(client, locations):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Staff Log In" in resp.data


def test_home_page_sends_a_logged_in_barber_to_their_queue(client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/mainstreet")

    resp = client.get("/")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/staff")
    assert client.get("/", follow_redirects=True).request.path == "/staff/mainstreet"


def test_home_page_shows_log_in_after_logging_out(client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.post("/logout")

    assert b"Staff Log In" in client.get("/").data
