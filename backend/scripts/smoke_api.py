"""End-to-end API smoke test against a running server.

Plays today's daily, or before launch day (no daily yet) a practice game,
under whichever rules the server is using:

  classic   off-board word, strike, back, hints to a win, solution reveal.
  six-type  off-board word, strike, type hint, a wrong type pick, back with
            a refund, then the board's frozen route to a win. The route comes
            from this checkout's data/typed_dailies.json and
            typed_practice.json, so the server must be serving the same data
            (it fails if the board isn't found there).

Then strikes out a practice game. Exits non-zero on failure.

    python scripts/smoke_api.py http://localhost:8000
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.sixtype.dailies import load_practice, load_typed  # noqa: E402
from app.sixtype.engine import TypedPuzzle  # noqa: E402

BASE = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"

failures: list[str] = []
linked: set[tuple[str, str]] = set()  # (game id, tile) known to link from the start


def call(method: str, path: str, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            if "json" not in r.headers.get("content-type", ""):
                return r.status, body.decode(errors="replace")[:200]   # /docs is HTML
            return r.status, json.loads(body or b"null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{f'  ({detail})' if detail else ''}")
    if not ok:
        failures.append(label)


def move(game: dict, word: str, type_: str | None = None) -> dict:
    body = {"word": word} | ({"type": type_} if type_ else {})
    _, r = call("POST", f"/games/{game['id']}/moves", body)
    return r


def strike(game: dict) -> tuple[dict, dict]:
    """Play tiles until one is rejected with a strike, taking back any that
    link. Returns (response, game). A six-type tile that fits two types
    comes back asking for a pick and spends nothing: skip it."""
    for word in game["tiles"]:
        if word in game["path"] or (game["id"], word) in linked:
            continue
        r = move(game, word)
        before = len(game["path"])
        game = r["game"]
        if r["strike"] or game["status"] != "in_progress":
            return r, game
        linked.add((game["id"], word))  # don't spend another move on it
        if len(game["path"]) > before:
            _, game = call("POST", f"/games/{game['id']}/back")
    raise SystemExit("every tile links to the start; no strike to test")


def common_checks(game: dict) -> dict:
    """Off-board word, back at the start, a strike, over-long word."""
    check(game["solution"] is None, "solution hidden while playing")
    r = move(game, "zzzzqx")
    check(not r["strike"] and r["game"]["strikes"] == 0, "off-board word is free", r["reason"] or "")
    status, _ = call("POST", f"/games/{game['id']}/back")
    check(status == 409, "nothing to take back at the start", str(status))
    r, game = strike(r["game"])
    check(game["strikes"] == 1, "unconnected tile costs a strike", r["reason"] or "")
    status, _ = call("POST", f"/games/{game['id']}/moves", {"word": "x" * 65})
    check(status == 422, "over-long word rejected", str(status))
    return game


def play_classic(game: dict) -> None:
    check(len(game["tiles"]) >= game["optimal_distance"] - 1, "board has tiles", ", ".join(game["tiles"]))
    game = common_checks(game)
    accidental = game["moves"]  # tiles strike() played and took back
    for _ in range(game["max_moves"]):
        _, h = call("POST", f"/games/{game['id']}/hint")
        if not h["hint"]:
            break
        game = move(game, h["hint"])["game"]
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


def frozen_board(game: dict) -> TypedPuzzle | None:
    """This checkout's copy of the board the server dealt."""
    if game["daily_number"] is not None:
        boards = list(load_typed(settings.typed_dailies_path).values())
    else:
        boards = load_practice(settings.typed_practice_path)
    for p in boards:
        if (p.start, p.target) == (game["start"], game["target"]) and sorted(p.tiles) == sorted(game["tiles"]):
            return p
    return None


def play_sixtype(game: dict) -> None:
    check(len(game["tiles"]) == 10 and len(game["types_left"]) == 6 and game["spent"] == [],
          "ten tiles, six types unspent", ", ".join(game["tiles"]))
    p = frozen_board(game)
    check(p is not None, "board matches this checkout's frozen data", f"{game['start']} -> {game['target']}")
    if p is None:
        return
    game = common_checks(game)
    route, types = p.route, p.route_types

    _, h = call("POST", f"/games/{game['id']}/hint")
    check(h["hint"] == types[0], "hint names the route's first type", h["message"])

    wrong = next(t["type"] for t in game["types_left"] if t["type"] != types[0])
    r = move(game, route[1], wrong)
    offered = [c["type"] for c in r.get("choices") or []]
    check(not r["accepted"] and not r["strike"] and types[0] in offered,
          "a type the link can't spend is refused, no strike", r["reason"] or "")

    r = move(game, route[1], types[0])
    check(r["accepted"] and r["type"] == types[0] and bool(r["why"]), "a link spends its type", r["why"] or "")
    _, game = call("POST", f"/games/{game['id']}/back")
    check(game["path"] == [route[0]] and len(game["types_left"]) == 6, "back refunds the type")

    for word, t in zip(route[1:], types):
        r = move(game, word, t)
        game = r["game"]
        if not r["accepted"]:
            check(False, f"route link {word} ({t}) accepted", r["reason"] or "")
            return
    check(game["status"] == "won", "the frozen route wins", " -> ".join(game["path"]))
    check(game["solution"] == list(route) and game["solution_types"] == list(types),
          "solution and its types revealed at the end")
    _, score = call("GET", f"/games/{game['id']}/score")
    check(score["rules"] == "sixtype" and score["connections_used"] == 6 and score["strikes"] == 1
          and score["hints_used"] == 1 and score["backs"] >= 1 and not score["clean"],
          "score records the strike, hint and back",
          f"strikes {score['strikes']}, hints {score['hints_used']}, backs {score['backs']}")


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
          f"#{game['daily_number']} {game['start']} -> {game['target']}")
status, _ = call("POST", "/games", {"daily": True, "date": "2099-01-01"})
check(status == 400, "future daily refused", str(status))

print(f"--  {game['rules']} rules: {'daily' if game['daily_number'] else 'practice'} "
      f"{game['start']} -> {game['target']}")
if game["rules"] == "sixtype":
    play_sixtype(game)
else:
    play_classic(game)

# -- practice: strike out ---------------------------------------------------
_, practice = call("POST", "/games", {})
while practice["status"] == "in_progress":
    _, practice = strike(practice)
check(practice["status"] == "lost" and practice["strikes"] == practice["max_strikes"]
      and bool(practice["solution"]), "three strikes loses and reveals the solution",
      f"{practice['rules']} rules")

# -- info ---------------------------------------------------------------------
status, _ = call("GET", "/docs")
print(f"info  /docs -> {status} (404 expected in production)")

print("\nALL PASSED" if not failures else f"\n{len(failures)} FAILED: {', '.join(failures)}")
sys.exit(1 if failures else 0)
