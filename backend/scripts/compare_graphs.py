"""Compare global-threshold vs mutual-kNN edges for game quality (hubness)."""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.embeddings import Embeddings  # noqa: E402

emb = Embeddings.load(settings)
V = emb.vectors
N = len(emb)
S = V @ V.T
np.fill_diagonal(S, -np.inf)


def stats(adj, label):
    deg = np.array([len(a) for a in adj])
    print(f"{label:14} degree min/median/mean/max={deg.min()}/{int(np.median(deg))}/"
          f"{deg.mean():.1f}/{deg.max()}  isolated={(deg==0).sum()}")
    return deg


def bfs_dist(adj, src):
    dist = np.full(N, -1, np.int32)
    dist[src] = 0
    q = deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if dist[v] == -1:
                dist[v] = dist[u] + 1
                q.append(int(v))
    return dist


# Global threshold (current approach) calibrated to ~degree 12.
target_deg = 12
thr = float(np.quantile(S[np.isfinite(S)][::97], 1 - target_deg / (N - 1)))
g_thr = [np.flatnonzero(S[i] >= thr) for i in range(N)]

# Mutual k-NN: edge iff each is in the other's top-K.
K = 12
topk = [set(np.argpartition(-S[i], K)[:K].tolist()) for i in range(N)]
g_knn = [np.array([j for j in topk[i] if i in topk[j]], np.int32) for i in range(N)]

print(f"threshold={thr:.3f}  K={K}\n")
stats(g_thr, "global-thr")
stats(g_knn, "mutual-kNN")

# How often does the WORST hub appear as a neighbor?
for label, adj in (("global-thr", g_thr), ("mutual-kNN", g_knn)):
    appears = np.zeros(N, int)
    for a in adj:
        for j in a:
            appears[j] += 1
    worst = np.argsort(-appears)[:8]
    print(f"\n{label} most-connected words: "
          + ", ".join(f"{emb.words[i]}({appears[i]})" for i in worst))

# Sample neighborhoods for hub-prone words.
print("\nNeighborhoods:")
for w in ("money", "ball", "fire", "house"):
    i = emb.index[w]
    for label, adj in (("global-thr", g_thr), ("mutual-kNN", g_knn)):
        nbs = adj[i]
        sims = S[i, nbs]
        order = np.argsort(-sims)[:8]
        names = ", ".join(f"{emb.words[nbs[o]]}({sims[o]:.2f})" for o in order)
        print(f"  {w:7} {label:11}: {names}")
