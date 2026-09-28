"""Take barbers off duty when nobody is working as them any more.

Logging out takes a barber off the kiosk, but some on-duty barbers never log out:
one an admin put on duty with "Log In" has no device at all, and a phone login
can simply go idle until its session expires. A background thread checks every
OFF_DUTY_CHECK_SECONDS and takes off duty anyone who has no live login session
and has been on duty longer than the session lifetime (SESSION_LIFETIME_HOURS).
"""
import threading

from flask import current_app

from app import audit, db, socketio
from app.models import Barber, LoginSession, utcnow

_started = False
_start_lock = threading.Lock()


def take_idle_barbers_off_duty():
    """Returns the barbers taken off duty."""
    from app.staff import clear_on_duty

    cutoff = utcnow() - current_app.permanent_session_lifetime
    idle = Barber.query.filter(
        Barber.on_duty_location_id.isnot(None),
        db.or_(Barber.on_duty_since.is_(None), Barber.on_duty_since < cutoff),
        ~Barber.login_sessions.any(LoginSession.last_seen_at >= cutoff),
    ).all()

    hours = current_app.permanent_session_lifetime.total_seconds() / 3600
    for barber in idle:
        location_name = barber.on_duty_location.name
        clear_on_duty(barber)
        audit.record(
            "barber.auto_off_duty",
            f"Took {barber.name} off duty at {location_name} after {hours:g} hours with no activity",
            automatic=True,
        )
    return idle


def start_off_duty_checks(app):
    """Start the background check once per process. Called on the first request,
    not from create_app, so CLI commands (flask db upgrade) never start it."""
    global _started
    interval = app.config["OFF_DUTY_CHECK_SECONDS"]
    if _started or not interval:
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
                take_idle_barbers_off_duty()
            except Exception:
                app.logger.exception("Taking idle barbers off duty failed")
                db.session.rollback()
            finally:
                db.session.remove()
