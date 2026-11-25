"""Build the six-type practice pool (data/typed_practice.json).

A board takes up to a few seconds to generate, too slow per request, so
practice games draw from a pool built here and checked at startup like the
dailies. One History runs across the pool so consecutive boards differ.

    python scripts/build_typed_practice.py --n 300
    python scripts/build_typed_practice.py --repair   # replace only boards the data now breaks

--repair keeps every board that still passes the checks (they may have been
reviewed) and swaps each failing one for a new board in the same slot.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.sixtype.board import History, build_board  # noqa: E402
from app.sixtype.dailies import load_practice, problem  # noqa: E402
from app.sixtype.engine import TypedPuzzle  # noqa: E402
from app.sixtype.links import load  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=settings.seed)
    ap.add_argument("--repair", action="store_true")
    args = ap.parse_args()

    links = load(settings.typed_links_path)
    if args.repair:
        repair(links, args.seed)
        return
    rng, history = random.Random(args.seed), History()
    boards, misses = [], 0
    while len(boards) < args.n and misses < args.n:
        made = build_board(links, rng, history=history)
        if made is None:
            misses += 1
            continue
        b, _ = made
        p = TypedPuzzle(b.start, b.target, tuple(b.route), tuple(b.route_types), tuple(b.tiles))
        assert problem(links, p) is None, (p, problem(links, p))
        boards.append({"start": p.start, "target": p.target, "route": list(p.route),
                       "route_types": list(p.route_types), "tiles": list(p.tiles)})
        if len(boards) % 25 == 0:
            print(f"  {len(boards)} boards")
    settings.typed_practice_path.write_text(json.dumps({"boards": boards}, indent=1) + "\n")
    print(f"Saved {len(boards)} practice boards to {settings.typed_practice_path} ({misses} misses).")


def as_row(p: TypedPuzzle) -> dict:
    return {"start": p.start, "target": p.target, "route": list(p.route),
            "route_types": list(p.route_types), "tiles": list(p.tiles)}


def repair(links, seed: int) -> None:
    pool = load_practice(settings.typed_practice_path)
    bad = [i for i, p in enumerate(pool) if problem(links, p)]
    if not bad:
        print("Every practice board passes; nothing to repair.")
        return
    # Avoid the kept boards' start/target pairs, and lean on History so the
    # replacements don't all land on the same hubs.
    rng, history = random.Random(f"{seed}-repair"), History()
    taken = {(p.start, p.target) for i, p in enumerate(pool) if i not in bad}
    for i in bad:
        old = pool[i]
        while True:
            made = build_board(links, rng, history=history)
            if made is None:
                continue
            b, _ = made
            new = TypedPuzzle(b.start, b.target, tuple(b.route), tuple(b.route_types), tuple(b.tiles))
            if (new.start, new.target) not in taken and problem(links, new) is None:
                break
        taken.add((new.start, new.target))
        pool[i] = new
        print(f"  P{i}: {old.start} -> {old.target}  =>  {new.start} -> {new.target}  ({problem(links, old)})")
    settings.typed_practice_path.write_text(
        json.dumps({"boards": [as_row(p) for p in pool]}, indent=1) + "\n")
    print(f"Replaced {len(bad)} of {len(pool)} practice boards: {', '.join(f'P{i}' for i in bad)}")


if __name__ == "__main__":
    main()
