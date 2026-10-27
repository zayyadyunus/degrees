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
from app.game import STATUS_LOST, STATUS_WON, Engine  # noqa: E402
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



def _unconnected_word(engine: Engine, game) -> str:
    """A real vocabulary word that doesn't connect to the current word."""
    graph, index = engine.graph, engine.embeddings.index
    here = index[game.current_word]
    for word in engine.embeddings.words:
        if word not in game.path and not graph.connected(here, index[word]):
            return word
    raise AssertionError("every word connects")


def test_strikes_only_for_real_unconnected_words():
    engine = build_engine()
    game = engine.new_game()
    engine.submit(game, "definitelynotaword")  # typo: free
    engine.submit(game, game.start)            # repeat: free
    assert game.strikes == 0
    result = engine.submit(game, _unconnected_word(engine, game))
    assert result.strike and game.strikes == 1


def test_max_strikes_loses_and_reveals_solution():
    from app.models import GameState

    engine = build_engine()
    game = engine.new_game()
    assert GameState.from_game(game).solution is None
    for _ in range(game.max_strikes):
        engine.submit(game, _unconnected_word(engine, game))
    assert game.status == STATUS_LOST
    assert GameState.from_game(game).solution == game.optimal_path


def test_hint_counted_once_per_step():
    engine = build_engine()
    game = engine.new_game()
    first = engine.hint(game)
    assert engine.hint(game) == first
    assert game.hints_used == 1
    engine.submit(game, first)
    engine.hint(game)
    assert game.hints_used == 2
    assert game.events == ["hint", "move", "hint"]


def test_daily_puzzle_is_deterministic_per_date():
    import datetime as dt

    engine = build_engine()
    day = settings.daily_epoch + dt.timedelta(days=9)
    a, b = engine.daily_game(day), engine.daily_game(day)
    assert (a.start, a.target) == (b.start, b.target)
    assert a.id != b.id  # separate games, same puzzle
    assert a.daily_number == 10
    days = [settings.daily_epoch + dt.timedelta(days=d) for d in range(5)]
    assert len({(g.start, g.target) for g in map(engine.daily_game, days)}) > 1



def test_frozen_dailies_served_as_stored():
    import datetime as dt

    engine = build_engine()
    epoch = settings.daily_epoch
    later = engine.daily_puzzle(epoch + dt.timedelta(days=5))
    frozen_engine = Engine(engine.embeddings, engine.graph, settings, frozen_dailies={epoch: later})
    assert frozen_engine.dailies.problems == {}
    assert frozen_engine.daily_puzzle(epoch) == later
    assert frozen_engine.daily_game(epoch).daily_number == 1


def test_frozen_dailies_that_break_are_reported():
    import datetime as dt

    import pytest
    from app.game import Puzzle

    engine = build_engine()
    epoch = settings.daily_epoch
    good = engine.daily_puzzle(epoch)
    bogus = Puzzle(start=good.start, target="notaword", optimal_distance=1,
                   optimal_path=(good.start, "notaword"))
    gap = {epoch: good, epoch + dt.timedelta(days=2): good}
    for frozen in ({epoch: bogus}, gap):
        broken = Engine(engine.embeddings, engine.graph, settings, frozen_dailies=frozen)
        assert broken.dailies.problems
        with pytest.raises(ValueError):
            broken.dailies.raise_if_invalid()


def test_frozen_daily_with_demoted_link_is_reported():
    engine = build_engine()
    epoch = settings.daily_epoch
    good = engine.daily_puzzle(epoch)
    demoted = {good.optimal_path[0], good.optimal_path[1]}

    class Labeler:
        """Names every link except the frozen route's first one."""
        enabled = True

        def classify(self, a: str, b: str) -> str | None:
            return None if {a, b} == demoted else "IsA"

    relabelled = Engine(engine.embeddings, engine.graph, settings, labeler=Labeler(),
                        frozen_dailies={epoch: good})
    assert "unnamed" in relabelled.dailies.problems[epoch]


def test_reroll_replaces_one_day_and_keeps_neighbours_fresh():
    import datetime as dt

    engine = build_engine()
    epoch = settings.daily_epoch
    days = [epoch + dt.timedelta(days=d) for d in range(3)]
    frozen = {d: engine.daily_puzzle(d) for d in days}
    schedule = Engine(engine.embeddings, engine.graph, settings, frozen_dailies=frozen).dailies
    new = schedule.reroll(days[1], salt=1)
    old = frozen[days[1]]
    assert {new.start, new.target}.isdisjoint({old.start, old.target})
    neighbour_ends = {w for d in (days[0], days[2]) for w in (frozen[d].start, frozen[d].target)}
    assert {new.start, new.target}.isdisjoint(neighbour_ends)



def test_reroll_can_override_par():
    import datetime as dt

    engine = build_engine()
    epoch = settings.daily_epoch
    frozen = {epoch + dt.timedelta(days=d): engine.daily_puzzle(epoch + dt.timedelta(days=d)) for d in range(3)}
    schedule = Engine(engine.embeddings, engine.graph, settings, frozen_dailies=frozen).dailies
    want = 3 if frozen[epoch].optimal_distance != 3 else 4
    assert schedule.reroll(epoch, salt=1, par=want).optimal_distance == want


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
