"""Server-side record of staff logins.

Flask's own session is just a signed cookie, so on its own there's no way to see
who is logged in or to end a session early. Each login therefore gets a row in
login_sessions, and the cookie carries a random token pointing at it. A request
is only authenticated while that row exists, hasn't been idle longer than
PERMANENT_SESSION_LIFETIME, and belongs to an active barber. Deleting rows is
how logout, admin "log out", password resets and deactivation end sessions.
"""
import hashlib
import secrets
from datetime import timedelta

from flask import current_app, request, session
from flask_login import login_user, logout_user
from sqlalchemy import func

from app import db
from app.models import Barber, LoginSession, utcnow

SESSION_TOKEN_KEY = "login_token"
# Don't write last_seen_at on every request - once a minute is plenty.
TOUCH_INTERVAL = timedelta(minutes=1)


def _hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _idle_cutoff():
    return utcnow() - current_app.permanent_session_lifetime


def start_session(barber):
    """Log `barber` in on this browser with a fresh server-side session."""
    token = secrets.token_urlsafe(32)
    db.session.add(
        LoginSession(
            barber_id=barber.id,
            token_hash=_hash(token),
            user_agent=(request.headers.get("User-Agent") or "")[:255],
        )
    )
    # Housekeeping: drop sessions that have already expired.
    LoginSession.query.filter(LoginSession.last_seen_at < _idle_cutoff()).delete()
    db.session.commit()

    session.clear()
    session.permanent = True
    session[SESSION_TOKEN_KEY] = token
    login_user(barber)


def _current_record():
    token = session.get(SESSION_TOKEN_KEY)
    if not token:
        return None
    return LoginSession.query.filter_by(token_hash=_hash(token)).first()


def load_user(user_id):
    """Flask-Login user_loader: only trusts the cookie if its session row is live."""
    record = _current_record()
    if not record or str(record.barber_id) != str(user_id):
        return None
    now = utcnow()
    last_seen = record.last_seen_at
    if last_seen.tzinfo is None:  # SQLite (tests) hands back naive datetimes
        last_seen = last_seen.replace(tzinfo=now.tzinfo)
    if last_seen < now - current_app.permanent_session_lifetime:
        db.session.delete(record)
        db.session.commit()
        return None
    barber = record.barber
    if not barber.active:
        return None
    if now - last_seen > TOUCH_INTERVAL:
        record.last_seen_at = now
        db.session.commit()
    return barber


def end_current_session():
    record = _current_record()
    if record:
        db.session.delete(record)
        db.session.commit()
    logout_user()
    session.clear()


def end_all_sessions(barber, keep_current=False):
    """Log `barber` out everywhere, optionally keeping the browser making this request."""
    query = LoginSession.query.filter_by(barber_id=barber.id)
    if keep_current:
        current = _current_record()
        if current:
            query = query.filter(LoginSession.id != current.id)
    query.delete()
    db.session.commit()


def logged_in_barbers():
    """{barber_id: (device_count, last_seen_at)} for everyone with a live session."""
    rows = (
        db.session.query(
            LoginSession.barber_id,
            func.count(LoginSession.id),
            func.max(LoginSession.last_seen_at),
        )
        .filter(LoginSession.last_seen_at >= _idle_cutoff())
        .group_by(LoginSession.barber_id)
        .all()
    )
    return {barber_id: (count, last_seen) for barber_id, count, last_seen in rows}
