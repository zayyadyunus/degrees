"""Content checks on the real shipped data: every example the game teaches
must actually be accepted, and par routes must use only named links.

Run from backend/:  python -m pytest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.bootstrap import build_engine  # noqa: E402
from app.config import settings  # noqa: E402
from app.game import UNNAMED, Engine  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
HOW_TO_PLAY = REPO / "frontend/src/components/HowToPlayModal.tsx"
RULES = REPO / "docs/RULES.md"

# Pairs written as "a ↔ b" or "a → b"; "Doesn't count" examples use "/".
PAIR = re.compile(r"\b([a-z]+) [↔→] ([a-z]+)\b")

pytestmark = pytest.mark.skipif(
    not settings.vectors_path.exists(), reason="real vectors not built"
)


@pytest.fixture(scope="module")
def engine() -> Engine:
    engine = build_engine(settings)
    if not engine.labeler.enabled:
        pytest.skip("WordNet corpus not installed")
    return engine


def _check_pairs(engine: Engine, pairs: list[tuple[str, str]]) -> list[str]:
    index, graph = engine.embeddings.index, engine.graph
    bad = []
    for a, b in pairs:
        if a not in index or b not in index:
            bad.append(f"{a}-{b} (not in vocabulary)")
        elif not graph.connected(index[a], index[b]):
            bad.append(f"{a}-{b} (not connected)")
    return bad


def test_rules_examples_are_accepted(engine):
    pairs = PAIR.findall(RULES.read_text(encoding="utf-8"))
    assert len(pairs) >= 25
    assert _check_pairs(engine, pairs) == []


def test_how_to_play_examples_are_accepted(engine):
    source = HOW_TO_PLAY.read_text(encoding="utf-8")
    pairs = PAIR.findall(source)
    chain = re.search(r"EXAMPLE_CHAIN = \[([^\]]*)\]", source)
    words = re.findall(r'"([a-z]+)"', chain.group(1))
    pairs += list(zip(words, words[1:]))
    assert _check_pairs(engine, pairs) == []


def test_par_routes_use_only_named_links(engine):
    index = engine.embeddings.index
    for _ in range(25):
        game = engine.new_game()
        path = [index[w] for w in game.optimal_path]
        assert len(path) - 1 == game.optimal_distance
        labels = [engine._label_edge(a, b) for a, b in zip(path, path[1:])]
        assert UNNAMED not in labels, (game.optimal_path, labels)


def test_dailies_do_not_repeat_recent_words(engine):
    import datetime as dt

    s = settings
    days = [engine.daily_puzzle(s.daily_epoch + dt.timedelta(days=d)) for d in range(60)]
    for i, p in enumerate(days):
        recent_ends = {w for q in days[max(0, i - s.daily_fresh_ends_days):i] for w in (q.start, q.target)}
        recent_route = {w for q in days[max(0, i - s.daily_fresh_route_days):i] for w in q.optimal_path}
        assert not {p.start, p.target} & (recent_ends | recent_route), (i + 1, p)
        assert not set(p.optimal_path[1:-1]) & recent_route, (i + 1, p)



def test_dailies_follow_weekday_difficulty_ramp(engine):
    import datetime as dt

    for d in range(28):
        day = settings.daily_epoch + dt.timedelta(days=d)
        if engine.dailies.is_frozen(day):
            continue  # reviewed days may deliberately differ (e.g. launch day)
        want = settings.daily_par_by_weekday[day.weekday()]
        assert engine.daily_puzzle(day).optimal_distance == want, (day, day.strftime("%a"))



def test_daily_pairs_never_reused(engine):
    import datetime as dt

    pairs = [frozenset((p.start, p.target)) for p in
             (engine.daily_puzzle(settings.daily_epoch + dt.timedelta(days=d)) for d in range(120))]
    assert len(set(pairs)) == len(pairs)


def test_daily_boards_are_fair(engine):
    """Every daily board holds its par route and has no unfair pairs: two
    visible words that look linked but aren't (see app.board.near_misses)."""
    import datetime as dt

    import numpy as np
    from app.board import assess, board_for

    for d in range(60):
        puzzle = engine.daily_puzzle(settings.daily_epoch + dt.timedelta(days=d))
        assert set(puzzle.optimal_path[1:-1]) <= set(puzzle.tiles), (d + 1, puzzle)
        a = assess(engine, board_for(engine, puzzle), np.random.default_rng(0), walks=1)
        assert a.par_solutions, (d + 1, puzzle)
        assert a.unfair == [], (d + 1, puzzle.start, puzzle.target, a.unfair)
