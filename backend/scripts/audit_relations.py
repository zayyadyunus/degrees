"""Audit how well the live game rule (mutual k-NN) covers named semantic relations.

For a curated set of word pairs grouped by relation type, this reports:
  - cosine similarity,
  - each word's rank in the other's nearest-neighbor list,
  - whether the move is ACCEPTED by the real game rule (mutual top-k membership).

Run from backend/:  .venv/bin/python scripts/audit_relations.py
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

K = 12  # must match DEGREES_K default

DATA = Path(__file__).resolve().parent.parent / "data"
words = json.loads((DATA / "words.json").read_text())
V = np.load(DATA / "vectors.npy")  # already L2-normalized
idx = {w: i for i, w in enumerate(words)}

# Full cosine matrix (small vocab) and per-row neighbor ranking.
S = V @ V.T
np.fill_diagonal(S, -np.inf)
# rank_of[i] gives, for each j, how many words are strictly closer to i than j is.
order = np.argsort(-S, axis=1)            # nearest-first column order per row
rank = np.empty_like(order)
rows = np.arange(len(words))[:, None]
rank[rows, order] = np.arange(len(words))[None, :]  # rank[i, j] = position of j among i's neighbors (0 = nearest)

# relation -> list of (a, b) pairs; "->" reads naturally as a relates-to b
RELATIONS: dict[str, list[tuple[str, str]]] = {
    "1. Same meaning  (is another word for)": [
        ("sea", "ocean"), ("road", "street"), ("sound", "noise"),
        ("photo", "picture"), ("film", "movie"), ("rock", "stone"),
        ("home", "house"), ("joy", "happy"),
    ],
    "2. Opposite  (is the opposite of)": [
        ("hot", "cold"), ("big", "small"), ("day", "night"), ("love", "hate"),
        ("war", "peace"), ("good", "bad"), ("black", "white"), ("fast", "slow"),
        ("hard", "soft"), ("strong", "weak"), ("old", "new"), ("clean", "dirty"),
    ],
    "3. Is a kind of  (is a type of)": [
        ("dog", "animal"), ("apple", "fruit"), ("carrot", "vegetable"),
        ("violin", "instrument"), ("ant", "insect"), ("eagle", "bird"),
        ("hammer", "tool"), ("soup", "food"),
    ],
    "4. Same category  (is the same kind of thing as)": [
        ("dog", "cat"), ("lion", "tiger"), ("fork", "spoon"), ("violin", "guitar"),
        ("red", "blue"), ("gold", "silver"), ("cup", "bowl"), ("sun", "moon"),
    ],
    "5. Part of  (is a part of)": [
        ("wheel", "car"), ("leaf", "tree"), ("finger", "hand"), ("eye", "face"),
        ("tooth", "mouth"), ("engine", "car"), ("roof", "house"), ("page", "book"),
    ],
    "6. Made of  (is made of)": [
        ("milk", "cow"), ("butter", "milk"), ("cheese", "milk"), ("wine", "grape"),
        ("ice", "water"), ("glass", "sand"), ("honey", "bee"), ("paper", "wood"),
    ],
    "7. Used for / does  (is used to ___)": [
        ("hammer", "nail"), ("saw", "wood"), ("pen", "paper"), ("teacher", "student"),
        ("soldier", "army"), ("astronaut", "space"), ("ship", "sea"), ("lamp", "light"),
    ],
    "8. Found with / at  (you find one near the other)": [
        ("fish", "sea"), ("shark", "ocean"), ("bee", "flower"), ("snow", "mountain"),
        ("sand", "beach"), ("tree", "forest"), ("star", "sky"), ("cloud", "sky"),
    ],
    "9. Causes / comes from  (leads to / comes from)": [
        ("fire", "smoke"), ("storm", "rain"), ("seed", "tree"), ("egg", "chicken"),
        ("flame", "fire"), ("fire", "ash"), ("cloud", "rain"), ("sun", "heat"),
    ],
    "10. Stands for  (is a symbol of)": [
        ("crown", "king"), ("heart", "love"), ("gold", "money"), ("crown", "queen"),
        ("diamond", "treasure"), ("dove", "peace"), ("red", "anger"), ("white", "peace"),
    ],
    "11. Has feature  (is a feature of)": [
        ("sweet", "sugar"), ("bitter", "coffee"), ("cold", "ice"), ("hot", "fire"),
        ("loud", "noise"), ("soft", "pillow"), ("yellow", "lemon"), ("round", "ball"),
    ],
}


def audit() -> None:
    print(f"Mutual k-NN rule, k={K}.  ACCEPT = each word in the other's top-{K}.\n")
    grand_total = grand_accept = 0
    for relation, pairs in RELATIONS.items():
        rows_out = []
        n_accept = n_valid = 0
        for a, b in pairs:
            if a not in idx or b not in idx:
                rows_out.append(f"    {a:>10} -> {b:<10}  (skipped: not in vocab)")
                continue
            n_valid += 1
            ia, ib = idx[a], idx[b]
            sim = float(S[ia, ib])
            ra, rb = int(rank[ia, ib]), int(rank[ib, ia])  # b's rank in a's list, a's rank in b's
            accepted = ra < K and rb < K
            n_accept += accepted
            mark = "OK " if accepted else " . "
            rows_out.append(
                f"  {mark} {a:>10} -> {b:<10}  cos={sim:5.2f}  "
                f"rank {a}->{b}: {ra:>3},  {b}->{a}: {rb:>3}"
            )
        grand_total += n_valid
        grand_accept += n_accept
        pct = (100 * n_accept / n_valid) if n_valid else 0
        print(f"{relation}   [{n_accept}/{n_valid} accepted, {pct:.0f}%]")
        print("\n".join(rows_out))
        print()
    print(f"OVERALL: {grand_accept}/{grand_total} pairs accepted "
          f"({100*grand_accept/grand_total:.0f}%)")


if __name__ == "__main__":
    audit()
