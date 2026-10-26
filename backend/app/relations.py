"""Typed-relation overlay loaded from a sparse edge file.

The embedding graph (mutual k-NN) covers same-meaning / opposite / is-a /
category / part-of well, but ranks cross-domain links (MadeOf, SymbolOf,
Causes, HasProperty) too low to ever connect them. This overlay supplies those
edges explicitly. Because the list is sparse (a few edges per word), unioning it
onto the embedding graph recovers those links without creating hub shortcuts.

File format (data/relations.json):
    {"relations": [{"rel": "MadeOf", "a": "glass", "b": "sand"}, ...]}

Edges whose words are outside the embedding vocabulary are silently dropped, so
the same file can be reused across different wordlists.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .embeddings import Embeddings

logger = logging.getLogger("degrees.relations")


class RelationOverlay:
    def __init__(self, edges: list[tuple[int, int]], labels: dict[frozenset[int], str]):
        self.edges = edges                 # undirected index pairs, both in vocab
        self.labels = labels               # {frozenset({i, j}): relation label}

    def label_for(self, i: int, j: int) -> str | None:
        return self.labels.get(frozenset((i, j)))

    @classmethod
    def empty(cls) -> "RelationOverlay":
        return cls([], {})

    @classmethod
    def load(cls, path: Path, embeddings: Embeddings) -> "RelationOverlay":
        if not path.exists():
            logger.info("No relation overlay at %s — embedding graph only.", path)
            return cls.empty()

        raw = json.loads(path.read_text(encoding="utf-8"))
        entries = raw["relations"] if isinstance(raw, dict) else raw

        edges: list[tuple[int, int]] = []
        labels: dict[frozenset[int], str] = {}
        seen: set[frozenset[int]] = set()
        dropped = 0
        index = embeddings.index
        for e in entries:
            a, b = e["a"].strip().lower(), e["b"].strip().lower()
            ia, ib = index.get(a), index.get(b)
            if ia is None or ib is None or ia == ib:
                dropped += 1
                continue
            key = frozenset((ia, ib))
            if key in seen:
                continue
            seen.add(key)
            edges.append((ia, ib))
            labels[key] = e.get("rel", "Related")

        logger.info(
            "Relation overlay: %d edges loaded, %d dropped (out of vocab).",
            len(edges), dropped,
        )
        return cls(edges, labels)
