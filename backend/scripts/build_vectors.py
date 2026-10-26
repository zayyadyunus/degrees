"""Build real word vectors for Degrees from a GloVe-format file.

Reads a GloVe text file (each line: `word v1 v2 ... vd`), keeps only the words
in the curated wordlist, L2-normalizes them, and writes:
    data/vectors.npy   (float32, shape [N, dim])
    data/words.json    (list[str], aligned with vectors rows)

Download GloVe vectors first, e.g.:
    curl -LO https://nlp.stanford.edu/data/glove.6B.zip
    unzip glove.6B.zip            # gives glove.6B.50d.txt, .100d.txt, ...

Then:
    python scripts/build_vectors.py --glove glove.6B.100d.txt
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"


def read_wordlist(path: Path) -> list[str]:
    words, seen = [], set()
    for line in path.read_text(encoding="utf-8").splitlines():
        w = line.strip().lower()
        if w and not w.startswith("#") and w not in seen:
            seen.add(w)
            words.append(w)
    return words


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--glove", required=True, type=Path, help="GloVe .txt file")
    parser.add_argument("--wordlist", type=Path, default=DATA_DIR / "wordlist.txt")
    parser.add_argument("--out-vectors", type=Path, default=DATA_DIR / "vectors.npy")
    parser.add_argument("--out-words", type=Path, default=DATA_DIR / "words.json")
    args = parser.parse_args()

    wanted = set(read_wordlist(args.wordlist))
    print(f"Wordlist has {len(wanted)} words; scanning {args.glove} ...")

    found: dict[str, np.ndarray] = {}
    with args.glove.open(encoding="utf-8") as fh:
        for line in fh:
            space = line.find(" ")
            word = line[:space]
            if word in wanted and word not in found:
                found[word] = np.fromstring(line[space + 1:], sep=" ", dtype=np.float32)

    missing = sorted(wanted - found.keys())
    if missing:
        print(f"WARNING: {len(missing)} words not in GloVe (dropped): {missing[:20]}"
              + (" ..." if len(missing) > 20 else ""))

    words = sorted(found.keys())
    vectors = np.stack([found[w] for w in words]).astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    vectors /= norms

    args.out_vectors.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.out_vectors, vectors)
    args.out_words.write_text(json.dumps(words), encoding="utf-8")
    print(f"Wrote {len(words)} vectors (dim={vectors.shape[1]}) to {args.out_vectors}")


if __name__ == "__main__":
    main()
