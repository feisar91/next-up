import glob
import re
from pathlib import Path

import pytest

from app import db
from app.models import Barber, QueueEntry
from tests.conftest import kiosk_url

TOKEN_RE = re.compile(r'name="csrf_token" value="([^"]+)"')


@pytest.fixture()
def csrf_on(app):
    # TestConfig switches CSRF off for convenience; these tests switch it back on.
    app.config["WTF_CSRF_ENABLED"] = True
    yield
    app.config["WTF_CSRF_ENABLED"] = False


def _token(client, url):
    return TOKEN_RE.search(client.get(url).data.decode()).group(1)


def _login(client, username="alex", password="password123"):
    token = _token(client, "/login")
    return client.post("/login", data={"username": username, "password": password, "csrf_token": token})


def test_every_post_form_in_templates_carries_a_csrf_token():
    missing = []
    for path in glob.glob("app/templates/**/*.html", recursive=True):
        source = Path(path).read_text()
        for match in re.finditer(r"<form\b[^>]*>", source, flags=re.I):
            if 'method="post"' not in match.group(0).lower():
                continue
            body = source[match.end():source.find("</form>", match.end())]
            if "csrf_token()" not in body:
                missing.append(f"{path}: {match.group(0)[:80]}")
    assert missing == []


def test_js_built_staff_forms_include_the_token():
    assert "csrf_token" in Path("app/static/js/staff.js").read_text()
    assert 'name="csrf-token"' in Path("app/templates/base.html").read_text()


def test_login_without_token_is_rejected(app, client, barber, csrf_on):
    resp = client.post("/login", data={"username": "alex", "password": "password123"})

    assert resp.status_code == 302
    assert client.get("/staff/choose-location").status_code == 302  # still logged out


def test_login_with_token_works(app, client, barber, csrf_on):
    _login(client)
    assert client.get("/staff/choose-location").status_code == 200


def test_expired_page_sends_user_back_with_a_message(app, client, barber, csrf_on):
    resp = client.post(
        "/login",
        data={"username": "alex", "password": "password123"},
        headers={"Referer": "http://localhost/login"},
        follow_redirects=True,
    )
    assert b"That page had expired" in resp.data


def test_admin_action_without_token_does_nothing(app, client, admin_barber, barber, csrf_on):
    _login(client, "morgan")

    client.post(f"/admin/barbers/{barber['id']}/toggle-active")

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).active is True


def test_admin_action_with_token_works(app, client, admin_barber, barber, csrf_on):
    _login(client, "morgan")
    token = _token(client, "/admin/")

    client.post(f"/admin/barbers/{barber['id']}/toggle-active", data={"csrf_token": token})

    with app.app_context():
        assert db.session.get(Barber, barber["id"]).active is False


def test_kiosk_check_in_needs_the_pages_token(app, client, locations, csrf_on):
    url = kiosk_url(app, "main-street")
    client.post(url, data={"customer_name": "Forged"})
    client.post(url, data={"customer_name": "Real", "csrf_token": _token(client, url)})

    with app.app_context():
        names = [e.customer_name for e in QueueEntry.query.all()]
    assert names == ["Real"]


def test_logout_is_post_only(app, client, barber):
    from tests.conftest import login

    login(client, "alex", "password123")
    assert client.get("/logout").status_code == 405
    assert client.get("/staff/choose-location").status_code == 200
