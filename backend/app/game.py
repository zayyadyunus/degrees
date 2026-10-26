"""Game logic: puzzle generation, move validation, hints, scoring."""
from __future__ import annotations

import datetime as dt
import logging
import uuid
from dataclasses import dataclass, field

import numpy as np

from .dailies import DailySchedule
from .embeddings import Embeddings
from .graph import WordGraph, bfs, trace_path

logger = logging.getLogger("degrees.game")

STATUS_IN_PROGRESS = "in_progress"
STATUS_WON = "won"
STATUS_LOST = "lost"

# The generic label for edges nothing more specific can explain.
UNNAMED = "Related"

# Per-game event log, in order; drives the shareable emoji result.
EVENT_MOVE = "move"
EVENT_STRIKE = "strike"
EVENT_HINT = "hint"


@dataclass
class Game:
    id: str
    start: str
    target: str
    optimal_distance: int
    optimal_path: list[str]
    max_connections: int
    max_strikes: int = 3
    path: list[str] = field(default_factory=list)
    status: str = STATUS_IN_PROGRESS
    # relations[i] names the edge path[i] -> path[i+1].
    relations: list[str] = field(default_factory=list)
    strikes: int = 0
    # Chain positions (connections_used) at which a hint was revealed, so
    # asking again for the same step doesn't count twice.
    hint_steps: set[int] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    daily_number: int | None = None

    @property
    def current_word(self) -> str:
        return self.path[-1]

    @property
    def connections_used(self) -> int:
        return len(self.path) - 1

    @property
    def hints_used(self) -> int:
        return len(self.hint_steps)


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
    strike: bool = False


@dataclass(frozen=True)
class Puzzle:
    """A start/target pair and one par route (all words)."""
    start: str
    target: str
    optimal_distance: int
    optimal_path: tuple[str, ...]


class PuzzleUnavailable(RuntimeError):
    pass


