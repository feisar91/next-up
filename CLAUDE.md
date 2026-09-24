# Next Up Check-In

Walk-in check-in and queue system for a barber shop with several locations. It replaces the paper sign-in pad. See [README.md](README.md) for the full user-facing docs, Docker setup, and VPS deployment.

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
- [app/sockets.py](app/sockets.py): `queue_state` / `broadcast_queue` and `on_duty_state` / `broadcast_barbers`, plus the `join` handler that gates room access
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
- **Any state change must broadcast.** After committing a queue change call `broadcast_queue(location)`; after an on-duty change call `broadcast_barbers(location)`. Rooms are named `location-<slug>`.
- **Default vs on-duty location.** `Barber.default_location_id` only pre-selects the login picker. `on_duty_location_id` is where they are actually working (set on reaching a dashboard, cleared on logout) and drives the kiosk's preferred-barber list. Any barber can work any location. Barbers with `show_on_kiosk=False` can work the queue but never appear on the kiosk; use `kiosk_barbers()` in [app/sockets.py](app/sockets.py) as the single source for that list.
- **Forced password change.** `must_change_password` is set for new accounts and admin resets; a `before_request` hook in [app/__init__.py](app/__init__.py) redirects those users to `/change-password`.
- **Logins are server-side sessions** ([app/login_sessions.py](app/login_sessions.py)). Each login gets a `LoginSession` row, and the signed Flask cookie only carries its random token. `load_user` rejects the request unless the row exists, has been active within `PERMANENT_SESSION_LIFETIME` (12h idle), and the barber is active. Log people in with `start_session()` (never `login_user` directly) and end sessions with `end_current_session()` / `end_all_sessions()`. Password resets, deactivation and admin "Log Out" all call `end_all_sessions`. Admin "Log In" (`put_barber_on_duty`) only sets `on_duty_location_id` and creates no session, so that barber stays on the kiosk until someone logs them out; nothing expires it.
- `SESSION_COOKIE_SECURE` defaults to true, so plain-HTTP deployments must set it to false in `.env`.
- The test `app` fixture holds one app context for the whole test, so [tests/conftest.py](tests/conftest.py) clears Flask-Login's `g._login_user` before each request. Multi-device tests use separate `app.test_client()` instances.
- Timestamps are stored timezone-aware in UTC (`utcnow()` in models); convert with `get_timezone()` for display and metrics.
- Schema changes need an Alembic migration (`flask db migrate -m "..."`), since production runs `flask db upgrade` on every start.

## Running and testing

```bash
docker compose up -d --build                   # app on http://localhost:8000
docker compose logs app | grep "Admin login"   # first-run admin password
docker compose exec app python -m pytest       # tests
```

Tests in [tests/](tests/) use `config.TestConfig` with in-memory SQLite, so they never touch Postgres. Fixtures in [tests/conftest.py](tests/conftest.py) provide `app`, `client`, `locations`, and `barber`.

For local dev without Docker: set `DATABASE_URL`, then `python wsgi.py` (port 5000, debug).
