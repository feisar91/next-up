#!/bin/sh
# Rebuilds the docs screenshots and demo video (docs/assets/img, docs/assets/video).
#
# Starts a throwaway copy of the app in Docker on port 8090 (its own containers
# and volumes, separate from any copy you're running), drives it with Playwright,
# then removes it. Needs Docker and Python with the packages in requirements.txt:
#
#   pip install -r docs/tools/requirements.txt && playwright install chromium
#   docs/tools/build-media.sh
#
# Set CHROMIUM_PATH to use an installed Chromium instead of Playwright's.
set -eu

cd "$(dirname "$0")/../.."
PYTHON=${PYTHON:-python3}
PORT=8090
BASE="http://127.0.0.1:$PORT"

export COMPOSE_PROJECT_NAME=nextup-docs
# Build from this checkout, so the pictures show the code you're about to release.
export COMPOSE_FILE=docker-compose.yml:docker-compose.dev.yml:docs/tools/docker-compose.docs.yml
export APP_PORT="127.0.0.1:$PORT"
export SECRET_KEY=docs-screenshots-only
export SESSION_COOKIE_SECURE=false
export TIMEZONE="${TIMEZONE:-Europe/London}"
# Keep the demo exactly as seeded while the screenshots are taken: no stores
# opening or closing on their schedule, no overnight queue clear, nobody taken
# off duty.
export OPENING_HOURS_CHECK_SECONDS=0
export QUEUE_CLEANUP_CHECK_SECONDS=0
export OFF_DUTY_CHECK_SECONDS=0
# Never create an admin from the environment: the fresh phase uses the setup page.
export ADMIN_PASSWORD=

start() {
    docker compose up -d --build --quiet-pull >/dev/null
    printf "Waiting for the app"
    until curl -fs -o /dev/null "$BASE/login" 2>/dev/null || curl -fs -o /dev/null "$BASE/setup" 2>/dev/null; do
        printf "."
        sleep 1
    done
    echo
}

stop() {
    docker compose down --volumes >/dev/null 2>&1
}
trap stop EXIT

stop
start
"$PYTHON" docs/tools/capture.py fresh --base "$BASE"

stop
start
docker compose exec -T app flask seed-demo
"$PYTHON" docs/tools/capture.py demo --base "$BASE" "$@"

if [ -f docs/assets/video/demo.webm ]; then
    echo "Converting the video to MP4"
    docker run --rm -v "$PWD/docs/assets/video:/video" linuxserver/ffmpeg:7.1.1 \
        -y -loglevel error -i /video/demo.webm \
        -c:v libx264 -preset slow -crf 26 -pix_fmt yuv420p -movflags +faststart -an /video/demo.mp4
    ls -l docs/assets/video
fi
