"""Pydantic request/response schemas for the public API."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from .game import STATUS_IN_PROGRESS, Game


class NewGameRequest(BaseModel):
    min_distance: int | None = Field(default=None, ge=1)
    max_distance: int | None = Field(default=None, ge=1)
    # Daily puzzle for the player's local calendar date (must be within a day
    # of the server's UTC date). Distance bounds are ignored for dailies.
    daily: bool = False
    date: dt.date | None = None


class GameState(BaseModel):
    id: str
    start: str
    target: str
    current_word: str
    path: list[str]
    relations: list[str]
    status: str
    connections_used: int
    connections_left: int
    max_connections: int
    optimal_distance: int
    strikes: int
    max_strikes: int
    hints_used: int
    # Ordered "move" / "strike" / "hint" events, for the share grid.
    events: list[str]
    daily_number: int | None
    # A par route, revealed only once the game is over.
    solution: list[str] | None

    @classmethod
    def from_game(cls, game: Game) -> "GameState":
        return cls(
            id=game.id,
            start=game.start,
            target=game.target,
            current_word=game.current_word,
            path=list(game.path),
            relations=list(game.relations),
            status=game.status,
            connections_used=game.connections_used,
            connections_left=game.max_connections - game.connections_used,
            max_connections=game.max_connections,
            optimal_distance=game.optimal_distance,
            strikes=game.strikes,
            max_strikes=game.max_strikes,
            hints_used=game.hints_used,
            events=list(game.events),
            daily_number=game.daily_number,
            solution=None if game.status == STATUS_IN_PROGRESS else list(game.optimal_path),
        )


class MoveRequest(BaseModel):
    word: str = Field(max_length=64)


class MoveResponse(BaseModel):
    accepted: bool
    reason: str | None = None
    similarity: float | None = None
    relation: str | None = None
    # True when the rejection cost a strike (a real word that didn't connect).
    strike: bool = False
    game: GameState


class HintResponse(BaseModel):
    hint: str | None
    message: str | None = None
    game: GameState


class ScoreResponse(BaseModel):
    status: str
    connections_used: int
    optimal_distance: int
    over_optimal: int | None
    is_optimal: bool
    strikes: int
    hints_used: int
