---
title: Development and releases
lead: Running Next Up from the source code, testing changes, and publishing a release.
---

## Running from the source

Clone the repository and start it with the development override, which builds the image from your checkout instead of downloading it:

```bash
git clone https://github.com/{{ site.repository }}.git
cd next-up
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

The app is on `http://localhost:8000`. Run the last command again after changing the code. Every start waits for Postgres, applies database migrations (`flask db upgrade`), then runs `flask bootstrap`, which does nothing once a login exists.

To work on a filled-in shop, run `docker compose exec app flask seed-demo` before creating the admin login. It loads the made-up shop used for the screenshots. Log in as `dana`, password `demo-password`.

Without Docker: create a Python 3.12 virtual environment, `pip install -r requirements.txt`, point `DATABASE_URL` at a Postgres database, and run `python wsgi.py` (port 5000, with the debugger on).

## Tests

```bash
docker compose exec app python -m pytest -p no:cacheprovider
```

(`-p no:cacheprovider` because the container can't write pytest's cache folder. In a local virtual environment, plain `python -m pytest` works.)

The tests use an in-memory SQLite database (`config.TestConfig`), so they never touch Postgres and need no setup beyond the requirements. `pytest.ini` turns every warning into a failure, so deprecations get fixed when they first appear. GitHub Actions runs the suite on every push and pull request.

## Database changes

Any change to the models needs a migration, because every start runs `flask db upgrade`. Generate it from a local Python environment (see "Without Docker" above), with `DATABASE_URL` pointing at a database on the current schema:

```bash
export FLASK_APP=wsgi.py
flask db upgrade
flask db migrate -m "describe the change"
```

Check the generated file in `migrations/versions/` before committing it. (Inside the container the code folder is read-only, so the file can't be written there.)

## Command-line tools

Run with `docker compose exec app flask <command>`:

| Command | What it does |
|---|---|
| `bootstrap` | First-run setup, run on every start. Creates an `admin` login from `ADMIN_PASSWORD` if set and no login exists. |
| `seed-demo` | Loads the demo shop into an empty database. |
| `set-branding` | Sets the shop name, colours, logo or icon. See `--help`. |
| `reset-admin-password --username <name>` | Gives an admin login a new temporary password and switches it back on. |

## Releasing

`.github/workflows/publish.yml` runs the tests, then builds the image for amd64 and arm64 and pushes it to `ghcr.io/{{ site.repository }}`:

- Every push to `main` publishes `:main` and `:sha-<commit>`.
- A version tag publishes `:1.2.3`, `:1.2`, `:1` and `:latest`, then creates a GitHub release with `docker-compose.yml` and `env.example` attached. Those two files are what the install instructions download.

To release:

```bash
git tag v1.2.3
git push origin v1.2.3
```

Use a new patch number (`1.2.4`) for fixes, a new minor number (`1.3.0`) for new features, and a new major number (`2.0.0`) for changes that need people to do something when they upgrade.

## The documentation site

These pages are in the `docs/` folder and published by GitHub Pages from `main`. Each push that changes them rebuilds the site. See `docs/README.md` to preview it locally.

The screenshots, the demo video and the link-preview image are generated, never edited by hand. `docs/tools/build-media.sh` starts a throwaway copy of the app from your checkout, loads the demo shop and drives it with Playwright. Re-run it after changing how a screen looks:

```bash
pip install -r docs/tools/requirements.txt && playwright install chromium
docs/tools/build-media.sh
```

## Where things are

`CLAUDE.md` in the repository has a map of the code and the rules the codebase follows, such as broadcasting after every queue change and never sending full customer names to the TV. Ideas not built yet are in `ROADMAP.md`.
