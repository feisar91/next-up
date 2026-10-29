---
title: Putting it online
lead: Running Next Up on a server with its own web address and HTTPS, so barbers can reach it from their phones anywhere.
next: { title: "Backups and upgrades", url: /guides/maintenance/ }
---

## Choosing where it runs

**A rented server (VPS)** from any hosting company is the usual choice. The smallest plans are enough: 1 CPU and 1 GB of memory runs a handful of shops. Pick Ubuntu or Debian, and a data centre near you so the screens update quickly.

**A computer at the shop** also works, if it stays on. Barbers' phones then have to be on the shop Wi-Fi to reach it. Without HTTPS (see below) a few things don't work: tablets can't keep the screen awake by themselves, and Android won't open the kiosk as a full-screen app.

The rest of this page assumes a VPS.

## 1. Install Docker

Log in to the server and install Docker using [Docker's instructions for your system](https://docs.docker.com/engine/install/). On Ubuntu or Debian the short version is:

```bash
curl -fsSL https://get.docker.com | sh
```

## 2. Point a web address at it

Choose an address like `queue.yourshop.com` and add a DNS **A record** for it, pointing at the server's IP address, wherever you manage your domain. It can take a few minutes to take effect.

## 3. Download Next Up and set it up

```bash
git clone https://github.com/{{ site.repository }}.git
cd next-up
cp .env.example .env
```

Edit `.env` and set at least these:

```bash
TIMEZONE=Europe/London
POSTGRES_PASSWORD=pick-a-long-random-password
# Only reachable through the web server set up in the next step.
APP_PORT=127.0.0.1:8000
BEHIND_PROXY=true
```

`POSTGRES_PASSWORD` only takes effect the first time the database is created. Set it before the first start.

Then start it:

```bash
docker compose up -d --build
```

## 4. Add HTTPS

A small web server sits in front of Next Up and handles HTTPS. [Caddy](https://caddyserver.com/docs/install) is the simplest, because it gets and renews the certificate by itself. Install it, then replace the contents of `/etc/caddy/Caddyfile` with:

```
queue.yourshop.com {
    reverse_proxy 127.0.0.1:8000
}
```

and reload it:

```bash
sudo systemctl reload caddy
```

Open `https://queue.yourshop.com` and you should see the page to create your admin login. Carry on from [step 3 of Install and set up](../../getting-started/#3-create-your-admin-login).

Make sure the server's firewall lets in ports 80 and 443. Port 8000 doesn't need to be open, since only Caddy talks to the app.

### Using Nginx instead

If the server already runs Nginx, add a site for the address and pass the connection through, including the WebSocket headers the live updates need:

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

Get a certificate for it with [Certbot](https://certbot.eff.org/).

## Settings

Everything is set in `.env`, and every setting is optional. After changing it, run `docker compose up -d` to apply it.

| Setting | Default | What it does |
|---|---|---|
| `TIMEZONE` | `UTC` | The timezone to use until an admin picks one on the Settings tab. |
| `APP_PORT` | `8000` | The port the app listens on. `127.0.0.1:8000` keeps it private to the server. |
| `BEHIND_PROXY` | `false` | Set to `true` behind Caddy or Nginx, so login limits see each visitor's real address. |
| `SESSION_COOKIE_SECURE` | `true` | Logins only work over HTTPS. Set to `false` if you use plain `http://`. |
| `SESSION_LIFETIME_HOURS` | `12` | Hours without using the app before a barber is logged out. |
| `POSTGRES_PASSWORD` | `checkin` | The database password. Only used when the database is first created. |
| `ADMIN_PASSWORD` | | Creates an `admin` login with this password on the first start, instead of the setup page. |
| `SECRET_KEY` | generated | Signs login cookies. Made and saved for you on the first start. |
| `LOGIN_MAX_FAILURES_PER_USER` | `5` | Wrong passwords allowed per username before a lockout. |
| `LOGIN_MAX_FAILURES_PER_IP` | `20` | Wrong passwords allowed from one address before a lockout. |
| `LOGIN_LOCKOUT_MINUTES` | `15` | How long a lockout lasts. |

## How big can it get?

The app runs as a single process, which keeps the live updates simple. That comfortably handles a business with several shops on a small server. It isn't built to host many separate businesses on one install. Each business should run its own copy.
