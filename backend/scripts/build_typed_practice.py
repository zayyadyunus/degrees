"""Build the six-type practice pool (data/typed_practice.json).

A board takes up to a few seconds to generate, too slow per request, so
practice games draw from a pool built here and checked at startup like the
dailies. One History runs across the pool so consecutive boards differ.

    python scripts/build_typed_practice.py --n 300
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
from app.sixtype.dailies import problem  # noqa: E402
from app.sixtype.engine import TypedPuzzle  # noqa: E402
from app.sixtype.links import load  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=settings.seed)
    args = ap.parse_args()

    links = load(settings.typed_links_path)
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


if __name__ == "__main__":
    main()
