"""Preview upcoming daily puzzles exactly as players will get them.

Dailies are seeded by date, so future puzzles are known today. For each day
this prints the start/target, par, and the par route with the relation label
and cosine similarity of every link, then flags things worth a human look:

    weak     a non-curated link whose similarity is in the bottom 15% of all links
    repeat   start or target word already used by another daily in the window

    python scripts/preview_dailies.py                 # next 14 days from today
    python scripts/preview_dailies.py --from 2026-11-01 --days 30

Note: changing the word list, vectors, relations or DEGREES_SEED changes every
daily, past and future. Re-run this after any such change.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.embeddings import Embeddings  # noqa: E402
from app.game import Engine  # noqa: E402
from app.graph import WordGraph  # noqa: E402
from app.relations import RelationOverlay  # noqa: E402
from app.wordnet_relations import WordNetLabeler  # noqa: E402

WEAK_PERCENTILE = 15


def build_engine() -> Engine:
    """Same construction as app/main.py."""
    emb = Embeddings.load(settings)
    overlay = (
        RelationOverlay.load(settings.relations_path, emb)
        if settings.use_relations
        else RelationOverlay.empty()
    )
    graph = WordGraph(emb, k=settings.k, rng=np.random.default_rng(settings.seed),
                      extra_edges=overlay.edges)
    labeler = WordNetLabeler()
    if not labeler.enabled:
        sys.exit("WordNet corpus missing: these previews would not match production.")
    return Engine(emb, graph, settings, overlay=overlay, labeler=labeler)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="start", type=dt.date.fromisoformat, default=dt.date.today())
    parser.add_argument("--days", type=int, default=14)
    args = parser.parse_args()

    logging.disable(logging.INFO)
    engine = build_engine()
    if engine.embeddings.synthetic:
        sys.exit("Synthetic embeddings loaded: build real vectors first.")
    vec, idx = engine.embeddings.vectors, engine.embeddings.index

    edge_sims = [float(vec[i] @ vec[j]) for i in range(engine.graph.n)
                 for j in engine.graph.neighbors(i) if i < j]
    weak_cutoff = float(np.percentile(edge_sims, WEAK_PERCENTILE))

    games = [(args.start + dt.timedelta(days=d), None) for d in range(args.days)]
    games = [(day, engine.daily_game(day)) for day, _ in games]
    seen = collections.Counter(w for _, g in games for w in (g.start, g.target))

    par_counts: collections.Counter[int] = collections.Counter()
    flagged = 0
    print(f"Daily puzzles {args.start} .. {games[-1][0]}  "
          f"(weak link = similarity < {weak_cutoff:.2f}, bottom {WEAK_PERCENTILE}%)\n")
    for day, game in games:
        par_counts[game.optimal_distance] += 1
        route = game.optimal_path
        links = []
        flags = []
        for a, b in zip(route, route[1:]):
            label = engine._label_edge(idx[a], idx[b])
            sim = float(vec[idx[a]] @ vec[idx[b]])
            # Hand-curated overlay links are deliberate even when the vectors
            # disagree (sand-glass), so only embedding links can be weak.
            curated = engine.overlay is not None and engine.overlay.label_for(idx[a], idx[b])
            weak = sim < weak_cutoff and not curated
            links.append(f"{a} -[{label} {sim:.2f}{' WEAK' if weak else ''}]->")
            if weak:
                flags.append(f"weak {a}-{b}")
        for word in (game.start, game.target):
            if seen[word] > 1:
                flags.append(f"repeat '{word}'")
        flagged += bool(flags)

        print(f"#{game.daily_number:<4} {day} {day.strftime('%a')}  "
              f"{game.start} -> {game.target}  par {game.optimal_distance}")
        print(f"      {' '.join(links)} {route[-1]}")
        if flags:
            print(f"      FLAGS: {'; '.join(flags)}")
        print()

    print(f"Par mix: {dict(sorted(par_counts.items()))}  |  flagged: {flagged}/{len(games)}")


if __name__ == "__main__":
    main()
