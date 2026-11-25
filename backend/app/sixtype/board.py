"""Six-type boards: the generator and its quality checks.

A board is a six-link route that spends every type once, plus five decoys,
built so that no valid chain shorter than six exists, one or two solutions
do, at least one type trap tempts a player to spend a type twice, and
random play rarely gets through. History keeps a run of boards (dailies)
from leaning on the same words, links and features.
"""
from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .links import BOARD, CHAIN, Links, assign_types, chains

_DATA = Path(__file__).resolve().parent.parent.parent / "data"
# Word vectors for the look-alike check, by links file name: (words, vectors).
# typed_links.txt is the game's; links.txt is the ~240-word prototype's.
VECTORS = {
    "typed_links.txt": (_DATA / "typed_words.json", _DATA / "typed_vectors.npy"),
    "links.txt": (_DATA / "words.json", _DATA / "vectors.npy"),
}


@dataclass
class Board:
    start: str
    target: str
    route: list[str]             # the intended solution, start..target
    route_types: list[str]
    tiles: list[str]             # middle tiles, shuffled
    roles: dict[str, str]


@dataclass
class Assessment:
    solutions: list[tuple[list[str], list[str]]]   # valid 6-link chains + a type order
    short_valid: list[list[str]]                   # valid chains under 6 links (must be none)
    traps: list[list[str]]                         # chains that only work by repeating a type
    first_moves: int
    last_moves: int
    isolated: list[str]
    random_win_rate: float
    global_distance: int
    look_alikes: list[tuple[str, str]]             # unlinked pairs that look linked


def distance(links: Links, a: str, b: str) -> int:
    """Fewest links between two words over the whole vocabulary (types ignored)."""
    seen, frontier, d = {a}, {a}, 0
    while frontier:
        if b in frontier:
            return d
        frontier = {n for w in frontier for n in links.adj[w]} - seen
        seen |= frontier
        d += 1
    return -1


def assess(links: Links, board: Board, rng: random.Random, walks: int = 3000) -> Assessment:
    tiles = board.tiles
    every = chains(links, board.start, board.target, tiles)
    solutions, short_valid, traps = [], [], []
    for c in every:
        types = assign_types(links, c)
        if types is None:
            traps.append(c)
        elif len(c) - 1 < CHAIN:
            short_valid.append(c)
        else:
            solutions.append((c, types))
    nodes = [board.start, *tiles, board.target]
    linked = {w: [n for n in nodes if n != w and links.types(w, n)] for w in nodes}

    # A player who picks a random legal tile (and a random unused type that
    # fits) each move, never going back.
    wins = 0
    for _ in range(walks):
        here, used, seen = board.start, set(), {board.start}
        while here != board.target:
            moves = [(n, t) for n in linked[here] if n not in seen
                     for t in links.types(here, n) if t not in used]
            if not moves:
                break
            here, t = rng.choice(moves)
            used.add(t)
            seen.add(here)
        wins += here == board.target

    return Assessment(
        solutions=solutions,
        short_valid=short_valid,
        traps=traps,
        first_moves=len(linked[board.start]),
        last_moves=len(linked[board.target]),
        isolated=[w for w in tiles if not linked[w]],
        random_win_rate=wins / walks,
        global_distance=distance(links, board.start, board.target),
        look_alikes=sorted(tuple(sorted(p)) for p in look_alikes(links)
                           if p <= set(nodes)),
    )


# -- generating ---------------------------------------------------------------
NEAR_RANK = 15   # same cut-off as the live game's near_misses (app/board.py)
MAX_SOLUTIONS = 2
MAX_RANDOM_WIN = 0.15
# Traps tempt a player into spending a type twice. A few are the puzzle; dozens
# (dense boards where "found with" fits everywhere) are a strike tax.
MAX_TRAPS = 25


def look_alikes(links: Links, rank: int = NEAR_RANK) -> frozenset[frozenset[str]]:
    """Unlinked pairs a player would expect to link: either word is in the
    other's `rank` nearest by word vector. On one board, each is a strike
    the player didn't earn (or a missing link to add to links.txt).

    Vectors catch everyday pairs (potato/salad, grape/juice) but rank
    compound phrases low (lemon tree, egg white): those need a person.
    """
    if links._look_alikes is not None:
        return links._look_alikes
    import json
    import numpy as np
    if links.source not in VECTORS:
        links._look_alikes = frozenset()
        return links._look_alikes
    words_path, vectors_path = VECTORS[links.source]
    try:
        all_words = json.loads(words_path.read_text())
        vectors = np.load(vectors_path)
    except FileNotFoundError:
        links._look_alikes = frozenset()
        return links._look_alikes
    where = {w: i for i, w in enumerate(all_words)}
    vocab = sorted(w for w in links.words if w in where)
    m = vectors[[where[w] for w in vocab]]
    sims = m @ m.T
    np.fill_diagonal(sims, -np.inf)
    nearest = np.argsort(-sims, axis=1)[:, :rank]
    pairs = set()
    for i, row in enumerate(nearest):
        for j in row:
            a, b = vocab[i], vocab[int(j)]
            if not links.types(a, b):
                pairs.add(frozenset((a, b)))
    links._look_alikes = frozenset(pairs)
    return links._look_alikes


