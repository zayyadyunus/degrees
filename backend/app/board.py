"""Word boards (prototype): a fixed set of tiles to build each puzzle's chain from.

Instead of guessing words blind, the player sees the start, the target and a
handful of middle tiles, and builds the chain from those. A board holds:

    route   the par route's middle words (always solvable at par)
    alt     words from one other par route, when a different one exists
    trap    the start's most target-like link that can't reach the target
            in par: the wrong first turn a greedy player takes
    lure    any other off-par word linked to a route word: a plausible move
            that leads nowhere useful
    bait    an off-par word linked to the target: a real last step, but
            reaching it costs more than par. Stops players simply working
            backwards from the only tile that touches the target
    echo    a word two links from the target that isn't on any par route:
            a genuine near-miss

Every decoy links to at least two board words where possible, so none can be
ruled out at a glance.

Fairness gate: no decoy or alt word may sit on a board next to a word it
*looks* linked to but isn't (`near_misses`: one is in the other's nearest
NEAR_RANK words, or WordNet relates them). On a board, every such pair is a
strike a player didn't deserve. Route words that look linked but aren't
(time-winter) are the steps the puzzle asks you not to skip, so they're
allowed.

Off-par means start -> word -> target can't be done in par steps, so decoys
never open a route shorter than par (par is already the global shortest).
Decoys can still be legal moves; they just cost connections.

The board's quality numbers come from `assess`: how many par solutions the
tiles allow, whether a greedy "most similar to the target" player solves it
at par, and how often random legal play does.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cache
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from .game import Engine, Puzzle

ROLES = ("route", "alt", "trap", "lure", "bait", "echo")

# Unlinked words this close (by nearest-neighbour rank, either direction)
# look linked to a player. Tuned on play-tested unfair pairs: 15 catches
# lamp-desk (5), hot-sun (7), dinner-wine (12), spring-rain (15) and keeps
# boards near full size; 25 also catches wall-clock (17) and pencil-wood
# (24) but leaves some boards with 4 tiles. Pairs the vectors rank lower
# need a curated link in data/relations.json instead.
NEAR_RANK = 15


@cache
def near_misses(engine: "Engine") -> frozenset[frozenset[int]]:
    """Unlinked pairs a player would expect to be linked."""
    vec, graph, words = engine.embeddings.vectors, engine.graph, engine.embeddings.words
    sims = vec @ vec.T
    np.fill_diagonal(sims, -np.inf)
    nearest = np.argsort(-sims, axis=1)
    pairs: set[frozenset[int]] = set()
    labeler = engine.labeler if getattr(engine.labeler, "enabled", False) else None
    for i in range(graph.n):
        # WordNet catches pairs the vectors rank lower (emotion-hope); only
        # ask about reasonably close words, as it's slow.
        for rank, j in enumerate(nearest[i, : NEAR_RANK * 3]):
            j = int(j)
            if graph.connected(i, j):
                continue
            if rank < NEAR_RANK or (labeler and labeler.classify(words[i], words[j])):
                pairs.add(frozenset((i, j)))
    return frozenset(pairs)


@dataclass
class Board:
    start: str
    target: str
    par: int
    # Middle tiles in display order, and each one's role.
    tiles: list[str]
    roles: dict[str, str] = field(default_factory=dict)


@dataclass
class Assessment:
    par_solutions: list[list[str]]
    greedy_path: list[str]
    greedy_solves_at_par: bool
    random_par_rate: float
    # Tiles with no link to any other board word (start/target included).
    isolated: list[str]
    first_moves: int
    last_moves: int
    # Board words that look linked but aren't (see near_misses), leaving
    # out pairs of route words.
    unfair: list[tuple[str, str]]


def build_board(
    engine: "Engine",
    puzzle: "Puzzle",
    rng: np.random.Generator,
    size: int = 10,
    avoid: frozenset[str] = frozenset(),
) -> Board:
    """Pick `size` middle tiles for a puzzle: route words first, then decoys.

    `avoid` lists decoy words to skip if possible (tiles from recent boards).
    """
    I, words, vec, graph = engine.embeddings.index, engine.embeddings.words, engine.embeddings.vectors, engine.graph
    s, t, par = I[puzzle.start], I[puzzle.target], puzzle.optimal_distance
    d_s, _ = graph.distances(s)
    d_t, _ = graph.distances(t)
    route = [I[w] for w in puzzle.optimal_path]
    sims = vec @ vec[t]

    def on_par(w: int) -> bool:
        return d_s[w] >= 0 and d_t[w] >= 0 and d_s[w] + d_t[w] == par

    taken: set[int] = set(route)
    roles: dict[int, str] = {w: "route" for w in route[1:-1]}
    misses = near_misses(engine)

    def fair(w: int) -> bool:
        return not any(frozenset((w, b)) in misses for b in taken)

    def add(w: int, role: str) -> None:
        taken.add(w)
        roles[w] = role

    # alt: one other named par route, so the board can have more than one
    # answer. Sharing words with the main route is fine; it must add at least
    # one new word and at most two.
    for _ in range(20):
        node, alt = s, []
        for step in range(1, par):
            options = [int(n) for n in engine._named_adj[node] if d_s[n] == step and d_t[n] == par - step]
            if not options:
                break
            node = int(rng.choice(options))
            alt.append(node)
        new = [w for w in alt if w not in taken]
        if len(alt) == par - 1 and alt[-1] in engine._named_adj[t] and 1 <= len(new) <= 2 and all(map(fair, new)):
            for w in new:
                add(w, "alt")
            break

    # Decoy slots, each a ranked list of candidates (all off-par) and how
    # many to take. Forward decoys hang off the start and early route words;
    # target-side ones off the target and the last route word, so working
    # backwards from the target is a real choice too.
    def off_par_neighbours(w: int) -> list[int]:
        return [int(n) for n in graph.neighbors(w) if not on_par(int(n)) and int(n) not in (s, t)]

    def by_pull(ws: list[int]) -> list[int]:
        return sorted(ws, key=lambda w: -sims[w])

    slots: list[tuple[str, list[int], int]] = []
    # The start always gets two: its most target-like dead end is the trap
    # (ideally more target-like than the right first step), then a lure.
    opening = by_pull(off_par_neighbours(s))
    slots.append(("trap", opening, 1))
    slots.append(("lure", opening, 1))
    for here in route[1:-2]:
        slots.append(("lure", by_pull(off_par_neighbours(here)), 1))
    slots.append(("lure", by_pull(off_par_neighbours(route[-2])), 1))
    slots.append(("bait", by_pull(off_par_neighbours(t)), 2))
    # echo: two steps from the target, so it really does sit one link from
    # it — a near-miss, not a missing edge. Fills whatever room is left.
    echoes = [w for w in map(int, np.argsort(-sims)) if d_t[w] == 2 and not on_par(w) and w != s]
    slots.append(("echo", echoes, size))

    # Every decoy should link to two board words (else it's ruled out at a
    # glance), and skip recently used tiles; relax both if a slot runs dry.
    filled = [0] * len(slots)
    for min_links, skip_recent in ((2, True), (1, True), (1, False)):
        for n, (role, candidates, quota) in enumerate(slots):
            for w in candidates:
                if filled[n] >= quota or len(roles) >= size:
                    break
                if w in taken or (skip_recent and words[w] in avoid) or not fair(w):
                    continue
                if sum(graph.connected(w, b) for b in taken) >= min_links:
                    add(w, role)
                    filled[n] += 1

    tiles = [words[w] for w in roles]
    rng.shuffle(tiles)
    return Board(
        start=puzzle.start,
        target=puzzle.target,
        par=par,
        tiles=tiles,
        roles={words[w]: r for w, r in roles.items()},
    )


def board_for(engine: "Engine", puzzle: "Puzzle") -> Board:
    """A stored puzzle's board, with each tile's role worked out again.

    Roles aren't stored, so they're inferred: on a par route is route/alt,
    linked to the start is a trap/lure, linked to the target is bait, else
    an echo (or lure, if it links to a route word).
    """
    I, graph = engine.embeddings.index, engine.graph
    s, t, par = I[puzzle.start], I[puzzle.target], puzzle.optimal_distance
    d_s, _ = graph.distances(s)
    d_t, _ = graph.distances(t)
    route = {I[w] for w in puzzle.optimal_path[1:-1]}
    roles: dict[str, str] = {}
    for w in puzzle.tiles:
        i = I[w]
        if i in route:
            roles[w] = "route"
        elif d_s[i] + d_t[i] == par:
            roles[w] = "alt"
        elif graph.connected(i, s):
            roles[w] = "trap"
        elif graph.connected(i, t):
            roles[w] = "bait"
        elif any(graph.connected(i, r) for r in route):
            roles[w] = "lure"
        else:
            roles[w] = "echo"
    return Board(puzzle.start, puzzle.target, par, list(puzzle.tiles), roles)


def assess(engine: "Engine", board: Board, rng: np.random.Generator, walks: int = 2000) -> Assessment:
    """How the board plays: solutions, a greedy player, random play."""
    I, vec, graph = engine.embeddings.index, engine.embeddings.vectors, engine.graph
    s, t = I[board.start], I[board.target]
    nodes = [s, *(I[w] for w in board.tiles), t]
    adj = {a: [b for b in nodes if b != a and graph.connected(a, b)] for a in nodes}
    name = engine.embeddings.words
    on_route = {s, t} | {I[w] for w, role in board.roles.items() if role == "route"}

    # Every par-length chain through the tiles.
    solutions: list[list[str]] = []

    def dfs(path: list[int]) -> None:
        if len(path) - 1 == board.par:
            if path[-1] == t:
                solutions.append([name[i] for i in path])
            return
        for n in adj[path[-1]]:
            if n not in path and (n != t or len(path) == board.par):
                dfs(path + [n])

    dfs([s])

    # Greedy: always play the linked tile most similar to the target.
    greedy = [s]
    while greedy[-1] != t and len(greedy) - 1 < engine.settings.max_connections:
        options = [n for n in adj[greedy[-1]] if n not in greedy]
        if not options:
            break
        greedy.append(max(options, key=lambda n: (n == t, float(vec[n] @ vec[t]))))
    greedy_names = [name[i] for i in greedy]

    # Random legal play (always takes the target when it's linked).
    hits = 0
    for _ in range(walks):
        here, seen = s, {s}
        for _ in range(board.par):
            options = [n for n in adj[here] if n not in seen]
            if not options:
                break
            here = t if t in options else int(rng.choice(options))
            seen.add(here)
            if here == t:
                break
        hits += here == t

    return Assessment(
        par_solutions=solutions,
        greedy_path=greedy_names,
        greedy_solves_at_par=greedy[-1] == t and len(greedy) - 1 == board.par,
        random_par_rate=hits / walks,
        isolated=[name[n] for n in nodes[1:-1] if not adj[n]],
        first_moves=len(adj[s]),
        last_moves=len(adj[t]),
        unfair=[
            (name[a], name[b]) for x, a in enumerate(nodes) for b in nodes[x + 1:]
            if frozenset((a, b)) in near_misses(engine) and not (a in on_route and b in on_route)
        ],
    )
