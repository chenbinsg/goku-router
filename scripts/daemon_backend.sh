#!/bin/bash
# daemon_backend.sh — launchd wrapper for Goku Router backend
# Sources .env and execs uvicorn so launchd tracks the correct PID.
set -e

DIR="/Users/chenbin/router"

# Load env vars
if [ -f "$DIR/.env" ]; then
  set -a
  . "$DIR/.env"
  set +a
fi

# Activate venv
if [ -d "$DIR/.venv" ]; then
  source "$DIR/.venv/bin/activate"
fi

cd "$DIR/backend"

exec "$DIR/.venv/bin/python" -m uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8159}"
