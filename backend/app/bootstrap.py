"""Build the game engine from settings.

The one place the production engine is assembled, so the API, scripts and
content tests always see the same graph, labels and puzzles.
"""
from __future__ import annotations

import numpy as np

from .embeddings import Embeddings
from .game import Engine
from .graph import WordGraph
from .relations import RelationOverlay
from .wordnet_relations import WordNetLabeler


def build_engine(settings) -> Engine:
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
    return Engine(embeddings, graph, settings, overlay=overlay, labeler=labeler)
