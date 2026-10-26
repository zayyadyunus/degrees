"""FastAPI app for Degrees — connect a start word to a target word semantically.

Run from the backend/ directory:
    uvicorn app.main:app --reload
Interactive docs at http://localhost:8000/docs
"""
from __future__ import annotations

import logging

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import settings
from .embeddings import Embeddings
from .game import Engine, PuzzleUnavailable
from .graph import WordGraph
from .relations import RelationOverlay
from .wordnet_relations import WordNetLabeler
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

app = FastAPI(title="Degrees", version="0.1.0")

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
_embeddings = Embeddings.load(settings)
_overlay = (
    RelationOverlay.load(settings.relations_path, _embeddings)
    if settings.use_relations
    else RelationOverlay.empty()
)
_graph = WordGraph(
    _embeddings,
    k=settings.k,
    rng=np.random.default_rng(settings.seed),
    extra_edges=_overlay.edges,
)
_labeler = WordNetLabeler()
_engine = Engine(_embeddings, _graph, settings, overlay=_overlay, labeler=_labeler)
_store = GameStore()


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


@app.post("/games", response_model=GameState, status_code=201)
def create_game(req: NewGameRequest | None = None) -> GameState:
    req = req or NewGameRequest()
    try:
        game = _engine.new_game(req.min_distance, req.max_distance)
    except (PuzzleUnavailable, ValueError) as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    _store.save(game)
    return GameState.from_game(game)


@app.get("/games/{game_id}", response_model=GameState)
def get_game(game_id: str) -> GameState:
    return GameState.from_game(_require_game(game_id))


@app.post("/games/{game_id}/moves", response_model=MoveResponse)
def submit_move(game_id: str, req: MoveRequest) -> MoveResponse:
    game = _require_game(game_id)
    result = _engine.submit(game, req.word)
    if result.accepted:
        _store.save(game)
    return MoveResponse(
        accepted=result.accepted,
        reason=result.reason,
        similarity=result.similarity,
        relation=result.relation,
        game=GameState.from_game(game),
    )


@app.get("/games/{game_id}/hint", response_model=HintResponse)
def get_hint(game_id: str) -> HintResponse:
    game = _require_game(game_id)
    hint = _engine.hint(game)
    if hint is None:
        return HintResponse(hint=None, message="no hint available")
    return HintResponse(hint=hint)


@app.get("/games/{game_id}/score", response_model=ScoreResponse)
def get_score(game_id: str) -> ScoreResponse:
    return ScoreResponse(**_engine.score(_require_game(game_id)))


# Mounted last so the API routes above take precedence over static files.
if settings.static_dir is not None:
    app.mount("/", StaticFiles(directory=settings.static_dir, html=True), name="frontend")
