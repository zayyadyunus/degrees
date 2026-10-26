"""Prototype: base embedding graph + a sparse TYPED-RELATION overlay.

Architecture this demonstrates:
  - BASE  = mutual k-NN over embeddings (broad associative coverage; the
    current rule). Great at synonym/antonym/is-a/co-hyponym/part-of.
  - OVERLAY = a small typed-edge table (IsA, PartOf, MadeOf, UsedFor,
    AtLocation, Causes, SymbolOf, HasProperty). In production this comes from
    ConceptNet assertions filtered to the wordlist; here a hand-authored sample
    stands in for it. These are exactly the cross-domain symbolic/material links
    the audit showed embeddings rank too low to ever catch.

Key claim verified below: because typed edges are SPARSE (a few per word), the
overlay recovers the misses WITHOUT inflating node degree (no new hub words),
which is the property that makes the base rule produce good puzzles.

Run from backend/:  .venv/bin/python scripts/prototype_typed_overlay.py
"""
from __future__ import annotations

import json
from importlib import import_module
from pathlib import Path
import sys

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "data"
words = json.loads((DATA / "words.json").read_text())
V = np.load(DATA / "vectors.npy")
idx = {w: i for i, w in enumerate(words)}
n = len(words)

S = V @ V.T
np.fill_diagonal(S, -np.inf)
order = np.argsort(-S, axis=1)

sys.path.insert(0, str(Path(__file__).resolve().parent))
LABELED = import_module("audit_relations").RELATIONS
PAIRS = [(a, b) for pairs in LABELED.values() for (a, b) in pairs
         if a in idx and b in idx]

# --- BASE: mutual top-12 (the current rule) ----------------------------------
K = 12
tk = [set(order[i, :K].tolist()) for i in range(n)]
base: list[set[int]] = [set() for _ in range(n)]
for i in range(n):
    for j in tk[i]:
        if i in tk[j]:
            base[i].add(j)
            base[j].add(i)

# --- OVERLAY: typed edges (a stand-in for ConceptNet, filtered to vocab) ------
# Each entry: (relation, word_a, word_b). Direction is informational only;
# the game graph is undirected.
TYPED_EDGES = [
    ("MadeOf",     "glass",   "sand"),
    ("MadeOf",     "paper",   "wood"),
    ("MadeOf",     "wine",    "grape"),
    ("MadeOf",     "bread",   "flour"),   # flour not in vocab -> dropped, shown as such
    ("Causes",     "seed",    "tree"),
    ("Causes",     "fire",    "ash"),
    ("SymbolOf",   "gold",    "money"),
    ("SymbolOf",   "diamond", "treasure"),
    ("SymbolOf",   "red",     "anger"),
    ("SymbolOf",   "white",   "peace"),
    ("SymbolOf",   "crown",   "king"),
    ("HasProperty", "bitter", "coffee"),
    ("HasProperty", "yellow", "lemon"),
    ("UsedFor",    "saw",     "wood"),
    ("AtLocation", "bee",     "flower"),
]


def overlay_edges() -> list[tuple[str, int, int]]:
    out, dropped = [], []
    for rel, a, b in TYPED_EDGES:
        if a in idx and b in idx:
            out.append((rel, idx[a], idx[b]))
        else:
            dropped.append((rel, a, b))
    if dropped:
        for rel, a, b in dropped:
            print(f"  (overlay edge dropped, not in vocab: {rel} {a}-{b})")
    return out


def stats(adj: list[set[int]]) -> str:
    deg = np.array([len(a) for a in adj])
    top = np.argsort(-deg)[:5]
    hubs = ", ".join(f"{words[i]}({deg[i]})" for i in top)
    return f"maxdeg={deg.max()} meddeg={int(np.median(deg))}  hubs: {hubs}"


def recall(adj: list[set[int]]) -> float:
    hits = sum(idx[b] in adj[idx[a]] for a, b in PAIRS)
    return 100 * hits / len(PAIRS)


def main() -> None:
    print(f"{len(PAIRS)} labeled pairs.\n")
    print("BASE (mutual top-12):")
    print(f"   recall={recall(base):.0f}%   {stats(base)}\n")

    edges = overlay_edges()
    combined = [set(a) for a in base]
    added = 0
    for _rel, i, j in edges:
        if j not in combined[i]:
            combined[i].add(j)
            combined[j].add(i)
            added += 1

    print(f"\nOVERLAY added {added} new edges ({len(edges)} typed edges, "
          f"{len(edges) - added} already present in base).")
    print("BASE + OVERLAY:")
    print(f"   recall={recall(combined):.0f}%   {stats(combined)}\n")

    # Show that degree barely moved (no hubs created).
    db = np.array([len(a) for a in base])
    dc = np.array([len(a) for a in combined])
    changed = np.flatnonzero(dc > db)
    print("Per-word degree change (only affected words):")
    for i in sorted(changed, key=lambda i: -dc[i]):
        print(f"   {words[i]:>10}: {db[i]} -> {dc[i]}")


if __name__ == "__main__":
    main()
