from datetime import timedelta
from unittest.mock import patch

from app import db, off_duty, socketio
from app.models import AdminAction, Barber, Location, LoginSession, utcnow
from app.off_duty import start_off_duty_checks, take_idle_barbers_off_duty
from tests.conftest import kiosk_url, login


def _age_on_duty(app, barber_id, extra=timedelta(minutes=1)):
    with app.app_context():
        b = db.session.get(Barber, barber_id)
        b.on_duty_since = utcnow() - app.permanent_session_lifetime - extra
        db.session.commit()


def _admin_logs_in(client, locations, admin_barber, barber):
    login(client, admin_barber["username"], admin_barber["password"])
    client.post(f"/admin/barbers/{barber['id']}/login", data={"location_id": locations["launceston"]})


def _sweep(app):
    with app.app_context():
        return [b.id for b in take_idle_barbers_off_duty()]


def _on_duty_location(app, barber_id):
    with app.app_context():
        return db.session.get(Barber, barber_id).on_duty_location_id


def test_going_on_duty_records_when(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    with app.app_context():
        since = db.session.get(Barber, barber["id"]).on_duty_since
    assert since is not None

    client.post("/logout")
    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_duty_since is None


def test_admin_logged_in_barber_goes_off_duty_after_the_session_lifetime(
    app, client, locations, barber, admin_barber
):
    _admin_logs_in(client, locations, admin_barber, barber)
    assert b"Alex" in client.get(kiosk_url(app, "launceston")).data

    _age_on_duty(app, barber["id"])
    assert _sweep(app) == [barber["id"]]

    assert _on_duty_location(app, barber["id"]) is None
    assert b"Alex" not in client.get(kiosk_url(app, "launceston")).data


def test_admin_logged_in_barber_stays_on_duty_within_the_lifetime(
    app, client, locations, barber, admin_barber
):
    _admin_logs_in(client, locations, admin_barber, barber)
    _age_on_duty(app, barber["id"], extra=-timedelta(minutes=1))

    assert _sweep(app) == []
    assert _on_duty_location(app, barber["id"]) == locations["launceston"]


def test_barber_with_a_live_session_stays_on_duty_on_a_long_shift(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    _age_on_duty(app, barber["id"], extra=timedelta(hours=3))

    assert _sweep(app) == []
    assert _on_duty_location(app, barber["id"]) == locations["launceston"]


def test_barber_whose_phone_session_went_idle_goes_off_duty(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    _age_on_duty(app, barber["id"])
    with app.app_context():
        for record in LoginSession.query.filter_by(barber_id=barber["id"]):
            record.last_seen_at = utcnow() - app.permanent_session_lifetime - timedelta(minutes=1)
        db.session.commit()

    assert _sweep(app) == [barber["id"]]
    assert _on_duty_location(app, barber["id"]) is None


def test_going_off_duty_automatically_ends_a_break(app, client, locations, barber):
    login(client, barber["username"], barber["password"])
    client.get("/staff/launceston")
    client.post("/staff/launceston/break", data={"on_break": "1"})
    with app.app_context():
        LoginSession.query.filter_by(barber_id=barber["id"]).delete()
        db.session.commit()
    _age_on_duty(app, barber["id"])

    _sweep(app)
    with app.app_context():
        assert db.session.get(Barber, barber["id"]).on_break is False


def test_automatic_off_duty_is_logged_as_automatic(app, client, locations, barber, admin_barber):
    _admin_logs_in(client, locations, admin_barber, barber)
    _age_on_duty(app, barber["id"])
    _sweep(app)

    with app.app_context():
        entry = AdminAction.query.filter_by(action="barber.auto_off_duty").one()
        assert entry.actor_name == "Automatic"
        assert entry.actor_id is None
        assert entry.summary == "Took Alex off duty at Launceston after 12 hours with no activity"


def test_kiosk_gets_a_live_update_when_a_barber_goes_off_duty(app, client, locations, barber, admin_barber):
    _admin_logs_in(client, locations, admin_barber, barber)
    _age_on_duty(app, barber["id"])
    with app.app_context():
        kiosk_token = Location.query.filter_by(slug="launceston").one().kiosk_token

    sio_client = socketio.test_client(app, flask_test_client=app.test_client())
    sio_client.emit("join", {"location": "launceston", "token": kiosk_token})
    sio_client.get_received()

    _sweep(app)

    updates = [e["args"][0] for e in sio_client.get_received() if e["name"] == "barbers_update"]
    assert updates and updates[-1]["barbers"] == []
    sio_client.disconnect()


def test_admin_page_shows_when_an_admin_logged_in_barber_goes_off_duty(
    app, client, locations, barber, admin_barber
):
    _admin_logs_in(client, locations, admin_barber, barber)

    html = client.get("/admin/").data.decode()
    assert "Off duty automatically at" in html
    assert "They go off duty automatically after 12 hours" not in html  # Alex is on duty; no Log In button


def test_log_in_confirmation_mentions_the_automatic_off_duty(app, client, locations, barber, admin_barber):
    login(client, admin_barber["username"], admin_barber["password"])
    assert "They go off duty automatically after 12 hours" in client.get("/admin/").data.decode()


def test_background_check_starts_once_and_not_when_disabled(app):
    with patch.object(off_duty, "_started", False), patch.object(
        socketio, "start_background_task"
    ) as start:
        start_off_duty_checks(app)  # TestConfig sets OFF_DUTY_CHECK_SECONDS = 0
        start.assert_not_called()

        app.config["OFF_DUTY_CHECK_SECONDS"] = 300
        try:
            start_off_duty_checks(app)
            start_off_duty_checks(app)
        finally:
            app.config["OFF_DUTY_CHECK_SECONDS"] = 0
        start.assert_called_once()


class _StopLoop(Exception):
    pass


def test_background_loop_runs_the_check_and_survives_errors(app, client, locations, barber, admin_barber):
    _admin_logs_in(client, locations, admin_barber, barber)
    _age_on_duty(app, barber["id"])

    real_check = off_duty.take_idle_barbers_off_duty
    calls = []

    def check():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("database hiccup")
        return real_check()

    with patch.object(socketio, "sleep", side_effect=[None, None, _StopLoop]), patch.object(
        off_duty, "take_idle_barbers_off_duty", side_effect=check
    ), patch.object(app.logger, "exception") as log_exception:
        try:
            off_duty._run(app, 300)
        except _StopLoop:
            pass

    assert len(calls) == 2
    log_exception.assert_called_once()
    assert _on_duty_location(app, barber["id"]) is None
