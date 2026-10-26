"""Game logic: puzzle generation, move validation, hints, scoring."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import numpy as np

from .embeddings import Embeddings
from .graph import WordGraph

STATUS_IN_PROGRESS = "in_progress"
STATUS_WON = "won"
STATUS_LOST = "lost"


@dataclass
class Game:
    id: str
    start: str
    target: str
    optimal_distance: int
    optimal_path: list[str]
    max_connections: int
    path: list[str] = field(default_factory=list)
    status: str = STATUS_IN_PROGRESS

    @property
    def current_word(self) -> str:
        return self.path[-1]

    @property
    def connections_used(self) -> int:
        return len(self.path) - 1


@dataclass
class MoveResult:
    accepted: bool
    status: str
    current_word: str
    connections_used: int
    connections_left: int
    reason: str | None = None
    similarity: float | None = None
    relation: str | None = None


class PuzzleUnavailable(RuntimeError):
    pass


class Engine:
    def __init__(self, embeddings: Embeddings, graph: WordGraph, settings, overlay=None, labeler=None):
        self.embeddings = embeddings
        self.graph = graph
        self.settings = settings
        self.overlay = overlay
        self.labeler = labeler
        self.rng = np.random.default_rng(settings.seed)

    def _label_edge(self, i: int, j: int) -> str:
        """Name the relation behind an accepted edge.

        Precedence: curated typed overlay -> WordNet -> generic "Related".
        Every accepted move gets a label so the UI never shows a bare cosine.
        """
        if self.overlay:
            label = self.overlay.label_for(i, j)
            if label:
                return label
        if self.labeler:
            label = self.labeler.classify(self.embeddings.words[i], self.embeddings.words[j])
            if label:
                return label
        return "Related"

    # -- puzzle generation ----------------------------------------------
    def new_game(self, min_distance: int | None = None, max_distance: int | None = None) -> Game:
        min_d = min_distance or self.settings.min_puzzle_distance
        max_d = min(max_distance or self.settings.max_puzzle_distance, self.settings.max_connections)
        if min_d > max_d:
            raise ValueError("min_distance must be <= max_distance")

        candidate_starts = [i for i, a in enumerate(self.graph.adjacency) if len(a) > 0]
        if not candidate_starts:
            raise PuzzleUnavailable("graph has no connected words")

        self.rng.shuffle(candidate_starts)
        for start_idx in candidate_starts[:200]:
            dist, _ = self.graph.distances(start_idx)
            reachable = np.flatnonzero((dist >= min_d) & (dist <= max_d))
            if reachable.size == 0:
                continue
            target_idx = int(self.rng.choice(reachable))
            path_idx = self.graph.shortest_path(start_idx, target_idx)
            assert path_idx is not None
            words = self.embeddings.words
            return Game(
                id=uuid.uuid4().hex,
                start=words[start_idx],
                target=words[target_idx],
                optimal_distance=int(dist[target_idx]),
                optimal_path=[words[i] for i in path_idx],
                max_connections=self.settings.max_connections,
                path=[words[start_idx]],
            )
        raise PuzzleUnavailable(
            f"no puzzle found with optimal distance in [{min_d}, {max_d}]"
        )

    # -- moves -----------------------------------------------------------
    def submit(self, game: Game, raw_word: str) -> MoveResult:
        word = raw_word.strip().lower()

        def result(
            accepted: bool,
            reason: str | None = None,
            similarity: float | None = None,
            relation: str | None = None,
        ) -> MoveResult:
            return MoveResult(
                accepted=accepted,
                status=game.status,
                current_word=game.current_word,
                connections_used=game.connections_used,
                connections_left=game.max_connections - game.connections_used,
                reason=reason,
                similarity=similarity,
                relation=relation,
            )

        if game.status != STATUS_IN_PROGRESS:
            return result(False, "game is already over")
        if not word:
            return result(False, "empty word")
        if not self.embeddings.contains(word):
            return result(False, "word is not in the game's vocabulary")
        if word in game.path:
            return result(False, "word already used in this chain")

        current_idx = self.embeddings.index[game.current_word]
        word_idx = self.embeddings.index[word]
        similarity = float(self.embeddings.vectors[current_idx] @ self.embeddings.vectors[word_idx])
        if not self.graph.connected(current_idx, word_idx):
            return result(
                False,
                f"'{word}' is not a close enough association of '{game.current_word}'",
                similarity,
            )

        # Accept the move. Name the relation behind the edge so the UI can
        # explain the connection instead of showing a raw cosine.
        relation = self._label_edge(current_idx, word_idx)
        game.path.append(word)
        if word == game.target:
            game.status = STATUS_WON
        elif game.connections_used >= game.max_connections:
            game.status = STATUS_LOST
        return result(True, similarity=similarity, relation=relation)

    # -- hint ------------------------------------------------------------
    def hint(self, game: Game) -> str | None:
        """A valid next word that lies on a shortest path to the target."""
        if game.status != STATUS_IN_PROGRESS:
            return None
        target_idx = self.embeddings.index[game.target]
        current_idx = self.embeddings.index[game.current_word]
        dist_to_target, _ = self.graph.distances(target_idx)
        here = dist_to_target[current_idx]
        if here <= 0:
            return None
        best: tuple[float, str] | None = None
        for nb in self.graph.neighbors(current_idx):
            if dist_to_target[nb] != here - 1:
                continue
            word = self.embeddings.words[nb]
            if word in game.path:
                continue
            sim = float(self.embeddings.vectors[current_idx] @ self.embeddings.vectors[nb])
            if best is None or sim > best[0]:
                best = (sim, word)
        return best[1] if best else None

    # -- scoring ---------------------------------------------------------
    def score(self, game: Game) -> dict:
        used = game.connections_used
        optimal = game.optimal_distance
        return {
            "status": game.status,
            "connections_used": used,
            "optimal_distance": optimal,
            "over_optimal": max(0, used - optimal) if game.status == STATUS_WON else None,
            "is_optimal": game.status == STATUS_WON and used == optimal,
        }
