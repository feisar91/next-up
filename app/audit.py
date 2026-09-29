"""Activity log: every action the app can produce - admin changes, barber queue
actions, customer check-ins, and automatic/CLI changes - who did it, when, and
what. Filterable on the admin Activity tab (see app/admin.py)."""
from flask import has_request_context
from flask_login import current_user

from app import db
from app.models import AdminAction, Location

CLI_ACTOR = "Command line"
# Changes the app makes by itself, e.g. taking idle barbers off duty (app/off_duty.py).
AUTOMATIC_ACTOR = "Automatic"
# A check-in from the kiosk, where there's no logged-in barber to be the actor.
CUSTOMER_ACTOR = "Customer"
# A failed login: whoever typed the password hasn't proven who they are.
UNKNOWN_ACTOR = "Unknown"

CATEGORY_ADMIN = "admin"
CATEGORY_BARBER = "barber"
CATEGORY_CUSTOMER = "customer"
CATEGORY_AUTOMATIC = "automatic"
CATEGORY_CLI = "cli"
CATEGORY_SECURITY = "security"

# Order they're offered in the Activity tab's category filter.
CATEGORY_LABELS = {
    CATEGORY_ADMIN: "Admin",
    CATEGORY_BARBER: "Barber",
    CATEGORY_CUSTOMER: "Customer",
    CATEGORY_AUTOMATIC: "Automatic",
    CATEGORY_CLI: "Command line",
    CATEGORY_SECURITY: "Security",
}

# Human-readable label for each action code, for the Activity tab's event-type
# filter and table. Falls back to the raw code for anything not listed here.
ACTION_LABELS = {
    "settings.timezone": "Changed timezone",
    "location.create": "Created location",
    "location.delete": "Deleted location",
    "location.remove": "Removed location",
    "location.restore": "Restored location",
    "location.regenerate_kiosk_link": "Regenerated kiosk link",
    "location.regenerate_display_link": "Regenerated TV display link",
    "location.close": "Closed store to check-ins",
    "location.open": "Opened store to check-ins",
    "location.hours": "Changed opening hours",
    "location.special_hours_set": "Set special hours",
    "location.special_hours_remove": "Removed special hours",
    "barber.create": "Created barber",
    "barber.edit": "Edited barber",
    "barber.reset_password": "Reset password",
    "barber.activate": "Activated barber",
    "barber.deactivate": "Deactivated barber",
    "barber.logout": "Logged out barber",
    "barber.login": "Logged in barber",
    "barber.kiosk_visibility": "Changed kiosk visibility",
    "barber.delete": "Deleted barber",
    "barber.auto_off_duty": "Automatic off duty",
    "session.login": "Logged in",
    "session.logout": "Logged out",
    "session.location": "Chose working location",
    "session.login_failed": "Failed login",
    "session.lockout": "Login locked out",
    "barber.change_own_password": "Changed own password",
    "barber.edit_own_profile": "Updated own profile",
    "barber.break_start": "Went on break",
    "barber.break_end": "Back from break",
    "queue.checkin": "Customer checked in",
    "queue.call": "Called customer to chair",
    "queue.complete": "Completed customer",
    "queue.remove": "Removed customer (no-show)",
    "queue.undo": "Undid finish",
    "queue.auto_clear": "Cleared leftover queue",
}


def action_label(action):
    return ACTION_LABELS.get(action, action)


def record(action, summary, actor=None, automatic=False, category=CATEGORY_ADMIN, actor_name=None):
    """Add an entry. `actor` defaults to the logged-in user; outside a request
    (the flask CLI) it's recorded as "Command line", in a request with nobody
    logged in (a kiosk check-in) as "Customer", or as "Automatic" when
    `automatic` is set - each of those also overrides `category`, which
    otherwise defaults to "admin" for the original /admin callers. `actor_name`
    names an actor who isn't a user (e.g. "Unknown" for a failed login) and
    keeps `category` as given."""
    if actor is None and not automatic and has_request_context() and current_user.is_authenticated:
        actor = current_user

    if automatic:
        category, fallback = CATEGORY_AUTOMATIC, AUTOMATIC_ACTOR
    elif actor is not None:
        fallback = None
    elif actor_name is not None:
        fallback = actor_name
    elif not has_request_context():
        category, fallback = CATEGORY_CLI, CLI_ACTOR
    else:
        category, fallback = CATEGORY_CUSTOMER, CUSTOMER_ACTOR

    db.session.add(
        AdminAction(
            actor_id=actor.id if actor else None,
            actor_name=actor.name if actor else fallback,
            action=action,
            summary=summary[:500],
            category=category,
        )
    )
    db.session.commit()


def barber_changes(barber, name, username, default_location_id, is_admin):
    """Human-readable list of what an edit to `barber` changes, for summaries.
    Call before applying the edit."""
    changes = []
    if name != barber.name:
        changes.append(f"name {barber.name} to {name}")
    if username != barber.username:
        changes.append(f"username {barber.username} to {username}")
    if default_location_id != barber.default_location_id:
        new_location = db.session.get(Location, default_location_id) if default_location_id else None
        old_name = barber.default_location.name if barber.default_location else "none"
        changes.append(f"default location {old_name} to {new_location.name if new_location else 'none'}")
    if is_admin != barber.is_admin:
        changes.append("granted admin access" if is_admin else "removed admin access")
    return changes


def recent(limit=100, category=None, action=None, actor_name=None, start=None, end=None):
    """Log entries, newest first, filtered by any of the Activity tab's filters
    that are given. `start`/`end` are UTC datetimes; `end` is exclusive."""
    query = AdminAction.query
    if category:
        query = query.filter_by(category=category)
    if action:
        query = query.filter_by(action=action)
    if actor_name:
        query = query.filter_by(actor_name=actor_name)
    if start is not None:
        query = query.filter(AdminAction.created_at >= start)
    if end is not None:
        query = query.filter(AdminAction.created_at < end)
    return query.order_by(AdminAction.created_at.desc(), AdminAction.id.desc()).limit(limit).all()


def categories():
    """[(value, label), ...] for the Activity tab's category filter."""
    return list(CATEGORY_LABELS.items())


def actions_in_use():
    """[(action code, label), ...] for every action ever logged, for the Activity
    tab's event-type filter, sorted by label."""
    codes = [row[0] for row in db.session.query(AdminAction.action).distinct()]
    return sorted(((code, action_label(code)) for code in codes), key=lambda pair: pair[1])


def actor_names():
    """Distinct actor names ever logged, for the Activity tab's "who" filter."""
    return sorted(row[0] for row in db.session.query(AdminAction.actor_name).distinct())
