---
title: Hosting a public demo
lead: Running the demo shop on the internet for anyone to try, put back to how it started every hour.
---

Demo mode runs the made-up shop from [Try the demo shop](../../demo/) at a public web address. Anyone can open it, log in with one click as the owner or a barber, check in on the kiosk and watch the TV update. Every visitor shares the same shop, and on the hour everything they changed is erased and the demo is loaded again.

Run it as its own install, on its own address. It is not a setting for a shop's real install.

## What's different in demo mode

**It resets every hour**, on the hour (UTC), and each time the app starts. A reset empties the database and loads the demo again with today's queue and five weeks of history counted back from now. Everyone is logged out. Open kiosk and TV screens reload by themselves and keep working, because their links stay the same.

**Both locations stay open around the clock**, since visitors come from every timezone.

**The login and home pages** have buttons to log in as Dana (the owner) or Marco (a barber), the password for the other logins, and links to each location's kiosk and TV. A bar at the top of every page, and a label in the corner of the kiosk and TV, says when the next reset is.

**Some things are turned off**, so one visitor can't spoil the demo for everyone else until the next reset:

- the Branding tab (name, colours, logo and icon)
- changing, resetting the password of, switching off, logging out or deleting the demo's own logins (visitors can still add their own logins and do all of that to them)
- removing or deleting the demo's locations, or resetting their kiosk and TV links
- the first-run setup page

**Rude words are refused** in anything typed into a form: names on the kiosk, announcements, new logins and locations, notes on special hours. Passwords aren't checked. The word list is in `app/data/blocked_words.txt` (from the [List of Dirty, Naughty, Obscene, and Otherwise Bad Words](https://github.com/LDNOOBW/List-of-Dirty-Naughty-Obscene-and-Otherwise-Bad-Words)), and `app/word_filter.py` adds a few words, skips a few that are also people's names, and catches simple tricks like `sh1t` or `f u c k`.

To protect a real shop, demo mode only runs on an empty database or one it set up itself. If `DEMO_MODE=true` is set on an install that has its own logins, the app refuses to start and erases nothing.

## Setting it up

You need a server with Docker and a web address for the demo. These steps use Caddy for HTTPS, as in [Putting it online](../../guides/server/). The demo can run on the same server as a real install: it has its own containers, database and port.

**1. Point the address at the server.** Add a DNS A record for the demo's address (for example `demo.yourdomain.com`) pointing at the server's IP address.

**2. Download the demo's Compose file** into its own folder:

```bash
mkdir next-up-demo && cd next-up-demo
curl -fsSLO https://raw.githubusercontent.com/{{ site.repository }}/main/docker-compose.demo.yml
```

**3. Start it:**

```bash
docker compose -f docker-compose.demo.yml up -d
docker compose -f docker-compose.demo.yml logs app
```

The log should end with `Loaded a fresh copy of the demo shop.` and Gunicorn starting. The app listens on `127.0.0.1:8010`, so only Caddy can reach it.

**4. Add it to Caddy.** Add this to `/etc/caddy/Caddyfile` and run `sudo systemctl reload caddy`:

```
demo.yourdomain.com {
    reverse_proxy 127.0.0.1:8010
}
```

Open the address in a browser. You should see the demo's welcome page.

## Settings

Set these in a `.env` file next to `docker-compose.demo.yml`. They have their own names, so a real install's `.env` doesn't affect the demo.

| Setting | Default | What it does |
|---|---|---|
| `DEMO_VERSION` | `latest` | Which version of Next Up to run. Demo mode needs 1.1.0 or later. |
| `DEMO_PORT` | `8010` | The port on `127.0.0.1` that Caddy forwards to. |
| `DEMO_RESET_MINUTES` | `60` | How often it resets. |
| `DEMO_TIMEZONE` | `UTC` | The demo shop's timezone, used for its history and the Metrics page. |

## Looking after it

- **Reset it now:** `docker compose -f docker-compose.demo.yml exec app flask demo-reset`
- **Update it:** `docker compose -f docker-compose.demo.yml pull && docker compose -f docker-compose.demo.yml up -d`. Each start loads a fresh demo.
- **Remove it:** `docker compose -f docker-compose.demo.yml down --volumes`. This only removes the demo's own containers and volumes.
