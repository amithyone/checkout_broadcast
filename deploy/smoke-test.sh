#!/usr/bin/env bash
# Smoke test: local bank_api + register terminal + demo-send + verify-broadcast
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${ROOT}/.venv/bin/python3.14"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="${ROOT}/.venv/bin/python"
fi
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="python3"
fi

export CHECKOUT_BANK_ADMIN_KEY="${CHECKOUT_BANK_ADMIN_KEY:-smoke-test-admin-key}"
export CHECKOUT_SIGNING_KEY="${CHECKOUT_SIGNING_KEY:-test-signing-key-min-16-chars}"
export CHECKOUT_BANK_DB="${CHECKOUT_BANK_DB:-/tmp/checkout-broadcast-smoke.db}"
export CHECKOUT_BIND_PUBLIC="${CHECKOUT_BIND_PUBLIC:-false}"
export PYTHONPATH="sdk/python:."

rm -f "$CHECKOUT_BANK_DB"
"$PYTHON" -m checkout_broadcast.cli run-bank &
BANK_PID=$!
trap 'kill "$BANK_PID" 2>/dev/null || true' EXIT

for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8090/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

curl -sf "http://127.0.0.1:8090/health" | "$PYTHON" -m json.tool

"$PYTHON" -m checkout_broadcast.cli register-terminal \
  --bank-url "http://127.0.0.1:8090" \
  --id "POS-SMOKE-001" \
  --merchant "Smoke Test Merchant"

"$PYTHON" -m checkout_broadcast.cli demo-send \
  --amount 3200 \
  --bank-url "http://127.0.0.1:8090" \
  --terminal-id "POS-SMOKE-001"

echo "smoke-test: OK — bank_api verify-broadcast path works locally"
echo "Production: deploy Laravel controller or sidecar per deploy/checkoutpay-production.md"
