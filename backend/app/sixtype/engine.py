"""The six-type game: moves, type choices, back, hints and scoring.

A puzzle is start -> five tiles -> target, six links, and each link spends
one of the six types (see links.py); no type can be spent twice. Rules:

  * Only a board tile (or the target) can be played. Anything else, or a
    word already in the chain, is refused for free.
  * A tile that doesn't link to the current word costs a strike. So does a
    link whose every type is already spent.
  * When a link fits more than one unspent type, the player picks which to
    spend: the move comes back with the choices and nothing is spent until
    it's played again with a type. No strike.
  * Back takes the last word off the chain and refunds its type.
  * A hint names the type to spend next on a way through, never the tile.
    None means there is no way through from here: go back.
  * Three strikes loses. There is no move limit: backing out is the cost.

The board itself guarantees no valid chain shorter than six, so reaching
the target is always a six-link win.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from .links import CHAIN, TYPE_NAMES, TYPES, Links, assign_types, chains

STATUS_IN_PROGRESS = "in_progress"
STATUS_WON = "won"
STATUS_LOST = "lost"

EVENT_MOVE = "move"
EVENT_STRIKE = "strike"
EVENT_HINT = "hint"
EVENT_BACK = "back"


@dataclass(frozen=True)
class TypedPuzzle:
    """A six-type board: the intended route (with its types) and the tiles."""
    start: str
    target: str
    route: tuple[str, ...]          # start .. target, seven words
    route_types: tuple[str, ...]    # the type each route link spends, six
    tiles: tuple[str, ...]          # the ten middle tiles, shuffled


@dataclass
class TypedGame:
    id: str
    puzzle: TypedPuzzle
    max_strikes: int = 3
    path: list[str] = field(default_factory=list)
    # spent[i] is the type the link path[i] -> path[i+1] spent, and whys[i]
    # the sentence that explains it ("hammer is used for nail").
    spent: list[str] = field(default_factory=list)
    whys: list[str] = field(default_factory=list)
    # The intended route's sentences, link by link, for the end screen.
    route_whys: list[str] = field(default_factory=list)
    status: str = STATUS_IN_PROGRESS
    strikes: int = 0
    # Chain lengths at which a hint was shown, so asking twice in a row
    # counts once.
    hint_steps: set[int] = field(default_factory=set)
    events: list[str] = field(default_factory=list)
    daily_number: int | None = None

    @property
    def start(self) -> str:
        return self.puzzle.start

    @property
    def target(self) -> str:
        return self.puzzle.target

    @property
    def tiles(self) -> list[str]:
        return list(self.puzzle.tiles)

    @property
    def current_word(self) -> str:
        return self.path[-1]

    @property
    def types_left(self) -> list[str]:
        return [t for t in TYPES if t not in self.spent]

    @property
    def hints_used(self) -> int:
        return len(self.hint_steps)

    @property
    def backs(self) -> int:
        return self.events.count(EVENT_BACK)


@dataclass
class Choice:
    type: str
    name: str
    why: str


@dataclass
class TypedMoveResult:
    accepted: bool
    status: str
    current_word: str
    reason: str | None = None
    strike: bool = False
    # Set when accepted: the type spent and the sentence that explains it.
    type: str | None = None
    why: str | None = None
    # Set when the link fits several unspent types and none was given.
    choices: list[Choice] = field(default_factory=list)


class SixTypeEngine:
    def __init__(self, links: Links, max_strikes: int = 3):
        self.links = links
        self.max_strikes = max_strikes

    def start_game(self, puzzle: TypedPuzzle, daily_number: int | None = None) -> TypedGame:
        return TypedGame(
            id=uuid.uuid4().hex,
            puzzle=puzzle,
            max_strikes=self.max_strikes,
            path=[puzzle.start],
            daily_number=daily_number,
            route_whys=[self.links.types(a, b)[t]
                        for a, b, t in zip(puzzle.route, puzzle.route[1:], puzzle.route_types)],
        )

    # -- moves -----------------------------------------------------------
    def submit(self, game: TypedGame, raw_word: str, type_: str | None = None) -> TypedMoveResult:
        word = raw_word.strip().lower()

        def result(accepted: bool, reason: str | None = None, **kw) -> TypedMoveResult:
            return TypedMoveResult(accepted, game.status, game.current_word, reason, **kw)

        if game.status != STATUS_IN_PROGRESS:
            return result(False, "game is already over")
        if not word:
            return result(False, "empty word")
        if word != game.target and word not in game.puzzle.tiles:
            return result(False, f"'{word}' isn't on the board")
        if word in game.path:
            return result(False, "word already used in this chain")
        if type_ is not None and type_ not in TYPES:
            return result(False, f"unknown link type '{type_}'")

        here = game.current_word
        fits = self.links.types(here, word)
        free = [t for t in TYPES if t in fits and t not in game.spent]
        if not free:
            if fits:
                names = " / ".join(TYPE_NAMES[t] for t in TYPES if t in fits)
                reason = f"'{word}' is a {names} link from '{here}', and that's already spent"
            else:
                reason = f"'{word}' doesn't link to '{here}'"
            return self._strike(game, reason)

        if type_ is None and len(free) > 1:
            return result(False, "pick which type to spend", choices=self._choices(here, word, free))
        if type_ is not None and type_ not in free:
            # A stale or mistaken pick: offer the real options, no strike.
            return result(False, f"that link can't spend {TYPE_NAMES[type_]}",
                          choices=self._choices(here, word, free))

        spend = type_ or free[0]
        game.path.append(word)
        game.spent.append(spend)
        game.whys.append(fits[spend])
        game.events.append(EVENT_MOVE)
        if word == game.target:
            game.status = STATUS_WON
        return result(True, type=spend, why=fits[spend])

    def _choices(self, here: str, word: str, free: list[str]) -> list[Choice]:
        fits = self.links.types(here, word)
        return [Choice(t, TYPE_NAMES[t], fits[t]) for t in free]

    def _strike(self, game: TypedGame, reason: str) -> TypedMoveResult:
        game.strikes += 1
        game.events.append(EVENT_STRIKE)
        if game.strikes >= game.max_strikes:
            game.status = STATUS_LOST
        return TypedMoveResult(False, game.status, game.current_word, reason, strike=True)

    def back(self, game: TypedGame) -> bool:
        """Take back the last word and refund the type it spent."""
        if game.status != STATUS_IN_PROGRESS or len(game.path) < 2:
            return False
        game.path.pop()
        game.spent.pop()
        game.whys.pop()
        game.events.append(EVENT_BACK)
        return True

    # -- hints -----------------------------------------------------------
    def next_steps(self, game: TypedGame) -> list[tuple[str, str]]:
        """(tile, type) moves from here that still lead to a six-link solve."""
        need = CHAIN - len(game.spent)
        pool = (set(game.puzzle.tiles) | {game.target}) - set(game.path)
        out = []
        for rest in chains(self.links, game.current_word, game.target, sorted(pool - {game.target}), max_len=need):
            if len(rest) - 1 != need:
                continue
            types = assign_types(self.links, rest, frozenset(game.spent))
            if types is not None:
                out.append((rest[1], types[0]))
        return out

    def hint(self, game: TypedGame) -> str | None:
        """The type to spend next on a way through, or None at a dead end.

        Prefers the intended route's next type when the player is still on
        it, so hints lead somewhere the player can recognise.
        """
        if game.status != STATUS_IN_PROGRESS:
            return None
        steps = self.next_steps(game)
        if not steps:
            return None
        route = game.puzzle.route
        k = len(game.path)
        on_route = list(route[:k]) == game.path and game.spent == list(game.puzzle.route_types[:k - 1])
        pick = steps[0][1]
        if on_route and (route[k], game.puzzle.route_types[k - 1]) in steps:
            pick = game.puzzle.route_types[k - 1]
        if len(game.path) not in game.hint_steps:
            game.hint_steps.add(len(game.path))
            game.events.append(EVENT_HINT)
        return pick

    # -- scoring ---------------------------------------------------------
    def solution(self, game: TypedGame) -> list[dict]:
        """The intended route, link by link, for the end screen."""
        p = game.puzzle
        return [
            {"from": a, "to": b, "type": t, "name": TYPE_NAMES[t], "why": self.links.types(a, b)[t]}
            for a, b, t in zip(p.route, p.route[1:], p.route_types)
        ]

    def score(self, game: TypedGame) -> dict:
        return {
            "status": game.status,
            "links": len(game.spent),
            "strikes": game.strikes,
            "backs": game.backs,
            "hints_used": game.hints_used,
            "clean": game.status == STATUS_WON and not (game.strikes or game.backs or game.hints_used),
        }
