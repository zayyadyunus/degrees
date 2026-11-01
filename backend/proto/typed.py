"""Prototype of the six-type rule: typed links, a solver and a board generator.

The rules being tested:

  * every puzzle is start -> 5 middle words -> target: six links;
  * each link spends one of six types, and no type can be spent twice, so a
    solved chain uses every type exactly once;
  * the board holds 10 tiles: the 5 route words and 5 decoys;
  * no chain shorter than six can be made on the board, so the six-degrees
    shape never needs to be a stated rule.

A link between two words can carry more than one type (wheel/car could be
"part of" or, loosely, "found with"); the player chooses which to spend.
Nothing here touches the live game (app/): it's a standalone sketch.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

LINKS_PATH = Path(__file__).with_name("links.txt")

TYPES = ("kind", "family", "part", "feature", "use", "found")
TYPE_NAMES = {
    "kind": "kind of",
    "family": "same family",
    "part": "part of / made of",
    "feature": "share a feature",
    "use": "used for / makes",
    "found": "found with",
}
# Relation keywords in links.txt -> the type they spend.
REL_TYPE = {
    "kind": "kind", "part": "part", "made": "part", "feature": "feature",
    "use": "use", "makes": "use", "in": "found", "with": "found",
}
REL_PHRASE = {
    "kind": "{a} is a kind of {b}",
    "part": "{a} is part of {b}",
    "made": "{a} is made of {b}",
    "use": "{a} is used for {b}",
    "makes": "{a} makes {b}",
    "in": "{a} is found in {b}",
    "with": "{a} goes with {b}",
}
CHAIN = 6       # links in every puzzle (five words between start and target)
BOARD = 10      # middle tiles


@dataclass
class Links:
    """Every typed link. pair -> {type: sentence explaining it}."""
    words: set[str] = field(default_factory=set)
    edges: dict[frozenset[str], dict[str, str]] = field(default_factory=dict)
    adj: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))
    # Category words (animal, color, ...): fine as tiles, dull as ends.
    categories: set[str] = field(default_factory=set)
    # Words that describe things (red, soft, loud): the subjects of
    # "feature" lines. Not playable; they name what two nouns share.
    adjectives: set[str] = field(default_factory=set)
    # Pairs never put on one board: real phrases that aren't one of the six
    # types (fruit salad + banana), so a player would try them and strike.
    avoid: set[frozenset[str]] = field(default_factory=set)
    # As written in links.txt, for lint.py: word -> the categories it's
    # directly in, and feature -> the nouns that have it.
    parents: dict[str, set[str]] = field(default_factory=dict)
    features: dict[str, list[str]] = field(default_factory=dict)
    _look_alikes: frozenset[frozenset[str]] | None = None

    def add(self, a: str, b: str, type_: str, why: str) -> None:
        if a == b:
            return
        self.words |= {a, b}
        self.edges.setdefault(frozenset((a, b)), {}).setdefault(type_, why)
        self.adj[a].add(b)
        self.adj[b].add(a)

    def types(self, a: str, b: str) -> dict[str, str]:
        return self.edges.get(frozenset((a, b)), {})

    def count_by_type(self) -> dict[str, int]:
        counts = dict.fromkeys(TYPES, 0)
        for ts in self.edges.values():
            for t in ts:
                counts[t] += 1
        return counts


def load(path: Path = LINKS_PATH) -> Links:
    lines = []
    for raw in path.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            head, _, rest = line.partition(":")
            lines.append((raw, head.split(), rest.split()))

    links = Links()
    # Adjectives (red, soft, loud) aren't words on the board: they only name
    # what two nouns share. "red feature: tomato blood" links tomato and
    # blood ("both red"). As tiles they could only sit at a route's end.
    links.adjectives = {h[0] for _, h, _ in lines if len(h) == 2 and h[1] == "feature"}
    parents: dict[str, set[str]] = defaultdict(set)   # word -> categories it's directly in
    shared: dict[frozenset[str], list[str]] = defaultdict(list)

    for raw, head_words, targets in lines:
        targets = [w for w in targets if w not in links.adjectives]
        if head_words[0] in ("category", "kinds"):
            name = head_words[1]
            if name in links.adjectives:
                continue
            if not name.startswith("~"):
                links.categories.add(name)
            for w in targets:
                parents[w].add(name)
            links.words |= set(targets)
            if head_words[0] == "kinds":
                continue
            label = name.lstrip("~").replace("_", " ")
            for a, b in combinations(targets, 2):
                links.add(a, b, "family", f"{a} and {b} are the same family ({label})")
        elif head_words[0] == "family":
            for a, b in combinations(targets, 2):
                links.add(a, b, "family", f"{a} and {b} are the same family")
        elif head_words[0] == "avoid":
            links.avoid.add(frozenset(targets))
        else:
            a, rel = head_words
            if rel not in REL_TYPE:
                raise ValueError(f"unknown relation {rel!r} in: {raw}")
            if rel == "feature":
                links.features.setdefault(a, []).extend(targets)
                for x, y in combinations(targets, 2):
                    shared[frozenset((x, y))].append(a)
                continue
            for b in targets:
                links.add(a, b, REL_TYPE[rel], REL_PHRASE[rel].format(a=a, b=b))

    for pair, adjs in shared.items():
        x, y = sorted(pair)
        links.add(x, y, "feature", f"{x} and {y} are both {' and '.join(adjs)}")

    # "kind" passes up the categories (eagle -> bird -> animal), but not
    # through a word in two categories: fish is an animal and a food, so
    # shark -> fish -> food would switch meaning ("shark is a kind of food").
    def is_fork(w: str) -> bool:
        return sum(not p.startswith("~") for p in parents.get(w, ())) > 1

    def ancestors(w: str, seen: frozenset[str] = frozenset()) -> list[tuple[str, list[str]]]:
        out = []
        for p in parents.get(w, ()):
            if p.startswith("~") or p in seen:
                continue
            out.append((p, []))
            if not is_fork(p):
                out += [(q, [p, *via]) for q, via in ancestors(p, seen | {p})]
        return out

    for w in list(parents):
        for anc, via in ancestors(w):
            why = f"{w} is a kind of {anc}" + (f" (a {via[0]})" if via else "")
            links.add(w, anc, "kind", why)
    links.parents = dict(parents)
    return links


# -- solving ------------------------------------------------------------------
def assign_types(links: Links, path: list[str], used: frozenset[str] = frozenset()) -> list[str] | None:
    """One way to give each link in `path` a different type, or None."""
    options = [list(links.types(a, b)) for a, b in zip(path, path[1:])]
    order = sorted(range(len(options)), key=lambda i: len(options[i]))
    chosen: dict[int, str] = {}

    def go(k: int, taken: frozenset[str]) -> bool:
        if k == len(order):
            return True
        i = order[k]
        for t in options[i]:
            if t not in taken:
                chosen[i] = t
                if go(k + 1, taken | {t}):
                    return True
        return False

    return [chosen[i] for i in range(len(path) - 1)] if go(0, used) else None


def chains(links: Links, start: str, target: str, words: list[str], max_len: int = CHAIN) -> list[list[str]]:
    """Every simple chain start -> target through `words`, ignoring types."""
    pool = set(words) | {target}
    out: list[list[str]] = []

    def dfs(path: list[str]) -> None:
        here = path[-1]
        if here == target:
            out.append(path[:])
            return
        if len(path) - 1 == max_len:
            return
        for n in sorted(links.adj[here]):
            if n in pool and n not in path:
                path.append(n)
                dfs(path)
                path.pop()

    dfs([start])
    return out


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
    data = Path(__file__).resolve().parent.parent / "data"
    try:
        all_words = json.loads((data / "words.json").read_text())
        vectors = np.load(data / "vectors.npy")
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
    boards: list["Board"] = field(default_factory=list)
    routes: set[tuple[str, ...]] = field(default_factory=set)   # never repeated

    @property
    def ends(self) -> set[str]:
        return {w for b in self.boards[-self.window:] for w in (b.start, b.target)}

    @property
    def uses(self) -> Counter:
        return Counter(w for b in self.boards[-self.window:] for w in (b.start, b.target, *b.tiles))

    @property
    def overused(self) -> set[str]:
        return {w for w, n in self.uses.items() if n >= self.max_uses}

    def record(self, board: "Board") -> None:
        self.boards.append(board)
        self.routes.add(tuple(board.route))


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
                    and _keeps_rules(links, start, end, path[1:-1]))
        options = [(n, t) for n in sorted(links.adj[path[-1]]) if n not in path
                   for t in links.types(path[-1], n) if t not in used]
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
                         and _keeps_rules(links, start, target, route[1:-1] + decoys + [w])), None)
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
        # Prefer: few solutions (a real puzzle), many traps, rarely won at random.
        quality = len(a.traps) * 2 - len(a.solutions) * 3 - a.random_win_rate * 20
        if best is None or quality > best[0]:
            best = (quality, board)
        if len(a.solutions) <= 2 and len(a.traps) >= 3 and a.random_win_rate < 0.1:
            break
    if best is None:
        return None
    board = best[1]
    history.record(board)
    return board, assess(links, board, rng)


def _keeps_rules(links: Links, start: str, target: str, tiles: list[str]) -> bool:
    """No valid chain shorter than six on these tiles."""
    for c in chains(links, start, target, tiles, max_len=CHAIN - 1):
        if assign_types(links, c) is not None:
            return False
    return True


def phrase(links: Links, a: str, b: str, type_: str) -> str:
    return links.types(a, b)[type_]

