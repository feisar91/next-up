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
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Only send the login cookie over HTTPS. Set SESSION_COOKIE_SECURE=false if the app
    # is reached over plain HTTP (no TLS proxy in front), or logins won't stick.
    SESSION_COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "true").lower() != "false"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL", "sqlite:///:memory:")
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False
