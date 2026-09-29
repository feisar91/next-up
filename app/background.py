"""Background checks, started once per process by the first web request or
Socket.IO join (never from create_app, so CLI commands don't start them)."""
from app.off_duty import start_off_duty_checks
from app.opening_hours import start_opening_hours_checks


def start_background_checks(app):
    start_off_duty_checks(app)
    start_opening_hours_checks(app)
