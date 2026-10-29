"""Shop branding: the shop name, two colours, an optional logo and an optional
icon. An admin sets them on the Branding tab (app/admin.py) or with
`flask set-branding` (app/cli.py); every page gets them as `brand` (see
create_app) and the colours as CSS variables (templates/_brand_head.html).

Uploaded images are re-encoded as PNG and stored in the database (BrandAsset).
Favicons and home-screen icons are rendered from the icon (or the logo, or a
built-in mark in the shop's colours) at the sizes browsers ask for.

Every change bumps `brand_version`, which is part of the version the kiosk, TV
and staff screens compare against (app/static/js/app-version.js), so they reload
and pick up the new look straight away.
"""
import io
import re
import secrets
import warnings
from dataclasses import dataclass
from functools import lru_cache

from flask import Blueprint, abort, current_app, request, url_for
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from app import db, socketio
from app.models import BrandAsset, Location, Setting, utcnow

DEFAULT_NAME = "Next Up"
DEFAULT_DARK = "#1f2933"
DEFAULT_ACCENT = "#0d9488"
NAME_MAX_LENGTH = 60

LOGO = "logo"
ICON = "icon"
ASSET_LABELS = {LOGO: "logo", ICON: "icon"}

# The rendered favicon / home-screen icon sizes (see icon_url).
ICON_SIZES = (16, 32, 180, 192, 512)
MARK_SIZE = 256

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_SOURCE_PIXELS = 25_000_000
MAX_STORED_SIZE = {LOGO: (1600, 800), ICON: (1024, 1024)}
ACCEPTED_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}

# White text sits on the dark colour (headers, kiosk, TV) and on the accent
# colour (buttons). The dark colour is also the main text colour, so it needs
# the normal-text contrast ratio; the accent the large-text one.
MIN_DARK_CONTRAST = 4.5
MIN_ACCENT_CONTRAST = 3.0

KEY_NAME = "shop_name"
KEY_DARK = "brand_dark"
KEY_ACCENT = "brand_accent"
KEY_VERSION = "brand_version"

HEX_COLOUR = re.compile(r"^#[0-9a-f]{6}$")
OFF_WHITE = "#f6f7f7"


class BrandingError(ValueError):
    """A change was refused; the message is shown to the admin as-is."""


@dataclass(frozen=True)
class Brand:
    name: str
    dark: str
    accent: str
    version: str
    has_logo: bool
    has_icon: bool

    @property
    def file_slug(self):
        """The name as a file-name prefix, e.g. "Next Up" -> "next-up"."""
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-") or "shop"

    @property
    def logo_url(self):
        return _asset_url("brand.logo", self) if self.has_logo else None

    @property
    def mark_url(self):
        """A small square-ish picture for beside the shop name: the uploaded icon,
        or the built-in mark in the shop's colours."""
        return _asset_url("brand.icon", self) if self.has_icon else _asset_url("brand.mark", self)

    @property
    def header_image_url(self):
        """The picture in the staff header and on the TV: the icon if there is one,
        else the logo, else the built-in mark."""
        if self.has_icon or not self.has_logo:
            return self.mark_url
        return self.logo_url

    @property
    def show_name_in_header(self):
        """A logo on its own already says who the shop is; beside a mark, the name."""
        return self.has_icon or not self.has_logo

    def icon_url(self, size):
        return _asset_url("brand.rendered_icon", self, size=size)

    def css_vars(self):
        """CSS custom properties for _brand_head.html. Every value is built from
        validated #rrggbb colours, so it's safe to put in a <style> block."""
        return {
            "--brand-dark": self.dark,
            "--brand-dark-light": mix(self.dark, "#ffffff", 0.1),
            "--brand-dark-deep": mix(self.dark, "#000000", 0.35),
            "--brand-dark-rgb": rgb_triplet(self.dark),
            "--brand-accent": self.accent,
            "--brand-accent-dark": mix(self.accent, "#000000", 0.15),
            "--brand-accent-deep": mix(self.accent, "#000000", 0.3),
            "--brand-accent-rgb": rgb_triplet(self.accent),
        }


def _asset_url(endpoint, brand, **values):
    return url_for(endpoint, v=brand.version, **values)


def _settings():
    rows = Setting.query.filter(Setting.key.in_((KEY_NAME, KEY_DARK, KEY_ACCENT, KEY_VERSION))).all()
    return {row.key: row.value for row in rows}


def get_brand():
    values = _settings()
    assets = {key for (key,) in db.session.query(BrandAsset.key)}
    dark = values.get(KEY_DARK)
    accent = values.get(KEY_ACCENT)
    return Brand(
        name=values.get(KEY_NAME) or DEFAULT_NAME,
        dark=dark if dark and HEX_COLOUR.match(dark) else DEFAULT_DARK,
        accent=accent if accent and HEX_COLOUR.match(accent) else DEFAULT_ACCENT,
        version=values.get(KEY_VERSION, "0"),
        has_logo=LOGO in assets,
        has_icon=ICON in assets,
    )


