import secrets
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

MIN_PASSWORD_LENGTH = 8


def utcnow():
    return datetime.now(timezone.utc)


def generate_token():
    return secrets.token_urlsafe(24)


class Location(db.Model):
    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), nullable=False, unique=True)
    address = db.Column(db.String(255))
    active = db.Column(db.Boolean, nullable=False, default=True)

    # Bearer secrets for the unattended kiosk tablet / TV display at this
    # location - there's no human to log in on that hardware, so possession
    # of the URL (bookmarked once on the device) is the access control.
    kiosk_token = db.Column(db.String(64), nullable=False, unique=True, default=generate_token)
    display_token = db.Column(db.String(64), nullable=False, unique=True, default=generate_token)

    barbers = db.relationship(
        "Barber", back_populates="default_location", foreign_keys="Barber.default_location_id"
    )
    queue_entries = db.relationship("QueueEntry", back_populates="location")

    def regenerate_kiosk_token(self):
        self.kiosk_token = generate_token()

    def regenerate_display_token(self):
        self.display_token = generate_token()

    def __repr__(self):
        return f"<Location {self.slug}>"


class Barber(UserMixin, db.Model):
    __tablename__ = "barbers"

    id = db.Column(db.Integer, primary_key=True)
    # A barber can work a shift at any location (chosen at login) - this is just
    # the location pre-selected for them on the login-time location picker.
    default_location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)
    # The location this barber is currently working at - set when they land on a
    # location's staff dashboard, cleared on logout. This is what the kiosk's
    # preferred-barber list is drawn from, not default_location_id (which is
    # just a login-time convenience and may not reflect where they actually are).
    on_duty_location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)
    name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    # Set whenever an admin hands them a temporary password (new account or a
    # reset) - the enforce_password_change hook in app/__init__.py redirects
    # them to /change-password until they pick their own.
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)
    # When False the barber can still log in and work the queue, but never shows
    # up in the kiosk's preferred-barber list (e.g. an owner/admin login).
    show_on_kiosk = db.Column(db.Boolean, nullable=False, default=True)

    default_location = db.relationship("Location", back_populates="barbers", foreign_keys=[default_location_id])
    on_duty_location = db.relationship("Location", foreign_keys=[on_duty_location_id])
    login_sessions = db.relationship(
        "LoginSession", back_populates="barber", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def is_active(self):
        # Flask-Login refuses to log in inactive users; app/login_sessions.py also
        # rejects their existing sessions on every request.
        return self.active

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<Barber {self.username}>"


class QueueEntry(db.Model):
    __tablename__ = "queue_entries"

    STATUS_WAITING = "waiting"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    customer_name = db.Column(db.String(120), nullable=False)
    preferred_barber_id = db.Column(db.Integer, db.ForeignKey("barbers.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_WAITING)

    checked_in_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    called_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    called_by_barber_id = db.Column(db.Integer, db.ForeignKey("barbers.id"), nullable=True)

    location = db.relationship("Location", back_populates="queue_entries")
    preferred_barber = db.relationship("Barber", foreign_keys=[preferred_barber_id])
    called_by = db.relationship("Barber", foreign_keys=[called_by_barber_id])

    def to_dict(self):
        return {
            "id": self.id,
            "customer_name": self.customer_name,
            "preferred_barber": self.preferred_barber.name if self.preferred_barber else None,
            "status": self.status,
            "checked_in_at": self.checked_in_at.isoformat(),
            "called_by": self.called_by.name if self.called_by else None,
        }


class LoginSession(db.Model):
    """One logged-in browser/device. The cookie holds the raw token; only its
    SHA-256 is stored, and deleting the row logs that device out."""

    __tablename__ = "login_sessions"

    id = db.Column(db.Integer, primary_key=True)
    barber_id = db.Column(
        db.Integer, db.ForeignKey("barbers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash = db.Column(db.String(64), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    user_agent = db.Column(db.String(255))

    barber = db.relationship("Barber", back_populates="login_sessions")


class Setting(db.Model):
    """Shop-wide settings editable from /admin (key/value, one row per setting)."""

    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)
