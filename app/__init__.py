from flask import Flask, flash, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFError, CSRFProtect

from config import Config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to continue."
csrf = CSRFProtect()
socketio = SocketIO(async_mode="threading", path="updates")


def compute_app_version():
    """Fingerprint of the app's code, templates and static files. A deploy that
    changes any of them changes this, which tells open kiosk/TV/staff screens to
    reload (see app/static/js/app-version.js); a plain restart doesn't."""
    import hashlib
    from pathlib import Path

    digest = hashlib.sha256()
    root = Path(__file__).parent
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    if app.config.get("BEHIND_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    socketio.init_app(app)
    csrf.init_app(app)

    app.config.setdefault("APP_VERSION", compute_app_version())

    @app.url_defaults
    def version_static_urls(endpoint, values):
        # ?v=<version> on every static URL, so a deploy can't be undone by a
        # browser holding on to a cached copy of the old JS/CSS.
        if endpoint == "static":
            values.setdefault("v", app.config["APP_VERSION"])

    @app.context_processor
    def inject_app_version():
        return {"app_version": app.config["APP_VERSION"]}

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

    @app.errorhandler(CSRFError)
    def handle_csrf_error(error):
        # Usually a page left open across a restart or an expired login: send
        # them back to where they were (same site only) to try again.
        flash("That page had expired, so nothing was changed. Please try again.", "error")
        referrer = request.referrer or ""
        if referrer.startswith(request.host_url):
            return redirect(referrer)
        return redirect(url_for("index"))

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

        # Same as /login: someone already logged in goes straight to their queue.
        if current_user.is_authenticated:
            return redirect(url_for("staff.landing"))
        return render_template("index.html")

    return app
