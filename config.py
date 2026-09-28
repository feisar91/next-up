import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or "dev-secret-change-me"
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://checkin:checkin@localhost:5432/checkin"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Staff logins end after this long with no activity (see app/login_sessions.py).
    PERMANENT_SESSION_LIFETIME = timedelta(hours=float(os.environ.get("SESSION_LIFETIME_HOURS", 12)))
    # How often to take barbers with no live login off duty once they've been on
    # duty longer than the session lifetime (see app/off_duty.py). 0 disables it.
    OFF_DUTY_CHECK_SECONDS = int(os.environ.get("OFF_DUTY_CHECK_SECONDS", 300))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Only send the login cookie over HTTPS. Set SESSION_COOKIE_SECURE=false if the app
    # is reached over plain HTTP (no TLS proxy in front), or logins won't stick.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() != "false"

    # CSRF tokens (Flask-WTF) last as long as the browser session rather than
    # expiring after an hour, so an unattended kiosk left open all day still works.
    WTF_CSRF_TIME_LIMIT = None

    # Login rate limiting: after this many failed attempts within the window, further
    # attempts for that username (or from that IP) are refused until the window passes.
    # The per-IP limit is higher because a shop's devices usually share one address.
    LOGIN_MAX_FAILURES_PER_USER = int(os.environ.get("LOGIN_MAX_FAILURES_PER_USER", 5))
    LOGIN_MAX_FAILURES_PER_IP = int(os.environ.get("LOGIN_MAX_FAILURES_PER_IP", 20))
    LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", 15))

    # Set when running behind a reverse proxy (Nginx, Caddy) so the client's real IP
    # (X-Forwarded-For) is used for rate limiting instead of the proxy's.
    BEHIND_PROXY = os.environ.get("BEHIND_PROXY", "false").lower() == "true"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
    # Tests call take_idle_barbers_off_duty() directly instead of a background thread.
    OFF_DUTY_CHECK_SECONDS = 0
