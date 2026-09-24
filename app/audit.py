"""Admin activity log: who changed what, and when, from /admin and the CLI."""
from flask import has_request_context
from flask_login import current_user

from app import db
from app.models import AdminAction

CLI_ACTOR = "Command line"


def record(action, summary, actor=None):
    """Add an entry. `actor` defaults to the logged-in user; outside a request
    (the flask CLI) it's recorded as "Command line"."""
    if actor is None and has_request_context() and current_user.is_authenticated:
        actor = current_user
    db.session.add(
        AdminAction(
            actor_id=actor.id if actor else None,
            actor_name=actor.name if actor else CLI_ACTOR,
            action=action,
            summary=summary[:500],
        )
    )
    db.session.commit()


def recent(limit=100):
    return AdminAction.query.order_by(AdminAction.created_at.desc(), AdminAction.id.desc()).limit(limit).all()
