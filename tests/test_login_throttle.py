from datetime import timedelta

from app import db
from app.models import LoginAttempt, utcnow
from tests.conftest import login


def _fail(client, username, times):
    for _ in range(times):
        client.post("/login", data={"username": username, "password": "wrong"})


def _logged_in(client):
    return client.get("/staff/choose-location").status_code == 200


def test_fifth_failure_locks_the_username(app, client, barber):
    _fail(client, "alex", 5)

    resp = client.post("/login", data={"username": "alex", "password": "password123"})

    assert resp.status_code == 429
    assert b"Too many failed log-in attempts. Try again in 15 minutes." in resp.data
    assert not _logged_in(client)


def test_four_failures_still_allow_login(app, client, barber):
    _fail(client, "alex", 4)
    login(client, "alex", "password123")
    assert _logged_in(client)


def test_lockout_is_per_username(app, client, barber, other_location_barber):
    _fail(client, "alex", 5)
    login(client, "sam", "password123")
    assert _logged_in(client)


def test_username_lockout_ignores_case(app, client, barber):
    _fail(client, "ALEX", 5)
    resp = client.post("/login", data={"username": "alex", "password": "password123"})
    assert resp.status_code == 429


def test_ip_lockout_after_twenty_failures_across_usernames(app, client, barber):
    for i in range(20):
        _fail(client, f"guess{i}", 1)

    resp = client.post("/login", data={"username": "alex", "password": "password123"})
    assert resp.status_code == 429


def test_other_ips_are_unaffected_by_an_ip_lockout(app, barber):
    attacker = app.test_client()
    for i in range(20):
        attacker.post("/login", data={"username": f"guess{i}", "password": "x"},
                      environ_base={"REMOTE_ADDR": "203.0.113.9"})

    shop = app.test_client()
    shop.post("/login", data={"username": "alex", "password": "password123"},
              environ_base={"REMOTE_ADDR": "198.51.100.7"})
    assert shop.get("/staff/choose-location", environ_base={"REMOTE_ADDR": "198.51.100.7"}).status_code == 200


def test_successful_login_clears_that_usernames_failures(app, client, barber):
    _fail(client, "alex", 4)
    login(client, "alex", "password123")
    client.post("/logout")

    _fail(client, "alex", 4)
    login(client, "alex", "password123")
    assert _logged_in(client)


def test_lockout_expires_after_the_window(app, client, barber):
    _fail(client, "alex", 5)
    with app.app_context():
        for attempt in LoginAttempt.query.all():
            attempt.attempted_at = utcnow() - timedelta(minutes=16)
        db.session.commit()

    login(client, "alex", "password123")
    assert _logged_in(client)


def test_wait_message_counts_down(app, client, barber):
    _fail(client, "alex", 5)
    with app.app_context():
        for attempt in LoginAttempt.query.all():
            attempt.attempted_at = utcnow() - timedelta(minutes=14, seconds=30)
        db.session.commit()

    resp = client.post("/login", data={"username": "alex", "password": "password123"})
    assert b"Try again in 1 minute." in resp.data
