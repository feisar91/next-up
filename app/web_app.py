"""Web app manifests, so the staff pages and each shop's kiosk can be added to a
phone or tablet home screen and open full-screen like an app (no browser bar).

The staff app's manifest is the same for everyone. A kiosk's has to include its
secret link: an installed app opens its start_url, and the kiosk page only works
with the token in it. So each kiosk serves its own manifest from under its link.
Browsers fetch manifests without cookies, so neither may need a login.
"""
from flask import jsonify

from app.branding import OFF_WHITE, get_brand


def _icons(brand):
    icons = []
    for size in (192, 512):
        src = brand.icon_url(size)
        # app/branding.py keeps the picture inside the maskable safe zone on a
        # full-bleed background, so the same file works as-is and cropped to a
        # circle or squircle.
        for purpose in ("any", "maskable"):
            icons.append({"src": src, "sizes": f"{size}x{size}", "type": "image/png", "purpose": purpose})
    return icons


def manifest_response(*, app_id, name, short_name, start_url, scope, display):
    brand = get_brand()
    response = jsonify(
        {
            "id": app_id,
            "name": name,
            "short_name": short_name,
            "start_url": start_url,
            "scope": scope,
            "display": display,
            # The page background, for the launch screen, and the browser/status bar colour.
            "background_color": OFF_WHITE,
            "theme_color": brand.dark,
            "icons": _icons(brand),
        }
    )
    response.mimetype = "application/manifest+json"
    return response
