#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

( cd services/agent && ./.venv/bin/uvicorn main:app --reload --port 8000 ) &
AGENT_PID=$!
( cd apps/web && npm run dev ) &
WEB_PID=$!

trap "kill $AGENT_PID $WEB_PID 2>/dev/null || true" EXIT
wait
