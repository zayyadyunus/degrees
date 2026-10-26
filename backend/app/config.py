"""Runtime configuration for the Degrees backend.

Everything is overridable via environment variables so the same code runs in
dev (synthetic embeddings) and prod (real GloVe vectors) without edits.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent  # .../backend
DATA_DIR = BASE_DIR / "data"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # --- Connection / difficulty ----------------------------------------
    # Edges are MUTUAL k-nearest-neighbors: a move prev -> next is valid iff
    # each word is among the other's k nearest by cosine similarity. k is the
    # difficulty knob — smaller k means fewer valid moves and longer paths.
    k: int = int(os.environ.get("DEGREES_K", "12"))

    # 6 connections == 7 words total.
    max_connections: int = int(os.environ.get("DEGREES_MAX_CONNECTIONS", "6"))

    # Puzzle generation: target an optimal distance in this inclusive range
    # so puzzles are neither trivial nor unwinnable. Must be <= max_connections.
    min_puzzle_distance: int = int(os.environ.get("DEGREES_MIN_DISTANCE", "3"))
    max_puzzle_distance: int = int(os.environ.get("DEGREES_MAX_DISTANCE", "5"))

    # Cap the graph size to keep the dense similarity matrix affordable.
    max_words: int = int(os.environ.get("DEGREES_MAX_WORDS", "5000"))

    # --- Data sources ----------------------------------------------------
    vectors_path: Path = Path(os.environ.get("DEGREES_VECTORS", str(DATA_DIR / "vectors.npy")))
    words_path: Path = Path(os.environ.get("DEGREES_WORDS", str(DATA_DIR / "words.json")))
    wordlist_path: Path = Path(os.environ.get("DEGREES_WORDLIST", str(DATA_DIR / "wordlist.txt")))

    # Typed-relation overlay: a sparse list of word pairs (ConceptNet IsA,
    # PartOf, MadeOf, SymbolOf, ...) unioned onto the embedding graph. These are
    # the cross-domain links embeddings rank too low to catch on their own.
    relations_path: Path = Path(os.environ.get("DEGREES_RELATIONS", str(DATA_DIR / "relations.json")))
    use_relations: bool = _env_bool("DEGREES_USE_RELATIONS", True)

    # If real vectors are absent, fall back to deterministic synthetic vectors
    # so the API is runnable. Synthetic connections are MEANINGLESS — dev only.
    allow_synthetic: bool = _env_bool("DEGREES_ALLOW_SYNTHETIC", True)

    seed: int = int(os.environ.get("DEGREES_SEED", "1234"))

    # --- Serving ----------------------------------------------------------
    # Extra browser origins allowed to call the API, comma-separated (e.g.
    # "https://degrees.example.com"). Localhost on any port is always allowed
    # for dev. Not needed when the API serves the frontend itself (same origin).
    cors_origins: list[str] = [
        o.strip() for o in os.environ.get("DEGREES_CORS_ORIGINS", "").split(",") if o.strip()
    ]

    # If set, serve the built frontend (frontend/dist) from this directory so
    # the UI and API share one origin in production.
    static_dir: Path | None = (
        Path(os.environ["DEGREES_STATIC_DIR"]) if os.environ.get("DEGREES_STATIC_DIR") else None
    )


settings = Settings()
