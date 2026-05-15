#!/bin/bash
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# Load .env if exists (exports DATABASE_URL, PORT, SECRET_KEY, etc.)
if [ -f "$DIR/.env" ]; then
  set -a
  . "$DIR/.env"
  set +a
fi

# Activate venv if exists
if [ -d ".venv" ]; then
  source .venv/bin/activate
fi

# Start backend
cd "$DIR/backend"
echo "Starting backend on port 8159..."
nohup "$DIR/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8159 > "$DIR/backend.log" 2>&1 &
echo $! > "$DIR/backend.pid"
echo "Backend PID: $(cat $DIR/backend.pid)"

# Start frontend dev server
cd "$DIR/frontend"
echo "Starting frontend on port 5159..."
nohup npm run dev -- --host 0.0.0.0 --port 5159 > "$DIR/frontend.log" 2>&1 &
echo $! > "$DIR/frontend.pid"
echo "Frontend PID: $(cat $DIR/frontend.pid), port 5159"

echo "All services started."
