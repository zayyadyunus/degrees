"""Candidate word pairs for Claude to label (Phase 2, step 1).

Three sources, unioned:
  - vectors: each tile's k nearest tiles by Numberbatch vector;
  - WordNet: kind-of and part-of relations between tiles (top noun senses),
    which vectors can rank low (wheel / car, oak / tree);
  - Claude's suggestions (`label.py suggest`): partners named from the whole
    list, which catch hub words (food, table, water) and compounds.

Checked against the prototype: of the hand-typed links whose words are
both tiles, how many does each k catch?

    cd backend
    .venv/bin/python scripts/build_vectors.py --glove data/numberbatch-en.txt.gz \\
        --wordlist proto/labels/tiles-next.txt \\
        --out-vectors proto/labels/vectors-next.npy --out-words proto/labels/words-next.json
    .venv/bin/python -m proto.candidates [--k 30]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .label import PAIR_TYPES
from .typed import load

HERE = Path(__file__).parent
LABELS = HERE / "labels"
DATA = HERE.parent / "data"


def tiles() -> list[str]:
    out = []
    for line in (HERE / "vocab.txt").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "features", "cut")):
            out.append(line)
    return out


def vector_pairs(words: list[str], k: int) -> dict[frozenset[str], int]:
    """pair -> best neighbour rank (1 = nearest), over each word's k nearest."""
    have = json.loads((DATA / "typed_words.json").read_text())
    vecs = np.load(DATA / "typed_vectors.npy")
    where = {w: i for i, w in enumerate(have)}
    vocab = [w for w in words if w in where]
    m = vecs[[where[w] for w in vocab]]
    sims = m @ m.T
    np.fill_diagonal(sims, -np.inf)
    nearest = np.argsort(-sims, axis=1)[:, :k]
    out: dict[frozenset[str], int] = {}
    for i, row in enumerate(nearest):
        for r, j in enumerate(row, 1):
            p = frozenset((vocab[i], vocab[int(j)]))
            out[p] = min(out.get(p, r), r)
    return out


def wordnet_pairs(words: list[str], senses: int = 2, depth: int = 3) -> set[frozenset[str]]:
    """Kind-of (hypernyms, a few levels up) and part-of / made-of (meronyms,
    holonyms) between tiles, from each word's most common noun senses."""
    from nltk.corpus import wordnet as wn

    vocab = set(words)
    out: set[frozenset[str]] = set()

    def names(s) -> set[str]:
        return {l.name().lower() for l in s.lemmas()} & vocab

    for w in words:
        for s in wn.synsets(w, pos=wn.NOUN)[:senses]:
            related = set()
            frontier = [s]
            for _ in range(depth):
                frontier = [h for f in frontier for h in f.hypernyms()]
                related.update(frontier)
            for rel in ("part_meronyms", "substance_meronyms", "member_meronyms",
                        "part_holonyms", "substance_holonyms", "member_holonyms"):
                related.update(getattr(s, rel)())
            for r in related:
                for n in names(r) - {w}:
                    out.add(frozenset((w, n)))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=30)
    ap.add_argument("--suggest", default="suggest-next", help="suggestion run to add ('' for none)")
    args = ap.parse_args()
    words = tiles()
    wn_pairs = wordnet_pairs(words)
    sg_path = LABELS / f"{args.suggest}.suggestions.json"
    sg_pairs = {frozenset(p) for p in json.loads(sg_path.read_text())} if args.suggest and sg_path.exists() else set()

    # How well does each k catch the links we typed by hand?
    proto = load()
    vocab = set(words)
    gold = {p for p, t in proto.edges.items() if p <= vocab and set(t) & set(PAIR_TYPES)}
    print(f"{len(words)} tiles; {len(wn_pairs)} WordNet pairs; "
          f"{len(gold)} hand-typed prototype links between tiles to check against")
    if sg_pairs:
        print(f"Claude suggested {len(sg_pairs)} pairs, catching {len(gold & sg_pairs) / len(gold):.0%} of hand links alone")
    print("   k   pairs   catches hand links" + ("   (vectors + WordNet + suggestions)" if sg_pairs else "   (vectors + WordNet)"))
    for k in (10, 20, 30, 40, 50):
        vp = vector_pairs(words, k)
        both = set(vp) | wn_pairs | sg_pairs
        print(f"  {k:>3} {len(both):>7}   {len(gold & both) / len(gold):.0%}")

    vp = vector_pairs(words, args.k)
    pairs = set(vp) | wn_pairs | sg_pairs
    rows = [{"a": a, "b": b, "rank": vp.get(p), "wordnet": p in wn_pairs, "suggested": p in sg_pairs}
            for p in sorted(pairs, key=sorted) for a, b in [sorted(p)]]
    out = LABELS / f"candidates-next-k{args.k}.json"
    out.write_text(json.dumps(rows))
    missed = sorted(tuple(sorted(p)) for p in gold - pairs)
    print(f"\nk={args.k}: {len(rows)} pairs ({len(rows) / len(words):.1f} per tile) -> {out}")
    print(f"  hand links it misses ({len(missed)}): " + ", ".join(f"{a}/{b}" for a, b in missed[:60]))


if __name__ == "__main__":
    main()
