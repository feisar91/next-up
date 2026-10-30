from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from flask import current_app

from app import db
from app.models import Setting

FALLBACK_TIMEZONE = "UTC"


@lru_cache(maxsize=1)
def _zone_names():
    """Every zone name this system knows. Listing them reads the timezone files
    (a few milliseconds), and one page can look up the timezone dozens of times,
    so it's read once per process."""
    return frozenset(available_timezones())


@lru_cache(maxsize=1)
def timezone_choices():
    """Region/City zone names for the admin picker, skipping legacy aliases like 'EST'."""
    return sorted(
        name
        for name in _zone_names()
        if "/" in name and not name.startswith(("Etc/", "posix/", "right/", "SystemV/"))
    )


def default_timezone_name():
    """The TIMEZONE env var (Config.DEFAULT_TIMEZONE), if it's a real zone."""
    name = current_app.config.get("DEFAULT_TIMEZONE")
    return name if name in _zone_names() else FALLBACK_TIMEZONE


def timezone_is_set():
    return db.session.get(Setting, "timezone") is not None


def get_timezone_name():
    setting = db.session.get(Setting, "timezone")
    if setting and setting.value in _zone_names():
        return setting.value
    return default_timezone_name()


def get_timezone():
    return ZoneInfo(get_timezone_name())


def set_timezone_name(name):
    setting = db.session.get(Setting, "timezone")
    if setting:
        setting.value = name
    else:
        db.session.add(Setting(key="timezone", value=name))
    db.session.commit()
