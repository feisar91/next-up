"""The public demo (DEMO_MODE=true): the made-up shop from app/demo.py, open to
anyone on the internet, and erased and loaded again every DEMO_RESET_MINUTES.

Every visitor shares the one shop, so demo mode turns off what one visitor could
use to spoil it for everyone else until the next reset:

- branding (the name, colours, logo and icon), and the first-run /setup page
- changing, resetting, deactivating, logging out or deleting the demo's own
  logins, and removing or deleting its locations or resetting their device links.
  Logins and locations a visitor adds can still have all of that done to them.
- any form text with a blocked word in it (app/word_filter.py), such as a
  customer name on the kiosk or an announcement

Resets happen on the hour (or every DEMO_RESET_MINUTES, counted in UTC) from a
background thread, plus once whenever the app starts (`flask bootstrap`). A reset
empties every table and runs seed_demo() again, keeping each location's kiosk
and TV links so screens left open carry on. It only ever runs on an empty
database or one it reset before, so turning DEMO_MODE on by mistake can't erase
a real shop.
"""
import threading
from datetime import datetime, timedelta, timezone

from flask import current_app, flash, redirect, request, session, url_for
from flask_login import current_user

from app import db, socketio
from app.demo import BARBERS, LOCATIONS, DemoError, seed_demo
from app.models import Barber, Location, Setting, utcnow
from app.word_filter import contains_blocked_word

# When the demo was last loaded. Its presence also marks the database as the demo's.
LAST_RESET_KEY = "demo_last_reset"
# The message for a refused kiosk check-in (the kiosk page has no flash messages).
KIOSK_ERROR_SESSION_KEY = "kiosk_error"

DEMO_USERNAMES = {username for _, username, _, _ in BARBERS}
DEMO_SLUGS = {fields["slug"] for fields in LOCATIONS}
# Shown as one-click logins on the demo's login page.
FEATURED_LOGINS = [("dana", "the owner"), ("marco", "a barber")]

TURNED_OFF = "That's turned off in the demo, so the demo keeps working for everyone else trying it."
BLOCKED_WORD = "That has a word the demo doesn't allow. Please try something else."

ALWAYS_OFF = {"admin.update_branding", "admin.upload_brand_image", "admin.remove_brand_image"}
DEMO_LOGIN_ACTIONS = {
    "admin.edit_barber",
    "admin.reset_barber_password",
    "admin.toggle_barber_active",
    "admin.force_logout_barber",
    "admin.delete_barber",
}
OWN_LOGIN_ACTIONS = {"auth.change_password", "staff.profile"}
DEMO_LOCATION_ACTIONS = {
    "admin.toggle_location_active",
    "admin.delete_location",
    "admin.regenerate_kiosk_token",
    "admin.regenerate_display_token",
}
# Not checked for blocked words: passwords aren't shown anywhere.
UNCHECKED_FIELDS = {"csrf_token", "password", "current_password", "confirm_password"}


def enabled():
    return current_app.config.get("DEMO_MODE", False)


# Requests ----------------------------------------------------------------------


def _get(model, record_id):
    return db.session.get(model, record_id) if record_id is not None else None


def _is_demo_login(barber):
    return barber is not None and barber.username in DEMO_USERNAMES


def _is_demo_location(location):
    return location is not None and location.slug in DEMO_SLUGS


def _turned_off():
    endpoint = request.endpoint
    if endpoint in ALWAYS_OFF:
        return True
    view_args = request.view_args or {}
    if endpoint in DEMO_LOGIN_ACTIONS:
        return _is_demo_login(_get(Barber, view_args.get("barber_id")))
    if endpoint in DEMO_LOCATION_ACTIONS:
        return _is_demo_location(_get(Location, view_args.get("location_id")))
    if endpoint in OWN_LOGIN_ACTIONS:
        return _is_demo_login(current_user)
    return False


def _has_blocked_word():
    return any(
        contains_blocked_word(value)
        for field, value in request.form.items(multi=True)
        if field not in UNCHECKED_FIELDS
    )


