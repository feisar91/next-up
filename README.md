# Next Up - Check-In System

Digital replacement for the paper sign-in pad across a barber shop's locations:

- **Kiosk** (`/kiosk/<location>/<token>`) - tablet check-in screen. Customer enters their name and optionally a preferred barber. "Add another person" checks in a group at once (up to 6, e.g. a parent with their kids): they get consecutive places, share the preferred barber, and the confirmation lists everyone's position.
- **Display** (`/display/<location>/<token>`) - read-only TV screen showing who's in the chair and who's waiting, live. Because the whole shop can read it, customers appear as first name and last initial ("Jordan S."); the staff dashboard shows full names.
- **Staff** (`/staff/<location>`) - barber login to call the next customer to the chair, mark them complete, or remove a no-show. A Complete or Remove tapped by mistake can be undone from "Recently Finished" for 10 minutes. "Go On Break" takes the barber off the kiosk's preferred-barber list without logging out (they can still call customers), and logging out ends the break. Works on a barber's phone or on the tablet.
- **Admin** (`/admin`) - admin-only screen to add locations, set their opening hours, add/edit barber logins, and get each location's Kiosk/Display links.
- **Metrics** (`/admin/metrics`) - admin-only charts for a chosen period (7/14/30/90 days): cuts per day, by barber and by location, a busiest-times heatmap (per store and combined), average time in chair per barber, preferred-barber demand, plus wait/service time stats. Days and hours use the timezone set under Admin > Settings (default `Australia/Hobart`). For the chosen period you can **Download Visits (CSV)** (one row per check-in: location, customer, preferred barber, who served them, status, times, wait and time in chair) or **Print / Save as PDF** (a print layout of the page, including every location's heatmap).

Live updates across all screens are pushed over Socket.IO - no polling, no manual refresh.

### Kiosk & Display access

The kiosk tablet and TV display run unattended with no one to log in on them, but the app is centrally hosted - so instead of being open to anyone who finds the URL, each location has its own long random `kiosk_token` / `display_token` baked into its URL (e.g. `/kiosk/mainstreet/Xy7f...`). Get the exact links for each location from `/admin/` under "Device Links", and set one as the home page/bookmark on that location's tablet and TV. If a link ever leaks, regenerate it from the same page - the old link stops working immediately. The Socket.IO layer enforces this too (a raw websocket connection can't join a location's live feed without either that location's display token or an authenticated staff session), not just the page route.

The Device Links tab shows, live, whether each shop's kiosk and TV are connected ("Online", "Offline since 3:05 pm" or "Never connected"), and warns if more than one screen is using the same link. A screen that's closed or reloading shows as offline after 10 seconds; one that loses Wi-Fi or power takes up to about 25 seconds, since the app has to notice it stopped answering. For a minute after the app restarts, a screen that hasn't reconnected yet shows as "Unknown", since a restart doesn't record which screens were connected; it changes to Online as soon as it reconnects, or to Offline when the minute is up. Regenerating a link, or removing a location, immediately disconnects any screen still open on the old link.

Each shop can show a one-line announcement on its TV and kiosk, such as "EFTPOS is down - cash only today". Barbers set it from the Announcement card on their dashboard, and admins from the Locations tab. It appears on the screens straight away and clears itself at midnight, so it's for today's news: a regular promotion needs setting each day.

While a store is open, the staff dashboard's store card says "The kiosk isn't connected" if that shop's kiosk has been off for more than 10 seconds (a kiosk briefly drops off on every check-in, so shorter gaps don't count). It updates live and clears as soon as the kiosk is back. A location whose kiosk has never connected gets no warning.

After a deploy, open kiosk, TV and staff dashboard screens reload themselves when their live connection comes back, so nobody has to refresh the shop devices by hand. A kiosk waits until nobody is partway through typing a name, and clears a name left untouched for a minute (someone who walked off), so it's neither shown to the next customer nor holding up the reload.

If a kiosk, TV or staff dashboard loses its live connection for more than a few seconds, a red "Connection lost" banner shows across the top until it reconnects. The kiosk also holds its Check In button while the banner is up, so a customer can't send a check-in that would fail. On the staff dashboard it tells barbers their queue isn't updating.

The kiosk and TV pages ask the browser to keep the screen on (the Screen Wake Lock API), so a tablet or TV browser doesn't dim or lock while the page is open, even if its own sleep setting would. Browsers only allow this over HTTPS, and older ones don't support it, so on those set the device's own sleep timer to never. Staff pages don't do this, so barbers' phones still sleep normally.

