"""Word embeddings: the vector space the whole game is built on.

Loads real vectors (built from GloVe via scripts/build_vectors.py) when present,
otherwise builds a deterministic *synthetic* space from the wordlist so the API
stays runnable in development. Synthetic similarities are not semantically
meaningful — they only exercise the plumbing.

Vectors are stored L2-normalized, so cosine similarity is a plain dot product.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger("degrees.embeddings")


def _normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype(np.float32)


def _read_wordlist(path: Path) -> list[str]:
    words: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        word = line.strip().lower()
        if not word or word.startswith("#") or word in seen:
            continue
        seen.add(word)
        words.append(word)
    return words


class Embeddings:
    def __init__(self, words: list[str], vectors: np.ndarray, synthetic: bool):
        if vectors.shape[0] != len(words):
            raise ValueError("words and vectors length mismatch")
        self.words = words
        self.index = {w: i for i, w in enumerate(words)}
        self.vectors = _normalize(vectors)
        self.synthetic = synthetic

    def __len__(self) -> int:
        return len(self.words)

    @property
    def dim(self) -> int:
        return int(self.vectors.shape[1])

    def contains(self, word: str) -> bool:
        return word in self.index

    def similarity(self, a: str, b: str) -> float:
        ia, ib = self.index[a], self.index[b]
        return float(self.vectors[ia] @ self.vectors[ib])

    # -- construction ----------------------------------------------------
    @classmethod
    def load(cls, settings) -> "Embeddings":
        if settings.vectors_path.exists() and settings.words_path.exists():
            return cls._load_real(settings)
        if settings.allow_synthetic:
            logger.warning(
                "No vectors at %s — using SYNTHETIC embeddings. Connections are "
                "NOT semantically meaningful. Build real vectors with "
                "scripts/build_vectors.py for real gameplay.",
                settings.vectors_path,
            )
            return cls._build_synthetic(settings)
        raise FileNotFoundError(
            f"Missing embeddings ({settings.vectors_path}) and synthetic fallback "
            "disabled (DEGREES_ALLOW_SYNTHETIC=0)."
        )

    @classmethod
    def _load_real(cls, settings) -> "Embeddings":
        words = json.loads(settings.words_path.read_text(encoding="utf-8"))
        vectors = np.load(settings.vectors_path)
        if settings.max_words and len(words) > settings.max_words:
            words = words[: settings.max_words]
            vectors = vectors[: settings.max_words]
        logger.info("Loaded %d real word vectors (dim=%d).", len(words), vectors.shape[1])
        return cls(words, vectors.astype(np.float32), synthetic=False)

    @classmethod
    def _build_synthetic(cls, settings) -> "Embeddings":
        """Place words on a smooth manifold so neighbors-by-index are similar.

        This yields a ring-like similarity graph with non-trivial path lengths,
        which is exactly what puzzle generation needs to exercise. It says
        nothing about real meaning.
        """
        words = _read_wordlist(settings.wordlist_path)
        if settings.max_words:
            words = words[: settings.max_words]
        n = len(words)
        positions = np.arange(n, dtype=np.float64) / max(n, 1)
        freqs = [1, 2, 3, 4, 5, 6]
        cols = []
        for f in freqs:
            angle = 2.0 * np.pi * f * positions
            cols.append(np.sin(angle))
            cols.append(np.cos(angle))
        vectors = np.stack(cols, axis=1).astype(np.float32)
        return cls(words, vectors, synthetic=True)
