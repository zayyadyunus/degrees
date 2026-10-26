"""Compare candidate move-acceptance rules on two axes that actually matter:

  RECALL  - of the human-labeled "should connect" pairs, how many are accepted?
  HUBS    - does the rule create high-degree shortcut words that wreck puzzles?

The point: naively raising k (or going one-directional) trades hub safety for
recall, and STILL misses the cross-domain symbolic/material links (which live
far down the neighbor list). That motivates a typed-relation overlay, not just
k-tuning.

Run from backend/:  .venv/bin/python scripts/rule_experiment.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parent.parent / "data"
words = json.loads((DATA / "words.json").read_text())
V = np.load(DATA / "vectors.npy")
idx = {w: i for i, w in enumerate(words)}
n = len(words)

S = V @ V.T
np.fill_diagonal(S, -np.inf)
order = np.argsort(-S, axis=1)
rank = np.empty_like(order)
rows = np.arange(n)[:, None]
rank[rows, order] = np.arange(n)[None, :]

# Reuse the labeled pairs from the audit (flattened, vocab-filtered).
from importlib import import_module
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
LABELED = import_module("audit_relations").RELATIONS
PAIRS = [(a, b) for pairs in LABELED.values() for (a, b) in pairs
         if a in idx and b in idx]


def topk_sets(k: int) -> list[set[int]]:
    return [set(order[i, :k].tolist()) for i in range(n)]


def degree_stats(adj: list[set[int]]) -> tuple[int, int, list[str]]:
    deg = np.array([len(a) for a in adj])
    top = np.argsort(-deg)[:5]
    hubs = [f"{words[i]}({deg[i]})" for i in top]
    return int(deg.max()), int(np.median(deg)), hubs


def recall(accept) -> float:
    hits = sum(accept(idx[a], idx[b]) for a, b in PAIRS)
    return 100 * hits / len(PAIRS)


def build_adj(accept) -> list[set[int]]:
    adj: list[set[int]] = [set() for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            if accept(i, j):
                adj[i].add(j)
                adj[j].add(i)
    return adj


def main() -> None:
    print(f"{len(PAIRS)} labeled pairs.\n")
    print(f"{'rule':<34}{'recall':>8}{'maxdeg':>8}{'meddeg':>8}   top hubs")
    print("-" * 96)

    rules = []
    for k in (12, 16, 20):
        tk = topk_sets(k)
        rules.append((f"mutual top-{k} (current style)",
                      lambda i, j, tk=tk: j in tk[i] and i in tk[j]))
    for k in (12, 20):
        tk = topk_sets(k)
        rules.append((f"one-way top-{k} (union)",
                      lambda i, j, tk=tk: j in tk[i] or i in tk[j]))
    # Asymmetric tolerance: strict on one side, lenient on the other.
    tk12, tk30 = topk_sets(12), topk_sets(30)
    rules.append(("soft-mutual top-12/30",
                  lambda i, j: (j in tk12[i] and i in tk30[j]) or
                               (i in tk12[j] and j in tk30[i])))
    # Mutual-12 OR a high cosine floor (catch tight pairs ranked just outside k).
    rules.append(("mutual-12 OR cos>=0.45",
                  lambda i, j: (j in tk12[i] and i in tk12[j]) or S[i, j] >= 0.45))

    for name, accept in rules:
        r = recall(accept)
        adj = build_adj(accept)
        mx, med, hubs = degree_stats(adj)
        print(f"{name:<34}{r:7.0f}%{mx:8d}{med:8d}   {', '.join(hubs)}")

    # Which pairs does the BEST k-based rule still miss?
    print("\nPairs still missed by one-way top-20 (the most permissive k-rule):")
    tk20 = topk_sets(20)
    miss = [(a, b) for a, b in PAIRS
            if not (idx[b] in tk20[idx[a]] or idx[a] in tk20[idx[b]])]
    for a, b in miss:
        ia, ib = idx[a], idx[b]
        print(f"   {a:>10} -> {b:<10}  cos={S[ia,ib]:5.2f}  "
              f"ranks {int(rank[ia,ib])}/{int(rank[ib,ia])}")
    print(f"\n=> {len(miss)} pairs are unreachable by ANY k-rule: cross-domain "
          "symbolic/material links live too far down the neighbor list.")


if __name__ == "__main__":
    main()
