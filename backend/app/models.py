"""Pydantic request/response schemas for the public API.

Two rule sets share these shapes: "classic" (app/game.py) and "sixtype"
(app/sixtype/). `GameState.rules` says which; fields that only one rule set
has are None for the other.
"""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field

from .game import STATUS_IN_PROGRESS, Game
from .sixtype.engine import TypedGame
from .sixtype.links import CHAIN, TYPE_NAMES

RULES_CLASSIC = "classic"
RULES_SIXTYPE = "sixtype"


class NewGameRequest(BaseModel):
    min_distance: int | None = Field(default=None, ge=1)
    max_distance: int | None = Field(default=None, ge=1)
    # Daily puzzle for the player's local calendar date (must be within a day
    # of the server's UTC date). Distance bounds are ignored for dailies.
    daily: bool = False
    date: dt.date | None = None


class LinkType(BaseModel):
    type: str
    name: str


class GameState(BaseModel):
    id: str
    rules: str
    start: str
    target: str
    current_word: str
    path: list[str]
    # Classic: the relation label of each link. Six-type: the name of the
    # type each link spent ("kind of", ...).
    relations: list[str]
    status: str
    # The board's middle tiles, in display order (start and target aside).
    tiles: list[str]
    # Words in the chain now (path length - 1).
    connections_used: int
    # Accepted moves so far, including taken-back ones.
    moves: int
    # Classic only: the move budget and what's left of it.
    max_moves: int | None
    connections_left: int | None
    # Classic: par. Six-type: always six.
    optimal_distance: int
    strikes: int
    max_strikes: int
    hints_used: int
    # Ordered "move" / "strike" / "hint" / "back" events, for the share grid.
    events: list[str]
    daily_number: int | None
    # Six-type only: the type each link spent, and the types still free
    # (in the order the UI shows its six keys).
    spent: list[str] | None = None
    whys: list[str] | None = None
    types_left: list[LinkType] | None = None
    # A par route, revealed only once the game is over. Six-type adds the
    # type each of its links spends.
    solution: list[str] | None
    solution_types: list[str] | None = None
    solution_whys: list[str] | None = None

    @classmethod
    def from_game(cls, game: Game | TypedGame) -> "GameState":
        if isinstance(game, TypedGame):
            return cls._from_typed(game)
        return cls(
            id=game.id,
            rules=RULES_CLASSIC,
            start=game.start,
            target=game.target,
            current_word=game.current_word,
            path=list(game.path),
            relations=list(game.relations),
            status=game.status,
            tiles=list(game.tiles),
            connections_used=game.connections_used,
            moves=game.moves,
            max_moves=game.max_moves,
            connections_left=game.max_moves - game.moves,
            optimal_distance=game.optimal_distance,
            strikes=game.strikes,
            max_strikes=game.max_strikes,
            hints_used=game.hints_used,
            events=list(game.events),
            daily_number=game.daily_number,
            solution=None if game.status == STATUS_IN_PROGRESS else list(game.optimal_path),
        )

    @classmethod
    def _from_typed(cls, game: TypedGame) -> "GameState":
        over = game.status != STATUS_IN_PROGRESS
        return cls(
            id=game.id,
            rules=RULES_SIXTYPE,
            start=game.start,
            target=game.target,
            current_word=game.current_word,
            path=list(game.path),
            relations=[TYPE_NAMES[t] for t in game.spent],
            status=game.status,
            tiles=game.tiles,
            connections_used=len(game.spent),
            moves=game.events.count("move"),
            max_moves=None,
            connections_left=None,
            optimal_distance=CHAIN,
            strikes=game.strikes,
            max_strikes=game.max_strikes,
            hints_used=game.hints_used,
            events=list(game.events),
            daily_number=game.daily_number,
            spent=list(game.spent),
            whys=list(game.whys),
            types_left=[LinkType(type=t, name=TYPE_NAMES[t]) for t in game.types_left],
            solution=list(game.puzzle.route) if over else None,
            solution_types=list(game.puzzle.route_types) if over else None,
            solution_whys=list(game.route_whys) if over else None,
        )


class MoveRequest(BaseModel):
    word: str = Field(max_length=64)
    # Six-type only: which type to spend, when the link fits more than one.
    type: str | None = Field(default=None, max_length=16)


class Choice(BaseModel):
    type: str
    name: str
    why: str


class MoveResponse(BaseModel):
    accepted: bool
    reason: str | None = None
    similarity: float | None = None
    # Classic: the relation label. Six-type: the type's name.
    relation: str | None = None
    # True when the rejection cost a strike (a tile that didn't connect).
    strike: bool = False
    # Six-type only: the type spent and the sentence explaining the link;
    # or, when the link fits several free types and none was given, the
    # choices (nothing is spent until the move is sent again with one).
    type: str | None = None
    why: str | None = None
    choices: list[Choice] = []
    game: GameState


class HintResponse(BaseModel):
    # Classic: the next tile. Six-type: the type to spend next.
    hint: str | None
    message: str | None = None
    game: GameState


class ScoreResponse(BaseModel):
    status: str
    rules: str = RULES_CLASSIC
    connections_used: int
    moves: int
    optimal_distance: int
    over_optimal: int | None
    is_optimal: bool
    strikes: int
    hints_used: int
    # Six-type only.
    backs: int | None = None
    clean: bool | None = None
