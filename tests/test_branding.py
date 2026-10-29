import io

from PIL import Image

from app import branding, db, socketio
from app.models import AdminAction, BrandAsset, Location
from tests.conftest import display_url, kiosk_url, login


def _png(size=(120, 60), colour=(255, 255, 255, 255), transparent_border=0):
    image = Image.new("RGBA", (size[0] + 2 * transparent_border, size[1] + 2 * transparent_border), (0, 0, 0, 0))
    image.paste(Image.new("RGBA", size, colour), (transparent_border, transparent_border))
    out = io.BytesIO()
    image.save(out, "PNG")
    return out.getvalue()


def _upload(client, kind, data, filename="logo.png"):
    return client.post(
        f"/admin/branding/{kind}",
        data={"image": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
        follow_redirects=True,
    )


def _save_identity(client, name="Fade Street", dark="#202a44", accent="#8a2be2"):
    return client.post(
        "/admin/branding", data={"name": name, "dark": dark, "accent": accent}, follow_redirects=True
    )


def _branding_log(app):
    with app.app_context():
        return [
            (a.action, a.summary)
            for a in AdminAction.query.filter(AdminAction.action.like("settings.%")).order_by(AdminAction.id)
        ]


def _image(resp):
    return Image.open(io.BytesIO(resp.data))


# Defaults ----------------------------------------------------------------------


def test_a_new_install_uses_the_next_up_defaults(app, client, locations):
    html = client.get(kiosk_url(app, "main-street")).data.decode()

    assert "<title>Check In - Main Street</title>" in html
    assert f"--brand-dark: {branding.DEFAULT_DARK};" in html
    assert f"--brand-accent: {branding.DEFAULT_ACCENT};" in html
    assert 'class="kiosk-brand-name"' in html  # no logo: the shop name instead
    assert "Next Up" in html
    assert "<title>Welcome - Next Up</title>" in client.get("/", follow_redirects=True).data.decode()


def test_no_page_mentions_the_original_shop(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    pages = ["/", "/admin/", "/admin/metrics", "/staff/profile", kiosk_url(app, "main-street"), display_url(app, "main-street")]
    for url in pages:
        assert "George" not in client.get(url).data.decode(), url


def test_default_colours_are_readable():
    branding.check_colours(branding.DEFAULT_DARK, branding.DEFAULT_ACCENT)


# Name and colours ----------------------------------------------------------------


def test_admin_sets_name_and_colours(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    resp = _save_identity(client)

    assert b"Branding saved" in resp.data
    html = client.get(kiosk_url(app, "main-street")).data.decode()
    assert "Fade Street" in html
    assert "--brand-dark: #202a44;" in html
    assert "--brand-accent: #8a2be2;" in html
    assert "--brand-accent-rgb: 138, 43, 226;" in html
    assert "<title>Admin - Fade Street</title>" in client.get("/admin/").data.decode()
    assert _branding_log(app) == [
        (
            "settings.branding",
            "Changed the shop name from Next Up to Fade Street, the dark colour from #1f2933 to #202a44 "
            "and the accent colour from #0d9488 to #8a2be2",
        )
    ]


def test_saving_without_changes_is_not_logged(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    _save_identity(client)
    _save_identity(client)
    assert len(_branding_log(app)) == 1


def test_colours_too_light_for_white_text_are_refused(app, client, admin_barber, locations):
    login(client, "morgan", "password123")

    resp = _save_identity(client, dark="#dddddd")
    assert b"too light" in resp.data
    resp = _save_identity(client, accent="#ffee00")
    assert b"too light" in resp.data
    resp = _save_identity(client, accent="not-a-colour")
    assert b"isn&#39;t a colour" in resp.data

    with app.app_context():
        assert branding.get_brand().name == "Next Up"
    assert _branding_log(app) == []


def test_blank_or_long_names_are_refused(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    assert b"can&#39;t be blank" in _save_identity(client, name="   ").data
    assert b"60 characters" in _save_identity(client, name="x" * 61).data


def test_short_hex_colours_are_accepted():
    assert branding.normalise_colour("#ABC") == "#aabbcc"
    assert branding.normalise_colour("1f2933") == "#1f2933"


def test_branding_needs_an_admin(app, client, barber, locations):
    login(client, "alex", "password123")
    assert client.post("/admin/branding", data={"name": "Mine"}).status_code == 403
    assert client.post("/admin/branding/logo", data={}).status_code == 403
    assert client.post("/admin/branding/logo/remove").status_code == 403


# Logo and icon -------------------------------------------------------------------


def test_logo_upload_shows_on_kiosk_tv_and_header(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    resp = _upload(client, "logo", _png(transparent_border=20))
    assert b"New logo saved" in resp.data

    brand = branding.get_brand()
    assert brand.has_logo
    logo_url = f"/brand/logo.png?v={brand.version}"
    for url in (kiosk_url(app, "main-street"), display_url(app, "main-street"), "/admin/"):
        html = client.get(url).data.decode()
        assert f'src="{logo_url}"' in html, url
    assert 'class="display-font brand-text"' not in client.get("/admin/").data.decode()

    logo = client.get(logo_url)
    assert logo.mimetype == "image/png"
    assert _image(logo).size == (120, 60)  # transparent border trimmed
    assert "immutable" in logo.headers["Cache-Control"]
    assert _branding_log(app) == [("settings.logo", "Uploaded a new logo")]


def test_large_logos_are_scaled_down(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    _upload(client, "logo", _png(size=(4000, 1000)))
    assert _image(client.get("/brand/logo.png")).size == (1600, 400)


def test_files_that_are_not_images_are_refused(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    resp = _upload(client, "logo", b"<svg onload=alert(1)>", filename="logo.svg")
    assert b"isn&#39;t an image we can use" in resp.data
    resp = _upload(client, "icon", _png(colour=(0, 0, 0, 0)))
    assert b"completely transparent" in resp.data
    with app.app_context():
        assert BrandAsset.query.count() == 0
    assert _branding_log(app) == []


def test_oversized_uploads_are_refused(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    resp = _upload(client, "logo", b"x" * (branding.MAX_UPLOAD_BYTES + 1))
    assert b"over 5 MB" in resp.data


def test_removing_the_logo(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    _upload(client, "logo", _png())
    resp = client.post("/admin/branding/logo/remove", follow_redirects=True)

    assert b"The logo was removed" in resp.data
    assert client.get("/brand/logo.png").status_code == 404
    assert 'class="kiosk-brand-name"' in client.get(kiosk_url(app, "main-street")).data.decode()
    assert _branding_log(app)[-1] == ("settings.logo", "Removed the logo")


def test_unknown_image_kind_is_404(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    assert client.post("/admin/branding/banner", data={}).status_code == 404


def test_rendered_icons_come_in_each_size(app, client):
    for size in branding.ICON_SIZES:
        resp = client.get(f"/brand/icon-{size}.png")
        assert resp.status_code == 200
        assert _image(resp).size == (size, size)
    assert client.get("/brand/icon-64.png").status_code == 404
    assert _image(client.get("/favicon.ico")).format == "ICO"


def test_default_icon_is_drawn_in_the_shop_colours(app, client, admin_barber):
    login(client, "morgan", "password123")
    _save_identity(client, dark="#202a44")
    corner = _image(client.get("/brand/icon-192.png")).convert("RGB").getpixel((0, 0))
    assert corner == (0x20, 0x2A, 0x44)


def test_transparent_logo_becomes_an_icon_on_the_dark_colour(app, client, admin_barber):
    login(client, "morgan", "password123")
    _save_identity(client, dark="#202a44")
    _upload(client, "logo", _png(size=(200, 50), colour=(255, 255, 255, 255), transparent_border=5))

    icon = _image(client.get("/brand/icon-512.png")).convert("RGB")
    assert icon.getpixel((0, 0)) == (0x20, 0x2A, 0x44)
    assert icon.getpixel((256, 256)) == (255, 255, 255)


def test_opaque_square_icon_fills_the_whole_icon(app, client, admin_barber):
    login(client, "morgan", "password123")
    _upload(client, "icon", _png(size=(300, 300), colour=(200, 10, 10, 255)))

    icon = _image(client.get("/brand/icon-192.png")).convert("RGB")
    assert icon.getpixel((0, 0)) == (200, 10, 10)
    assert 'src="/brand/icon.png' in client.get("/admin/").data.decode()  # beside the name in the header


def test_manifests_use_the_shop_name_and_colour(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    _save_identity(client)

    manifest = client.get("/staff/app.webmanifest").get_json()
    assert manifest["name"] == "Fade Street Staff"
    assert manifest["theme_color"] == "#202a44"
    assert all(icon["src"].startswith("/brand/icon-") for icon in manifest["icons"])


def test_visits_export_is_named_after_the_shop(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    _save_identity(client, name="Fade St. Barbers")
    resp = client.get("/admin/metrics/visits.csv")
    assert 'filename="fade-st-barbers-visits-' in resp.headers["Content-Disposition"]


# Screens update ------------------------------------------------------------------


def test_branding_change_tells_open_screens_to_reload(app, client, admin_barber, locations):
    with app.app_context():
        token = db.session.get(Location, locations["main-street"]).display_token
    tv = socketio.test_client(app)
    first_ack = tv.emit("join", {"location": "main-street", "token": token}, callback=True)
    tv.get_received()

    login(client, "morgan", "password123")
    _save_identity(client)

    pushes = [evt["args"][0] for evt in tv.get_received() if evt["name"] == "app_version"]
    tv.disconnect()
    assert len(pushes) == 1
    assert pushes[0]["version"] != first_ack["version"]
    assert pushes[0]["version"].startswith(app.config["APP_VERSION"] + "-")


def test_screens_listen_for_version_pushes():
    from pathlib import Path

    for script in ("kiosk.js", "display.js", "staff.js"):
        assert 'socket.on("app_version"' in Path(f"app/static/js/{script}").read_text()


# Command line --------------------------------------------------------------------


def test_cli_sets_branding(app, tmp_path):
    logo = tmp_path / "logo.png"
    logo.write_bytes(_png())
    result = app.test_cli_runner().invoke(
        args=["set-branding", "--name", "Fade Street", "--accent", "#8a2be2", "--logo", str(logo)]
    )

    assert result.exit_code == 0, result.output
    brand = branding.get_brand()
    assert (brand.name, brand.dark, brand.accent, brand.has_logo) == ("Fade Street", branding.DEFAULT_DARK, "#8a2be2", True)
    with app.app_context():
        entries = AdminAction.query.order_by(AdminAction.id).all()
    assert [(e.actor_name, e.action) for e in entries] == [
        ("Command line", "settings.branding"),
        ("Command line", "settings.logo"),
    ]


def test_cli_refuses_bad_colours(app):
    result = app.test_cli_runner().invoke(args=["set-branding", "--dark", "#ffffff"])
    assert result.exit_code != 0
    assert "too light" in result.output


def test_with_an_icon_the_header_and_tv_show_it_and_the_kiosk_keeps_the_logo(app, client, admin_barber, locations):
    login(client, "morgan", "password123")
    _upload(client, "logo", _png())
    _upload(client, "icon", _png(size=(100, 100)))
    version = branding.get_brand().version

    header = client.get("/admin/").data.decode()
    assert f'src="/brand/icon.png?v={version}"' in header
    assert 'class="display-font brand-text"' in header
    assert f'src="/brand/icon.png?v={version}"' in client.get(display_url(app, "main-street")).data.decode()
    assert f'src="/brand/logo.png?v={version}"' in client.get(kiosk_url(app, "main-street")).data.decode()
