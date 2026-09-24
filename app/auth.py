from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.models import MIN_PASSWORD_LENGTH, Barber
from app.login_sessions import end_all_sessions, end_current_session, start_session
from app.staff import clear_on_duty

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("staff.landing"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        barber = Barber.query.filter_by(username=username, active=True).first()

        if barber and barber.check_password(password):
            # start_session() starts from an empty session, so a fresh login always
            # re-picks a location - the location picker uses their default (if any)
            # to make this a one-click confirmation, not a chore.
            start_session(barber)
            return redirect(url_for("staff.landing"))

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
            flash("Password updated.", "success")
            return redirect(url_for("staff.landing"))

    return render_template("change_password.html")


@auth_bp.route("/logout")
@login_required
def logout():
    clear_on_duty(current_user)
    end_current_session()
    return redirect(url_for("auth.login"))
