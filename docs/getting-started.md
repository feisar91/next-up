---
title: Install and set up
lead: From nothing to a working kiosk, TV and staff logins. Allow about half an hour, most of it spent on the shop details.
next: { title: "Try the demo shop", url: /demo/ }
---

This guide sets Next Up up on one machine and gets every screen talking to it. To try it out on your own computer before using it for real, [load the demo shop](../demo/) first: it has made-up customers and history to click around in.

## 1. Get a machine with Docker

Next Up runs in [Docker](https://docs.docker.com/get-docker/). Docker packages the app and its database, so there's nothing else to install.

- **To try it out**, your own computer is fine. Install Docker Desktop (Windows or Mac) or Docker Engine (Linux).
- **For the shop**, use a machine that stays on: a small rented server (a VPS) or a spare computer at the shop. A VPS is the usual choice, because barbers' phones can reach it from anywhere. 1 GB of memory is plenty. [Putting it online](../guides/server/) covers the extra steps for a server, such as an address and HTTPS.

## 2. Download and start it

Open a terminal on that machine and run:

```bash
git clone https://github.com/{{ site.repository }}.git
cd next-up
cp .env.example .env
```

Open `.env` in a text editor. Every line in it is optional, but two matter now:

```bash
# Your shop's timezone, so days and opening hours line up with your clock.
TIMEZONE=Europe/London

# Only while you don't have HTTPS set up yet (see below).
SESSION_COOKIE_SECURE=false
```

Logins only work over HTTPS by default, which is what you want once the app is online. While you try it out at an address starting with `http://`, set `SESSION_COOKIE_SECURE=false`, or the app won't keep you logged in. Opening it as `http://localhost` on the same computer usually works either way. If you forget, the setup and login pages show a red warning saying so.

Then start it:

```bash
docker compose up -d --build
```

The first start takes a few minutes while Docker downloads and builds everything. After that, starts take seconds. Docker restarts the app after a reboot or a crash.

Open `http://localhost:8000` in a browser (or the server's address with `:8000` on the end).

## 3. Create your admin login

The first page asks you to create the admin login. This is your account for setting the shop up. Pick a password of at least 8 characters.

{% include figure.html src="setup.webp" size="card" alt="The welcome page with fields for your name, a username and a password" %}

<div class="note warning" markdown="1">
Until you've done this, anyone who can open the app could create the admin login instead of you. Do it as soon as the app starts. If you'd rather set the first password in advance, put `ADMIN_PASSWORD=...` in `.env` before the first start. That creates a login called `admin`, and you're asked to change the password the first time you use it.
</div>

## 4. Work through the checklist

After you log in, the Admin page shows a Getting Started list. Each item links to the part of the Admin page that does it, and ticks itself off when it's done.

{% include figure.html src="getting-started.webp" alt="The Getting Started checklist with five steps" %}

### Name your shop

Go to the **Branding** tab. Put in your shop name, and change the two colours if you want to. You can add your logo now or later. [Your name, colours and logo](../guides/branding/) has the details.

### Set your timezone

On the **Settings** tab, pick the city your shop's clock follows. It decides when each day starts for the charts, and when stores open and close on their schedule. Daylight saving is handled for you.

{% include figure.html src="admin-settings.webp" alt="The Settings tab with a timezone picker" %}

### Add your locations

On the **Locations** tab, add each shop. Only the name is needed. The short name is used in the shop's links (for example `main-street`), and is made from the name if you leave it blank.

{% include figure.html src="admin-locations.webp" alt="The Locations tab listing two shops, with the form for adding another" %}

Then click **Opening Hours** next to each shop. Fill in the days and times, and tick **Open and close automatically** if you want the kiosk to stop taking names at closing time without anyone touching it. [Running the shop](../guides/admin/#opening-hours) explains how this works with holidays and early closes.

### Add your barbers

On the **Barbers** tab, add a login for each barber: their name as customers know it, a username, and a temporary password. Tell them the username and password. The first time they log in, they're asked to pick their own password.

{% include figure.html src="admin-barbers.webp" alt="The Barbers tab listing logins, who's working where, and the form for adding a barber" %}

- **Default location** saves a tap for barbers who usually work at the same shop. Anyone can still work at any location.
- **Grant admin access** lets that person use the Admin and Metrics pages too.
- **Show on check-in kiosk** is on for barbers customers can ask for by name. Turn it off for someone who works the queue but doesn't cut, like a receptionist.

### Set up the kiosk and the TV

On the **Device Links** tab, each shop has two links: one for the kiosk tablet and one for the TV. Open each link on its device. The checklist ticks itself off once a kiosk and a TV have both connected.

{% include figure.html src="admin-device-links.webp" alt="The Device Links tab with a kiosk link and a TV link for each shop, and whether each screen is connected" %}

These links work without a login, because nobody logs in on a tablet by the door. That makes them secret: don't share them. [Kiosk and TV](../guides/kiosk-and-tv/) covers mounting the tablet, keeping the screen on, and what to do if a link gets out.

## 5. Get the barbers on

Each barber opens the app's address on their phone, logs in, picks a password, and chooses the shop they're working at. They show up on that shop's kiosk straight away, so customers can ask for them.

Adding the page to their home screen makes it open like an app: in Safari, tap Share and then **Add to Home Screen**; in Chrome on Android, open the menu and tap **Add to Home screen**. Send them the [guide for barbers](../guides/barbers/), which takes five minutes to read.

That's it. When the next customer walks in, they put their name in at the door.
