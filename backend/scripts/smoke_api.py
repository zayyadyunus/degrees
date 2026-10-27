"""End-to-end API smoke test against a running server.

Plays today's daily (off-board word, strike, back, hints, win), checks daily determinism and
the solution reveal, then strikes out a practice game. Before launch day,
when there's no daily yet, checks the "no daily yet" reply and plays a
practice game instead. Exits non-zero on failure.

    python scripts/smoke_api.py http://localhost:8000
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"

failures: list[str] = []
linked: set[tuple[str, str]] = set()  # (game id, tile) known to link from the start


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
    """Play tiles until one is rejected with a strike, taking back any that
    connect. Returns (response, game)."""
    for word in game["tiles"]:
        if word in game["path"] or (game["id"], word) in linked:
            continue
        _, r = call("POST", f"/games/{game['id']}/moves", {"word": word})
        game = r["game"]
        if r["strike"] or game["status"] != "in_progress":
            return r, game
        linked.add((game["id"], word))  # don't spend another move on it
        _, game = call("POST", f"/games/{game['id']}/back")
    raise SystemExit("every tile connects to the start; no strike to test")


# -- health ---------------------------------------------------------------
status, health = call("GET", "/health")
check(status == 200 and not health["synthetic_embeddings"], "health: real embeddings",
      f"vocabulary={health['vocabulary']}" if status == 200 else str(status))

# -- daily ----------------------------------------------------------------
today = dt.date.today().isoformat()
status, game = call("POST", "/games", {"daily": True, "date": today})
if status == 404 and "no_daily_yet" in game:
    starts = json.loads(game)["detail"]["daily_starts"]
    check(starts > today, "before launch: no daily yet", f"dailies start {starts}")
    _, game = call("POST", "/games", {})
else:
    _, again = call("POST", "/games", {"daily": True, "date": today})
    check((game["start"], game["target"]) == (again["start"], again["target"]),
          "daily is the same puzzle on every request",
          f"#{game['daily_number']} {game['start']} -> {game['target']}, par {game['optimal_distance']}")
check(game["solution"] is None, "solution hidden while playing")
check(len(game["tiles"]) >= game["optimal_distance"] - 1, "board has tiles", ", ".join(game["tiles"]))
status, _ = call("POST", "/games", {"daily": True, "date": "2099-01-01"})
check(status == 400, "future daily refused", str(status))

# -- off-board words, strikes, back, validation ------------------------------
_, r = call("POST", f"/games/{game['id']}/moves", {"word": "zzzzqx"})
check(not r["strike"] and r["game"]["strikes"] == 0, "off-board word is free", r["reason"] or "")
status, _ = call("POST", f"/games/{game['id']}/back")
check(status == 409, "nothing to take back at the start", str(status))
r, game = strike(r["game"])
check(game["strikes"] == 1, "unconnected tile costs a strike", r["reason"] or "")
status, _ = call("POST", f"/games/{game['id']}/moves", {"word": "x" * 65})
check(status == 422, "over-long word rejected", str(status))

# -- hints to the finish ----------------------------------------------------
accidental = game["moves"]  # tiles strike() played and took back
for _ in range(game["max_moves"]):
    _, h = call("POST", f"/games/{game['id']}/hint")
    if not h["hint"]:
        break
    _, r = call("POST", f"/games/{game['id']}/moves", {"word": h["hint"]})
    game = r["game"]
    if game["status"] != "in_progress":
        break
check(game["status"] == "won", "following hints wins", " -> ".join(game["path"]))
if accidental == 0:
    check(game["moves"] == game["optimal_distance"], "hints reach par")
else:
    check("back" in game["events"] and game["moves"] == game["optimal_distance"] + accidental,
          "taken-back moves still count", f"{accidental} taken back")
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
