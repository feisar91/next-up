# Roadmap

Features suggested but not built yet, roughly in priority order within each group. Sizes are rough: small is a few hours, medium is a day or two.

## Protect what's already there

### Database backups (small, do first)
Every visit, barber and metric lives in the `checkin_pg_data` Docker volume on one machine, with no backups. Run a nightly `pg_dump` to another disk or to cloud storage, and keep about 30 days. This matters most once the app is the shops' only record.

### HTTPS (small, infrastructure)
Put a reverse proxy with TLS in front of the app. Caddy is the simplest because it gets certificates automatically. Then set `SESSION_COOKIE_SECURE=true` and `BEHIND_PROXY=true` in `.env`. Until then, staff passwords cross the network unencrypted.

## For customers

### Estimated wait time (medium)
Show "You're #4, about 25 minutes" on the kiosk confirmation, and a wait estimate on the TV. The inputs already exist: queue length, barbers on duty, and each barber's average time in the chair (see `compute_metrics` in `app/metrics.py`).

### Sound when a customer is called (small)
Play a chime on the TV when someone is called, so customers who are reading or on their phones notice. Some TVs block sound that plays without a tap, so test on the real hardware.

### Opening hours (medium)
Outside opening hours, the kiosk shows "Closed, back at 9am" instead of accepting check-ins. Optionally, pause new check-ins near closing time once the queue passes a set length.

## For barbers

### "On break" button (small)
Let barbers take themselves off the kiosk from the staff dashboard without logging out. Today only an admin can do this, with the On Kiosk switch. Reuses the `show_on_kiosk` logic.

### Undo and reorder in the queue (medium)
Undo an accidental Complete or Remove, move a customer up or down, and hand a customer to a different barber.

### Service type (medium)
Customers pick a service on the kiosk (haircut, beard trim, kids' cut, skin fade). This makes wait estimates more accurate and makes metrics more useful ("beard trims average 15 minutes").

### Take admin-logged-in barbers off duty automatically (small)
A barber an admin puts on duty with Log In has no device session, so nothing ever takes them off the kiosk. Take them off duty after `SESSION_LIFETIME_HOURS` of no activity, the same as device logins.

## For the owner

### Weekly email summary (medium)
Email last week's cuts, busiest times and wait times, with the visits CSV attached. Needs an email service.

### Automatically delete old customer names (small)
After a set time (for example 90 days), replace customer names with "Customer" but keep the times, so metrics still work. Reduces privacy risk under the Australian Privacy Act.

### One-click PDF download (medium)
The metrics PDF currently comes from the browser's print dialog. A PDF built on the server would download in one click, but its charts would need redrawing (for example with matplotlib), so they would look simpler than on screen.
