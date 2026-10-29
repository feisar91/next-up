from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app import audit, db
from app.models import MIN_PASSWORD_LENGTH, Barber, Setting
from app.login_sessions import end_all_sessions, end_current_session, start_session
from app.login_throttle import clear_failures, client_ip, lockout_minutes, record_failure
from app.staff import clear_on_duty

auth_bp = Blueprint("auth", __name__)

# Inserted in the same transaction as the first admin login. Its primary key means
# only one of two setup forms submitted at the same moment can succeed.
SETUP_CLAIM_KEY = "first_admin_created"


def needs_first_admin():
    """A brand-new install: nobody can log in until the owner creates the first
    admin login on /setup (or `flask bootstrap` makes one from ADMIN_PASSWORD)."""
    return Barber.query.first() is None


@auth_bp.route("/setup", methods=["GET", "POST"])
def setup():
    """First-run page where the owner picks the admin username and password.
    Open to whoever gets there first, and only until any login exists."""
    if not needs_first_admin():
        return redirect(url_for("auth.login"))

    form = {"name": "", "username": ""}
    if request.method == "POST":
        name = " ".join(request.form.get("name", "").split())
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        form = {"name": name, "username": username}

        if not name or not username:
            flash("Enter your name and a username.", "error")
        elif len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            admin = Barber(name=name, username=username, is_admin=True)
            admin.set_password(password)
            db.session.add_all([admin, Setting(key=SETUP_CLAIM_KEY, value=username)])
            try:
                db.session.commit()
            except IntegrityError:
                # Someone else finished setup a moment earlier.
                db.session.rollback()
                flash("Setup has already been completed. Log in instead.", "error")
                return redirect(url_for("auth.login"))
            start_session(admin)
            audit.record("setup.first_admin", f"Created the first admin login, {name} ({username})", actor=admin)
            flash("Welcome! Your admin login is ready. Let's set up your shop.", "success")
            return redirect(url_for("admin.overview"))

    return render_template("setup.html", form=form, min_password_length=MIN_PASSWORD_LENGTH)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("staff.landing"))
    if needs_first_admin():
        return redirect(url_for("auth.setup"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        wait = lockout_minutes(username)
        if wait is not None:
            flash(
                f"Too many failed log-in attempts. Try again in {wait} minute{'s' if wait != 1 else ''}.",
                "error",
            )
            return render_template("login.html", username=username), 429

        barber = Barber.query.filter_by(username=username, active=True).first()

        if barber and barber.check_password(password):
            clear_failures(username)
            # start_session() starts from an empty session, so a fresh login always
            # re-picks a location - the location picker uses their default (if any)
            # to make this a one-click confirmation, not a chore.
            start_session(barber)
            audit.record("session.login", f"{barber.name} logged in", actor=barber, category=audit.CATEGORY_BARBER)
            return redirect(url_for("staff.landing"))

        record_failure(username)
        # The typed username is shown in quotes because it's unverified input,
        # and may not be an account at all.
        attempted = f"'{username[:80]}' from {client_ip()}"
        audit.record(
            "session.login_failed",
            f"Failed login for {attempted}",
            category=audit.CATEGORY_SECURITY,
            actor_name=audit.UNKNOWN_ACTOR,
        )
        # Logged once, as the lockout starts: attempts refused while locked out
        # aren't logged, so a brute-force run can't flood the activity log.
        wait = lockout_minutes(username)
        if wait is not None:
            audit.record(
                "session.lockout",
                f"Locked out logins for {attempted} for {wait} minute{'s' if wait != 1 else ''} "
                "after too many failed attempts",
                category=audit.CATEGORY_SECURITY,
                actor_name=audit.UNKNOWN_ACTOR,
            )
        flash("Incorrect username or password.", "error")

    return render_template("login.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < MIN_PASSWORD_LENGTH:
            flash(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.", "error")
        elif password != confirm_password:
            flash("Passwords do not match.", "error")
        else:
            current_user.set_password(password)
            current_user.must_change_password = False
            db.session.commit()
            end_all_sessions(current_user, keep_current=True)
            audit.record(
                "barber.change_own_password",
                f"{current_user.name} set a new password after being asked to change it",
                category=audit.CATEGORY_BARBER,
            )
            flash("Password updated.", "success")
            return redirect(url_for("staff.landing"))

    return render_template("change_password.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    location = current_user.on_duty_location
    summary = f"{current_user.name} logged out"
    if location:
        summary += f" and went off duty at {location.name}"
    audit.record("session.logout", summary, category=audit.CATEGORY_BARBER)
    clear_on_duty(current_user)
    end_current_session()
    return redirect(url_for("auth.login"))
