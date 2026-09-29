from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import audit, db
from app.models import MIN_PASSWORD_LENGTH, Barber
from app.login_sessions import end_all_sessions, end_current_session, start_session
from app.login_throttle import clear_failures, client_ip, lockout_minutes, record_failure
from app.staff import clear_on_duty

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("staff.landing"))

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
