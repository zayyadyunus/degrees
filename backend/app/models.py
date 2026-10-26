"""Pydantic request/response schemas for the public API."""
from __future__ import annotations

from pydantic import BaseModel, Field

from .game import Game


class NewGameRequest(BaseModel):
    min_distance: int | None = Field(default=None, ge=1)
    max_distance: int | None = Field(default=None, ge=1)


class GameState(BaseModel):
    id: str
    start: str
    target: str
    current_word: str
    path: list[str]
    status: str
    connections_used: int
    connections_left: int
    max_connections: int
    optimal_distance: int

    @classmethod
    def from_game(cls, game: Game) -> "GameState":
        return cls(
            id=game.id,
            start=game.start,
            target=game.target,
            current_word=game.current_word,
            path=list(game.path),
            status=game.status,
            connections_used=game.connections_used,
            connections_left=game.max_connections - game.connections_used,
            max_connections=game.max_connections,
            optimal_distance=game.optimal_distance,
        )


class MoveRequest(BaseModel):
    word: str = Field(max_length=64)


class MoveResponse(BaseModel):
    accepted: bool
    reason: str | None = None
    similarity: float | None = None
    relation: str | None = None
    game: GameState


class HintResponse(BaseModel):
    hint: str | None
    message: str | None = None


class ScoreResponse(BaseModel):
    status: str
    connections_used: int
    optimal_distance: int
    over_optimal: int | None
    is_optimal: bool
