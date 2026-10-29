---
title: Try the demo shop
lead: Load a made-up shop with barbers, a queue and five weeks of history, so you can try every screen before setting up your own.
next: { title: "For barbers", url: /guides/barbers/ }
---

The demo is a pretend business called Harbour Lane Barbers, with two shops, an owner, five barbers and about 1,200 past visits. It's the same data used for the pictures in these guides.

## Load it

Follow steps 1 and 2 of [Install and set up](../getting-started/), but **don't create the admin login yet**. The demo only loads into an empty install. Then run:

```bash
docker compose exec app flask seed-demo
```

Open `http://localhost:8000` and log in:

| Username | Password | Who |
|---|---|---|
| `dana` | `demo-password` | The owner (admin) |
| `marco`, `priya`, `tom`, `jess`, `leo` | `demo-password` | Barbers |

## Things to try

- Log in as `dana` and open **Device Links** on the Admin page. Open the Harbour Lane kiosk link in one browser window and the TV link in another.
- Check someone in on the kiosk and watch them appear on the TV.
- Log in as `marco` in a private window (or on your phone) and call them to the chair.
- Close the store from Marco's screen, then look at the kiosk.
- Open **Metrics** as Dana to see the charts with a few weeks of history behind them.
- Change the colours on the **Branding** tab while the kiosk is open in another window.

The demo's opening hours are real, so if you try it late at night the Station Street shop may close itself. Harbour Lane follows manual hours, so it stays open.

## Start again with a clean install

When you're done, remove the demo and its data:

```bash
docker compose down --volumes
docker compose up -d
```

`--volumes` deletes the database, so only do this on an install you're happy to empty. The next start is a fresh install that asks you to create the admin login.

<div class="note warning" markdown="1">
Don't load the demo into the install you use for the shop. The made-up visits would be mixed in with your real ones on the Metrics page. That's why `seed-demo` refuses to run on an install that already has logins or locations.
</div>
