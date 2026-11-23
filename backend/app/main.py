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

from .bootstrap import build_engine, build_sixtype
from .config import settings
from .game import PuzzleUnavailable
from .ratelimit import RateLimiter
from .models import (
    RULES_SIXTYPE,
    Choice,
    GameState,
    HintResponse,
    MoveRequest,
    MoveResponse,
    NewGameRequest,
    ScoreResponse,
)
from .sixtype.engine import TypedGame
from .sixtype.links import CHAIN, TYPE_NAMES
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
# The six-type rules (app/sixtype/): dailies from settings.sixtype_from on.
_sixtype, _typed_dailies = build_sixtype(settings)
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


def _is_sixtype_day(day: dt.date) -> bool:
    return settings.sixtype_from is not None and day >= settings.sixtype_from


def _engine_for(game):
    return _sixtype if isinstance(game, TypedGame) else _engine


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
        "sixtype_from": settings.sixtype_from.isoformat() if settings.sixtype_from else None,
        "sixtype_dailies_through": (
            _typed_dailies.last_day.isoformat() if _typed_dailies.last_day else None
        ),
        "sixtype_practice_boards": len(_typed_dailies.practice),
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
            day = _daily_date(req.date)
            if _is_sixtype_day(day):
                puzzle = _typed_dailies.puzzle(day)
                if puzzle is None:
                    raise PuzzleUnavailable(f"no six-type daily frozen for {day}")
                game = _sixtype.start_game(puzzle, daily_number=_typed_dailies.number(day))
            else:
                game = _engine.daily_game(day)
        elif _is_sixtype_day(dt.datetime.now(dt.timezone.utc).date()):
            if not _typed_dailies.practice:
                raise PuzzleUnavailable("no six-type practice boards built")
            pool = _typed_dailies.practice
            game = _sixtype.start_game(pool[int(_engine.rng.integers(len(pool)))])
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
    if isinstance(game, TypedGame):
        r = _sixtype.submit(game, req.word, req.type)
        _store.save(game)
        return MoveResponse(
            accepted=r.accepted,
            reason=r.reason,
            relation=TYPE_NAMES[r.type] if r.type else None,
            strike=r.strike,
            type=r.type,
            why=r.why,
            choices=[Choice(type=c.type, name=c.name, why=c.why) for c in r.choices],
            game=GameState.from_game(game),
        )
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
    """Undo the last word (out of a dead end). Classic: the move still
    counts. Six-type: the link's type is refunded."""
    game = _require_game(game_id)
    if not _engine_for(game).back(game):
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
    hint = _engine_for(game).hint(game)
    _store.save(game)
    if hint is None:
        message = "Dead end — go back a step" if game.status == "in_progress" else "game is already over"
    elif isinstance(game, TypedGame):
        message = f"Spend {TYPE_NAMES[hint]} next"
    else:
        message = None
    return HintResponse(hint=hint, message=message, game=GameState.from_game(game))


@app.get("/games/{game_id}/score", response_model=ScoreResponse)
def get_score(game_id: str) -> ScoreResponse:
    game = _require_game(game_id)
    if isinstance(game, TypedGame):
        s = _sixtype.score(game)
        return ScoreResponse(
            status=s["status"], rules=RULES_SIXTYPE, connections_used=s["links"],
            moves=game.events.count("move"), optimal_distance=CHAIN, over_optimal=None,
            is_optimal=s["clean"], strikes=s["strikes"], hints_used=s["hints_used"],
            backs=s["backs"], clean=s["clean"],
        )
    return ScoreResponse(**_engine.score(game))


# Mounted last so the API routes above take precedence over static files.
if settings.static_dir is not None:
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