@dataclass
class History:
    """What recent boards in a run used, so a batch (or a run of dailies)
    doesn't keep landing on the same words. Like the live dailies' freshness
    rules, it looks back `window` boards ("never again" runs out of good
    ends fast), and no word may be on more than `max_uses` of them: hubs
    like food would otherwise hold up most routes."""
    window: int = 10
    # 3 stalls generation after ~10 boards on this ~240-word prototype
    # (the hubs get blocked and the thin data has few routes without them);
    # the 819-word vocabulary should allow 3.
    max_uses: int = 4
    # A route link can't come back within `window` boards, nor a shared
    # feature (white, sweet) within `feature_window`: the links are fine, the
    # repetition (head -> pillow on 5 of 40 routes) is what makes a run dull.
    feature_window: int = 3
    # 10 suits the 735-word vocabulary; the ~240-word prototype stalls at
    # about 10 boards with it, so it uses PROTO_EDGE_WINDOW.
    edge_window: int = 10
    boards: list["Board"] = field(default_factory=list)
    routes: set[tuple[str, ...]] = field(default_factory=set)   # never repeated
    features: list[set[str]] = field(default_factory=list)      # per board: route features used

    @property
    def ends(self) -> set[str]:
        return {w for b in self.boards[-self.window:] for w in (b.start, b.target)}

    @property
    def uses(self) -> Counter:
        return Counter(w for b in self.boards[-self.window:] for w in (b.start, b.target, *b.tiles))

    @property
    def overused(self) -> set[str]:
        return {w for w, n in self.uses.items() if n >= self.max_uses}

    @property
    def edges(self) -> set[frozenset[str]]:
        """Route links used by recent boards."""
        return {frozenset(p) for b in self.boards[-self.edge_window:] for p in zip(b.route, b.route[1:])}

    @property
    def recent_features(self) -> set[str]:
        return set().union(*self.features[-self.feature_window:]) if self.features else set()

    def record(self, board: "Board", links: "Links | None" = None) -> None:
        self.boards.append(board)
        self.routes.add(tuple(board.route))
        used = set()
        if links is not None:
            for (a, b), t in zip(zip(board.route, board.route[1:]), board.route_types):
                if t == "feature":
                    used |= links.shared_features(a, b)
        self.features.append(used)


def daily_history() -> History:
    """History for a run of dailies: players see every day, so ends and
    route links stay away for a month (at 10 boards the generator came back
    to the same chains every two to three weeks), hub words for four uses
    in that month, and shared features for five days."""
    return History(window=28, max_uses=4, feature_window=5, edge_window=28)


def random_route(links: Links, rng: random.Random, start: str, min_distance: int,
                 history: History, budget: int = 3000) -> tuple[list[str], list[str]] | None:
    """A six-link route from `start` that spends each type once.

    Randomized backtracking (a plain random walk dead-ends ~97% of the
    time), trying words earlier boards used less first. The route must end
    at least `min_distance` from the start over the whole vocabulary, its
    own words mustn't allow a shorter chain (look-alike pairs between route
    words are allowed, as in the live game: they're the steps the puzzle
    asks you not to skip),
    no word may be one recent boards have leaned on (History.overused), no
    two words may be an avoid pair, and at most one middle word may be a
    category word.
    """
    path, used = [start], []
    steps = 0
    uses, ends, overused = history.uses, history.ends, history.overused
    recent_edges, recent_features = history.edges, history.recent_features

    def go() -> bool:
        nonlocal steps
        steps += 1
        if steps > budget:
            return False
        if len(path) - 1 == CHAIN:
            end = path[-1]
            return (end not in links.categories
                    and end not in ends
                    and tuple(path) not in history.routes
                    and distance(links, start, end) >= min_distance
                    and keeps_rules(links, start, end, path[1:-1]))
        # Only obvious links build the intended route; arguable ones are
        # still accepted in play and still count when checking the board.
        options = [(n, t) for n in sorted(links.adj[path[-1]]) if n not in path
                   for t in links.obvious(path[-1], n) if t not in used]
        rng.shuffle(options)
        options.sort(key=lambda o: uses[o[0]])
        last = len(path) == CHAIN
        for n, t in options:
            # Cheap end checks before recursing, or the search spends its
            # budget on routes that end on an adjective.
            if last and (n in links.categories or n in ends):
                continue
            if n in overused or any(frozenset((n, w)) in links.avoid for w in path):
                continue
            if frozenset((path[-1], n)) in recent_edges:
                continue
            if t == "feature" and links.shared_features(path[-1], n) & recent_features:
                continue
            if n in links.categories and any(w in links.categories for w in path[1:]):
                continue
            path.append(n)
            used.append(t)
            if go():
                return True
            path.pop()
            used.pop()
        return False

    return (path[:], used[:]) if go() else None


