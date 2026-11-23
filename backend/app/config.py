"""Runtime configuration for the Degrees backend.

Everything is overridable via environment variables so the same code runs in
dev (synthetic embeddings) and prod (real GloVe vectors) without edits.
"""
from __future__ import annotations

import datetime as dt
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

    # Tiles that don't connect cost a strike; this many loses.
    max_strikes: int = int(os.environ.get("DEGREES_MAX_STRIKES", "3"))

    # Word boards: middle tiles per puzzle, and how many previous dailies'
    # tiles a new board avoids reusing.
    board_size: int = int(os.environ.get("DEGREES_BOARD_SIZE", "10"))
    board_recent: int = int(os.environ.get("DEGREES_BOARD_RECENT", "3"))

    # Move budget. Every accepted move counts, including ones later taken
    # back, so backing out of a dead end costs moves, not just time.
    max_moves: int = int(os.environ.get("DEGREES_MAX_MOVES", "8"))

    # Daily puzzle #1 falls on this date (YYYY-MM-DD).
    daily_epoch: dt.date = dt.date.fromisoformat(os.environ.get("DEGREES_DAILY_EPOCH", "2026-11-28"))

    # Keep consecutive dailies feeling different: a word that started or
    # ended a daily in the last N days can't start/end today's, and a word
    # on any route in the last M days can't start, end or sit mid-route
    # today, and a link on a par route in the last L days (glass -> sand)
    # can't be on today's. 0 disables a rule.
    daily_fresh_ends_days: int = int(os.environ.get("DEGREES_DAILY_FRESH_ENDS_DAYS", "14"))
    daily_fresh_route_days: int = int(os.environ.get("DEGREES_DAILY_FRESH_ROUTE_DAYS", "7"))
    daily_fresh_link_days: int = int(os.environ.get("DEGREES_DAILY_FRESH_LINK_DAYS", "45"))

    # Difficulty ramp: the par each weekday's daily aims for, Monday first.
    daily_par_by_weekday: tuple[int, ...] = tuple(
        int(x) for x in os.environ.get("DEGREES_DAILY_PAR_BY_WEEKDAY", "3,3,4,4,4,5,4").split(",")
    )

    # Reviewed dailies, served exactly as frozen (scripts/freeze_dailies.py).
    dailies_path: Path = Path(os.environ.get("DEGREES_DAILIES", str(DATA_DIR / "dailies.json")))

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

    # WordNet senses (most common first) considered per part of speech when
    # naming a link. Lower = fewer rare-sense mislabels but fewer puzzles.
    # 0 = all senses.
    wordnet_senses: int | None = int(os.environ.get("DEGREES_WORDNET_SENSES", "3")) or None

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

    # Expose /docs, /redoc and /openapi.json. Turn off in production.
    enable_docs: bool = _env_bool("DEGREES_DOCS", True)

    # --- Abuse limits -----------------------------------------------------
    # Games idle this long are dropped; past max_games the oldest are evicted.
    game_ttl_seconds: float = float(os.environ.get("DEGREES_GAME_TTL_HOURS", "24")) * 3600
    max_games: int = int(os.environ.get("DEGREES_MAX_GAMES", "100000"))

    # Requests per client IP per minute (0 disables).
    new_games_per_minute: int = int(os.environ.get("DEGREES_NEW_GAMES_PER_MIN", "30"))
    moves_per_minute: int = int(os.environ.get("DEGREES_MOVES_PER_MIN", "120"))

    # Header carrying the real client IP, set by the hosting proxy (e.g.
    # "Fly-Client-IP"). Unset: use the connection / X-Forwarded-For address.
    client_ip_header: str | None = os.environ.get("DEGREES_CLIENT_IP_HEADER") or None


settings = Settings()
