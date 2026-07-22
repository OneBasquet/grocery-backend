#!/usr/bin/env bash
# Entrypoint for running the CLI scraper (app/worker.py) as its own ad-hoc
# container, decoupled from the API server — used by cron via `docker run
# --entrypoint`. Starts the same virtual X display docker-entrypoint.sh sets
# up for the API container, since the scrapers launch Chromium headed
# (headless=False) either way.
set -e

rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
export DISPLAY=:99
sleep 1

exec python3 -m app.worker "$@"
