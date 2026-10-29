---
title: Backups and upgrades
lead: Keeping a copy of your data, installing new versions, and getting back in when you're locked out.
next: { title: "Questions and problems", url: /faq/ }
---

All the commands on this page are run in the `next-up` folder on the machine running the app.

## Backing up

Everything lives in one database: shops, logins, the queue, the history, the activity log, and your logo. One command saves all of it to a file:

```bash
docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > next-up-$(date +%F).sql
```

Copy that file somewhere other than the server: your own computer, or cloud storage. A backup on the same machine won't help if the machine dies.

To make a backup every night at 2 am, run `crontab -e` and add this line, changing the folder to wherever `next-up` is:

```
0 2 * * * cd /root/next-up && docker compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backups/next-up-$(date +\%F).sql
```

Make the folder first with `mkdir backups`.

## Restoring a backup

Restoring replaces everything in the database with what's in the backup file.

```bash
docker compose down --volumes
docker compose up -d --wait postgres
docker compose exec -T postgres sh -c 'psql -q -o /dev/null -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < next-up-2026-10-29.sql
docker compose up -d
```

`down --volumes` empties the database before the backup goes back in. Everyone has to log in again afterwards. The same steps move Next Up to a new server: install it there, copy your `.env` and the backup file across, and restore.

## Upgrading

```bash
git pull
docker compose up -d --build
```

The app updates its database by itself as it starts. Kiosks, TVs and barbers' screens that are open reload themselves when they reconnect, so you don't need to touch the devices. It's best done outside opening hours, since the screens drop off for about half a minute while the app restarts.

Take a backup before upgrading, in case you need to go back.

## Locked out

If nobody can log in as an admin, give an admin login a new temporary password from the server:

```bash
docker compose exec app flask reset-admin-password --username dana
```

Use the admin's own username. It prints a temporary password, and they're asked to choose a new one when they log in. It also switches the login back on if it had been deactivated.

## Looking at the logs

```bash
docker compose logs -f app
```

This shows each page request and any errors as they happen. Press Ctrl+C to stop watching. Useful if something isn't working and you want to see why, or to include in a problem report.

## Stopping it

```bash
docker compose down
```

stops the app and keeps all the data. `docker compose up -d` starts it again. Only add `--volumes` if you want the data gone.
