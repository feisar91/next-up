import re
from datetime import timedelta

from app import db
from app.models import Barber, LoginSession, utcnow
from config import Config
from tests.conftest import login


def _is_logged_in(client):
    return client.get("/staff/choose-location").status_code == 200


def _session_count(app, barber_id):
    with app.app_context():
        return LoginSession.query.filter_by(barber_id=barber_id).count()


def test_login_creates_a_session_with_an_expiring_cookie(app, client, barber):
    resp = client.post("/login", data={"username": "alex", "password": "password123"})

    cookie = resp.headers["Set-Cookie"]
    assert "Expires=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert _session_count(app, barber["id"]) == 1
    assert _is_logged_in(client)


def test_production_config_uses_secure_cookies_and_12_hour_sessions():
    assert Config.SESSION_COOKIE_SECURE is True
    assert Config.PERMANENT_SESSION_LIFETIME == timedelta(hours=12)


def test_logout_ends_only_that_session(app, barber):
    phone, tablet = app.test_client(), app.test_client()
    login(phone, "alex", "password123")
    login(tablet, "alex", "password123")

    phone.post("/logout")

    assert not _is_logged_in(phone)
    assert _is_logged_in(tablet)
    assert _session_count(app, barber["id"]) == 1


def test_idle_session_expires(app, client, barber):
    login(client, "alex", "password123")
    with app.app_context():
        record = LoginSession.query.filter_by(barber_id=barber["id"]).one()
        record.last_seen_at = utcnow() - timedelta(hours=13)
        db.session.commit()

    assert not _is_logged_in(client)
    assert _session_count(app, barber["id"]) == 0


def test_activity_keeps_session_alive(app, client, barber):
    login(client, "alex", "password123")
    with app.app_context():
        record = LoginSession.query.filter_by(barber_id=barber["id"]).one()
        record.last_seen_at = utcnow() - timedelta(hours=11)
        db.session.commit()

    assert _is_logged_in(client)
    with app.app_context():
        record = LoginSession.query.filter_by(barber_id=barber["id"]).one()
        assert record.last_seen_at.replace(tzinfo=None) > (utcnow() - timedelta(minutes=5)).replace(tzinfo=None)


def test_deactivated_barber_is_logged_out_immediately(app, barber, admin_barber):
    barber_client, admin_client = app.test_client(), app.test_client()
    login(barber_client, "alex", "password123")
    login(admin_client, "morgan", "password123")

    admin_client.post(f"/admin/barbers/{barber['id']}/toggle-active")

    assert not _is_logged_in(barber_client)
    assert _session_count(app, barber["id"]) == 0


def test_inactive_flag_rejects_existing_session_even_without_admin_action(app, client, barber):
    login(client, "alex", "password123")
    with app.app_context():
        db.session.get(Barber, barber["id"]).active = False
        db.session.commit()

    assert not _is_logged_in(client)


def test_admin_password_reset_logs_barber_out(app, barber, admin_barber):
    barber_client, admin_client = app.test_client(), app.test_client()
    login(barber_client, "alex", "password123")
    login(admin_client, "morgan", "password123")

    admin_client.post(
        f"/admin/barbers/{barber['id']}/reset-password",
        data={"password": "temp-pass-1", "confirm_password": "temp-pass-1"},
    )

    assert not _is_logged_in(barber_client)


def test_changing_own_password_logs_out_other_devices_only(app, barber):
    phone, tablet = app.test_client(), app.test_client()
    login(phone, "alex", "password123")
    login(tablet, "alex", "password123")

    phone.post(
        "/staff/profile",
        data={
            "form_name": "change_password",
            "current_password": "password123",
            "password": "brand-new-pass",
            "confirm_password": "brand-new-pass",
        },
    )

    assert _is_logged_in(phone)
    assert not _is_logged_in(tablet)


def test_cli_admin_password_reset_logs_admin_out(app, admin_barber):
    client = app.test_client()
    login(client, "morgan", "password123")

    app.test_cli_runner().invoke(args=["reset-admin-password", "--username", "morgan"])

    assert not _is_logged_in(client)


def test_admin_table_shows_who_is_logged_in(app, barber, other_location_barber, admin_barber):
    barber_client, admin_client = app.test_client(), app.test_client()
    login(barber_client, "alex", "password123")
    login(admin_client, "morgan", "password123")

    html = admin_client.get("/admin/").data.decode()
    alex_row = html[html.index(">alex<"):html.index("</tr>", html.index(">alex<"))]
    sam_row = html[html.index(">sam<"):html.index("</tr>", html.index(">sam<"))]
    own_row = html[html.index(">morgan<"):html.index("</tr>", html.index(">morgan<"))]

    assert "active " in alex_row
    assert f"/admin/barbers/{barber['id']}/logout" in alex_row
    assert "active " not in sam_row and "/logout" not in sam_row
    assert "active " in own_row and "/logout" not in own_row


