#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "→ Installing web dependencies"
( cd apps/web && npm install )

echo "→ Creating agent virtualenv and installing dependencies"
( cd services/agent && python3 -m venv .venv && ./.venv/bin/pip install --upgrade pip && ./.venv/bin/pip install -r requirements.txt )

echo "✓ Setup complete. Run 'make dev' to start."
