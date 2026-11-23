"""Build the game engine from settings.

The one place the production engine is assembled, so the API, scripts and
content tests always see the same graph, labels and puzzles.
"""
from __future__ import annotations

import numpy as np

from .dailies import load_frozen
from .embeddings import Embeddings
from .game import Engine
from .graph import WordGraph
from .relations import RelationOverlay
from .wordnet_relations import WordNetLabeler


def build_engine(settings, strict: bool = True) -> Engine:
    """strict: refuse frozen dailies that no longer match the data (the
    app and tests); the freeze script passes False so it can repair them."""
    embeddings = Embeddings.load(settings)
    overlay = (
        RelationOverlay.load(settings.relations_path, embeddings)
        if settings.use_relations
        else RelationOverlay.empty()
    )
    graph = WordGraph(
        embeddings,
        k=settings.k,
        rng=np.random.default_rng(settings.seed),
        extra_edges=overlay.edges,
    )
    labeler = WordNetLabeler(max_senses_per_pos=settings.wordnet_senses)
    engine = Engine(
        embeddings, graph, settings, overlay=overlay, labeler=labeler,
        frozen_dailies=load_frozen(settings.dailies_path),
    )
    if strict:
        engine.dailies.raise_if_invalid()
    return engine


def build_sixtype(settings, strict: bool = True):
    """The six-type engine and its frozen dailies (app/sixtype/)."""
    from .sixtype.dailies import TypedDailies, load_typed
    from .sixtype.engine import SixTypeEngine
    from .sixtype.links import load

    links = load(settings.typed_links_path)
    dailies = TypedDailies(links, settings.daily_epoch, load_typed(settings.typed_dailies_path))
    if strict:
        dailies.raise_if_invalid()
    return SixTypeEngine(links, max_strikes=settings.max_strikes), dailies
