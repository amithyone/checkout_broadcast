#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -q -r requirements.txt -e .

echo "Register terminal..."
PYTHONPATH="sdk/python:." python -m checkout_broadcast.cli register-terminal

echo "Run: PYTHONPATH=sdk/python:. python -m checkout_broadcast.cli run-bank"
echo "Then: PYTHONPATH=sdk/python:. python -m checkout_broadcast.cli demo-send"
