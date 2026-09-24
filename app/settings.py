from functools import lru_cache
from zoneinfo import ZoneInfo, available_timezones

from app import db
from app.models import Setting

DEFAULT_TIMEZONE = "Australia/Hobart"


@lru_cache(maxsize=1)
def timezone_choices():
    """Region/City zone names for the admin picker, skipping legacy aliases like 'EST'."""
    return sorted(
        name
        for name in available_timezones()
        if "/" in name and not name.startswith(("Etc/", "posix/", "right/", "SystemV/"))
    )


def get_timezone_name():
    setting = db.session.get(Setting, "timezone")
    if setting and setting.value in available_timezones():
        return setting.value
    return DEFAULT_TIMEZONE


def get_timezone():
    return ZoneInfo(get_timezone_name())


def set_timezone_name(name):
    setting = db.session.get(Setting, "timezone")
    if setting:
        setting.value = name
    else:
        db.session.add(Setting(key="timezone", value=name))
    db.session.commit()