class Engine:
    def __init__(
        self,
        embeddings: Embeddings,
        graph: WordGraph,
        settings,
        overlay=None,
        labeler=None,
        frozen_dailies: dict[dt.date, "Puzzle"] | None = None,
    ):
        self.embeddings = embeddings
        self.graph = graph
        self.settings = settings
        self.overlay = overlay
        self.labeler = labeler
        self.rng = np.random.default_rng(settings.seed)

        # Label every edge once up front: labels feed puzzle generation, hints
        # and move feedback, and WordNet lookups are too slow per request.
        self._labels: dict[tuple[int, int], str] = {}
        for i in range(graph.n):
            for j in graph.neighbors(i):
                if i < j:
                    self._labels[(i, int(j))] = self._compute_label(i, int(j))

        # The "named" subgraph keeps only edges we can explain (synonym, is-a,
        # made-of, ...). Puzzles are only generated when a par route exists in
        # it, so the solution revealed at the end always reads as sensible.
        # Without a labeler (no WordNet, synthetic dev vectors) nearly every
        # edge is unnamed, so fall back to the full graph.
        if labeler is not None and getattr(labeler, "enabled", True):
            self._named_adj: list[list[int]] = [[] for _ in range(graph.n)]
            for (i, j), label in self._labels.items():
                if label != UNNAMED:
                    self._named_adj[i].append(j)
                    self._named_adj[j].append(i)
        else:
            logger.warning("No relation labeler: par routes may use unexplained links.")
            self._named_adj = [list(a) for a in graph.adjacency]
        self._named_cache: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self.dailies = DailySchedule(self, settings, frozen_dailies)

    def _compute_label(self, i: int, j: int) -> str:
        """Name the relation behind an edge.

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
        return UNNAMED

    def _label_edge(self, i: int, j: int) -> str:
        return self._labels.get((min(i, j), max(i, j))) or self._compute_label(i, j)

    def _named_distances(self, src: int) -> tuple[np.ndarray, np.ndarray]:
        cached = self._named_cache.get(src)
        if cached is None:
            cached = self._named_cache[src] = bfs(self._named_adj, src)
        return cached

    # -- puzzle generation ----------------------------------------------
    def new_game(
        self,
        min_distance: int | None = None,
        max_distance: int | None = None,
        rng: np.random.Generator | None = None,
    ) -> Game:
        """A random practice puzzle."""
        min_d = min_distance or self.settings.min_puzzle_distance
        max_d = min(max_distance or self.settings.max_puzzle_distance, self.settings.max_connections)
        if min_d > max_d:
            raise ValueError("min_distance must be <= max_distance")
        puzzle = self._find_puzzle(rng or self.rng, min_d, max_d)
        if puzzle is None:
            raise PuzzleUnavailable(f"no puzzle found with optimal distance in [{min_d}, {max_d}]")
        return self._start_game(puzzle)

    def _find_puzzle(
        self,
        rng: np.random.Generator,
        min_d: int,
        max_d: int,
        avoid_ends: frozenset[int] = frozenset(),
        avoid_via: frozenset[int] = frozenset(),
    ) -> Puzzle | None:
        """Pick a start/target whose par route uses only named links.

        `avoid_ends` can't be the start or target; `avoid_via` can't appear
        in the middle of the par route (the daily schedule uses these to keep
        consecutive puzzles from feeling the same).
        """
        candidate_starts = [
            i for i, a in enumerate(self._named_adj) if len(a) > 0 and i not in avoid_ends
        ]
        rng.shuffle(candidate_starts)
        for start_idx in candidate_starts[:200]:
            dist, _ = self.graph.distances(start_idx)
            if avoid_via:
                named_dist, named_prev = bfs(self._named_adj, start_idx, no_pass=set(avoid_via))
            else:
                named_dist, named_prev = self._named_distances(start_idx)
            # Par comes from the full graph (no route is shorter), but the
            # target must also be reachable in par steps using named links.
            ok = (dist >= min_d) & (dist <= max_d) & (named_dist == dist)
            if avoid_ends:
                ok[list(avoid_ends)] = False
            reachable = np.flatnonzero(ok)
            if reachable.size == 0:
                continue
            target_idx = int(rng.choice(reachable))
            words = self.embeddings.words
            return Puzzle(
                start=words[start_idx],
                target=words[target_idx],
                optimal_distance=int(dist[target_idx]),
                optimal_path=tuple(words[i] for i in trace_path(named_prev, start_idx, target_idx)),
            )
        return None

    def _start_game(self, puzzle: Puzzle, daily_number: int | None = None) -> Game:
        return Game(
            id=uuid.uuid4().hex,
            start=puzzle.start,
            target=puzzle.target,
            optimal_distance=puzzle.optimal_distance,
            optimal_path=list(puzzle.optimal_path),
            max_connections=self.settings.max_connections,
            max_strikes=self.settings.max_strikes,
            path=[puzzle.start],
            daily_number=daily_number,
        )

    # -- daily puzzles ---------------------------------------------------
    def daily_number(self, day: dt.date) -> int:
        return self.dailies.number(day)

    def daily_puzzle(self, day: dt.date) -> Puzzle:
        return self.dailies.puzzle(day)

    def daily_game(self, day: dt.date) -> Game:
        """The day's shared puzzle as a fresh game: the same for everyone."""
        return self._start_game(self.dailies.puzzle(day), daily_number=self.dailies.number(day))

    # -- moves -----------------------------------------------------------
    def submit(self, game: Game, raw_word: str) -> MoveResult:
        word = raw_word.strip().lower()

        def result(
            accepted: bool,
            reason: str | None = None,
            similarity: float | None = None,
            relation: str | None = None,
            strike: bool = False,
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
                strike=strike,
            )

        if game.status != STATUS_IN_PROGRESS:
            return result(False, "game is already over")
        # Typos and repeats are free: only a real word that fails to connect
        # costs a strike.
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
            game.strikes += 1
            game.events.append(EVENT_STRIKE)
            if game.strikes >= game.max_strikes:
                game.status = STATUS_LOST
            return result(
                False,
                f"'{word}' isn't connected to '{game.current_word}'",
                similarity,
                strike=True,
            )

        # Accept the move. Name the relation behind the edge so the UI can
        # explain the connection instead of showing a raw cosine.
        relation = self._label_edge(current_idx, word_idx)
        game.path.append(word)
        game.relations.append(relation)
        game.events.append(EVENT_MOVE)
        if word == game.target:
            game.status = STATUS_WON
        elif game.connections_used >= game.max_connections:
            game.status = STATUS_LOST
        return result(True, similarity=similarity, relation=relation)

    # -- hint ------------------------------------------------------------
    def hint(self, game: Game) -> str | None:
        """A valid next word on a shortest path to the target.

        Prefers a step that keeps a fully-named route to the target, so hints
        read as sensible links. Revealing a hint is recorded on the game.
        """
        if game.status != STATUS_IN_PROGRESS:
            return None
        target_idx = self.embeddings.index[game.target]
        current_idx = self.embeddings.index[game.current_word]
        dist_to_target, _ = self.graph.distances(target_idx)
        named_to_target, _ = self._named_distances(target_idx)
        here = dist_to_target[current_idx]
        if here <= 0:
            return None
        best: tuple[bool, float, str] | None = None
        for nb in self.graph.neighbors(current_idx):
            if dist_to_target[nb] != here - 1:
                continue
            word = self.embeddings.words[nb]
            if word in game.path:
                continue
            sensible = (
                self._label_edge(current_idx, int(nb)) != UNNAMED
                and named_to_target[nb] == here - 1
            )
            sim = float(self.embeddings.vectors[current_idx] @ self.embeddings.vectors[nb])
            if best is None or (sensible, sim) > best[:2]:
                best = (sensible, sim, word)
        if best is None:
            return None
        if game.connections_used not in game.hint_steps:
            game.hint_steps.add(game.connections_used)
            game.events.append(EVENT_HINT)
        return best[2]

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
            "strikes": game.strikes,
            "hints_used": game.hints_used,
        }
