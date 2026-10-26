"""End-to-end API smoke test against a running server.

Plays today's daily (typo, strike, hints, win), checks daily determinism and
the solution reveal, then strikes out a practice game. Exits non-zero on
failure.

    python scripts/smoke_api.py http://localhost:8000
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"

# Real words that rarely connect to anything random. One may still connect by
# chance (~2-3% each), so strike() tries them in turn.
FAR_WORDS = ("banana", "volcano", "pencil", "elephant", "carrot", "bridge", "violin", "blanket")

failures: list[str] = []


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{f'  ({detail})' if detail else ''}")
    if not ok:
        failures.append(label)


def strike(game: dict) -> tuple[dict, dict]:
    """Play far words until one is rejected with a strike. Returns (response, game)."""
    for word in FAR_WORDS:
        if word in game["path"] or word == game["target"]:
            continue
        _, r = call("POST", f"/games/{game['id']}/moves", {"word": word})
        game = r["game"]
        if r["strike"] or game["status"] != "in_progress":
            return r, game
    raise SystemExit("every far word connected; pick different FAR_WORDS")


# -- health ---------------------------------------------------------------
status, health = call("GET", "/health")
check(status == 200 and not health["synthetic_embeddings"], "health: real embeddings",
      f"vocabulary={health['vocabulary']}" if status == 200 else str(status))

# -- daily ----------------------------------------------------------------
today = dt.date.today().isoformat()
_, game = call("POST", "/games", {"daily": True, "date": today})
_, again = call("POST", "/games", {"daily": True, "date": today})
check((game["start"], game["target"]) == (again["start"], again["target"]),
      "daily is the same puzzle on every request",
      f"#{game['daily_number']} {game['start']} -> {game['target']}, par {game['optimal_distance']}")
check(game["solution"] is None, "solution hidden while playing")
status, _ = call("POST", "/games", {"daily": True, "date": "2099-01-01"})
check(status == 400, "future daily refused", str(status))

# -- typos, strikes, validation --------------------------------------------
_, r = call("POST", f"/games/{game['id']}/moves", {"word": "zzzzqx"})
check(not r["strike"] and r["game"]["strikes"] == 0, "typo is free")
r, game = strike(r["game"])
check(game["strikes"] == 1, "unconnected word costs a strike", r["reason"] or "")
status, _ = call("POST", f"/games/{game['id']}/moves", {"word": "x" * 65})
check(status == 422, "over-long word rejected", str(status))

# -- hints to the finish ----------------------------------------------------
accidental = game["connections_used"]  # far words that happened to connect
for _ in range(game["max_connections"]):
    _, h = call("POST", f"/games/{game['id']}/hint")
    if not h["hint"]:
        break
    _, r = call("POST", f"/games/{game['id']}/moves", {"word": h["hint"]})
    game = r["game"]
    if game["status"] != "in_progress":
        break
check(game["status"] == "won", "following hints wins", " -> ".join(game["path"]))
if accidental == 0:
    check(game["connections_used"] == game["optimal_distance"], "hints reach par")
check(game["hints_used"] >= 1 and "hint" in game["events"], "hints are recorded",
      f"{game['hints_used']} hints")
check(bool(game["solution"]), "solution revealed at the end", " -> ".join(game["solution"] or []))

# -- practice: strike out ---------------------------------------------------
_, practice = call("POST", "/games", {})
while practice["status"] == "in_progress":
    _, practice = strike(practice)
check(practice["status"] == "lost" and practice["strikes"] == practice["max_strikes"]
      and bool(practice["solution"]), "three strikes loses and reveals the solution")

# -- info ---------------------------------------------------------------------
status, _ = call("GET", "/docs")
print(f"info  /docs -> {status} (404 expected in production)")

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {', '.join(failures)}")
sys.exit(1 if failures else 0)