Customers still waiting or in the chair from a previous day are cleared a few minutes after midnight (`QUEUE_CLEANUP_CHECK_SECONDS`, default 300): waiting ones are counted as no-shows and ones in the chair as done, without a time in the chair. The Activity tab notes each clear.

### Home-screen apps

Barbers can add the staff pages to their phone's home screen, and each shop's tablet can do the same with its kiosk, so they open full-screen from an icon with no browser bar. Open the page (the kiosk from its secret link), then use **Add to Home Screen**: Safari's Share menu on iPhone/iPad, or Chrome's menu on Android. The kiosk opens truly full-screen on Android; iPads still show the status bar. On Android, Chrome only opens it as an app over HTTPS; over plain HTTP the icon opens a normal browser tab. The installed app has its own login on iPhones (it doesn't share Safari's), so barbers log in once inside it.

Each kiosk's app remembers its secret link, so after regenerating that link, delete the icon and add it again from the new link.

### Opening hours

A store can be closed to new check-ins by hand ("Close Store" on the staff dashboard), or automatically on a schedule. Under Admin > Locations > **Opening Hours**, set each weekday's hours, how many minutes before closing to stop check-ins, and dates that differ (public holidays, a short Christmas Eve), then tick "Open and close automatically". The store then opens and closes on time (checked every 30 seconds, `OPENING_HOURS_CHECK_SECONDS`), each change is noted on the Activity tab, and a closed kiosk says when it's back ("Back Tuesday at 9:00 am"). Closing only stops new check-ins; customers already waiting stay in the queue.

Barbers can still open or close by hand. If that goes against the schedule (closing early, opening late for a walk-in), it holds until the next scheduled opening or closing, or midnight at the latest, so a store opened late isn't left taking check-ins overnight. Saving the opening hours hands control straight back to the schedule.

### Security

- Every form is CSRF-protected (Flask-WTF), and logging out is a POST.
- Staff logins are rate limited: after 5 failed attempts for a username, or 20 from one IP address, within 15 minutes, further attempts are refused until the window passes. All three numbers can be changed in `.env` (see `.env.example`).
- The admin **Activity** tab lists every action the app can produce - admin changes, barber actions (log in/out, choosing or switching shop, call/complete/remove/undo, break, open/close, changing their own profile or password), customer check-ins, security events (failed logins and lockouts, with the username tried and the IP address), and automatic/command-line changes: who did it, when, and what (the latest 200 matching entries). Filterable by type (admin/barber/customer/automatic/command line/security), event, who, and date range.
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

- **Location** - one of the 3 (soon more) shops; has a URL slug plus a `kiosk_token` and `display_token` (regenerable from `/admin/`). `closed` stops new check-ins; `auto_hours` sets it from the location's **OpeningHours** (one row per open weekday) and **SpecialHours** (one row per date that differs, with no times meaning closed all day), and `manual_until` is how long a barber's manual Open/Close holds against that schedule.
- **Barber** - an individual staff login. Any active barber can work any location (chosen at login); `default_location_id` just pre-selects one on the picker. `is_admin` grants access to `/admin` and `/admin/metrics`. The "On Kiosk" switch in the admin barber table (`show_on_kiosk`) keeps them off the kiosk's preferred-barber list, e.g. an admin hiding themselves for a while. Barbers can't change it themselves; their dashboard's break button is separate (`on_break`), and the admin barber table shows "on break" next to their location. Everyone can change their own display name from their Profile page.
- **QueueEntry** - one customer's place in a location's queue: `waiting → in_progress → done`, or `cancelled` if removed as a no-show.
- **LoginSession** - one logged-in device for a barber. Logins expire after 12 hours without activity (`SESSION_LIFETIME_HOURS`). The admin barber table shows who is logged in and on duty where. Its Log Out button ends a barber's sessions and takes them off duty. For a barber who isn't logged in, Log In puts them on duty at a chosen shop without a device (e.g. a forgotten phone), so they show on that kiosk until logged out, or until 12 hours (`SESSION_LIFETIME_HOURS`) have passed with no device login, when the app takes them off duty automatically and notes it on the Activity tab. The same applies to a barber whose phone login expired without them logging out. Logging out, a password reset, or deactivation also ends sessions.
- **AdminAction** - one entry in the activity log (originally admin-only, now every action - see `app/audit.py`). Stores the actor's name, a category (admin/barber/customer/automatic/cli/security) and a plain-English summary, so entries still read correctly after someone is renamed or deleted.
- **Setting** - shop-wide key/value settings edited from `/admin/` (currently just `timezone`).

Ideas for future work are listed in [ROADMAP.md](ROADMAP.md).
