"""The word graph: nodes are words; edges come from MUTUAL k-nearest-neighbors.

An edge connects two words iff each is among the other's K nearest words by
cosine similarity. This is the single source of truth shared by move validation
and puzzle generation, so any path the generator guarantees is one the validator
accepts.

Why mutual k-NN instead of a global cosine threshold: generic "hub" words
(good, big, time...) are cosine-close to almost everything and otherwise create
arbitrary shortcut paths. Requiring the relationship to be mutual removes those
asymmetric hub edges while preserving genuine associations, and gives every word
a uniform branching factor (<= K), which makes difficulty predictable.
"""
from __future__ import annotations

import logging
from collections import deque

import numpy as np

from .embeddings import Embeddings

logger = logging.getLogger("degrees.graph")


class WordGraph:
    def __init__(
        self,
        embeddings: Embeddings,
        k: int = 12,
        rng: np.random.Generator | None = None,
        extra_edges: list[tuple[int, int]] | None = None,
    ):
        self.embeddings = embeddings
        self.vectors = embeddings.vectors
        self.n = len(embeddings)
        self.rng = rng or np.random.default_rng(0)
        self.k = max(1, min(k, self.n - 1)) if self.n > 1 else 0

        self._adj_sets: list[set[int]] = [set(a.tolist()) for a in self._build_mutual_knn(self.k)]
        n_overlay = self._add_extra_edges(extra_edges or [])
        # Final adjacency arrays, sorted for stable iteration.
        self.adjacency: list[np.ndarray] = [
            np.array(sorted(s), dtype=np.int32) for s in self._adj_sets
        ]
        self._dist_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}

        degrees = np.array([len(a) for a in self.adjacency])
        logger.info(
            "Graph built: %d nodes, k=%d, %d overlay edges, "
            "degree min/median/max=%d/%d/%d, %d isolated.",
            self.n, self.k, n_overlay, degrees.min(initial=0),
            int(np.median(degrees)) if self.n else 0, degrees.max(initial=0),
            int((degrees == 0).sum()),
        )

    def _add_extra_edges(self, extra_edges: list[tuple[int, int]]) -> int:
        """Union typed-relation edges into the adjacency sets. Returns # added."""
        added = 0
        for i, j in extra_edges:
            if not (0 <= i < self.n and 0 <= j < self.n) or i == j:
                continue
            if j not in self._adj_sets[i]:
                self._adj_sets[i].add(j)
                self._adj_sets[j].add(i)
                added += 1
        return added

    # -- adjacency -------------------------------------------------------
    def _build_mutual_knn(self, k: int) -> list[np.ndarray]:
        if self.n <= 1:
            return [np.empty(0, np.int32) for _ in range(self.n)]
        # Pass 1: each word's K nearest (computed block-wise to bound memory).
        topk: list[set[int]] = [set() for _ in range(self.n)]
        block = 512
        for start in range(0, self.n, block):
            stop = min(start + block, self.n)
            sims = self.vectors[start:stop] @ self.vectors.T  # (block, n)
            for local, row in enumerate(sims):
                idx = start + local
                row[idx] = -np.inf  # never self
                nearest = np.argpartition(-row, k - 1)[:k]
                topk[idx] = set(int(x) for x in nearest)
        # Pass 2: keep only mutual edges.
        adjacency: list[np.ndarray] = []
        for i in range(self.n):
            mutual = [j for j in topk[i] if i in topk[j]]
            adjacency.append(np.array(sorted(mutual), dtype=np.int32))
        return adjacency

    def neighbors(self, i: int) -> np.ndarray:
        return self.adjacency[i]

    def connected(self, i: int, j: int) -> bool:
        return j in self._adj_sets[i]

    # -- traversal -------------------------------------------------------
    def distances(self, src: int) -> tuple[np.ndarray, np.ndarray]:
        """BFS from src. Returns (dist, prev); unreachable == -1."""
        cached = self._dist_cache.get(src)
        if cached is not None:
            return cached
        dist = np.full(self.n, -1, dtype=np.int32)
        prev = np.full(self.n, -1, dtype=np.int32)
        dist[src] = 0
        queue: deque[int] = deque([src])
        while queue:
            node = queue.popleft()
            for nb in self.adjacency[node]:
                if dist[nb] == -1:
                    dist[nb] = dist[node] + 1
                    prev[nb] = node
                    queue.append(int(nb))
        self._dist_cache[src] = (dist, prev)
        return dist, prev

    def shortest_path(self, src: int, dst: int) -> list[int] | None:
        dist, prev = self.distances(src)
        if dist[dst] == -1:
            return None
        path = [dst]
        while path[-1] != src:
            path.append(int(prev[path[-1]]))
        path.reverse()
        return path
