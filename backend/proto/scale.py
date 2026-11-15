"""How does freshness scale with vocabulary size?

Shrinks the prototype vocabulary at random (several sizes, several seeds)
and, for each, finds the longest run of days without a start or target
repeating that the generator can sustain: a History window of W boards
with no repeated end means an end word comes back after W days at the
soonest. The word-reuse cap scales with the window (4 per 10 boards).

    cd backend && .venv/bin/python -m proto.scale [--quick]
"""
from __future__ import annotations

import argparse
import math
import random
import statistics
import time
from collections import defaultdict

from .typed import History, Links, build_board, load


def restrict(links: Links, keep: set[str]) -> Links:
    """The links among `keep` only, as if the vocabulary were that small."""
    sub = Links()
    sub.words = set(links.words) & keep
    for pair, types in links.edges.items():
        if pair <= keep:
            sub.edges[pair] = dict(types)
            a, b = tuple(pair)
            sub.adj[a].add(b)
            sub.adj[b].add(a)
    sub.categories = links.categories & keep
    sub.adjectives = set(links.adjectives)
    sub.avoid = {p for p in links.avoid if p <= keep}
    sub.parents = {w: ps for w, ps in links.parents.items() if w in keep}
    return sub


def sustains(links: Links, window: int, seed: int, extra: int = 20, max_failures: int = 3) -> tuple[bool, int, int]:
    """Can the generator keep a `window`-day no-repeat-end rule going for
    window + extra boards? Returns (ok, boards built, distinct ends)."""
    rng = random.Random(seed)
    history = History(window=window, max_uses=max(4, math.ceil(0.4 * window)))
    built = failures = 0
    while built < window + extra:
        if build_board(links, rng, history=history, tries=150) is None:
            failures += 1
            if failures >= max_failures:
                break
        else:
            built += 1
    ends = {w for b in history.boards for w in (b.start, b.target)}
    return built >= window + extra, built, len(ends)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true", help="one size, one seed, for timing")
    args = ap.parse_args()
    full = load()
    nouns = sorted(full.words)
    fracs = [1.0] if args.quick else [0.4, 0.55, 0.7, 0.85, 1.0]
    seeds = [0] if args.quick else [0, 1, 2]
    windows = [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 80, 100]

    results: dict[float, list[int]] = defaultdict(list)
    for frac in fracs:
        for seed in seeds:
            keep = set(random.Random(100 + seed).sample(nouns, round(frac * len(nouns)))) if frac < 1 else set(nouns)
            links = restrict(full, keep)
            best, t0 = 0, time.time()
            for w in windows:
                ok, built, ends = sustains(links, w, seed)
                if not ok:
                    break
                best = w
            results[frac].append(best)
            print(f"  {len(keep):>3} words (seed {seed}): sustains a {best}-day window"
                  f"  [{time.time() - t0:.0f}s]", flush=True)
    print("\nwords   sustained no-repeat-end window (days, per seed)   median")
    for frac in fracs:
        n = round(frac * len(nouns))
        print(f"{n:>5}   {str(results[frac]):<45} {statistics.median(results[frac])}")


if __name__ == "__main__":
    main()
