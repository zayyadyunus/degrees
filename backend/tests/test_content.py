"""Content checks on the real shipped data: every example the game teaches
must actually be accepted, and par routes must use only named links.

Run from backend/:  python -m pytest
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.embeddings import Embeddings  # noqa: E402
from app.game import UNNAMED, Engine  # noqa: E402
from app.graph import WordGraph  # noqa: E402
from app.relations import RelationOverlay  # noqa: E402
from app.wordnet_relations import WordNetLabeler  # noqa: E402

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
    labeler = WordNetLabeler()
    if not labeler.enabled:
        pytest.skip("WordNet corpus not installed")
    emb = Embeddings.load(settings)
    overlay = RelationOverlay.load(settings.relations_path, emb)
    graph = WordGraph(emb, k=settings.k, rng=np.random.default_rng(settings.seed),
                      extra_edges=overlay.edges)
    return Engine(emb, graph, settings, overlay=overlay, labeler=labeler)


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