def screen_version(brand=None):
    """What long-running screens compare to decide whether to reload: the app's
    code plus the branding, so either a deploy or a branding change reloads them."""
    brand = brand or get_brand()
    return f"{current_app.config['APP_VERSION']}-{brand.version}"


# Colours ---------------------------------------------------------------------


def normalise_colour(value):
    value = (value or "").strip().lower()
    if re.fullmatch(r"[0-9a-f]{6}", value):
        value = "#" + value
    if re.fullmatch(r"#[0-9a-f]{3}", value):
        value = "#" + "".join(c * 2 for c in value[1:])
    if not HEX_COLOUR.match(value):
        raise BrandingError(f"'{value or 'blank'}' isn't a colour. Use the colour picker or a hex code like #1f2933.")
    return value


def _channels(colour):
    return [int(colour[i : i + 2], 16) for i in (1, 3, 5)]


def rgb_triplet(colour):
    return ", ".join(str(c) for c in _channels(colour))


def mix(colour, other, amount):
    """`colour` moved `amount` (0-1) of the way towards `other`."""
    mixed = [round(a + (b - a) * amount) for a, b in zip(_channels(colour), _channels(other))]
    return "#" + "".join(f"{c:02x}" for c in mixed)


def _luminance(colour):
    def linear(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in _channels(colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_with_white(colour):
    return 1.05 / (_luminance(colour) + 0.05)


def check_colours(dark, accent):
    """Normalised (dark, accent), or BrandingError if white text wouldn't be
    readable on them."""
    dark = normalise_colour(dark)
    accent = normalise_colour(accent)
    if contrast_with_white(dark) < MIN_DARK_CONTRAST:
        raise BrandingError(
            f"The dark colour {dark} is too light: white writing on it would be hard to read. "
            "Pick a darker shade."
        )
    if contrast_with_white(accent) < MIN_ACCENT_CONTRAST:
        raise BrandingError(
            f"The accent colour {accent} is too light for white writing on buttons. Pick a deeper shade."
        )
    return dark, accent


# Changes ---------------------------------------------------------------------


def _set(key, value):
    setting = db.session.get(Setting, key)
    if setting:
        setting.value = value
    else:
        db.session.add(Setting(key=key, value=value))


def _bump_version():
    _set(KEY_VERSION, secrets.token_hex(4))


def update_identity(name, dark, accent):
    """Set the shop name and colours. Returns a list of what changed, in words,
    for the activity log (empty if nothing did)."""
    name = " ".join((name or "").split())
    if not name:
        raise BrandingError("The shop name can't be blank.")
    if len(name) > NAME_MAX_LENGTH:
        raise BrandingError(f"Keep the shop name to {NAME_MAX_LENGTH} characters or fewer.")
    dark, accent = check_colours(dark, accent)

    brand = get_brand()
    changes = []
    if name != brand.name:
        changes.append(f"the shop name from {brand.name} to {name}")
    if dark != brand.dark:
        changes.append(f"the dark colour from {brand.dark} to {dark}")
    if accent != brand.accent:
        changes.append(f"the accent colour from {brand.accent} to {accent}")
    if not changes:
        return []

    _set(KEY_NAME, name)
    _set(KEY_DARK, dark)
    _set(KEY_ACCENT, accent)
    _bump_version()
    db.session.commit()
    notify_screens()
    return changes


def change_summary(changes):
    """The activity log line for update_identity's changes: "Changed a, b and c"."""
    words = changes[0] if len(changes) == 1 else ", ".join(changes[:-1]) + " and " + changes[-1]
    return f"Changed {words}"


def prepare_image(data, kind):
    """Check and re-encode an uploaded image as PNG: right way up, trimmed of
    transparent edges and scaled down to a sensible size. Re-encoding also drops
    anything in the file that isn't the picture."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise BrandingError(f"That image is over {MAX_UPLOAD_BYTES // (1024 * 1024)} MB. Use a smaller file.")
    unreadable = BrandingError("That file isn't an image we can use. Upload a PNG, JPEG or WebP.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(io.BytesIO(data))
            if image.format not in ACCEPTED_FORMATS:
                raise unreadable
            if image.width * image.height > MAX_SOURCE_PIXELS:
                raise BrandingError("That image is too large. Use one under 5000 x 5000 pixels.")
            image.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise unreadable from None

    image = ImageOps.exif_transpose(image).convert("RGBA")
    box = image.getchannel("A").getbbox()
    if not box:
        raise BrandingError("That image is completely transparent.")
    image = image.crop(box)
    image.thumbnail(MAX_STORED_SIZE[kind], Image.Resampling.LANCZOS)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


def save_asset(kind, data):
    png = prepare_image(data, kind)
    asset = db.session.get(BrandAsset, kind)
    if asset:
        asset.data = png
        asset.updated_at = utcnow()
    else:
        db.session.add(BrandAsset(key=kind, data=png))
    _bump_version()
    db.session.commit()
    notify_screens()


def remove_asset(kind):
    """Returns whether there was one to remove."""
    asset = db.session.get(BrandAsset, kind)
    if not asset:
        return False
    db.session.delete(asset)
    _bump_version()
    db.session.commit()
    notify_screens()
    return True


def notify_screens():
    """Tell every open kiosk, TV and staff dashboard the version changed, so they
    reload with the new branding (each screen is in its location's main room)."""
    from app.sockets import location_room

    payload = {"version": screen_version()}
    for location in Location.query.filter_by(active=True):
        socketio.emit("app_version", payload, to=location_room(location.slug))


# Rendering icons ---------------------------------------------------------------


def _asset_bytes(kind):
    asset = db.session.get(BrandAsset, kind)
    return asset.data if asset else None


def _default_mark(size, dark, accent, background):
    """The built-in mark: two forward chevrons ("next up"), off-white then accent,
    drawn 4x and scaled down for smooth edges."""
    scale = 4
    full = size * scale
    image = Image.new("RGBA", (full, full), dark if background else (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    inset = 0.18 if background and size > 32 else 0.08
    top, bottom = full * (inset + 0.08), full * (1 - inset - 0.08)
    mid = full / 2
    height = bottom - top
    width = height * 0.55
    thickness = height * 0.22
    gap = height * 0.12
    start = (full - (2 * width + gap)) / 2
    for i, colour in enumerate((OFF_WHITE, accent)):
        x = start + i * (width + gap)
        draw.polygon(
            [
                (x, top),
                (x + thickness, top),
                (x + width, mid),
                (x + thickness, bottom),
                (x, bottom),
                (x + width - thickness, mid),
            ],
            fill=colour,
        )
    return image.resize((size, size), Image.Resampling.LANCZOS)


def _fit_on_background(source, size, dark):
    """A square icon of `size`: an opaque square-ish source fills it (it brings
    its own background); anything else sits centred on the dark colour, inside
    the area a home screen's circle or squircle crop keeps."""
    is_opaque = source.getchannel("A").getextrema()[0] == 255
    if is_opaque and 0.8 <= source.width / source.height <= 1.25:
        return ImageOps.fit(source, (size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), dark)
    room = round(size * (0.84 if size <= 32 else 0.62))
    picture = source.copy()
    picture.thumbnail((room, room), Image.Resampling.LANCZOS)
    canvas.alpha_composite(picture, ((size - picture.width) // 2, (size - picture.height) // 2))
    return canvas


@lru_cache(maxsize=64)
def _rendered_icon(size, version, dark, accent):
    # Keyed on the brand version, which changes with every upload or colour change.
    source = _asset_bytes(ICON) or _asset_bytes(LOGO)
    if source:
        image = _fit_on_background(Image.open(io.BytesIO(source)).convert("RGBA"), size, dark)
    else:
        image = _default_mark(size, dark, accent, background=True)
    out = io.BytesIO()
    image.save(out, "PNG", optimize=True)
    return out.getvalue()


@lru_cache(maxsize=16)
def _mark(version, dark, accent):
    out = io.BytesIO()
    _default_mark(MARK_SIZE, dark, accent, background=False).save(out, "PNG", optimize=True)
    return out.getvalue()


def rendered_icon(size):
    brand = get_brand()
    return _rendered_icon(size, brand.version, brand.dark, brand.accent)


# Routes ----------------------------------------------------------------------
# Public: the kiosk and TV have no login, and browsers fetch icons and web app
# manifests without cookies. Branding isn't secret.

brand_bp = Blueprint("brand", __name__)


def _image_response(data, mimetype="image/png"):
    response = current_app.response_class(data, mimetype=mimetype)
    # URLs carry ?v=<brand version>, which changes whenever the branding does.
    if request.args.get("v") == get_brand().version:
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache"
    return response


@brand_bp.route("/brand/logo.png")
def logo():
    data = _asset_bytes(LOGO)
    if not data:
        abort(404)
    return _image_response(data)


@brand_bp.route("/brand/icon.png")
def icon():
    data = _asset_bytes(ICON)
    if not data:
        abort(404)
    return _image_response(data)


@brand_bp.route("/brand/mark.png")
def mark():
    brand = get_brand()
    return _image_response(_mark(brand.version, brand.dark, brand.accent))


@brand_bp.route("/brand/icon-<int:size>.png", endpoint="rendered_icon")
def rendered_icon_image(size):
    if size not in ICON_SIZES:
        abort(404)
    return _image_response(rendered_icon(size))


@brand_bp.route("/favicon.ico")
def favicon():
    image = Image.open(io.BytesIO(rendered_icon(32)))
    out = io.BytesIO()
    image.save(out, "ICO", sizes=[(16, 16), (32, 32)])
    return _image_response(out.getvalue(), mimetype="image/x-icon")
