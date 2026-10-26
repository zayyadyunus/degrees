"""Smoke tests for the engine over synthetic embeddings.

Run from backend/:  python -m pytest    (or)   python tests/test_engine.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.embeddings import Embeddings  # noqa: E402
from app.game import STATUS_WON, Engine  # noqa: E402
from app.graph import WordGraph  # noqa: E402


def build_engine() -> Engine:
    settings.allow_synthetic = True
    emb = Embeddings.load(settings)
    graph = WordGraph(emb, k=settings.k, rng=np.random.default_rng(settings.seed))
    return Engine(emb, graph, settings)


def test_puzzle_is_solvable_within_limit():
    engine = build_engine()
    game = engine.new_game()
    assert game.start != game.target
    assert settings.min_puzzle_distance <= game.optimal_distance <= settings.max_connections
    # The generator's optimal path must be a chain the validator accepts.
    assert game.optimal_path[0] == game.start
    assert game.optimal_path[-1] == game.target


def test_optimal_path_wins_optimally():
    engine = build_engine()
    game = engine.new_game()
    for word in game.optimal_path[1:]:
        result = engine.submit(game, word)
        assert result.accepted, result.reason
    assert game.status == STATUS_WON
    score = engine.score(game)
    assert score["is_optimal"] is True
    assert score["connections_used"] == game.optimal_distance


def test_invalid_moves_rejected():
    engine = build_engine()
    game = engine.new_game()
    assert engine.submit(game, "definitelynotaword").accepted is False
    assert engine.submit(game, game.start).accepted is False  # already used


def test_hint_is_a_valid_progressing_move():
    engine = build_engine()
    game = engine.new_game()
    hint = engine.hint(game)
    assert hint is not None
    result = engine.submit(game, hint)
    assert result.accepted, result.reason


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
