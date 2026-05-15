#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

for pidfile in backend.pid frontend.pid; do
  if [ -f "$pidfile" ]; then
    PID=$(cat "$pidfile")
    if kill -0 "$PID" 2>/dev/null; then
      echo "Stopping PID $PID..."
      kill "$PID"
    fi
    rm -f "$pidfile"
  fi
done

echo "All services stopped."
