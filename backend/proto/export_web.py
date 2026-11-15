"""Build the browser playtest page: a run of boards baked into one HTML file.

    cd backend && .venv/bin/python -m proto.export_web OUT.html [--n 40] [--seed 0]

Boards are generated in sequence with a History, the way dailies would be,
so board 2 respects board 1's freshness rules and so on.
"""
from __future__ import annotations

import argparse
import json
import random
from itertools import combinations
from pathlib import Path

from .typed import CHAIN, TYPE_NAMES, TYPES, History, build_board, load

TEMPLATE = Path(__file__).with_name("web") / "playtest.html"


def export(n: int, seed: int) -> list[dict]:
    links = load()
    rng, history = random.Random(seed), History()
    out = []
    while len(out) < n:
        made = build_board(links, rng, history=history)
        if made is None:
            break
        board, a = made
        words = [board.start, board.target, *board.tiles]
        edges = {}
        for x, y in combinations(sorted(words), 2):
            types = links.types(x, y)
            if types:
                edges[f"{x}|{y}"] = dict(sorted(types.items()))
        out.append({
            "start": board.start,
            "target": board.target,
            "tiles": board.tiles,
            "edges": edges,
            "solutions": [{"path": p, "types": t} for p, t in a.solutions],
            "traps": len(a.traps),
            "randomWin": round(a.random_win_rate, 3),
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    boards = export(args.n, args.seed)
    data = {"chain": CHAIN, "types": list(TYPES), "typeNames": TYPE_NAMES, "seed": args.seed, "boards": boards}
    html = TEMPLATE.read_text().replace("__DATA__", json.dumps(data, separators=(",", ":")))
    Path(args.out).write_text(html)
    print(f"wrote {len(boards)} boards to {args.out}")


if __name__ == "__main__":
    main()
