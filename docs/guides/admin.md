---
title: Running the shop
lead: The Admin page, tab by tab. Only logins with admin access can open it.
next: { title: "Your name, colours and logo", url: /guides/branding/ }
---

## Locations

Each location is one shop with its own queue, kiosk and TV. Add as many as you have.

{% include figure.html src="admin-locations.webp" alt="The Locations tab" %}

- **Name** is what customers and barbers see.
- **Short name for links** goes into the shop's addresses, like `/staff/main-street`. Leave it blank and it's made from the name.
- **Remove** takes a shop out of use: its kiosk and TV links stop working and it disappears from the barbers' list. Its history stays, and **Restore** brings it back.
- **Delete** is only offered for a removed shop, and only works if it was never used. A shop with any check-ins can't be deleted, so its history is kept.

The **Announcements** box on the same tab sets the notice on each shop's TV and kiosk. Barbers can set it from their own screen too. It clears itself at midnight.

## Opening hours

Click **Opening Hours** next to a shop.

{% include figure.html src="location-hours.webp" size="card" alt="The weekly opening hours for one shop" %}

Tick the days the shop opens, set the times, and choose how many minutes before closing to stop check-ins. Fifteen minutes before is common, so the last customer still gets a cut.

With **Open and close automatically** ticked, the kiosk opens and closes on time without anyone touching it. Each change is noted on the Activity tab. A closed kiosk tells customers when it opens next, for example "Back Tuesday at 9:00 am".

### Holidays and one-off days

Under **Holidays and special hours**, add any date that doesn't follow the weekly hours: closed all day for a public holiday, or shorter hours for Christmas Eve. Adding a date that's already listed replaces it.

{% include figure.html src="special-hours.webp" size="card" alt="Two special dates: closed for staff training, and a half day" %}

### When a barber overrides the schedule

Barbers can still close early or stay open late from their screen. If that goes against the schedule, it holds until the next scheduled opening or closing, or midnight, whichever comes first. Then the schedule takes over again. Saving the opening hours also hands control straight back to the schedule.

Closing never removes anyone. Customers already waiting stay in the queue.

## Barbers

{% include figure.html src="admin-barbers.webp" alt="The Barbers tab" %}

The table shows each login, where they're working right now, and whether they're logged in.

- **Add Barber** at the bottom creates a login with a temporary password. They pick their own the first time they log in.
- **Edit** changes their name, username, usual shop or admin access.
- **Reset Password** gives them a new temporary password and logs them out everywhere.
- **On Kiosk** decides whether customers can ask for them by name. Barbers can't change this themselves. Their own break button is separate.
- **Log Out** logs a barber out on all their devices and takes them off the kiosk. Handy when someone leaves a shared tablet logged in.
- **Log In** puts a barber who isn't logged in on duty at a shop you choose, for example when they've left their phone at home. They show on that shop's kiosk until someone logs them out, or for 12 hours if they never log in on a device.
- **Deactivate** blocks a login without deleting it, for someone who's left. **Delete** removes a deactivated login for good. Their past cuts stay in the history, shown as "Unassigned".

## Device Links

The kiosk and TV links for each shop, and whether each screen is connected right now. See [Kiosk and TV](../kiosk-and-tv/).

## Branding

The shop name, colours, logo and icon. See [Your name, colours and logo](../branding/).

## Settings

The timezone your shops' clocks follow. It decides when each day starts on the Metrics page and in the activity log, and when shops open and close on their schedule. Daylight saving is handled for you.

## Activity

A log of everything that happens: customers checking in, barbers calling and finishing customers, logins, failed logins, admin changes, and the things the app does by itself, like opening a shop on schedule.

{% include figure.html src="admin-activity.webp" alt="The Activity tab, listing recent events with who did them" %}

Filter it by type of event, by person, or by date. It shows the 200 most recent entries that match. Names are stored as they were at the time, so the log still reads correctly after someone changes their name or is deleted.

The **Security** type lists failed logins with the username tried and where from. After 5 wrong passwords for one username, or 20 from one address, within 15 minutes, further attempts are refused until the 15 minutes are up.
