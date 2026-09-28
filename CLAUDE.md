# Barber on George Check-In

Walk-in check-in and queue system for Barber on George, a local barber shop with three locations in Tasmania (Launceston, Kings Meadows, Youngtown). It replaces the paper sign-in pad. See [README.md](README.md) for the full user-facing docs, Docker setup, and VPS deployment.

## What it does

Each shop runs four kinds of screen, all kept in sync live over Socket.IO:

| Screen | Route | Who uses it | Auth |
|---|---|---|---|
| Kiosk | `/kiosk/<slug>/<kiosk_token>` | Customers on the shop tablet: enter name, optionally pick an on-duty barber | Bearer token in URL |
| Display | `/display/<slug>/<display_token>` | TV in the shop: read-only "in the chair" and "waiting" lists | Bearer token in URL |
| Staff | `/staff/<slug>` | Barbers (phone or tablet): call next customer, mark done, remove no-shows | Flask-Login |
| Admin | `/admin/`, `/admin/metrics` | Shop owner: manage locations, barber logins, device links, timezone, view charts | Flask-Login + `is_admin` |

Customer flow: kiosk check-in creates a `QueueEntry` (`waiting`), a barber calls them (`in_progress`), then completes (`done`) or removes them as a no-show (`cancelled`).

## Stack

- Python 3.12, Flask app factory (`create_app` in [app/__init__.py](app/__init__.py)), one blueprint per screen
- Flask-SQLAlchemy + Flask-Migrate (Alembic migrations in [migrations/](migrations/)), PostgreSQL 16 in production
- Flask-SocketIO in **threading** mode (`simple-websocket`, no eventlet/gevent), socket path `/updates`
- Flask-Login for barber/admin sessions
- Server-rendered Jinja templates and vanilla JS in [app/static/js/](app/static/js/). No Node, no frontend build step.
- Docker Compose (app on Gunicorn + Postgres). Gunicorn must stay at **one worker** (`-k gthread -w 1 --threads 8`) because Socket.IO has no message queue to share broadcasts across processes.

## Code map

- [app/models.py](app/models.py): `Location`, `Barber` (the login model, also admins), `QueueEntry`, `Setting` (key/value, currently only `timezone`)
- [app/sockets.py](app/sockets.py): `queue_state` / `broadcast_queue` and `on_duty_state` / `broadcast_barbers`, the `join` handler that gates room access, and the in-memory registry of connected kiosk/TV screens (`device_status`, `disconnect_devices`)
- [app/audit.py](app/audit.py): admin activity log (`audit.record(action, summary)`), shown on the admin Activity tab
- [app/kiosk.py](app/kiosk.py), [app/display.py](app/display.py): token-protected device pages
- [app/staff.py](app/staff.py): location picker, dashboard, call/complete/remove actions, on-duty tracking
- [app/admin.py](app/admin.py): locations, barbers, password resets, token regeneration, settings
- [app/metrics.py](app/metrics.py): admin charts (cuts per day/barber/location, busiest-times heatmap, wait and service times) and the visits CSV export (`/admin/metrics/visits.csv`). PDF is the browser's print of the metrics page (print styles at the end of `brand.css`). Export values go through `_csv_safe` because customer names come from the public kiosk.
- [app/auth.py](app/auth.py): login, logout, forced password change
- [app/authz.py](app/authz.py): `admin_required` decorator
- [app/settings.py](app/settings.py): shop timezone (default `Australia/Hobart`), used by metrics for day/hour bucketing
- [app/cli.py](app/cli.py): `flask bootstrap` (first-run: creates the 3 locations and an `admin` login), `flask seed`, and `flask reset-admin-password` (lockout recovery)
- [docker/entrypoint.sh](docker/entrypoint.sh): generates/persists `SECRET_KEY`, waits for Postgres, runs `flask db upgrade` then `flask bootstrap`

## Key concepts and gotchas

