"""Six-type links: the data behind the six-type rules, and the solver.

Every link between two words carries one or more of six types; a puzzle is
start -> five words -> target, and each link spends a different type.
Loaded from data/typed_links.txt (syntax at the top of that file).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path

LINKS_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "typed_links.txt"

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
    # Links that are true but some players would hesitate over ("?word" in
    # links.txt): (pair, type). Accepted when played, never used to build a
    # puzzle's intended route. A link written both ways counts as obvious.
    arguable: set[tuple[frozenset[str], str]] = field(default_factory=set)
    _look_alikes: frozenset[frozenset[str]] | None = None
    source: str = ""                       # which links file, for picking word vectors

    def add(self, a: str, b: str, type_: str, why: str, arguable: bool = False) -> None:
        if a == b:
            return
        self.words |= {a, b}
        pair = frozenset((a, b))
        types = self.edges.setdefault(pair, {})
        if type_ not in types:
            types[type_] = why
            if arguable:
                self.arguable.add((pair, type_))
        elif not arguable and (pair, type_) in self.arguable:
            types[type_] = why
            self.arguable.discard((pair, type_))
        self.adj[a].add(b)
        self.adj[b].add(a)

    def obvious(self, a: str, b: str) -> dict[str, str]:
        """The types linking a and b that nearly every player would accept."""
        pair = frozenset((a, b))
        return {t: why for t, why in self.types(a, b).items() if (pair, t) not in self.arguable}

    def types(self, a: str, b: str) -> dict[str, str]:
        return self.edges.get(frozenset((a, b)), {})

    def shared_features(self, a: str, b: str) -> set[str]:
        """The adjectives behind a "share a feature" link (white for snow / milk)."""
        return {adj for adj, ws in self.features.items() if a in ws and b in ws}

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

    # "?word": the link(s) this line gives that word are arguable.
    doubtful: dict[str, set[str]] = defaultdict(set)   # line raw -> its ?words
    for i, (raw, head_words, targets) in enumerate(lines):
        doubtful[raw] = {w[1:] for w in targets if w.startswith("?")}
        lines[i] = (raw, head_words, [w.lstrip("?") for w in targets])

    links = Links(source=path.name)
    # Adjectives (red, soft, loud) aren't words on the board: they only name
    # what two nouns share. "red feature: tomato blood" links tomato and
    # blood ("both red"). As tiles they could only sit at a route's end.
    links.adjectives = {h[0] for _, h, _ in lines if len(h) == 2 and h[1] == "feature"}
    parents: dict[str, set[str]] = defaultdict(set)   # word -> categories it's directly in
    shaky_parent: set[tuple[str, str]] = set()          # (word, category) written "?word"
    shared: dict[frozenset[str], list[str]] = defaultdict(list)
    shaky_shared: dict[frozenset[str], bool] = {}        # pair -> arguable in every feature list

    for raw, head_words, targets in lines:
        targets = [w for w in targets if w not in links.adjectives]
        shaky = doubtful[raw]
        if head_words[0] in ("category", "kinds"):
            name = head_words[1]
            if name in links.adjectives:
                continue
            if not name.startswith("~"):
                links.categories.add(name)
            for w in targets:
                parents[w].add(name)
                if w in shaky:
                    shaky_parent.add((w, name))
            links.words |= set(targets)
            if head_words[0] == "kinds":
                continue
            label = name.lstrip("~").replace("_", " ")
            for a, b in combinations(targets, 2):
                links.add(a, b, "family", f"{a} and {b} are the same family ({label})",
                          arguable=bool({a, b} & shaky))
        elif head_words[0] == "family":
            for a, b in combinations(targets, 2):
                links.add(a, b, "family", f"{a} and {b} are the same family", arguable=bool({a, b} & shaky))
        elif head_words[0] == "avoid":
            links.avoid.add(frozenset(targets))
        else:
            a, rel = head_words
            if rel not in REL_TYPE:
                raise ValueError(f"unknown relation {rel!r} in: {raw}")
            if rel == "feature":
                links.features.setdefault(a, []).extend(targets)
                for x, y in combinations(targets, 2):
                    pair = frozenset((x, y))
                    shared[pair].append(a)
                    shaky_shared[pair] = shaky_shared.get(pair, True) and bool({x, y} & shaky)
                continue
            for b in targets:
                links.add(a, b, REL_TYPE[rel], REL_PHRASE[rel].format(a=a, b=b), arguable=b in shaky)

    for pair, adjs in shared.items():
        x, y = sorted(pair)
        links.add(x, y, "feature", f"{x} and {y} are both {' and '.join(adjs)}", arguable=shaky_shared[pair])

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
            steps = list(zip([w, *via], [*via, anc]))
            links.add(w, anc, "kind", why, arguable=any(s in shaky_parent for s in steps))
    # A kind-of pair is parent and child, not siblings: "mother and parent
    # are the same family" reads badly, and the spare type spoils planning.
    for pair, types in links.edges.items():
        if "kind" in types and "family" in types:
            del types["family"]
            links.arguable.discard((pair, "family"))
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


def phrase(links: Links, a: str, b: str, type_: str) -> str:
    return links.types(a, b)[type_]
