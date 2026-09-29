from app import db
from app.models import Location
from tests.conftest import kiosk_url, login


def _kiosk_token(app, slug="launceston"):
    with app.app_context():
        return Location.query.filter_by(slug=slug).one().kiosk_token


def test_staff_manifest_needs_no_login(client):
    resp = client.get("/staff/app.webmanifest")
    assert resp.status_code == 200
    assert resp.mimetype == "application/manifest+json"
    manifest = resp.get_json()
    assert manifest["start_url"] == "/staff"
    assert manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    assert manifest["short_name"] == "Barber App"
    assert {icon["sizes"] for icon in manifest["icons"]} == {"192x192", "512x512"}
    assert {icon["purpose"] for icon in manifest["icons"]} == {"any", "maskable"}


def test_staff_pages_link_the_staff_manifest(client, barber):
    for html in (client.get("/login").data.decode(), login(client, barber["username"], barber["password"]).data.decode()):
        assert '<link rel="manifest" href="/staff/app.webmanifest">' in html
        assert 'rel="apple-touch-icon"' in html


def test_kiosk_manifest_opens_this_kiosk_full_screen(app, client, locations):
    token = _kiosk_token(app)
    resp = client.get(f"/kiosk/launceston/{token}/manifest.webmanifest")
    assert resp.status_code == 200
    manifest = resp.get_json()
    assert manifest["start_url"] == kiosk_url(app, "launceston")
    assert manifest["scope"] == kiosk_url(app, "launceston")
    assert manifest["display"] == "fullscreen"
    assert manifest["id"] == "/kiosk/launceston"  # no token: survives a link regeneration
    assert manifest["name"] == "Barber on George Check-In - Launceston"


def test_kiosk_manifest_needs_the_kiosk_token(app, client, locations):
    assert client.get("/kiosk/launceston/wrong-token/manifest.webmanifest").status_code == 404
    with app.app_context():
        display_token = Location.query.filter_by(slug="launceston").one().display_token
    assert client.get(f"/kiosk/launceston/{display_token}/manifest.webmanifest").status_code == 404
    with app.app_context():
        Location.query.filter_by(slug="launceston").one().active = False
        db.session.commit()
    assert client.get(f"/kiosk/launceston/{_kiosk_token(app)}/manifest.webmanifest").status_code == 404


def test_kiosk_page_links_its_own_manifest(app, client, locations):
    token = _kiosk_token(app)
    html = client.get(kiosk_url(app, "launceston")).data.decode()
    assert f'<link rel="manifest" href="/kiosk/launceston/{token}/manifest.webmanifest">' in html
    assert "/staff/app.webmanifest" not in html
