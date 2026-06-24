#!/usr/bin/env bash
# Start a virtual X display, then run the API. The scrapers launch Chromium
# headed (headless=False), so they need a display even on a headless server.
set -e

# Clean any stale lock, start Xvfb in the background on :99.
rm -f /tmp/.X99-lock
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
export DISPLAY=:99

# Give Xvfb a moment to come up before Chromium ever needs it.
sleep 1

exec uvicorn api.main:app --host 0.0.0.0 --port 80 --workers 1
