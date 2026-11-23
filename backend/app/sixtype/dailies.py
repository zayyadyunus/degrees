"""Frozen six-type dailies: reviewed boards served exactly as stored.

data/typed_dailies.json holds {"dailies": [{date, start, target, route,
route_types, tiles}, ...]}. Daily numbers keep counting from the launch
epoch, so the first six-type daily follows the last classic one.

Every stored board is checked against the links at startup: the route's
links carry the types it says, it spends all six types once, its words
are on the board, and no valid chain shorter than six exists on it.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from .engine import TypedPuzzle
from .links import BOARD, CHAIN, TYPES, Links, assign_types, chains


class TypedDailiesInvalid(RuntimeError):
    pass


def load_typed(path: Path) -> dict[dt.date, TypedPuzzle]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text())
    return {
        dt.date.fromisoformat(d["date"]): TypedPuzzle(
            start=d["start"], target=d["target"], route=tuple(d["route"]),
            route_types=tuple(d["route_types"]), tiles=tuple(d["tiles"]),
        )
        for d in raw.get("dailies", [])
    }


def save_typed(path: Path, dailies: dict[dt.date, TypedPuzzle]) -> None:
    rows = [
        {"date": day.isoformat(), "start": p.start, "target": p.target, "route": list(p.route),
         "route_types": list(p.route_types), "tiles": list(p.tiles)}
        for day, p in sorted(dailies.items())
    ]
    path.write_text(json.dumps({"dailies": rows}, indent=2) + "\n")


def problem(links: Links, p: TypedPuzzle) -> str | None:
    """Why a stored board breaks the rules, or None if it's sound."""
    if len(p.route) != CHAIN + 1 or (p.route[0], p.route[-1]) != (p.start, p.target):
        return "route isn't start, five words, target"
    if sorted(p.route_types) != sorted(TYPES):
        return "route doesn't spend each type once"
    for a, b, t in zip(p.route, p.route[1:], p.route_types):
        if t not in links.types(a, b):
            return f"{a} -> {b} isn't a {t} link"
    if len(p.tiles) != BOARD or len(set(p.tiles)) != BOARD:
        return f"board needs {BOARD} different tiles"
    if not set(p.route[1:-1]) <= set(p.tiles) or {p.start, p.target} & set(p.tiles):
        return "route words aren't the board's middle tiles"
    unknown = set(p.tiles) - links.words
    if unknown:
        return f"unknown tiles: {', '.join(sorted(unknown))}"
    for c in chains(links, p.start, p.target, list(p.tiles), max_len=CHAIN - 1):
        if assign_types(links, c) is not None:
            return f"shorter chain: {' -> '.join(c)}"
    return None


class TypedDailies:
    def __init__(self, links: Links, epoch: dt.date, dailies: dict[dt.date, TypedPuzzle]):
        self.links = links
        self.epoch = epoch
        self.dailies = dailies

    def number(self, day: dt.date) -> int:
        return (day - self.epoch).days + 1

    def puzzle(self, day: dt.date) -> TypedPuzzle | None:
        return self.dailies.get(day)

    @property
    def last_day(self) -> dt.date | None:
        return max(self.dailies) if self.dailies else None

    def problems(self) -> dict[dt.date, str]:
        out = {}
        for day, p in self.dailies.items():
            why = problem(self.links, p)
            if why:
                out[day] = why
        return out

    def raise_if_invalid(self) -> None:
        bad = self.problems()
        if bad:
            lines = "; ".join(f"{d}: {m}" for d, m in sorted(bad.items()))
            raise TypedDailiesInvalid(f"six-type dailies break the rules: {lines}")
