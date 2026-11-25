"""Generate, show and freeze six-type dailies (data/typed_dailies.json).

Frozen days are served exactly as stored. Each day's board is seeded by its
date, and a History of the frozen days before it keeps runs from repeating
ends, links, features and hub words.

    python scripts/freeze_typed_dailies.py --from 2027-01-09 --through 2027-02-05   # freeze a month
    python scripts/freeze_typed_dailies.py --show --from 2027-01-09 --days 28        # review
    python scripts/freeze_typed_dailies.py --reroll 2027-01-12 2027-01-20            # swap bad days

--from defaults to the day after the last frozen day, or DEGREES_SIXTYPE_FROM
when none are frozen yet. --reroll keeps the neighbours and tries new seeds
until the start/target pair changes; re-rolled days need reviewing again.
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.sixtype.board import Board, History, assess, build_board, daily_history  # noqa: E402
from app.sixtype.dailies import TypedDailies, load_typed, problem, save_typed  # noqa: E402
from app.sixtype.engine import TypedPuzzle  # noqa: E402
from app.sixtype.links import TYPE_NAMES, Links, load  # noqa: E402

MAX_SALTS = 40


def history_before(links: Links, frozen: dict[dt.date, TypedPuzzle], day: dt.date) -> History:
    h = daily_history()
    for d in sorted(frozen):
        if d >= day:
            break
        p = frozen[d]
        h.record(Board(p.start, p.target, list(p.route), list(p.route_types), list(p.tiles), {}), links)
    return h


def clash_after(links: Links, frozen: dict[dt.date, TypedPuzzle], day: dt.date, p: TypedPuzzle) -> str | None:
    """Why `p` on `day` breaks the run rules against the frozen days after
    it, or None. History only looks back, so a re-roll checks forward here:
    the same windows, measured from the following days."""
    h = daily_history()
    features = {f for (a, b), t in zip(zip(p.route, p.route[1:]), p.route_types) if t == "feature"
                for f in links.shared_features(a, b)}
    edges = {frozenset(e) for e in zip(p.route, p.route[1:])}
    for i in range(1, h.window + 1):
        q = frozen.get(day + dt.timedelta(days=i))
        if q is None:
            continue
        if {p.start, p.target} & {q.start, q.target}:
            return f"end word repeats {day + dt.timedelta(days=i)}"
        if i <= h.edge_window and edges & {frozenset(e) for e in zip(q.route, q.route[1:])}:
            return f"route link repeats {day + dt.timedelta(days=i)}"
        if i <= h.feature_window and features & {
                f for (a, b), t in zip(zip(q.route, q.route[1:]), q.route_types) if t == "feature"
                for f in links.shared_features(a, b)}:
            return f"feature repeats {day + dt.timedelta(days=i)}"
    return None


def generate(links: Links, frozen: dict[dt.date, TypedPuzzle], day: dt.date, salt: int = 0) -> TypedPuzzle | None:
    rng = random.Random(f"{settings.seed}-{day.isoformat()}-{salt}")
    made = build_board(links, rng, history=history_before(links, frozen, day))
    if made is None:
        return None
    b, _ = made
    return TypedPuzzle(b.start, b.target, tuple(b.route), tuple(b.route_types), tuple(b.tiles))


def show(links: Links, dailies: TypedDailies, day: dt.date) -> None:
    p = dailies.puzzle(day)
    if p is None:
        print(f"#{dailies.number(day):<4} {day} {day:%a}  (not frozen)")
        return
    a = assess(links, Board(p.start, p.target, list(p.route), list(p.route_types), list(p.tiles), {}),
               random.Random(0), walks=1000)
    bad = problem(links, p)
    print(f"#{dailies.number(day):<4} {day} {day:%a}  {p.start} -> {p.target}"
          + (f"  INVALID: {bad}" if bad else ""))
    for x, y, t in zip(p.route, p.route[1:], p.route_types):
        print(f"      {TYPE_NAMES[t]:<18} {links.types(x, y)[t]}")
    print(f"      tiles: {', '.join(p.tiles)}")
    print(f"      solutions {len(a.solutions)}, traps {len(a.traps)}, random win {a.random_win_rate:.0%}, "
          f"first/last moves {a.first_moves}/{a.last_moves}, apart {a.global_distance}"
          + (f", look-alikes: {', '.join('/'.join(q) for q in a.look_alikes)}" if a.look_alikes else ""))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="start", type=dt.date.fromisoformat)
    ap.add_argument("--through", type=dt.date.fromisoformat)
    ap.add_argument("--reroll", nargs="+", type=dt.date.fromisoformat, default=[])
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--days", type=int, default=7, help="with --show: how many days")
    args = ap.parse_args()
    if not (args.through or args.reroll or args.show):
        ap.error("nothing to do")

    links = load(settings.typed_links_path)
    path = settings.typed_dailies_path
    frozen = load_typed(path)
    changed = False

    if args.through:
        first = args.start or (max(frozen) + dt.timedelta(days=1) if frozen else settings.sixtype_from)
        if first is None:
            sys.exit("Pass --from (or set DEGREES_SIXTYPE_FROM): no six-type days are frozen yet.")
        if frozen and first != max(frozen) + dt.timedelta(days=1):
            sys.exit(f"Frozen days end {max(frozen)}; --from must be the day after, so there are no gaps.")
        day = first
        while day <= args.through:
            p = generate(links, frozen, day)
            if p is None:
                sys.exit(f"No board found for {day}; nothing saved past {day - dt.timedelta(days=1)}.")
            frozen[day] = p
            print(f"Froze {day}: {p.start} -> {p.target}")
            day += dt.timedelta(days=1)
        changed = True

    for day in args.reroll:
        old = frozen.get(day)
        if old is None:
            sys.exit(f"{day} isn't frozen; only frozen days can be re-rolled.")
        rest = {d: p for d, p in frozen.items() if d != day}
        for salt in range(1, MAX_SALTS + 1):
            new = generate(links, rest, day, salt)
            if new and (new.start, new.target) != (old.start, old.target) \
                    and clash_after(links, rest, day, new) is None:
                break
        else:
            sys.exit(f"No new board for {day} after {MAX_SALTS} seeds.")
        frozen[day] = new
        print(f"Re-rolled {day}: {old.start} -> {old.target}  =>  {new.start} -> {new.target}")
        changed = True

    dailies = TypedDailies(links, settings.daily_epoch, frozen)
    if changed:
        bad = dailies.problems()
        if bad:
            sys.exit("Not saved; invalid: " + "; ".join(f"{d}: {m}" for d, m in sorted(bad.items())))
        save_typed(path, frozen)
        print(f"Saved {len(frozen)} six-type dailies ({min(frozen)} .. {max(frozen)}) to {path}.")

    if args.show:
        first = args.start or (min(frozen) if frozen else settings.sixtype_from)
        if first is None:
            sys.exit("Nothing to show: pass --from.")
        for i in range(args.days):
            show(links, dailies, first + dt.timedelta(days=i))


if __name__ == "__main__":
    main()
