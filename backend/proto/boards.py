"""Generate prototype boards and print how they play.

    cd backend && .venv/bin/python -m proto.boards            # 10 boards
    .venv/bin/python -m proto.boards --n 30 --seed 7 --brief  # one line each
    .venv/bin/python -m proto.boards --stats                  # link coverage only
"""
from __future__ import annotations

import argparse
import random
import statistics
from collections import Counter

from .typed import NEXT_PATH, PROTO_EDGE_WINDOW, TYPE_NAMES, TYPES, History, build_board, load, look_alikes, phrase


def stats(links) -> None:
    counts = links.count_by_type()
    print(f"{len(links.words)} words, {len(links.edges)} linked pairs")
    for t in TYPES:
        has = sum(1 for w in links.words if any(t in links.types(w, n) for n in links.adj[w]))
        print(f"  {TYPE_NAMES[t]:<18} {counts[t]:>4} links   {has:>3} words have one")
    multi = sum(1 for ts in links.edges.values() if len(ts) > 1)
    print(f"  pairs with 2+ types: {multi}")
    loners = sorted(w for w in links.words if len(links.adj[w]) <= 1)
    print(f"  words with 0-1 links ({len(loners)}): {' '.join(loners)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--brief", action="store_true")
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--gaps", action="store_true", help="list unlinked pairs that look linked")
    ap.add_argument("--next", action="store_true", help="use data/typed_links.txt (the Phase 2 vocabulary)")
    args = ap.parse_args()

    links = load(NEXT_PATH) if args.next else load()
    stats(links)
    if args.gaps:
        pairs = sorted(" / ".join(sorted(p)) for p in look_alikes(links))
        print(f"\n{len(pairs)} look-alike pairs (unlinked, but close by word vector):")
        print("  " + ", ".join(pairs))
        return
    if args.stats:
        return
    rng = random.Random(args.seed)
    rows, failed, history = [], 0, History() if args.next else History(edge_window=PROTO_EDGE_WINDOW)
    for i in range(args.n):
        made = build_board(links, rng, history=history)
        if made is None:
            failed += 1
            continue
        board, a = made
        rows.append(a)
        line = (f"{board.start} -> {board.target}: {len(a.solutions)} solutions, "
                f"{len(a.traps)} traps, random win {a.random_win_rate:.0%}, "
                f"first/last moves {a.first_moves}/{a.last_moves}, apart {a.global_distance}")
        if args.brief:
            print(line)
            continue
        print(f"\n#{i + 1}  {line}")
        print(f"   tiles: {', '.join(sorted(board.tiles))}")
        print("   route:")
        for x, y, t in zip(board.route, board.route[1:], board.route_types):
            print(f"     {x} -> {y}  [{TYPE_NAMES[t]}]  {phrase(links, x, y, t)}")
        others = [s for s in a.solutions if s[0] != board.route]
        for path, types in others[:3]:
            print(f"   also: {' -> '.join(path)}  ({', '.join(TYPE_NAMES[t] for t in types)})")
        if a.look_alikes:
            print(f"   look-alikes: {', '.join('/'.join(p) for p in a.look_alikes)}")
        for trap in a.traps[:3]:
            print(f"   trap: {' -> '.join(trap)}  (needs a type twice)")

    if rows:
        print(f"\n{len(rows)} boards built, {failed} failed")
        print(f"  solutions  median {statistics.median(len(a.solutions) for a in rows)}, "
              f"max {max(len(a.solutions) for a in rows)}")
        print(f"  traps      median {statistics.median(len(a.traps) for a in rows)}")
        print(f"  random win median {statistics.median(a.random_win_rate for a in rows):.0%}")
        print(f"  ends apart {dict(sorted(Counter(a.global_distance for a in rows).items()))}")
        print(f"  most-used words {history.uses.most_common(6)}")


if __name__ == "__main__":
    main()
