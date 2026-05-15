#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "[1/5] Backend tests"
cd "$ROOT_DIR/backend"
pytest -q

echo "[2/5] Frontend typecheck"
cd "$ROOT_DIR/frontend"
npm run typecheck

echo "[3/5] Frontend build"
npm run build

echo "[4/5] Targeted gateway regressions"
cd "$ROOT_DIR/backend"
pytest -q \
  tests/test_gateway.py::test_router_api_key_supports_environment_expiry_and_rotation \
  tests/test_gateway.py::test_environment_filters_logs_billing_and_analytics \
  tests/test_gateway.py::test_guardrail_policy_compare_export_returns_download_artifact \
  tests/test_gateway.py::test_route_scoring_replay_export_returns_download_artifact \
  tests/test_gateway.py::test_detect_anomaly_notifications_creates_notifications

echo "[5/5] Eval smoke"
python3 evals/run_eval.py --dataset evals/datasets/finance_compliance_pack.json >/tmp/router_eval_smoke.log
tail -n 20 /tmp/router_eval_smoke.log

echo "Release smoke check passed."
