#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# ── Unload launchd agent first (stops backend and prevents auto-restart) ───────
_PLIST="$HOME/Library/LaunchAgents/com.chenbin.goku-router.plist"
if [ -f "$_PLIST" ]; then
  launchctl unload "$_PLIST" 2>/dev/null || true
fi
unset _PLIST

for pidfile in backend.pid frontend.pid llama-qwen.pid llama-deepseek.pid; do
  if [ -f "$pidfile" ]; then
    PID=$(cat "$pidfile")
    if kill -0 "$PID" 2>/dev/null; then
      echo "Stopping PID $PID..."
      kill "$PID" 2>/dev/null || true
      for i in $(seq 1 10); do sleep 0.5; kill -0 "$PID" 2>/dev/null || break; done
      kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$pidfile"
  fi
done

# Fallback: kill lingering processes on router ports
for PORT in 8159 5159; do
  PIDS=$(lsof -ti:$PORT 2>/dev/null) || true
  if [ -n "$PIDS" ]; then
    echo "Force-killing lingering process on port $PORT (PID: $PIDS)..."
    echo "$PIDS" | xargs kill -9 2>/dev/null || true
  fi
done
pkill -f "uvicorn app.main.*8159" 2>/dev/null || true
pkill -f "vite.*5159" 2>/dev/null || true

echo "All services stopped."