- **Device tokens are the access control** for kiosk and display. There is nobody to log in on that hardware, so each `Location` has a random `kiosk_token` and `display_token` in the URL. Compare them with `secrets.compare_digest`. Admins can regenerate them, which instantly breaks the old link. The Socket.IO `join` handler enforces the same rule (valid display/kiosk token or an authenticated session).
- **Any state change must broadcast.** After committing a queue change call `broadcast_queue(location)`; after an on-duty change call `broadcast_barbers(location)`. Each location has three rooms (helpers in `app/sockets.py`): `location-<slug>` (every screen, barber roster), `location-<slug>-staff` (queue with full names) and `location-<slug>-display` (queue with names shortened by `shorten_name`, "Jordan S."). The kiosk joins only the first. Never send full customer names to the display room.
- **Default vs on-duty location.** `Barber.default_location_id` only pre-selects the login picker. `on_duty_location_id` is where they are actually working (set on reaching a dashboard, cleared on logout) and drives the kiosk's preferred-barber list. Any barber can work any location. Barbers with `show_on_kiosk=False` (set by an admin) or `on_break=True` (set by the barber from their dashboard, cleared by `clear_on_duty`) can work the queue but don't appear on the kiosk; use `kiosk_barbers()` in [app/sockets.py](app/sockets.py) as the single source for that list.
- **Forced password change.** `must_change_password` is set for new accounts and admin resets; a `before_request` hook in [app/__init__.py](app/__init__.py) redirects those users to `/change-password`.
- **Logins are server-side sessions** ([app/login_sessions.py](app/login_sessions.py)). Each login gets a `LoginSession` row, and the signed Flask cookie only carries its random token. `load_user` rejects the request unless the row exists, has been active within `PERMANENT_SESSION_LIFETIME` (12h idle), and the barber is active. Log people in with `start_session()` (never `login_user` directly) and end sessions with `end_current_session()` / `end_all_sessions()`. Password resets, deactivation and admin "Log Out" all call `end_all_sessions`. Admin "Log In" (`put_barber_on_duty`) only sets `on_duty_location_id` and creates no session, so that barber stays on the kiosk until someone logs them out; nothing expires it.
- **CSRF (Flask-WTF) covers every POST.** Any new `<form method="post">` needs `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` (a test scans all templates for this). JS-built forms read the token from `<meta name="csrf-token">` in `base.html` (see `staff.js`). Logout is POST-only. `TestConfig` disables CSRF; [tests/test_csrf.py](tests/test_csrf.py) turns it back on.
- **Login rate limiting** is in [app/login_throttle.py](app/login_throttle.py): failures are stored in `login_attempts`, and a login is refused (429) once the username has 5 or the IP has 20 failures within 15 minutes. Limits come from `LOGIN_*` config. Set `BEHIND_PROXY=true` behind a reverse proxy (enables `ProxyFix`) or every visitor shares the proxy's IP.
- **Log every admin action.** Any new admin (or CLI) action that changes something should call `audit.record("thing.verb", "Plain-English summary")` after it succeeds, and not when it's refused. [tests/test_audit.py](tests/test_audit.py) checks the wording.
- **Screen connection status** comes from `_device_connections` in `app/sockets.py` (Socket.IO sid to location and kiosk/display), which is only correct because the app runs as one process. `Location.kiosk_last_seen_at` / `display_last_seen_at` record the last connect or disconnect. Anything that invalidates a device link must call `disconnect_devices()`, or screens on the old link keep receiving live updates.
- **App version and auto-reload.** `compute_app_version()` hashes everything under `app/` at startup. It's added as `?v=` to every static URL and returned as the Socket.IO `join` acknowledgement. Kiosk, display and staff pages pass that ack to `checkAppVersion` ([app/static/js/app-version.js](app/static/js/app-version.js)) and reload when it differs from `window.APP_VERSION`. Any new long-running screen should do the same.
- `SESSION_COOKIE_SECURE` defaults to true, so plain-HTTP deployments must set it to false in `.env`.
- The test `app` fixture holds one app context for the whole test, so [tests/conftest.py](tests/conftest.py) clears Flask-Login's `g._login_user` and Flask-WTF's `g.csrf_token` before each request. Multi-device tests use separate `app.test_client()` instances.
- Timestamps are stored timezone-aware in UTC (`utcnow()` in models); convert with `get_timezone()` for display and metrics.
- `pytest.ini` turns every warning into a test failure. Fix new warnings at the source; only add an `ignore::` filter for one you can't fix.
- Schema changes need an Alembic migration (`flask db migrate -m "..."`), since production runs `flask db upgrade` on every start.

## Running and testing

```bash
docker compose up -d --build                   # app on http://localhost:8000
docker compose logs app | grep "Admin login"   # first-run admin password
docker compose exec app python -m pytest       # tests
```

Tests in [tests/](tests/) use `config.TestConfig` with in-memory SQLite, so they never touch Postgres. Fixtures in [tests/conftest.py](tests/conftest.py) provide `app`, `client`, `locations`, and `barber`.

For local dev without Docker: set `DATABASE_URL`, then `python wsgi.py` (port 5000, debug).

## Future work

Suggested features not built yet are in [ROADMAP.md](ROADMAP.md). Check it before proposing new features.
