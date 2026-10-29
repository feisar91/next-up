"""The login and setup pages warn when the browser won't keep a login cookie
(app/static/js/cookie-check.js decides in the browser; these check the page)."""
from pathlib import Path

from tests.conftest import login


def _warning(html):
    start = html.index('id="cookie-warning"')
    return html[html.rindex("<div", 0, start) : html.index("</script>", start)]


def test_setup_page_has_the_cookie_check(app, client):
    app.config["SESSION_COOKIE_SECURE"] = True
    warning = _warning(client.get("/setup").data.decode())

    assert 'data-secure-cookies="true"' in warning
    assert " hidden" in warning.split(">")[0]  # only the script shows it
    assert "SESSION_COOKIE_SECURE=false" in warning
    assert "creating the admin login will only bring you back to this page" in warning
    assert "js/cookie-check.js" in warning


def test_login_page_has_the_cookie_check(app, client, barber):
    app.config["SESSION_COOKIE_SECURE"] = True
    warning = _warning(client.get("/login").data.decode())

    assert "Logins won't work at this address yet" in warning
    assert "logging in will only bring you back to this page" in warning


def test_cookie_check_knows_when_cookies_are_not_https_only(app, client, barber):
    app.config["SESSION_COOKIE_SECURE"] = False
    assert 'data-secure-cookies="false"' in _warning(client.get("/login").data.decode())


def test_cookie_check_tests_a_cookie_like_the_login_one():
    script = Path("app/static/js/cookie-check.js").read_text()
    assert '"; Secure"' in script and "document.cookie" in script
    assert "max-age=0" in script  # cleans up after itself
    assert 'window.location.protocol === "http:"' in script


def test_logged_in_pages_do_not_run_the_check(app, client, barber):
    html = login(client, "alex", "password123").data.decode()
    assert "cookie-warning" not in html
