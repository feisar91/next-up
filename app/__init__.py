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
# The server pings every screen every 5s and drops one that hasn't answered within
# 10s more, so a tablet that loses Wi-Fi or power (and never closes its connection)
# shows as offline within about 15s. The library default is 25s + 20s.
socketio = SocketIO(async_mode="threading", path="updates", ping_interval=5, ping_timeout=10)


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
    def inject_brand():
        from app.branding import get_brand, screen_version

        from app import demo_mode

        brand = get_brand()
        # app_version is what long-running screens compare on reconnect (see
        # app/static/js/app-version.js): code version plus branding version.
        return {
            "brand": brand,
            "app_version": screen_version(brand),
            "demo": demo_mode.DemoInfo() if demo_mode.enabled() else None,
        }

    from app.models import MAX_LENGTHS

    # For maxlength on form inputs; the server checks the same limits.
    app.jinja_env.globals["max_lengths"] = MAX_LENGTHS

    from app.login_sessions import load_user

    login_manager.user_loader(load_user)

    from app.auth import auth_bp
    from app.kiosk import kiosk_bp
    from app.display import display_bp
    from app.staff import staff_bp
    from app.admin import admin_bp
    from app.metrics import metrics_bp
    from app.branding import brand_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(kiosk_bp)
    app.register_blueprint(display_bp)
    app.register_blueprint(staff_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(metrics_bp)
    app.register_blueprint(brand_bp)

    from app import sockets  # noqa: F401  registers socketio event handlers
    from app.cli import register_cli

    register_cli(app)

    PASSWORD_CHANGE_EXEMPT_ENDPOINTS = {"auth.change_password", "auth.logout", "static"}

    @app.before_request
    def start_background_checks():
        from app.background import start_background_checks

        start_background_checks(app)

    if app.config["DEMO_MODE"]:
        from app.demo_mode import check_request

        app.before_request(check_request)

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

    @app.errorhandler(413)
    def handle_too_large(error):
        flash("That file is too big to upload.", "error")
        referrer = request.referrer or ""
        if referrer.startswith(request.host_url):
            return redirect(referrer)
        return redirect(url_for("index"))

    @app.template_filter("local_time")
    def local_time(value):
        """Format a UTC timestamp in the shop timezone: '3:05 pm' today, else '24 Sep, 3:05 pm'."""
        from datetime import datetime, timezone

        from app.opening_hours import format_clock
        from app.settings import get_timezone

        if value.tzinfo is None:  # SQLite (tests) hands back naive UTC datetimes
            value = value.replace(tzinfo=timezone.utc)
        tz = get_timezone()
        local = value.astimezone(tz)
        time_text = format_clock(local)
        if local.date() == datetime.now(tz).date():
            return time_text
        return f"{local.day} {local:%b}, {time_text}"

    @app.route("/")
    def index():
        from flask import render_template

        from app.auth import needs_first_admin

        # Same as /login: someone already logged in goes straight to their queue,
        # and a brand-new install goes to the first-run setup page.
        if current_user.is_authenticated:
            return redirect(url_for("staff.landing"))
        if needs_first_admin():
            return redirect(url_for("auth.setup"))
        # The public demo's welcome and one-click logins are on the login page.
        if app.config["DEMO_MODE"]:
            return redirect(url_for("auth.login"))
        return render_template("index.html")

    return app
