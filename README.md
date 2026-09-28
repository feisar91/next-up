# Next Up - Check-In System

Digital replacement for the paper sign-in pad across a barber shop's locations:

- **Kiosk** (`/kiosk/<location>/<token>`) - tablet check-in screen. Customer enters their name and optionally a preferred barber.
- **Display** (`/display/<location>/<token>`) - read-only TV screen showing who's in the chair and who's waiting, live. Because the whole shop can read it, customers appear as first name and last initial ("Jordan S."); the staff dashboard shows full names.
- **Staff** (`/staff/<location>`) - barber login to call the next customer to the chair, mark them complete, or remove a no-show. Works on a barber's phone or on the tablet.
- **Admin** (`/admin`) - admin-only screen to add locations, add/edit barber logins, and get each location's Kiosk/Display links.
- **Metrics** (`/admin/metrics`) - admin-only charts for a chosen period (7/14/30/90 days): cuts per day, by barber and by location, a busiest-times heatmap (per store and combined), average time in chair per barber, preferred-barber demand, plus wait/service time stats. Days and hours use the timezone set under Admin > Settings (default `Australia/Hobart`). For the chosen period you can **Download Visits (CSV)** (one row per check-in: location, customer, preferred barber, who served them, status, times, wait and time in chair) or **Print / Save as PDF** (a print layout of the page, including every location's heatmap).

Live updates across all screens are pushed over Socket.IO - no polling, no manual refresh.

### Kiosk & Display access

The kiosk tablet and TV display run unattended with no one to log in on them, but the app is centrally hosted - so instead of being open to anyone who finds the URL, each location has its own long random `kiosk_token` / `display_token` baked into its URL (e.g. `/kiosk/mainstreet/Xy7f...`). Get the exact links for each location from `/admin/` under "Device Links", and set one as the home page/bookmark on that location's tablet and TV. If a link ever leaks, regenerate it from the same page - the old link stops working immediately. The Socket.IO layer enforces this too (a raw websocket connection can't join a location's live feed without either that location's display token or an authenticated staff session), not just the page route.

The Device Links tab shows whether each shop's kiosk and TV are connected right now ("Online", "Offline since 3:05 pm" or "Never connected"), and warns if more than one screen is using the same link. Regenerating a link, or removing a location, immediately disconnects any screen still open on the old link.

After a deploy, open kiosk, TV and staff dashboard screens reload themselves when their live connection comes back, so nobody has to refresh the shop devices by hand. A kiosk waits until nobody is partway through typing a name.

### Security

- Every form is CSRF-protected (Flask-WTF), and logging out is a POST.
- Staff logins are rate limited: after 5 failed attempts for a username, or 20 from one IP address, within 15 minutes, further attempts are refused until the window passes. All three numbers can be changed in `.env` (see `.env.example`).
- The admin **Activity** tab lists every change made from the admin area or with `flask reset-admin-password`: who did it, when, and what changed (the latest 100 entries).
- If the app sits behind a reverse proxy, set `BEHIND_PROXY=true` so the rate limit sees visitors' real IP addresses instead of the proxy's.

## Stack

Flask + Flask-SQLAlchemy + Flask-Migrate + PostgreSQL + Flask-SocketIO (threading mode, via `simple-websocket` - no eventlet/gevent required) + Flask-Login. Server-rendered templates, vanilla JS - no Node/frontend build step.

## Running with Docker

The whole stack - the Flask app (served by Gunicorn) and Postgres - runs via Docker Compose. Requires Docker with the Compose plugin. No configuration is needed for a first run:

```bash
docker compose up -d --build
docker compose logs app | grep "Admin login"    # shows the generated admin password
```

The app is then on `http://localhost:8000`. On every start the app container waits for Postgres and runs `flask db upgrade`. On the **first** start (when no logins exist yet) it also creates the 3 locations and an `admin` login with a random password, printed once in the logs. You'll be made to change that password when you first log in. If no `SECRET_KEY` is provided, one is generated on first start and kept in the `checkin_app_data` volume.

To override any defaults (port, Postgres password, a known admin password, your own `SECRET_KEY`), copy `.env.example` to `.env` and uncomment what you need.

