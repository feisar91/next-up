#!/bin/sh
set -e

# Use SECRET_KEY from the environment if given; otherwise generate one on first
# start and keep it in the app data volume so sessions survive restarts.
if [ -z "$SECRET_KEY" ]; then
    if [ ! -s /data/secret_key ]; then
        python -c "import secrets; print(secrets.token_hex(32))" > /data/secret_key
        chmod 600 /data/secret_key
    fi
    SECRET_KEY="$(cat /data/secret_key)"
    export SECRET_KEY
fi

# Wait for Postgres to accept connections before running migrations.
python - <<'PY'
import os, sys, time
import psycopg2

url = os.environ["DATABASE_URL"]
for attempt in range(30):
    try:
        psycopg2.connect(url).close()
        break
    except psycopg2.OperationalError:
        print("Waiting for database...", flush=True)
        time.sleep(2)
else:
    sys.exit("Database never became available")
PY

flask db upgrade

# First-run only: creates the locations and an "admin" login if no logins exist yet.
flask bootstrap

exec "$@"