def test_every_admin_table_has_a_header_for_every_column(app, barber, admin_barber, locations):
    client = app.test_client()
    login(client, "morgan", "password123")
    html = client.get("/admin/").data.decode()

    tables = html.split("<table")[1:]
    assert len(tables) == 4  # locations, device links, barbers, activity
    for table in tables:
        table = table[:table.index("</table>")]
        header = table[table.index("<thead>"):table.index("</thead>")]
        first_row = table[table.index("<tbody>"):]
        first_row = first_row[:first_row.index("</tr>")]
        cells = sum(int(span or 1) for span in re.findall(r'<td(?:[^>]*colspan="(\d+)")?', first_row))
        assert header.count("<th>") + header.count("<th ") == cells, header

    barbers_header = html[html.index('data-tab-panel="barbers"'):]
    barbers_header = barbers_header[:barbers_header.index("</thead>")]
    assert "Logged In" in barbers_header and "On Kiosk" in barbers_header
    locations_header = html[html.index('data-tab-panel="locations"'):]
    locations_header = locations_header[:locations_header.index("</thead>")]
    assert "Logged In" not in locations_header and "On Kiosk" not in locations_header


def test_admin_can_log_a_barber_out_everywhere(app, barber, admin_barber):
    phone, tablet, admin_client = app.test_client(), app.test_client(), app.test_client()
    login(phone, "alex", "password123")
    login(tablet, "alex", "password123")
    phone.get("/staff/main-street")
    login(admin_client, "morgan", "password123")

    admin_client.post(f"/admin/barbers/{barber['id']}/logout")

    assert not _is_logged_in(phone)
    assert not _is_logged_in(tablet)
    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_duty_location_id is None


def test_force_logout_requires_admin(app, barber, other_location_barber):
    client = app.test_client()
    login(client, "alex", "password123")
    assert client.post(f"/admin/barbers/{other_location_barber['id']}/logout").status_code == 403


def test_admin_cannot_force_logout_themselves(app, admin_barber):
    client = app.test_client()
    login(client, "morgan", "password123")
    client.post(f"/admin/barbers/{admin_barber['id']}/logout")
    assert _is_logged_in(client)


def test_deleting_a_barber_removes_their_sessions(app, barber, admin_barber):
    admin_client = app.test_client()
    login(app.test_client(), "alex", "password123")
    login(admin_client, "morgan", "password123")
    admin_client.post(f"/admin/barbers/{barber['id']}/toggle-active")
    admin_client.post(f"/admin/barbers/{barber['id']}/delete")

    with app.app_context():
        assert LoginSession.query.count() == 1  # just the admin's own


def _barber_row(html, username):
    start = html.index(f">{username}<")
    return html[start:html.index("</tr>", start)]


def test_logged_out_barber_row_offers_log_in_at_their_default_location(app, barber, admin_barber, locations):
    admin_client = app.test_client()
    login(admin_client, "morgan", "password123")

    row = _barber_row(admin_client.get("/admin/").data.decode(), "alex")

    assert f"/admin/barbers/{barber['id']}/login" in row
    assert f"/admin/barbers/{barber['id']}/logout" not in row
    # The location is chosen in a dialog; the form carries their default as the pre-fill.
    assert f'name="location_id" value="{locations["main-street"]}"' in row
    assert "<select" not in row


def test_admin_can_log_a_barber_in_at_a_shop(app, barber, admin_barber, locations):
    from tests.conftest import kiosk_url

    admin_client = app.test_client()
    login(admin_client, "morgan", "password123")

    admin_client.post(
        f"/admin/barbers/{barber['id']}/login", data={"location_id": locations["riverside"]}
    )

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_duty_location_id == locations["riverside"]
    assert b"Alex" in app.test_client().get(kiosk_url(app, "riverside")).data

    row = _barber_row(admin_client.get("/admin/").data.decode(), "alex")
    assert "On duty at Riverside" in row
    assert f"/admin/barbers/{barber['id']}/logout" in row
    assert f"/admin/barbers/{barber['id']}/login" not in row

    admin_client.post(f"/admin/barbers/{barber['id']}/logout")

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_duty_location_id is None
    assert b"Alex" not in app.test_client().get(kiosk_url(app, "riverside")).data


def test_admin_cannot_log_in_an_inactive_barber(app, barber, admin_barber, locations):
    with app.app_context():
        db.session.get(Barber, barber["id"]).active = False
        db.session.commit()
    admin_client = app.test_client()
    login(admin_client, "morgan", "password123")

    assert f"/admin/barbers/{barber['id']}/login" not in _barber_row(
        admin_client.get("/admin/").data.decode(), "alex"
    )
    admin_client.post(f"/admin/barbers/{barber['id']}/login", data={"location_id": locations["main-street"]})

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_duty_location_id is None


def test_admin_log_in_requires_a_valid_location(app, barber, admin_barber):
    admin_client = app.test_client()
    login(admin_client, "morgan", "password123")
    admin_client.post(f"/admin/barbers/{barber['id']}/login", data={"location_id": "9999"})

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_duty_location_id is None


def test_admin_log_in_requires_admin(app, barber, other_location_barber, locations):
    client = app.test_client()
    login(client, "alex", "password123")
    resp = client.post(
        f"/admin/barbers/{other_location_barber['id']}/login", data={"location_id": locations["main-street"]}
    )
    assert resp.status_code == 403
