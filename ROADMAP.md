# Roadmap

Features suggested but not built yet, roughly in priority order within each group. Sizes are rough: small is a few hours, medium is a day or two.

## For barbers

### "Call Next" that respects preferences (small)
One button that calls the next waiting customer who asked for this barber or has no preference, skipping anyone waiting for someone else. Barbers currently pick a row and tap "Call to Chair". Customers who asked for the viewing barber are already highlighted ("Asked for you", `is-mine` in `_staff_waiting_row.html` / `staff.js`), so this is the button plus a server-side pick in `app/staff.py`.

### Your cuts today (small)
A count on the staff dashboard of the customers this barber has completed today (shop time). The data is already there: `QueueEntry` rows that are `done`, with `called_by_barber_id` and `completed_at`.

### Shift history and hours worked (medium)
Record each on-duty stretch (start, end, location) in its own table instead of only the current `on_duty_since`, so the owner gets a weekly hours report for payroll. It also allows a "busy vs idle" metric: time in the chair compared with time on duty. Shifts start and end where on-duty already changes: `set_on_duty` / `clear_on_duty` in `app/staff.py` and `app/off_duty.py`.

## For customers

### Text me when I'm nearly up (medium, running costs)
The customer adds a mobile number at check-in and gets an SMS when they're about two away, so they can step out without losing their spot. Needs an SMS provider (charged per message), and adds personal data to handle: delete numbers once the visit is finished.

## For the owner

### Walk-out insight in metrics (small)
Show how long removed no-shows had been waiting before they left (from `checked_in_at` to `removed_at`), e.g. an average and a spread by hour of day. That shows when customers are being lost to wait time, which is a staffing signal. Leave out entries cleared overnight by `app/queue_cleanup.py`, which have no `removed_at`.

## Operations and security

### Health check for the app container (small)
A `/healthz` endpoint (app up and database reachable) plus a Docker `healthcheck` on the app service, so a hung app shows as unhealthy and a free uptime monitor can alert you if it's down when a shop opens. Postgres already has one in `docker-compose.yml`. Docker on its own only restarts containers that exit, not unhealthy ones; restarting on a failed check would need a small helper such as autoheal.

### Two-step login for admins (medium)
A code from an authenticator app (TOTP) when an admin logs in. Admins can regenerate device links and see customer names, and the app is reachable from the internet. Fits after the password check in `app/auth.py`, with recovery through `flask reset-admin-password`.
