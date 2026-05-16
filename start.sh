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

# ── Stop any existing instances first ─────────────────────────────────────────
"$DIR/stop.sh" 2>/dev/null || true
sleep 1

# ── Start local LLM servers (providers managed by this router) ────────────────
_QWEN_SCRIPT="$HOME/models/QWen/start_server.sh"
_QWEN_MODEL="$HOME/models/QWen/qwen2.5-14b-instruct-q4_k_m-00001-of-00003.gguf"
if [ -f "$_QWEN_SCRIPT" ] && [ -f "$_QWEN_MODEL" ]; then
  echo "Starting local_qwen llama-server on port 8080..."
  nohup "$_QWEN_SCRIPT" > "$DIR/llama-qwen.log" 2>&1 &
  echo $! > "$DIR/llama-qwen.pid"
  echo "local_qwen PID: $(cat $DIR/llama-qwen.pid)"
fi
unset _QWEN_SCRIPT _QWEN_MODEL

_DSR1_SCRIPT="$HOME/models/DeepSeek-R1/start.sh"
_DSR1_MODEL="$HOME/models/DeepSeek-R1/DeepSeek-R1-Distill-Qwen-7B-Q4_K_M.gguf"
if [ -f "$_DSR1_SCRIPT" ] && [ -f "$_DSR1_MODEL" ]; then
  echo "Starting local_deepseek llama-server on port 8081..."
  nohup "$_DSR1_SCRIPT" > "$DIR/llama-deepseek.log" 2>&1 &
  echo $! > "$DIR/llama-deepseek.pid"
  echo "local_deepseek PID: $(cat $DIR/llama-deepseek.pid)"
fi
unset _DSR1_SCRIPT _DSR1_MODEL

# ── Start backend ──────────────────────────────────────────────────────────────
cd "$DIR/backend"
echo "Starting backend on port 8159..."
nohup "$DIR/.venv/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8159 > "$DIR/backend.log" 2>&1 &
echo $! > "$DIR/backend.pid"
echo "Backend PID: $(cat $DIR/backend.pid)"

# ── Start frontend dev server ──────────────────────────────────────────────────
cd "$DIR/frontend"
echo "Starting frontend on port 5159..."
nohup npm run dev -- --host 0.0.0.0 --port 5159 > "$DIR/frontend.log" 2>&1 &
echo $! > "$DIR/frontend.pid"
echo "Frontend PID: $(cat $DIR/frontend.pid), port 5159"

echo "All services started."
