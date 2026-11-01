"""Check links.txt for the mistakes reviews keep finding.

    cd backend && .venv/bin/python -m proto.lint

Errors (tests fail on these):
  * a category word in a feature list: "fruit" under sweet makes lemon sweet.
  * a feature list naming a word twice, or an unknown word in an avoid pair.

Warnings (likely missing links, to check by hand):
  * sibling gaps: most of a word's category siblings link to X by some
    type, but the word doesn't link to X at all (duck, chicken and bird
    "make egg"; owl doesn't). Each one is a strike a player didn't earn
    whenever the word and X share a board.
"""
from __future__ import annotations

from collections import defaultdict

from .typed import Links, load

SIBLING_SHARE = 0.5   # flag when at least this share of siblings has the link


def errors(links: Links) -> list[str]:
    out = []
    for adj, nouns in links.features.items():
        for w in sorted(set(nouns) & links.categories):
            out.append(f"category word {w!r} in '{adj} feature' (its members inherit the feature)")
        dupes = sorted({w for w in nouns if nouns.count(w) > 1})
        if dupes:
            out.append(f"'{adj} feature' lists {', '.join(dupes)} twice")
    for pair in links.avoid:
        for w in sorted(pair - links.words):
            out.append(f"avoid pair {'/'.join(sorted(pair))}: {w!r} isn't a word")
    return out


def sibling_gaps(links: Links) -> list[tuple[str, str, str, list[str]]]:
    """(word, x, type, siblings that have it) for likely missing links."""
    members: dict[str, list[str]] = defaultdict(list)
    for w, ps in links.parents.items():
        for p in ps:
            members[p].append(w)
    gaps = set()
    out = []
    for cat, ws in sorted(members.items()):
        if len(ws) < 3:
            continue
        # x -> type -> siblings linking to x by that type (family and kind
        # links come from the category itself, so they're not evidence).
        has: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
        for w in ws:
            for x in links.adj[w]:
                if x in ws or x == cat.lstrip("~"):
                    continue
                for t in links.types(w, x):
                    # Siblings don't share colours or tastes (apple is red,
                    # banana isn't), so features aren't evidence either.
                    if t not in ("family", "kind", "feature"):
                        has[x][t].append(w)
        for x, by_type in sorted(has.items()):
            for t, holders in sorted(by_type.items()):
                if len(holders) < 2 or len(holders) / (len(ws) - 1) < SIBLING_SHARE:
                    continue
                for w in sorted(set(ws) - set(holders)):
                    if w != x and not links.types(w, x) and (w, x) not in gaps:
                        gaps.add((w, x))
                        out.append((w, x, t, sorted(holders)))
    return out


def main() -> None:
    links = load()
    errs = errors(links)
    for e in errs:
        print("ERROR  ", e)
    gaps = sibling_gaps(links)
    for w, x, t, holders in gaps:
        print(f"check  {w} / {x}: no link, but {', '.join(holders)} link to {x} ({t})")
    print(f"\n{len(errs)} errors, {len(gaps)} sibling gaps to check")


if __name__ == "__main__":
    main()
