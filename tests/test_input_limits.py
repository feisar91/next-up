"""Text that won't fit its column. PostgreSQL refuses it with an error, but SQLite
(these tests) stores anything, so these check the app's own limits instead."""
from app import db
from app.models import MAX_LENGTHS, Barber, Location, QueueEntry
from tests.conftest import kiosk_url, login


def test_kiosk_cuts_an_over_long_name_to_fit(app, client, locations):
    response = client.post(
        kiosk_url(app, "main-street"), data={"customer_name": ["A" * 500, "Mia"], "preferred_barber_id": ""}
    )

    assert response.status_code == 302
    names = [entry.customer_name for entry in QueueEntry.query.order_by(QueueEntry.id)]
    assert names == ["A" * MAX_LENGTHS["customer_name"], "Mia"]


def test_kiosk_name_inputs_have_a_maximum_length(app, client, locations):
    html = client.get(kiosk_url(app, "main-street")).data.decode()

    assert html.count(f'maxlength="{MAX_LENGTHS["customer_name"]}"') == 2  # the first name and the extra-person row


def test_admin_refuses_an_over_long_location(app, client, admin_barber, locations):
    login(client, "morgan", "password123")

    for data, message in [
        ({"name": "L" * 121}, "Keep the location name to 120 characters or fewer."),
        ({"name": "Shop", "slug": "s" * 121}, "Keep the short name for links to 120 characters or fewer."),
        ({"name": "Shop", "address": "a" * 256}, "Keep the address to 255 characters or fewer."),
    ]:
        response = client.post("/admin/locations", data=data, follow_redirects=True)
        assert message in response.data.decode()

    assert Location.query.count() == 2  # just the fixture's


def test_admin_refuses_an_over_long_barber(app, client, admin_barber):
    login(client, "morgan", "password123")
    password = {"password": "password123", "confirm_password": "password123"}

    response = client.post("/admin/barbers", data={"name": "N" * 121, "username": "new", **password}, follow_redirects=True)
    assert "Keep the name to 120 characters or fewer." in response.data.decode()
    response = client.post("/admin/barbers", data={"name": "New", "username": "u" * 81, **password}, follow_redirects=True)
    assert "Keep the username to 80 characters or fewer." in response.data.decode()

    assert Barber.query.count() == 1


def test_admin_refuses_an_over_long_name_when_editing(app, client, admin_barber, barber):
    login(client, "morgan", "password123")

    response = client.post(
        f"/admin/barbers/{barber['id']}/edit", data={"name": "N" * 121, "username": "alex"}, follow_redirects=True
    )

    assert "Keep the name to 120 characters or fewer." in response.data.decode()
    assert db.session.get(Barber, barber["id"]).name == "Alex"


def test_profile_refuses_an_over_long_name(app, client, barber):
    login(client, "alex", "password123")

    response = client.post("/staff/profile", data={"name": "N" * 121}, follow_redirects=True)

    assert "Keep the display name to 120 characters or fewer." in response.data.decode()
    assert db.session.get(Barber, barber["id"]).name == "Alex"


def test_setup_refuses_an_over_long_username(app, client):
    response = client.post(
        "/setup",
        data={"name": "Owner", "username": "u" * 81, "password": "password123", "confirm_password": "password123"},
    )

    assert "Keep the username to 80 characters or fewer." in response.data.decode()
    assert Barber.query.count() == 0


def test_admin_forms_have_maximum_lengths(app, client, admin_barber):
    login(client, "morgan", "password123")
    html = client.get("/admin/").data.decode()

    for field in ("location_name", "location_slug", "location_address", "barber_name", "username"):
        assert f'maxlength="{MAX_LENGTHS[field]}"' in html