def _refuse(message):
    if request.endpoint == "kiosk.check_in":
        session[KIOSK_ERROR_SESSION_KEY] = message
        return redirect(request.path)
    flash(message, "error")
    referrer = request.referrer or ""
    if referrer.startswith(request.host_url):
        return redirect(referrer)
    return redirect(url_for("index"))


def check_request():
    """before_request hook, registered only in demo mode (see create_app)."""
    if request.endpoint == "auth.setup":
        return redirect(url_for("auth.login"))
    if request.method != "POST":
        return None
    if current_user.is_authenticated and _turned_off():
        return _refuse(TURNED_OFF)
    if _has_blocked_word():
        return _refuse(BLOCKED_WORD)
    return None


# Resets ------------------------------------------------------------------------


def _interval():
    return timedelta(minutes=current_app.config["DEMO_RESET_MINUTES"])


def last_scheduled_reset(now=None):
    """The most recent scheduled reset time: the last whole multiple of the
    interval since the Unix epoch, so on the hour (UTC) for 60 minutes."""
    now = now or utcnow()
    step = _interval().total_seconds()
    return datetime.fromtimestamp(now.timestamp() // step * step, timezone.utc)


def next_reset(now=None):
    return last_scheduled_reset(now) + _interval()


def _last_reset():
    setting = db.session.get(Setting, LAST_RESET_KEY)
    return datetime.fromisoformat(setting.value) if setting else None


def reset_due(now=None):
    last = _last_reset()
    return last is None or last < last_scheduled_reset(now)


def reset_demo(now=None):
    """Erase everything and load the demo shop again. Raises DemoError if demo mode
    is off, or the database has logins or locations the demo didn't make."""
    from app.branding import notify_screens

    if not enabled():
        raise DemoError("Demo mode is off. Set DEMO_MODE=true to run the public demo.")
    if (Barber.query.first() or Location.query.first()) and _last_reset() is None:
        raise DemoError(
            "This database has logins or locations the demo didn't create. Demo mode erases "
            "everything every hour, so it only runs on an empty database or one it set up itself."
        )

    now = now or utcnow()
    links = {location.slug: (location.kiosk_token, location.display_token) for location in Location.query}
    for table in reversed(db.metadata.sorted_tables):
        db.session.execute(table.delete())
    db.session.expunge_all()

    seed_demo(current_app.config["DEMO_PASSWORD"])
    for location in Location.query:
        # Open around the clock: visitors come from every timezone.
        location.auto_hours = False
        location.closed = False
        if location.slug in links:
            location.kiosk_token, location.display_token = links[location.slug]
    db.session.add(Setting(key=LAST_RESET_KEY, value=now.isoformat()))
    db.session.commit()
    # Branding was loaded again with a new version, so this reloads every open screen.
    notify_screens()


_started = False
_start_lock = threading.Lock()


def start_demo_resets(app):
    """Start the reset thread once per process (see app/background.py)."""
    global _started
    interval = app.config["DEMO_RESET_CHECK_SECONDS"]
    if not app.config["DEMO_MODE"] or _started or not interval:
        return
    with _start_lock:
        if _started:
            return
        _started = True
    socketio.start_background_task(_run, app, interval)


def _run(app, interval):
    while True:
        socketio.sleep(interval)
        with app.app_context():
            try:
                if reset_due():
                    reset_demo()
                    app.logger.info("Reset the demo")
            except Exception:
                app.logger.exception("Resetting the demo failed")
                db.session.rollback()
            finally:
                db.session.remove()


# Templates ---------------------------------------------------------------------


class DemoInfo:
    """`demo` in templates (None outside demo mode): for the banner and the login page."""

    def __init__(self):
        self.password = current_app.config["DEMO_PASSWORD"]
        self.resets_at = next_reset().isoformat()
        names = {username: name for name, username, _, _ in BARBERS}
        self.featured_logins = [(username, names[username], role) for username, role in FEATURED_LOGINS]
        self.other_usernames = [u for _, u, _, _ in BARBERS if u not in dict(FEATURED_LOGINS)]

    def locations(self):
        return (
            Location.query.filter(Location.slug.in_(DEMO_SLUGS), Location.active.is_(True))
            .order_by(Location.id)
            .all()
        )
