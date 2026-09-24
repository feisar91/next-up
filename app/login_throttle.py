"""Rate limiting for the staff login form.

Failed attempts are stored in login_attempts, so limits survive restarts. A
login is refused (without checking the password) once either the username or
the client IP has reached its limit of failures within LOGIN_LOCKOUT_MINUTES.
"""
import math
from datetime import timedelta, timezone

from flask import current_app, request
from sqlalchemy import or_

from app import db
from app.models import LoginAttempt, utcnow


def _window():
    return timedelta(minutes=current_app.config["LOGIN_LOCKOUT_MINUTES"])


def _client_ip():
    return (request.remote_addr or "unknown")[:45]


def _as_aware(dt):
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt  # SQLite drops tzinfo


def _minutes_until_below(attempts, limit):
    """Minutes until enough of `attempts` (oldest first) age out to drop below `limit`."""
    frees_at = _as_aware(attempts[len(attempts) - limit].attempted_at) + _window()
    return max(1, math.ceil((frees_at - utcnow()).total_seconds() / 60))


def lockout_minutes(username):
    """None if this login may be attempted, else minutes until it can be."""
    cutoff = utcnow() - _window()
    username = username.lower()
    ip = _client_ip()
    recent = (
        LoginAttempt.query.filter(
            LoginAttempt.attempted_at >= cutoff,
            or_(LoginAttempt.username == username, LoginAttempt.ip_address == ip),
        )
        .order_by(LoginAttempt.attempted_at.asc())
        .all()
    )
    by_user = [a for a in recent if a.username == username]
    by_ip = [a for a in recent if a.ip_address == ip]

    waits = []
    user_limit = current_app.config["LOGIN_MAX_FAILURES_PER_USER"]
    ip_limit = current_app.config["LOGIN_MAX_FAILURES_PER_IP"]
    if len(by_user) >= user_limit:
        waits.append(_minutes_until_below(by_user, user_limit))
    if len(by_ip) >= ip_limit:
        waits.append(_minutes_until_below(by_ip, ip_limit))
    return max(waits) if waits else None


def record_failure(username):
    LoginAttempt.query.filter(LoginAttempt.attempted_at < utcnow() - _window()).delete()
    db.session.add(LoginAttempt(username=username.lower()[:80], ip_address=_client_ip()))
    db.session.commit()


def clear_failures(username):
    """A successful login wipes that username's failures (not the IP's)."""
    LoginAttempt.query.filter_by(username=username.lower()).delete()
    db.session.commit()
