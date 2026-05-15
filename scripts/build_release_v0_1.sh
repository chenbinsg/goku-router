#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VERSION="V0.1"
VERSION_SLUG="v0.1"
STAMP="$(date +%Y%m%d_%H%M%S)"
RELEASE_BASE="$ROOT_DIR/releases/$VERSION"
PACKAGE_DIR="$RELEASE_BASE/router-$VERSION_SLUG"
ARCHIVE_PATH="$RELEASE_BASE/router-$VERSION_SLUG-$STAMP.tar.gz"

echo "[1/7] Preparing release directories..."
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR/backend" "$PACKAGE_DIR/frontend" "$PACKAGE_DIR/scripts" "$PACKAGE_DIR/docs"
mkdir -p "$RELEASE_BASE"

echo "[2/7] Running backend tests..."
(
  cd "$ROOT_DIR/backend"
  pytest -q
)

echo "[3/7] Running frontend checks and production build..."
(
  cd "$ROOT_DIR/frontend"
  npm run typecheck
  npm run build
)

echo "[4/7] Copying application artifacts and data snapshot..."
cp "$ROOT_DIR/VERSION" "$PACKAGE_DIR/VERSION"
cp "$ROOT_DIR/start.sh" "$PACKAGE_DIR/start.dev.sh"
cp "$ROOT_DIR/stop.sh" "$PACKAGE_DIR/stop.dev.sh"
cp "$ROOT_DIR/backend/requirements.txt" "$PACKAGE_DIR/backend/requirements.txt"
cp "$ROOT_DIR/backend/app.db" "$PACKAGE_DIR/backend/app.db"
cp -R "$ROOT_DIR/backend/app" "$PACKAGE_DIR/backend/app"
cp -R "$ROOT_DIR/backend/evals" "$PACKAGE_DIR/backend/evals"
cp -R "$ROOT_DIR/database" "$PACKAGE_DIR/database"
cp -R "$ROOT_DIR/frontend/dist" "$PACKAGE_DIR/frontend/dist"
cp "$ROOT_DIR/scripts/serve_frontend.py" "$PACKAGE_DIR/scripts/serve_frontend.py"
find "$PACKAGE_DIR" -type d -name "__pycache__" -prune -exec rm -rf {} +
find "$PACKAGE_DIR" -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.log" -o -name "*.pid" \) -delete

echo "[5/7] Writing sanitized runtime files..."
cat > "$PACKAGE_DIR/.env.example" <<'EOF'
APP_ENV=prod
DATABASE_URL=sqlite:///./backend/app.db
ROUTER_API_KEYS=demo-router-key

# Configure your upstream providers before sending real traffic.
# Do not commit real API keys into source control or release bundles.
PROVIDER_PROVIDER_PRIMARY_BASE_URL=
PROVIDER_PROVIDER_PRIMARY_API_KEY=
PROVIDER_PROVIDER_BACKUP_BASE_URL=
PROVIDER_PROVIDER_BACKUP_API_KEY=
EOF

cat > "$PACKAGE_DIR/start.sh" <<'EOF'
#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

if [ -f "$DIR/.env" ]; then
  set -a
  . "$DIR/.env"
  set +a
fi

PYTHON_BIN="${PYTHON_BIN:-python3}"
if [ -d "$DIR/.venv" ]; then
  PYTHON_BIN="$DIR/.venv/bin/python"
fi

BACKEND_PORT="${BACKEND_PORT:-8159}"
FRONTEND_PORT="${FRONTEND_PORT:-5159}"

cd "$DIR/backend"
nohup "$PYTHON_BIN" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > "$DIR/backend.log" 2>&1 &
echo $! > "$DIR/backend.pid"

cd "$DIR"
nohup "$PYTHON_BIN" "$DIR/scripts/serve_frontend.py" --root "$DIR/frontend/dist" --host 0.0.0.0 --port "$FRONTEND_PORT" > "$DIR/frontend.log" 2>&1 &
echo $! > "$DIR/frontend.pid"

echo "Router $DIR started."
echo "Backend:  http://127.0.0.1:$BACKEND_PORT"
echo "Frontend: http://127.0.0.1:$FRONTEND_PORT"
EOF

cat > "$PACKAGE_DIR/stop.sh" <<'EOF'
#!/bin/bash
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

for pidfile in backend.pid frontend.pid; do
  if [ -f "$pidfile" ]; then
    PID="$(cat "$pidfile")"
    if kill -0 "$PID" 2>/dev/null; then
      kill "$PID"
    fi
    rm -f "$pidfile"
  fi
done

echo "Router services stopped."
EOF

cat > "$PACKAGE_DIR/RELEASE_MANIFEST.md" <<EOF
# Router $VERSION Release Manifest

- Version: $VERSION
- Built at: $STAMP
- Included data: \`backend/app.db\`
- Frontend mode: prebuilt static assets in \`frontend/dist\`
- Backend mode: FastAPI + Uvicorn
- Removed from package:
  - Local \`.env\`
  - Upstream LLM provider API keys
  - \`frontend/node_modules\`
  - PID files and local runtime logs

## Startup

1. Copy \`.env.example\` to \`.env\`
2. Fill provider endpoints and API keys manually
3. Run \`./start.sh\`
EOF

chmod +x "$PACKAGE_DIR/start.sh" "$PACKAGE_DIR/stop.sh" "$PACKAGE_DIR/scripts/serve_frontend.py"

echo "[6/7] Copying release documentation..."
cp "$ROOT_DIR/docs/releases/$VERSION/"*.md "$PACKAGE_DIR/docs/"

echo "[7/7] Creating archive..."
tar -czf "$ARCHIVE_PATH" -C "$RELEASE_BASE" "router-$VERSION_SLUG"

echo "Release package ready:"
echo "  Directory: $PACKAGE_DIR"
echo "  Archive:   $ARCHIVE_PATH"
