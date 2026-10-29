---
title: How it works
lead: The technical side of Next Up, for anyone hosting it or reading the code. Shop owners and barbers don't need any of this.
next: { title: "Development and releases", url: /technical/development/ }
---

## Stack

A Python 3.12 [Flask](https://flask.palletsprojects.com/) app with PostgreSQL 16, Flask-SQLAlchemy and Flask-Migrate (Alembic) for the database, Flask-Login for staff logins, and Flask-SocketIO for live updates. Pages are rendered on the server with Jinja templates and a little plain JavaScript. There's no Node and no front-end build step.

It ships as one Docker image, run by Gunicorn, alongside the official `postgres:16-alpine` image. Images are published for `linux/amd64` and `linux/arm64`.

## The screens

| Screen | Address | Who uses it | Access |
|---|---|---|---|
| Kiosk | `/kiosk/<location>/<token>` | Customers, on the tablet | Secret token in the link |
| TV | `/display/<location>/<token>` | Everyone in the shop | Secret token in the link |
| Staff | `/staff/<location>` | Barbers | Login |
| Admin | `/admin/`, `/admin/metrics` | Owners | Login with admin access |

The kiosk and TV have nobody to log in on them, so each location has a long random `kiosk_token` and `display_token`, compared in constant time. Regenerating one on the Device Links tab breaks the old link at once and disconnects any screen still open on it.

## Live updates

Every screen keeps a Socket.IO connection open (path `/updates`). Any change to the queue, the on-duty barbers, the store's open or closed state, or the announcement is pushed to the screens that need it, so nothing polls and nobody refreshes.

Each location has three rooms:

- `location-<slug>`: every screen. The barber list, open or closed state, and the announcement.
- `location-<slug>-staff`: staff screens. The queue with full names.
- `location-<slug>-display`: the TV. The queue with names shortened to "Jordan S.".

Joining a room is checked the same way as loading the page: a valid kiosk or TV token, or a logged-in staff session. A raw WebSocket connection without one gets nothing. The kiosk only joins the first room, so it never receives customer names.

### One process

The app runs as a single Gunicorn process with threads (`-k gthread -w 1 --threads 8`). Socket.IO keeps its rooms in memory, so a second worker process wouldn't see broadcasts from the first. One process comfortably serves a business with several shops. Running more would need a message queue such as Redis between them.

The record of which screens are connected (for the Device Links tab) is in memory for the same reason. After a restart a screen shows as "Unknown" until it reconnects or a minute passes.

### Screens reload themselves

At start-up the app hashes its own code, templates and static files. That version, plus a counter that changes with every branding change, is sent to each screen when it connects. A screen loaded with a different version reloads itself, so after an upgrade or a branding change nobody has to touch the shop devices. A kiosk waits until nobody is typing, and screens never reload more than once a minute.

## Background jobs

Three threads run inside the app process. They start on the first web request or screen connection, not on CLI commands.

| Job | How often | Setting | What it does |
|---|---|---|---|
| Opening hours | 30 s | `OPENING_HOURS_CHECK_SECONDS` | Opens and closes locations that follow their schedule, less the check-in cutoff. A barber's manual open or close against the schedule holds until the next scheduled change or midnight. |
| Overnight clear | 5 min | `QUEUE_CLEANUP_CHECK_SECONDS` | Clears customers left from a previous day: waiting ones become no-shows, ones in the chair become done with no time in the chair, so averages aren't skewed. Also clears expired announcements. |
| Off duty | 5 min | `OFF_DUTY_CHECK_SECONDS` | Takes barbers off the kiosk who have been on duty longer than the login lifetime with no live login, such as an admin's "Log In" for a barber without a phone. |

Each change they make is logged on the Activity tab as automatic. Setting a job's interval to `0` turns it off.

## Logins and security

- **Server-side sessions.** Each login is a row in `login_sessions`; the signed cookie only carries a random token. A login ends after 12 hours idle (`SESSION_LIFETIME_HOURS`), and password resets, deactivation and the admin "Log Out" end every session for that barber at once.
- **HTTPS-only cookies** by default (`SESSION_COOKIE_SECURE=true`). Over plain `http://` the browser drops them, and with them the CSRF token. The login and setup pages test for this in the browser and explain it.
- **CSRF protection** (Flask-WTF) on every form. Logging out is a POST.
- **Login rate limiting.** After 5 failures for a username, or 20 from one IP address, within 15 minutes, further attempts are refused (`LOGIN_MAX_FAILURES_PER_USER`, `LOGIN_MAX_FAILURES_PER_IP`, `LOGIN_LOCKOUT_MINUTES`). Behind a reverse proxy, set `BEHIND_PROXY=true` so it sees each visitor's real address.
- **First admin.** A new install has no logins. `/` and `/login` send visitors to `/setup` until the first admin login exists, and `/setup` closes as soon as any login does. Until then, anyone who can reach the app could claim it, so it should be set up straight away, or created ahead of time from `ADMIN_PASSWORD`.
- **Activity log.** Every action the app can produce is recorded with who did it: admin changes, barber actions, customer check-ins, failed logins and lockouts, and automatic or command-line changes.
- **Uploads.** Logos and icons are decoded and re-encoded as PNG by Pillow, which drops anything in the file that isn't the picture. SVG isn't accepted.

## Branding

The shop name and colours are rows in the `settings` table; the logo and icon are PNGs in `brand_assets`. Every page gets the colours as CSS variables, with derived shades worked out on the server. Favicons and home-screen icons are rendered from the icon, then the logo, then a built-in mark in the shop's colours, at `/brand/icon-<size>.png`.

## Data model

| Table | What it holds |
|---|---|
| `locations` | One row per shop: name, link name, the two device tokens, open or closed, whether it follows its schedule, the announcement, and when each screen was last seen. |
| `opening_hours` | A location's hours for one weekday. No row means closed that day. |
| `special_hours` | One date that differs from the weekly hours. No times means closed all day. |
| `barbers` | Every login, including admins. Where they usually work, where they're on duty now, on break, shown on the kiosk, admin access. |
| `queue_entries` | One customer's visit: `waiting`, then `in_progress`, then `done`, or `cancelled` if removed. A group check-in is one row per person with the same check-in time. |
| `login_sessions` | One logged-in device. |
| `login_attempts` | Failed logins, kept for the lockout window. |
| `admin_actions` | The activity log. Names are copied in, so entries still read correctly after someone is renamed or deleted. |
| `settings` | Key and value pairs: timezone, shop name, colours. |
| `brand_assets` | The uploaded logo and icon. |

Times are stored in UTC and converted with the timezone from the Settings tab for display, opening hours and metrics.

## Upgrading from before 1.0

Next Up started as the in-house system for one shop. An install from before 1.0 keeps its locations, logins and history when upgraded. If it never chose a timezone, the upgrade keeps it on the old default, `Australia/Hobart`. Until its name, colours and logo are set on the Branding tab, it shows the Next Up defaults.

Those installs ran from a clone of the repository, so their Docker volumes are named after that folder (for example `myfolder_checkin_pg_data`). Since 1.0.1 the volumes have fixed names (`next-up-postgres-data`, `next-up-app-data`). Before starting such an install on the new `docker-compose.yml`, either copy the data across, or keep the old volume by adding its name to the compose file:

```yaml
volumes:
  postgres_data:
    name: myfolder_checkin_pg_data
```
