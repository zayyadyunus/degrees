"""Freeze reviewed daily puzzles into data/dailies.json, and repair them.

Frozen dailies are served exactly as stored, so data fixes never reshuffle
puzzles that were reviewed or already played. Typical monthly loop:

    python scripts/preview_dailies.py --from 2026-11-23 --days 28   # review
    python scripts/freeze_dailies.py --reroll 2026-11-25 2026-12-02  # swap bad days
    python scripts/freeze_dailies.py --through 2026-12-20            # freeze the month

Commands (combine freely; applied in this order):
    --unfreeze-from DATE   drop frozen days from DATE on (pre-launch rework)
    --reroll DATE ...      replace frozen days with new picks; neighbours stay
    --par N                with --reroll: use par N instead of the weekday's
    --reroll-invalid       re-roll every frozen day the current data breaks
    --through DATE         freeze generated days up to and including DATE
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import build_engine  # noqa: E402
from app.config import settings  # noqa: E402
from app.dailies import DailySchedule, save_frozen  # noqa: E402

MAX_REROLL_TRIES = 50


def show(schedule: DailySchedule, day: dt.date, note: str = "") -> None:
    p = schedule.puzzle(day)
    print(f"  #{schedule.number(day):<4} {day} {day.strftime('%a')}  {p.start} -> {p.target}  "
          f"par {p.optimal_distance}  ({' -> '.join(p.optimal_path)}){note}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--unfreeze-from", type=dt.date.fromisoformat)
    parser.add_argument("--reroll", nargs="+", type=dt.date.fromisoformat, default=[])
    parser.add_argument("--reroll-invalid", action="store_true")
    parser.add_argument("--par", type=int, help="par for --reroll days (default: weekday ramp)")
    parser.add_argument("--through", type=dt.date.fromisoformat)
    args = parser.parse_args()
    if not (args.unfreeze_from or args.reroll or args.reroll_invalid or args.through):
        parser.error("nothing to do")

    logging.disable(logging.INFO)
    engine = build_engine(settings, strict=False)
    if not engine.labeler.enabled or engine.embeddings.synthetic:
        sys.exit("Needs real vectors and the WordNet corpus, like production.")
    frozen = dict(engine.dailies.frozen)
    path = settings.dailies_path

    def rebuild() -> DailySchedule:
        return DailySchedule(engine, settings, frozen)

    if args.unfreeze_from:
        dropped = [d for d in frozen if d >= args.unfreeze_from]
        for d in dropped:
            del frozen[d]
        print(f"Unfroze {len(dropped)} days from {args.unfreeze_from}.")

    schedule = rebuild()
    if schedule.problems.get(None):
        sys.exit(f"Schedule problem: {schedule.problems[None]}")
    to_reroll = sorted(set(args.reroll) | (set(schedule.problems) - {None} if args.reroll_invalid else set()))
    for day in to_reroll:
        if day not in frozen:
            sys.exit(f"{day} isn't frozen; only frozen days can be re-rolled.")
        old = frozen[day]
        reason = schedule.problems.get(day, "requested")
        for salt in range(1, MAX_REROLL_TRIES + 1):
            new = schedule.reroll(day, salt, par=args.par if day in args.reroll else None)
            if (new.start, new.target) != (old.start, old.target):
                break
        frozen[day] = new
        schedule = rebuild()
        print(f"Re-rolled {day} ({reason}): {old.start} -> {old.target}  =>  "
              f"{new.start} -> {new.target} par {new.optimal_distance}")

    if args.through:
        first_new = settings.daily_epoch + dt.timedelta(days=len(frozen))
        day = first_new
        while day <= args.through:
            frozen[day] = schedule.puzzle(day)
            day += dt.timedelta(days=1)
        if day > first_new:
            print(f"Froze {first_new} .. {args.through}:")
            schedule = rebuild()
            d = first_new
            while d <= args.through:
                show(schedule, d)
                d += dt.timedelta(days=1)

    remaining = rebuild().problems
    if remaining:
        sys.exit("Not saved; still invalid: " + "; ".join(f"{d}: {m}" for d, m in remaining.items()))
    save_frozen(path, frozen)
    span = f"{min(frozen)} .. {max(frozen)}" if frozen else "none"
    print(f"Saved {len(frozen)} frozen dailies ({span}) to {path}.")


if __name__ == "__main__":
    main()