def build_board(links: Links, rng: random.Random, min_distance: int = 3, tries: int = 400,
                history: History | None = None, rejected: Counter | None = None) -> tuple[Board, Assessment] | None:
    """A board meeting the rules, preferring ones with type traps.

    Route: see random_route. Decoys: words linked to two or more board
    words (none can be ruled out at a glance), favouring ones that set a
    type trap (they link to the chain using a type the route still needs)
    and ones earlier boards used less. No decoy may form a look-alike pair
    with another board word, and the board holds one category word at most.
    Pass a History to keep a batch varied; the board is recorded in it.
    Pass a Counter as `rejected` to count why candidate boards failed.
    """
    rejected = rejected if rejected is not None else Counter()
    history = history if history is not None else History()
    near = look_alikes(links)
    uses, recent_ends, overused = history.uses, history.ends, history.overused
    words = sorted(links.words)
    best = None
    for _ in range(tries):
        start = rng.choice(words)
        if start in links.categories or start in recent_ends or start in overused:
            continue
        walk = random_route(links, rng, start, min_distance, history)
        if walk is None:
            rejected["no route"] += 1
            continue
        route, route_types = walk
        target = route[-1]
        on_board = set(route)
        need_at = {w: set(route_types[i:]) for i, w in enumerate(route[:-1])}

        def allowed(w: str) -> bool:
            # A decoy must not look linked to any board word it isn't.
            if w in overused or any(frozenset((w, b)) in near or frozenset((w, b)) in links.avoid
                                    for b in on_board):
                return False
            return not (w in links.categories and any(b in links.categories for b in on_board))

        def score(w: str) -> float:
            touches = [b for b in on_board if links.types(w, b)]
            if len(touches) < 2:
                return -1
            # Trap value: links to a route word using a type that word's
            # remaining route still needs.
            trap = sum(1 for b in touches if b in need_at and set(links.types(w, b)) & need_at[b])
            # A second way into the target (or out of the start) is the
            # decoy the board most needs.
            ends = sum(1 for b in (start, target) if b in touches)
            return len(touches) + 2 * trap + 3 * ends - 1.5 * uses[w] + rng.random()

        decoys: list[str] = []
        candidates = {n for w in route for n in links.adj[w]} - on_board
        while len(decoys) < BOARD - (CHAIN - 1) and candidates:
            # Sorted first: set order varies between runs (string hashing),
            # and the same seed must always make the same board.
            ranked = sorted(sorted(candidates), key=score, reverse=True)
            pick = next((w for w in ranked if score(w) >= 0 and allowed(w)
                         and keeps_rules(links, start, target, route[1:-1] + decoys + [w])), None)
            if pick is None:
                break
            decoys.append(pick)
            on_board.add(pick)
            candidates.discard(pick)
            candidates |= links.adj[pick] - on_board
        if len(decoys) < BOARD - (CHAIN - 1):
            rejected["too few decoys"] += 1
            continue
        tiles = route[1:-1] + decoys
        rng.shuffle(tiles)
        roles = {w: "route" for w in route[1:-1]} | {w: "decoy" for w in decoys}
        board = Board(start, target, route, route_types, tiles, roles)
        a = assess(links, board, rng, walks=500)
        # Two ways in and out at least, so neither end gives the game away.
        if a.short_valid or not a.solutions or a.isolated or a.first_moves < 2 or a.last_moves < 2:
            rejected["shape (ends/isolated)"] += 1
            continue
        # A real puzzle: one or two answers, at least one type trap, and
        # random play rarely gets through.
        if len(a.solutions) > MAX_SOLUTIONS:
            rejected["too many solutions"] += 1
            continue
        if not a.traps or a.random_win_rate > MAX_RANDOM_WIN:
            rejected["too easy"] += 1
            continue
        if len(a.traps) > MAX_TRAPS:
            rejected["too many traps"] += 1
            continue
        # Prefer: few solutions (a real puzzle), many traps, rarely won at random.
        quality = len(a.traps) * 2 - len(a.solutions) * 3 - a.random_win_rate * 20
        if best is None or quality > best[0]:
            best = (quality, board)
        if len(a.solutions) <= 2 and len(a.traps) >= 3 and a.random_win_rate < 0.1:
            break
    if best is None:
        return None
    board = best[1]
    history.record(board, links)
    return board, assess(links, board, rng)


def keeps_rules(links: Links, start: str, target: str, tiles: list[str]) -> bool:
    """No valid chain shorter than six on these tiles."""
    for c in chains(links, start, target, tiles, max_len=CHAIN - 1):
        if assign_types(links, c) is not None:
            return False
    return True
