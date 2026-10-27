"""FastAPI app for Degrees — connect a start word to a target word semantically.

Run from the backend/ directory:
    uvicorn app.main:app --reload
Interactive docs at http://localhost:8000/docs
"""
from __future__ import annotations

import datetime as dt
import logging

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .bootstrap import build_engine
from .config import settings
from .game import PuzzleUnavailable
from .ratelimit import RateLimiter
from .models import (
    GameState,
    HintResponse,
    MoveRequest,
    MoveResponse,
    NewGameRequest,
    ScoreResponse,
)
from .store import GameStore

logging.basicConfig(level=logging.INFO)

_docs = settings.enable_docs
app = FastAPI(
    title="Degrees",
    version="0.1.0",
    docs_url="/docs" if _docs else None,
    redoc_url="/redoc" if _docs else None,
    openapi_url="/openapi.json" if _docs else None,
)

# Allow the Vite dev server (and other local origins) to call the API, plus
# any deployed frontend origins listed in DEGREES_CORS_ORIGINS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_methods=["*"],
    allow_headers=["*"],
)

# Built once at import: loading vectors and the dense similarity graph is the
# expensive part, so we do it a single time and share it across requests.
_engine = build_engine(settings)
_embeddings, _graph, _overlay = _engine.embeddings, _engine.graph, _engine.overlay
_store = GameStore(ttl_seconds=settings.game_ttl_seconds, max_games=settings.max_games)
_limit_new_games = RateLimiter(
    settings.new_games_per_minute, client_ip_header=settings.client_ip_header
)
_limit_moves = RateLimiter(settings.moves_per_minute, client_ip_header=settings.client_ip_header)


def _daily_date(requested: dt.date | None) -> dt.date:
    """The player's local date, allowed within a day of UTC (time zones)."""
    today = dt.datetime.now(dt.timezone.utc).date()
    day = today if requested is None else requested
    if abs((day - today).days) > 1:
        raise HTTPException(status_code=400, detail="date must be today")
    if day < settings.daily_epoch:
        # Before launch: the UI falls back to practice and shows this date.
        raise HTTPException(
            status_code=404,
            detail={"error": "no_daily_yet", "daily_starts": settings.daily_epoch.isoformat()},
        )
    return day


def _require_game(game_id: str):
    game = _store.get(game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="game not found")
    return game


@app.get("/vocabulary")
def vocabulary() -> dict:
    """All playable words, for client-side autocomplete."""
    return {"words": _embeddings.words}


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "vocabulary": len(_embeddings),
        "synthetic_embeddings": _embeddings.synthetic,
        "k": _graph.k,
        "relation_overlay_edges": len(_overlay.edges),
        "max_connections": settings.max_connections,
    }


@app.post(
    "/games",
    response_model=GameState,
    status_code=201,
    dependencies=[Depends(_limit_new_games)],
)
def create_game(req: NewGameRequest | None = None) -> GameState:
    req = req or NewGameRequest()
    try:
        if req.daily:
            game = _engine.daily_game(_daily_date(req.date))
        else:
            game = _engine.new_game(req.min_distance, req.max_distance)
    except (PuzzleUnavailable, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _store.save(game)
    return GameState.from_game(game)


@app.get("/games/{game_id}", response_model=GameState)
def get_game(game_id: str) -> GameState:
    return GameState.from_game(_require_game(game_id))


@app.post(
    "/games/{game_id}/moves",
    response_model=MoveResponse,
    dependencies=[Depends(_limit_moves)],
)
def submit_move(game_id: str, req: MoveRequest) -> MoveResponse:
    game = _require_game(game_id)
    result = _engine.submit(game, req.word)
    _store.save(game)  # strikes change the game too
    return MoveResponse(
        accepted=result.accepted,
        reason=result.reason,
        similarity=result.similarity,
        relation=result.relation,
        strike=result.strike,
        game=GameState.from_game(game),
    )


@app.post(
    "/games/{game_id}/back",
    response_model=GameState,
    dependencies=[Depends(_limit_moves)],
)
def take_back(game_id: str) -> GameState:
    """Undo the last word (out of a dead end). The move still counts."""
    game = _require_game(game_id)
    if not _engine.back(game):
        raise HTTPException(status_code=409, detail="nothing to take back")
    _store.save(game)
    return GameState.from_game(game)


# POST: revealing a hint is recorded on the game (it shows on the result).
@app.post(
    "/games/{game_id}/hint",
    response_model=HintResponse,
    dependencies=[Depends(_limit_moves)],
)
def get_hint(game_id: str) -> HintResponse:
    game = _require_game(game_id)
    hint = _engine.hint(game)
    _store.save(game)
    return HintResponse(
        hint=hint,
        message=None if hint else (
            "Dead end — go back a step" if game.status == "in_progress" else "game is already over"
        ),
        game=GameState.from_game(game),
    )


@app.get("/games/{game_id}/score", response_model=ScoreResponse)
def get_score(game_id: str) -> ScoreResponse:
    return ScoreResponse(**_engine.score(_require_game(game_id)))


# Mounted last so the API routes above take precedence over static files.
if settings.static_dir is not None:
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
