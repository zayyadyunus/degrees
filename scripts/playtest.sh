#!/usr/bin/env bash
# Full local playtest in production mode: build the UI, start the server
# (real vectors, docs off, serving the built UI), run the API smoke test and
# the Chrome UI playtest, then stop the server.
#
#   scripts/playtest.sh [screenshot_dir]      (default: playtest-output/)
#
# Needs backend/.venv (requirements-dev.txt), frontend node_modules, and
# Google Chrome installed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$(cd "$ROOT" && mkdir -p "${1:-playtest-output}" && cd "${1:-playtest-output}" && pwd)"
PORT="${PLAYTEST_PORT:-8799}"
URL="http://127.0.0.1:$PORT"
PY="$ROOT/backend/.venv/bin/python"

echo "== build frontend"
(cd "$ROOT/frontend" && npm run build --silent >/dev/null)

echo "== start server on $URL"
cd "$ROOT/backend"
DEGREES_ALLOW_SYNTHETIC=0 DEGREES_DOCS=0 DEGREES_STATIC_DIR="$ROOT/frontend/dist" \
  "$PY" -m uvicorn app.main:app --port "$PORT" >"$OUT/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 60); do
  curl -sf "$URL/health" >/dev/null && break
  sleep 0.25
done
curl -sf "$URL/health" >/dev/null || { echo "server failed to start:"; cat "$OUT/server.log"; exit 1; }

status=0
echo "== API smoke test"
"$PY" "$ROOT/backend/scripts/smoke_api.py" "$URL" || status=1

echo "== UI playtest (Chrome)"
(cd "$ROOT/frontend" && node scripts/ui-playtest.mjs "$URL" "$OUT") || status=1

exit $status
