import secrets
from datetime import datetime, timezone

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from app import db

MIN_PASSWORD_LENGTH = 8

# The longest text each of these columns holds. PostgreSQL refuses anything longer
# with an error (SQLite, used by the tests, doesn't check), so the forms that fill
# them check these too. Templates get them as `max_lengths`.
MAX_LENGTHS = {
    "customer_name": 120,
    "barber_name": 120,
    "username": 80,
    "location_name": 120,
    "location_slug": 120,
    "location_address": 255,
}


def length_error(label, value, field):
    """The message to show if `value` is too long for its column, else None."""
    limit = MAX_LENGTHS[field]
    return f"Keep the {label} to {limit} characters or fewer." if len(value) > limit else None


def utcnow():
    return datetime.now(timezone.utc)


def as_utc(value):
    """SQLite (tests) hands timestamps back without tzinfo; they're stored as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def generate_token():
    return secrets.token_urlsafe(24)


def token_matches(given, expected):
    """Whether a kiosk or TV token from a link or a socket message is the right one,
    compared in constant time. compare_digest raises on text that isn't ASCII (or
    isn't text), which only a made-up link would send, so that's just a mismatch."""
    return isinstance(given, str) and given.isascii() and secrets.compare_digest(given, expected)


class Location(db.Model):
    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(MAX_LENGTHS["location_name"]), nullable=False)
    slug = db.Column(db.String(MAX_LENGTHS["location_slug"]), nullable=False, unique=True)
    address = db.Column(db.String(MAX_LENGTHS["location_address"]))
    active = db.Column(db.Boolean, nullable=False, default=True)
    # While true the kiosk refuses new check-ins (enforced server-side, not just
    # hidden). Set by a barber from the staff dashboard, or by the opening-hours
    # schedule when auto_hours is on (see app/opening_hours.py).
    closed = db.Column(db.Boolean, nullable=False, default=False)
    # Open and close on the weekly schedule (opening_hours + special_hours). Off
    # means the store is only opened and closed by hand.
    auto_hours = db.Column(db.Boolean, nullable=False, default=False)
    # Stop new check-ins this many minutes before the scheduled closing time.
    checkin_cutoff_minutes = db.Column(db.Integer, nullable=False, default=0)
    # A barber's manual Open/Close that disagrees with the schedule holds until
    # this time (the next scheduled change, or midnight at the latest).
    manual_until = db.Column(db.DateTime(timezone=True), nullable=True)
    # A line of text for the TV and kiosk, e.g. "EFTPOS is down - cash only today",
    # shown until announcement_until (the local midnight after it was set). See
    # app/announcements.py.
    announcement = db.Column(db.String(140), nullable=True)
    announcement_until = db.Column(db.DateTime(timezone=True), nullable=True)

    # Bearer secrets for the unattended kiosk tablet / TV display at this
    # location - there's no human to log in on that hardware, so possession
    # of the URL (bookmarked once on the device) is the access control.
    kiosk_token = db.Column(db.String(64), nullable=False, unique=True, default=generate_token)
    display_token = db.Column(db.String(64), nullable=False, unique=True, default=generate_token)
    # When a kiosk / TV screen last connected or disconnected (see app/sockets.py),
    # for the "Offline since ..." status on the admin Device Links tab.
    kiosk_last_seen_at = db.Column(db.DateTime(timezone=True), nullable=True)
    display_last_seen_at = db.Column(db.DateTime(timezone=True), nullable=True)

    barbers = db.relationship(
        "Barber", back_populates="default_location", foreign_keys="Barber.default_location_id"
    )
    queue_entries = db.relationship("QueueEntry", back_populates="location")
    # Deleted along with the location by the ORM (not left to ON DELETE CASCADE,
    # which SQLite only enforces with a pragma).
    opening_hours = db.relationship("OpeningHours", back_populates="location", cascade="all, delete-orphan")
    special_hours = db.relationship(
        "SpecialHours", back_populates="location", cascade="all, delete-orphan", order_by="SpecialHours.date"
    )

    def regenerate_kiosk_token(self):
        self.kiosk_token = generate_token()

    def regenerate_display_token(self):
        self.display_token = generate_token()

    def __repr__(self):
        return f"<Location {self.slug}>"


class OpeningHours(db.Model):
    """A location's regular hours for one weekday. No row means closed that day."""

    __tablename__ = "opening_hours"
    __table_args__ = (db.UniqueConstraint("location_id", "weekday"),)

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(
        db.Integer, db.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    weekday = db.Column(db.SmallInteger, nullable=False)  # 0 = Monday, as date.weekday()
    opens_at = db.Column(db.Time, nullable=False)
    closes_at = db.Column(db.Time, nullable=False)

    location = db.relationship("Location", back_populates="opening_hours")


class SpecialHours(db.Model):
    """One date whose hours differ from the weekly schedule, e.g. a public holiday.
    With no opens_at/closes_at the location is closed all day."""

    __tablename__ = "special_hours"
    __table_args__ = (db.UniqueConstraint("location_id", "date"),)

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(
        db.Integer, db.ForeignKey("locations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date = db.Column(db.Date, nullable=False)
    opens_at = db.Column(db.Time, nullable=True)
    closes_at = db.Column(db.Time, nullable=True)
    note = db.Column(db.String(120))

    location = db.relationship("Location", back_populates="special_hours")

    @property
    def closed_all_day(self):
        return self.opens_at is None


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
    name = db.Column(db.String(MAX_LENGTHS["barber_name"]), nullable=False)
    username = db.Column(db.String(MAX_LENGTHS["username"]), nullable=False, unique=True)
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
    # Set by the barber from their staff dashboard ("Go on break"): off the kiosk,
    # still on duty. Separate from show_on_kiosk so a barber can't undo an admin's
    # choice, and cleared when they go off duty so nobody logs in still on break.
    on_break = db.Column(db.Boolean, nullable=False, default=False)
    # When they went on duty at on_duty_location_id. A barber with no live login
    # session who has been on duty longer than the session lifetime is taken off
    # duty automatically (app/off_duty.py), e.g. after an admin "Log In".
    on_duty_since = db.Column(db.DateTime(timezone=True), nullable=True)

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

    def off_duty_after(self, lifetime):
        """When app/off_duty.py takes them off duty if they have no live login session."""
        return as_utc(self.on_duty_since) + lifetime if self.on_duty_since else None

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    # Usernames ignore capitals: phones often capitalise the first letter typed.

    @classmethod
    def by_username(cls, username):
        """The login with this username, whatever its capitals. Should two differ only
        in capitals (possible on installs from before this), the exact spelling wins."""
        matches = cls.query.filter(db.func.lower(cls.username) == username.lower()).all()
        exact = next((barber for barber in matches if barber.username == username), None)
        return exact or (matches[0] if len(matches) == 1 else None)

    @classmethod
    def username_taken(cls, username, ignore_id=None):
        query = cls.query.filter(db.func.lower(cls.username) == username.lower())
        if ignore_id is not None:
            query = query.filter(cls.id != ignore_id)
        return db.session.query(query.exists()).scalar()

    def __repr__(self):
        return f"<Barber {self.username}>"


def shorten_name(name):
    """First name and last initial ("Jordan Smith" -> "Jordan S."), for the shop TV
    where the whole room can read it. A single name is shown as entered."""
    parts = name.split()
    if not parts:
        return ""
    initial = next((c for c in parts[-1] if c.isalpha()), None) if len(parts) > 1 else None
    return f"{parts[0]} {initial.upper()}." if initial else parts[0]


class QueueEntry(db.Model):
    __tablename__ = "queue_entries"

    STATUS_WAITING = "waiting"
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"

    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=False)
    customer_name = db.Column(db.String(MAX_LENGTHS["customer_name"]), nullable=False)
    preferred_barber_id = db.Column(db.Integer, db.ForeignKey("barbers.id"), nullable=True)
    status = db.Column(db.String(20), nullable=False, default=STATUS_WAITING)

    checked_in_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    called_at = db.Column(db.DateTime(timezone=True), nullable=True)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    # When a barber removed them (no-show). Only used to limit how long Undo is
    # offered; metrics count cancellations by status.
    removed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    called_by_barber_id = db.Column(db.Integer, db.ForeignKey("barbers.id"), nullable=True)

    location = db.relationship("Location", back_populates="queue_entries")
    preferred_barber = db.relationship("Barber", foreign_keys=[preferred_barber_id])
    called_by = db.relationship("Barber", foreign_keys=[called_by_barber_id])

    @property
    def finished_at(self):
        """When it was completed or removed, or None if it's still in the queue."""
        if self.status == self.STATUS_DONE:
            return as_utc(self.completed_at)
        if self.status == self.STATUS_CANCELLED:
            return as_utc(self.removed_at)
        return None

    @property
    def has_chair_time(self):
        """Whether time in the chair is known. Entries closed off by the nightly
        cleanup (app/queue_cleanup.py) are marked done with completed_at equal to
        called_at, since nobody recorded when the cut actually finished."""
        return bool(self.called_at and self.completed_at and self.completed_at > self.called_at)

    def to_dict(self, short_name=False):
        return {
            "id": self.id,
            "customer_name": shorten_name(self.customer_name) if short_name else self.customer_name,
            "preferred_barber": self.preferred_barber.name if self.preferred_barber else None,
            "preferred_barber_id": self.preferred_barber_id,
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


class LoginAttempt(db.Model):
    """A failed staff login, kept for LOGIN_LOCKOUT_MINUTES to rate-limit guessing
    (see app/login_throttle.py)."""

    __tablename__ = "login_attempts"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False, index=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    attempted_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)


class AdminAction(db.Model):
    """One entry in the activity log (see app/audit.py): originally admin-only,
    now every action the app can produce - admin, barber, customer, automatic and
    CLI. Names are copied in at the time, so the log still reads correctly after
    a barber or location is renamed or deleted."""

    __tablename__ = "admin_actions"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("barbers.id", ondelete="SET NULL"), nullable=True)
    actor_name = db.Column(db.String(120), nullable=False)
    action = db.Column(db.String(64), nullable=False, index=True)
    summary = db.Column(db.String(500), nullable=False)
    # Who/what kind of actor did it - "admin", "barber", "customer", "automatic"
    # or "cli" (see app/audit.py) - the Activity tab's broadest filter.
    category = db.Column(db.String(20), nullable=False, default="admin", index=True)


class Setting(db.Model):
    """Shop-wide settings editable from /admin (key/value, one row per setting)."""

    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.String(255), nullable=False)


class BrandAsset(db.Model):
    """An uploaded branding image ("logo" or "icon"), re-encoded as PNG by
    app/branding.py. Kept in the database so a database backup includes it."""

    __tablename__ = "brand_assets"

    key = db.Column(db.String(32), primary_key=True)
    data = db.Column(db.LargeBinary, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
