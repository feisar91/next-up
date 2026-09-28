from app import db, socketio
from app.models import Barber
from tests.conftest import kiosk_url, login


def test_kiosk_shows_no_barbers_before_anyone_logs_in(app, client, locations, barber):
    resp = client.get(kiosk_url(app, "launceston"))
    assert resp.status_code == 200
    assert b"Alex" not in resp.data


def test_barber_appears_on_kiosk_after_visiting_their_dashboard(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")

    resp = client.get(kiosk_url(app, "launceston"))
    assert b"Alex" in resp.data

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.on_duty_location_id == locations["launceston"]


def test_barber_disappears_from_kiosk_after_logout(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.post("/logout")

    resp = client.get(kiosk_url(app, "launceston"))
    assert b"Alex" not in resp.data

    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.on_duty_location_id is None


def test_barber_moves_kiosks_when_switching_locations(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.get("/staff/kings-meadows")

    assert b"Alex" not in client.get(kiosk_url(app, "launceston")).data
    assert b"Alex" in client.get(kiosk_url(app, "kings-meadows")).data


def test_deactivating_an_on_duty_barber_removes_them_from_kiosk(
    app, client, locations, barber, admin_barber
):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.post("/logout")

    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/barbers/{barber['id']}/toggle-active")

    resp = client.get(kiosk_url(app, "launceston"))
    assert b"Alex" not in resp.data


def test_kiosk_token_can_join_socket_room_and_receive_barbers_update(app, client, locations):
    kiosk_token, _ = _tokens(app, "launceston")

    sio_client = socketio.test_client(app, flask_test_client=client)
    sio_client.emit("join", {"location": "launceston", "token": kiosk_token})
    received = sio_client.get_received()

    assert any(evt["name"] == "barbers_update" for evt in received)
    sio_client.disconnect()


def _tokens(app, slug):
    from app.models import Location

    with app.app_context():
        location = Location.query.filter_by(slug=slug).first()
        return location.kiosk_token, location.display_token


def test_barber_hidden_from_kiosk_is_not_listed_while_on_duty(app, client, locations, barber):
    with app.app_context():
        db.session.get(Barber, barber["id"]).show_on_kiosk = False
        db.session.commit()

    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")

    assert b"Alex" not in client.get(kiosk_url(app, "launceston")).data


def test_admin_can_toggle_barber_kiosk_visibility(app, client, locations, barber, admin_barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.post("/logout")
    with app.app_context():
        db.session.get(Barber, barber["id"]).on_duty_location_id = locations["launceston"]
        db.session.commit()

    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/barbers/{barber['id']}/toggle-kiosk")

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).show_on_kiosk is False
    assert b"Alex" not in client.get(kiosk_url(app, "launceston")).data

    client.post(f"/admin/barbers/{barber['id']}/toggle-kiosk")
    assert b"Alex" in client.get(kiosk_url(app, "launceston")).data


def test_admin_can_hide_themselves_from_kiosk(app, client, locations, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    client.get("/staff/launceston")
    assert b"Morgan Admin" in client.get(kiosk_url(app, "launceston")).data

    client.post(f"/admin/barbers/{admin_barber['id']}/toggle-kiosk")

    assert b"Morgan Admin" not in client.get(kiosk_url(app, "launceston")).data


def test_toggle_kiosk_requires_admin(client, barber, other_location_barber):
    login(client, barber["username"], barber["password"])
    resp = client.post(f"/admin/barbers/{other_location_barber['id']}/toggle-kiosk")
    assert resp.status_code == 403


def test_editing_barber_does_not_change_kiosk_visibility(app, client, locations, barber, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(
        f"/admin/barbers/{barber['id']}/edit",
        data={"name": "Alex", "username": "alex", "default_location_id": ""},
    )
    with app.app_context():
        assert db.session.get(Barber, barber["id"]).show_on_kiosk is True


def test_kiosk_ignores_hidden_barber_as_preferred(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    with app.app_context():
        db.session.get(Barber, barber["id"]).show_on_kiosk = False
        db.session.commit()

    client.post(
        kiosk_url(app, "launceston"),
        data={"customer_name": "Jordan", "preferred_barber_id": str(barber["id"])},
    )

    from app.models import QueueEntry

    with app.app_context():
        entry = QueueEntry.query.filter_by(customer_name="Jordan").one()
        assert entry.preferred_barber_id is None


def test_kiosk_receives_live_update_when_on_duty_barber_renames_themselves(app, locations, barber):
    kiosk_token, _ = _tokens(app, "launceston")
    barber_client = app.test_client()
    login(barber_client, barber["username"], barber["password"])
    barber_client.get("/staff/launceston")

    sio_client = socketio.test_client(app, flask_test_client=app.test_client())
    sio_client.emit("join", {"location": "launceston", "token": kiosk_token})
    sio_client.get_received()

    barber_client.post("/staff/profile", data={"form_name": "display_name", "name": "Alexander"})

    updates = [evt["args"][0] for evt in sio_client.get_received() if evt["name"] == "barbers_update"]
    assert updates, "kiosk got no barbers_update after the rename"
    assert updates[-1]["barbers"] == [{"id": barber["id"], "name": "Alexander"}]
    sio_client.disconnect()


def test_kiosk_receives_live_update_when_admin_renames_on_duty_barber(app, locations, barber, admin_barber):
    kiosk_token, _ = _tokens(app, "launceston")
    admin_client = app.test_client()
    login(admin_client, admin_barber["username"], admin_barber["password"])
    admin_client.post(f"/admin/barbers/{barber['id']}/login", data={"location_id": locations["launceston"]})

    sio_client = socketio.test_client(app, flask_test_client=app.test_client())
    sio_client.emit("join", {"location": "launceston", "token": kiosk_token})
    sio_client.get_received()

    admin_client.post(
        f"/admin/barbers/{barber['id']}/edit",
        data={"name": "Alexander", "username": "alex", "default_location_id": ""},
    )

    updates = [evt["args"][0] for evt in sio_client.get_received() if evt["name"] == "barbers_update"]
    assert updates and updates[-1]["barbers"] == [{"id": barber["id"], "name": "Alexander"}]
    sio_client.disconnect()


def _set_break(client, on_break):
    return client.post("/staff/launceston/break", data={"on_break": "1" if on_break else "0"})


def test_barber_on_break_leaves_the_kiosk_but_stays_on_duty(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")

    resp = _set_break(client, True)
    assert resp.status_code == 302
    assert b"Alex" not in client.get(kiosk_url(app, "launceston")).data
    with app.app_context():
        updated = db.session.get(Barber, barber["id"])
        assert updated.on_break is True
        assert updated.on_duty_location_id == locations["launceston"]

    _set_break(client, False)
    assert b"Alex" in client.get(kiosk_url(app, "launceston")).data


def test_break_form_sets_state_rather_than_toggling(app, client, locations, barber):
    # Two devices, one showing a stale "Go On Break" button: pressing it twice
    # must leave the barber on break, not flip them back.
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    _set_break(client, True)
    _set_break(client, True)

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_break is True


def test_dashboard_shows_the_break_button_for_the_current_state(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    assert b"Go On Break" in client.get("/staff/launceston").data

    _set_break(client, True)
    page = client.get("/staff/launceston").data
    assert b"You're on break" in page
    assert b"Back from Break" in page


def test_dashboard_has_no_break_button_when_admin_hid_the_barber(app, client, locations, barber):
    with app.app_context():
        db.session.get(Barber, barber["id"]).show_on_kiosk = False
        db.session.commit()

    login(client, barber["username"], barber["password"])
    page = client.get("/staff/launceston").data
    assert b"Go On Break" not in page
    assert b"An admin has hidden you from the kiosk" in page


def test_logging_out_ends_the_break(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    _set_break(client, True)
    client.post("/logout")

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_break is False

    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    assert b"Alex" in client.get(kiosk_url(app, "launceston")).data


def test_kiosk_ignores_barber_on_break_as_preferred(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    _set_break(client, True)

    client.post(
        kiosk_url(app, "launceston"),
        data={"customer_name": "Jordan", "preferred_barber_id": str(barber["id"])},
    )
    with app.app_context():
        from app.models import QueueEntry

        assert QueueEntry.query.filter_by(customer_name="Jordan").one().preferred_barber_id is None


def test_break_requires_login(client, locations):
    resp = client.post("/staff/launceston/break", data={"on_break": "1"})
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_kiosk_receives_live_update_when_barber_goes_on_break(app, locations, barber):
    kiosk_token, _ = _tokens(app, "launceston")
    barber_client = app.test_client()
    login(barber_client, barber["username"], barber["password"])
    barber_client.get("/staff/launceston")

    sio_client = socketio.test_client(app, flask_test_client=app.test_client())
    sio_client.emit("join", {"location": "launceston", "token": kiosk_token})
    sio_client.get_received()

    _set_break(barber_client, True)

    updates = [evt["args"][0] for evt in sio_client.get_received() if evt["name"] == "barbers_update"]
    assert updates and updates[-1]["barbers"] == []
    sio_client.disconnect()


def test_admin_overview_shows_barber_on_break(app, client, locations, barber, admin_barber):
    barber_client = app.test_client()
    login(barber_client, barber["username"], barber["password"])
    barber_client.get("/staff/launceston")
    _set_break(barber_client, True)

    login(client, admin_barber["username"], admin_barber["password"])
    assert b"On duty at Launceston, on break" in client.get("/admin/").data