Visit `http://localhost:8000` for the public landing page, or:
- `http://localhost:8000/staff/mainstreet` (log in as `admin` / the password from the logs)
- `http://localhost:8000/admin/` to add barber accounts, and to get each location's Kiosk/Display links (with their tokens) to open on the tablet/TV

Useful commands:

```bash
docker compose logs -f app                 # app logs
docker compose exec app flask <command>    # run any Flask CLI command (e.g. flask seed)
docker compose exec app flask reset-admin-password   # locked out? prints a new temporary admin password
docker compose up -d --build               # rebuild + restart after pulling code changes
docker compose down                        # stop (data is kept in the checkin_pg_data volume)
```

Postgres isn't published to the host; it's only reachable by the app container. Its data lives in the `checkin_pg_data` volume. Note that `POSTGRES_USER`/`POSTGRES_PASSWORD` only take effect when that volume is first created - changing them later won't change the password on an existing database.

### Tests

```bash
docker compose exec app python -m pytest
```

Tests run against in-memory SQLite (see `config.TestConfig`), so they don't touch the Postgres data. GitHub Actions runs the same suite on every push and pull request (`.github/workflows/tests.yml`). Any warning during a test run counts as a failure (`pytest.ini`), so deprecations get fixed as they appear.

## Deploying to a VPS

1. Install Docker, clone the repo, optionally create `.env` (see `.env.example` - at least set `POSTGRES_PASSWORD` and `APP_PORT`), and `docker compose up -d --build`. `restart: unless-stopped` keeps both containers running across reboots - no systemd unit needed.
2. The container runs Gunicorn with a single worker and multiple threads (`-k gthread -w 1 --threads 8`). Keep it at one worker unless you introduce a message queue (e.g. Redis) for Socket.IO to coordinate broadcasts across multiple worker processes - with a single small VPS serving 3 shops, one process is plenty.
3. Login cookies are marked `Secure` (HTTPS only) by default. If you serve the app over plain HTTP, set `SESSION_COOKIE_SECURE=false` in `.env`, or barbers won't be able to stay logged in.
4. Put **Nginx** (or another reverse proxy handling TLS) in front of the app port, with WebSocket upgrade headers passed through. Consider setting `APP_PORT=127.0.0.1:8000` in `.env` so the app is only reachable through the proxy, and set `BEHIND_PROXY=true` so login rate limiting sees real client IPs.
   ```nginx
   location / {
       proxy_pass http://127.0.0.1:8000;
       proxy_http_version 1.1;
       proxy_set_header Upgrade $http_upgrade;
       proxy_set_header Connection "upgrade";
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
   }
   ```

Point each shop's tablet browser at its Kiosk link and each TV's browser (or a cheap streaming stick in kiosk-browser mode) at its Display link - both from `/admin/`. Barbers log in to `/staff/<slug>` from their own phones and pick a location each time (a default can be set per barber for a one-click continue).

## Data model

- **Location** - one of the 3 (soon more) shops; has a URL slug plus a `kiosk_token` and `display_token` (regenerable from `/admin/`).
- **Barber** - an individual staff login. Any active barber can work any location (chosen at login); `default_location_id` just pre-selects one on the picker. `is_admin` grants access to `/admin` and `/admin/metrics`. The "On Kiosk" switch in the admin barber table (`show_on_kiosk`) keeps them off the kiosk's preferred-barber list, e.g. an admin hiding themselves for a while. Everyone can change their own display name from their Profile page.
- **QueueEntry** - one customer's place in a location's queue: `waiting → in_progress → done`, or `cancelled` if removed as a no-show.
- **LoginSession** - one logged-in device for a barber. Logins expire after 12 hours without activity (`SESSION_LIFETIME_HOURS`). The admin barber table shows who is logged in and on duty where. Its Log Out button ends a barber's sessions and takes them off duty. For a barber who isn't logged in, Log In puts them on duty at a chosen shop without a device (e.g. a forgotten phone), so they show on that kiosk until logged out. Logging out, a password reset, or deactivation also ends sessions.
- **AdminAction** - one entry in the admin activity log. Stores the admin's name and a plain-English summary, so entries still read correctly after someone is renamed or deleted.
- **Setting** - shop-wide key/value settings edited from `/admin/` (currently just `timezone`).

Ideas for future work are listed in [ROADMAP.md](ROADMAP.md).
