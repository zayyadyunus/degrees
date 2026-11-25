#!/usr/bin/env bash
# Full local playtest in production mode: build the UI, start the server
# (real vectors, docs off, serving the built UI), run the API smoke test and
# the Chrome UI playtest, then stop the server.
#
#   scripts/playtest.sh [screenshot_dir]      (default: playtest-output/)
#
# Needs backend/.venv (requirements-dev.txt), frontend node_modules, and
# Google Chrome installed.
#
# The playtest needs a daily for today, so it moves daily #1 to today
# (PLAYTEST_EPOCH to override) and ignores the frozen schedule, whose dates
# wouldn't line up. tests/test_content.py checks the real frozen file.
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
  DEGREES_DAILY_EPOCH="${PLAYTEST_EPOCH:-$(date +%F)}" DEGREES_DAILIES="$OUT/no-frozen-dailies.json" \
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

# Six-type: restart with the switch set to today and a frozen six-type
# daily whose route needs the type picker moved to today (plus a tile that doesn't link to its start,
# for the mistake check).
echo "== six-type UI playtest (Chrome)"
kill $SERVER 2>/dev/null || true
wait $SERVER 2>/dev/null || true
TODAY="${PLAYTEST_EPOCH:-$(date +%F)}"
"$PY" - "$TODAY" "$OUT" <<'PYEOF'
import json, sys
sys.path.insert(0, ".")
from app.sixtype.links import load
today, out = sys.argv[1], sys.argv[2]
links = load()

def needs_choice(d):   # a route link that fits two unspent types: the picker shows
    spent = set()
    for a, b, t in zip(d["route"], d["route"][1:], d["route_types"]):
        if len([x for x in links.types(a, b) if x not in spent]) > 1:
            return True
        spent.add(t)
    return False

dailies = json.load(open("data/typed_dailies.json"))["dailies"]
d = next((x for x in dailies if needs_choice(x)), dailies[0]) | {"date": today}
json.dump({"dailies": [d]}, open(f"{out}/typed-today.json", "w"))
d["unlinked"] = next(w for w in d["tiles"] if not links.types(d["start"], w))
json.dump(d, open(f"{out}/typed-board.json", "w"))
PYEOF
DEGREES_ALLOW_SYNTHETIC=0 DEGREES_DOCS=0 DEGREES_STATIC_DIR="$ROOT/frontend/dist" \
  DEGREES_DAILY_EPOCH="$TODAY" DEGREES_DAILIES="$OUT/no-frozen-dailies.json" \
  DEGREES_SIXTYPE_FROM="$TODAY" DEGREES_TYPED_DAILIES="$OUT/typed-today.json" \
  "$PY" -m uvicorn app.main:app --port "$PORT" >"$OUT/server-sixtype.log" 2>&1 &
SERVER=$!
for _ in $(seq 60); do
  curl -sf "$URL/health" >/dev/null && break
  sleep 0.25
done
curl -sf "$URL/health" >/dev/null || { echo "six-type server failed to start:"; cat "$OUT/server-sixtype.log"; exit 1; }
(cd "$ROOT/frontend" && node scripts/ui-playtest-sixtype.mjs "$URL" "$OUT" "$OUT/typed-board.json") || status=1

exit $status
