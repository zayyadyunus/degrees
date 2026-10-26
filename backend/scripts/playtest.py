"""Difficulty play-test: inspect the real-embeddings graph and sample puzzles."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.embeddings import Embeddings  # noqa: E402
from app.game import Engine  # noqa: E402
from app.graph import WordGraph  # noqa: E402


def build(k: int) -> Engine:
    emb = Embeddings.load(settings)
    graph = WordGraph(emb, k=k, rng=np.random.default_rng(settings.seed))
    return Engine(emb, graph, settings)


def neighbors_of(engine: Engine, word: str, k: int = 8) -> list[str]:
    i = engine.embeddings.index[word]
    nbs = engine.graph.neighbors(i)
    sims = engine.embeddings.vectors[i] @ engine.embeddings.vectors[nbs].T
    order = np.argsort(-sims)[:k]
    return [f"{engine.embeddings.words[nbs[o]]}({sims[o]:.2f})" for o in order]


def run(k: int, n_puzzles: int = 12) -> None:
    print(f"\n{'='*70}\nK = {k}\n{'='*70}")
    engine = build(k)
    degrees = np.array([len(a) for a in engine.graph.adjacency])
    print(f"k={engine.graph.k}  "
          f"degree min/median/mean/max={degrees.min()}/{int(np.median(degrees))}/"
          f"{degrees.mean():.1f}/{degrees.max()}  isolated={(degrees==0).sum()}")

    print("\nSample neighborhoods (word -> nearest valid connections):")
    for w in ["ocean", "music", "money", "dog", "fire", "king"]:
        if engine.embeddings.contains(w):
            print(f"  {w:8} -> {', '.join(neighbors_of(engine, w))}")

    print(f"\n{n_puzzles} generated puzzles (start -> target, optimal path):")
    for _ in range(n_puzzles):
        g = engine.new_game()
        print(f"  [{g.optimal_distance}] {g.start} -> {g.target}:  "
              f"{' -> '.join(g.optimal_path)}")


if __name__ == "__main__":
    for k in (8, 12, 16):
        run(k)
