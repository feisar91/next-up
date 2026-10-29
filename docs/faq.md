---
title: Questions and problems
lead: Short answers to the things people ask most, and fixes for the usual problems.
next: { title: "How it works", url: /technical/how-it-works/ }
---

## About Next Up

### Does it cost anything?

No. Next Up is free and open source. Your only cost is wherever you run it, usually a small server for a few dollars a month.

### Do customers need an app or an account?

No. They type their name on the tablet and that's all. Nothing is installed on their phones.

### Can customers book appointments?

No. Next Up is for walk-ins only. Shops that take bookings as well can still use it for the walk-in queue.

### Can customers see the queue from home?

Not at the moment. The queue is shown on the TV in the shop, and the TV link is secret.

### I have three shops. Do I need three installs?

No. One install handles all of a business's shops, each with its own kiosk, TV and queue. Barbers can work at any of them. Separate businesses should each run their own install.

### What does it store about customers?

The name they type, which shop, the barber they asked for, who served them, and the times. No phone numbers, emails or payment details. It's all kept in your own database, on your own server.

The pages load their fonts from Google Fonts and two scripts (the live updates and the charts) from the cdnjs network, so customers' and barbers' browsers contact those services when a page opens. No customer details are sent to them.

### Can I change the wording on the screens, or use another language?

Not from the Admin page. The screens are in English. Because the code is open, someone comfortable editing web templates can change any text in the `app/templates` folder.

## Problems

### I log in and get sent straight back to the login page

The app only keeps you logged in over HTTPS unless told otherwise. When that's the problem, the login page shows a red "Logins won't work at this address yet" warning. If the address starts with `http://` (not `https://`), add `SESSION_COOKIE_SECURE=false` to `.env` and run `docker compose up -d`. Better still, [set up HTTPS](../guides/server/).

If the warning says the browser is blocking cookies, allow cookies for the site in the browser's settings.

### A barber isn't on the kiosk

Customers can only pick barbers who are working at that shop right now. Check that:

- they're logged in and picked that shop (the Barbers tab on the Admin page shows where everyone is working),
- they're not on break,
- **On Kiosk** is switched on for them on the Barbers tab.

### The kiosk or TV shows "Connection lost"

The device can't reach the app. Check the device's Wi-Fi and the shop's internet. The bar goes away by itself when the connection is back, and nothing is lost. Customers who checked in on other devices meanwhile still show up.

If every screen shows it at once, the app itself may be down. Run `docker compose ps` on the server to check, and `docker compose up -d` to start it.

### The days or hours on the Metrics page are off

Check the timezone on the Settings tab. Everything is stored in universal time and converted with that setting, so fixing it corrects past data too.

### The kiosk didn't open or close on time

Check the shop's Opening Hours page: **Open and close automatically** has to be ticked, and the times are in the timezone on the Settings tab. If a barber opened or closed the shop by hand against the schedule, their choice holds until the next scheduled change or midnight. The Activity tab shows what happened and who did it.

### The tablet's screen keeps going dark

The kiosk can only keep the screen awake over HTTPS. Set up HTTPS, or set the tablet's own auto-lock or sleep setting to never.

### Someone has the kiosk or TV link who shouldn't

Go to **Device Links** on the Admin page and click **Regenerate** next to it. The old link stops working immediately. Open the new one on your device.

### Nobody can log in as an admin

See [Locked out](../guides/maintenance/#locked-out).

## Still stuck?

[Open an issue on GitHub](https://github.com/{{ site.repository }}/issues) with what you did, what you expected, and what happened instead. The output of `docker compose logs app` helps.
