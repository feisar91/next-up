from flask import Flask, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_socketio import SocketIO

from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
socketio = SocketIO(async_mode="threading", path="updates")


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    socketio.init_app(app)

    from app.login_sessions import load_user

    login_manager.user_loader(load_user)

    from app.auth import auth_bp
    from app.kiosk import kiosk_bp
    from app.display import display_bp
    from app.staff import staff_bp
    from app.admin import admin_bp
    from app.metrics import metrics_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(kiosk_bp)
    app.register_blueprint(display_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(metrics_bp)

    from app import sockets  # noqa: F401  registers socketio event handlers
    from app.cli import register_cli

    register_cli(app)

    PASSWORD_CHANGE_EXEMPT_ENDPOINTS = {"auth.change_password", "auth.logout", "static"}

    @app.before_request
    def enforce_password_change():
        if not current_user.is_authenticated or not current_user.must_change_password:
            return None
        if request.endpoint in PASSWORD_CHANGE_EXEMPT_ENDPOINTS:
            return None
        return redirect(url_for("auth.change_password"))

    @app.template_filter("local_time")
    def local_time(value):
        """Format a UTC timestamp in the shop timezone: '3:05 pm' today, else '24 Sep, 3:05 pm'."""
        from datetime import datetime, timezone

        from app.settings import get_timezone

        if value.tzinfo is None:  # SQLite (tests) hands back naive UTC datetimes
            value = value.replace(tzinfo=timezone.utc)
        tz = get_timezone()
        local = value.astimezone(tz)
        time_text = f"{local.hour % 12 or 12}:{local:%M} {'am' if local.hour < 12 else 'pm'}"
        if local.date() == datetime.now(tz).date():
            return time_text
        return f"{local.day} {local:%b}, {time_text}"

    @app.route("/")
    def index():
        from flask import render_template

        return render_template("index.html")

    return app
