"""The daily puzzle schedule: frozen (reviewed) days plus generated ones.

Puzzle #1 falls on the epoch date. Days stored in data/dailies.json are
*frozen*: served exactly as reviewed, whatever later happens to the word data.
Days past the frozen range are generated in order, each one:

- aiming for the par its weekday asks for (an easy-Monday to hard-Saturday
  ramp, `daily_par_by_weekday`), and
- avoiding words recent dailies used (`daily_fresh_*_days`),

relaxing those preferences rather than failing when a day can't meet them.
Generation is deterministic for a given dataset, so previews match what
players will get. `scripts/freeze_dailies.py` freezes, re-rolls and unfreezes.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .game import Engine, Puzzle

logger = logging.getLogger("degrees.dailies")


def load_frozen(path: Path) -> dict[dt.date, "Puzzle"]:
    from .game import Puzzle

    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        dt.date.fromisoformat(d["date"]): Puzzle(
            start=d["start"],
            target=d["target"],
            optimal_distance=int(d["par"]),
            optimal_path=tuple(d["route"]),
        )
        for d in raw["dailies"]
    }


def save_frozen(path: Path, frozen: dict[dt.date, "Puzzle"]) -> None:
    entries = [
        {
            "date": day.isoformat(),
            "start": p.start,
            "target": p.target,
            "par": p.optimal_distance,
            "route": list(p.optimal_path),
        }
        for day, p in sorted(frozen.items())
    ]
    path.write_text(json.dumps({"dailies": entries}, indent=2) + "\n", encoding="utf-8")


class DailySchedule:
    def __init__(self, engine: "Engine", settings, frozen: dict[dt.date, "Puzzle"] | None = None):
        self.engine = engine
        self.settings = settings
        self.epoch: dt.date = settings.daily_epoch
        self.frozen = dict(frozen or {})
        # Frozen days that no longer match the word data. The app refuses to
        # start with any (see bootstrap); the freeze script uses this list to
        # re-roll them.
        self.problems: dict[dt.date | None, str] = self._check_frozen()
        # Index 0 is the epoch. Frozen days first, then generated on demand.
        self._days: list[Puzzle] = [self.frozen[d] for d in sorted(self.frozen)]
        self._lock = threading.Lock()

    # -- lookup ------------------------------------------------------------
    def number(self, day: dt.date) -> int:
        """Puzzle #1 is the epoch date; one new puzzle per day after."""
        return (day - self.epoch).days + 1

    def is_frozen(self, day: dt.date) -> bool:
        return day in self.frozen

    def puzzle(self, day: dt.date) -> "Puzzle":
        index = self.number(day) - 1
        if index < 0:
            raise ValueError("no daily puzzle before the epoch")
        with self._lock:
            while len(self._days) <= index:
                self._days.append(self._pick(len(self._days), self._days, []))
            return self._days[index]

    def reroll(self, day: dt.date, salt: int, par: int | None = None) -> "Puzzle":
        """A replacement for a frozen `day` that keeps its neighbours valid.

        Avoids recent words on *both* sides, so swapping one reviewed day
        doesn't break the no-repeat rules for the frozen days after it, and
        never returns the puzzle it replaces. `par` overrides the weekday's
        par (e.g. a gentler launch day).
        """
        index = self.number(day) - 1
        days = [self.frozen[d] for d in sorted(self.frozen)]
        if not 0 <= index < len(days):
            raise ValueError(f"{day} is not a frozen day")
        current = days[index]
        return self._pick(index, days[:index], days[index + 1:], salt=salt, exclude=current, par=par)

    # -- generation --------------------------------------------------------
    def _pick(
        self,
        index: int,
        before: list["Puzzle"],
        after: list["Puzzle"],
        salt: int = 0,
        exclude: "Puzzle | None" = None,
        par: int | None = None,
    ) -> "Puzzle":
        s, engine = self.settings, self.engine
        day = self.epoch + dt.timedelta(days=index)
        I = engine.embeddings.index

        def window(days: int) -> list["Puzzle"]:
            if not days:
                return []
            return before[-days:] + after[:days]

        recent_ends = {I[w] for p in window(s.daily_fresh_ends_days) for w in (p.start, p.target) if w in I}
        recent_route = {I[w] for p in window(s.daily_fresh_route_days) for w in p.optimal_path if w in I}
        # A re-roll must differ: never the same start or target again.
        replaced_ends = (
            {I[w] for w in (exclude.start, exclude.target) if w in I} if exclude is not None else set()
        )
        recent_ends |= replaced_ends
        # A start/target pair is never reused, in either direction, ever.
        used_pairs = frozenset(
            frozenset((I[p.start], I[p.target]))
            for p in before + after
            if p.start in I and p.target in I
        )

        want = par if par is not None else s.daily_par_by_weekday[day.weekday()]
        lowest, highest = s.min_puzzle_distance, s.max_connections
        pars = [p for p in (want, want - 1, want + 1) if lowest <= p <= highest]
        # Strictest first: exact par before neighbouring pars; within a par,
        # drop the mid-route rule, then the route-word rule, then all but
        # "not the puzzle being replaced".
        rule_levels = [
            (recent_ends | recent_route, recent_route),
            (recent_ends, recent_route),
            (recent_ends, set()),
            (replaced_ends, set()),
        ]
        for got in pars:
            for level, (ends, via) in enumerate(rule_levels):
                rng = np.random.default_rng([s.seed, day.toordinal(), salt])
                puzzle = engine._find_puzzle(rng, got, got, frozenset(ends), frozenset(via), used_pairs)
                if puzzle is None:
                    continue
                if got != want or level:
                    logger.warning(
                        "Daily %s: wanted par %d, got par %d (rule relax level %d).",
                        day, want, got, level,
                    )
                return puzzle
        from .game import PuzzleUnavailable

        raise PuzzleUnavailable(f"no daily puzzle for {day}")

    # -- validation ---------------------------------------------------------
    def _check_frozen(self) -> dict[dt.date | None, str]:
        """Frozen days must still be playable exactly as reviewed.

        Returns {day: problem}; the None key is a schedule-wide problem.
        """
        if not self.frozen:
            return {}
        I, graph = self.engine.embeddings.index, self.engine.graph
        problems: dict[dt.date | None, str] = {}
        days = sorted(self.frozen)
        expected = [self.epoch + dt.timedelta(days=i) for i in range(len(days))]
        if days != expected:
            problems[None] = (
                f"frozen dates must run without gaps from the epoch {self.epoch} "
                f"(got {days[0]} .. {days[-1]}, {len(days)} days)"
            )
        for day in days:
            p = self.frozen[day]
            route = p.optimal_path
            missing = [w for w in route if w not in I]
            if missing:
                problems[day] = f"not in vocabulary: {', '.join(missing)}"
                continue
            if route[0] != p.start or route[-1] != p.target or len(route) - 1 != p.optimal_distance:
                problems[day] = "route doesn't match start/target/par"
                continue
            broken = [f"{a}-{b}" for a, b in zip(route, route[1:]) if not graph.connected(I[a], I[b])]
            if broken:
                problems[day] = f"no longer linked: {', '.join(broken)}"
                continue
            par_now = int(graph.distances(I[p.start])[0][I[p.target]])
            if par_now != p.optimal_distance:
                problems[day] = f"par is now {par_now}, frozen as {p.optimal_distance}"
        return problems

    def raise_if_invalid(self) -> None:
        """Refuse to serve a daily whose route or par no longer holds."""
        if self.problems:
            lines = [f"{day or 'schedule'}: {msg}" for day, msg in self.problems.items()]
            raise ValueError(
                "Frozen dailies don't match the current word data:\n  "
                + "\n  ".join(lines)
                + "\nRe-roll them (scripts/freeze_dailies.py --reroll-invalid) "
                "or revert the data change."
            )
