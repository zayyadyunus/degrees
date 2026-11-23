"""In-memory game session store.

v1 keeps games server-side so optimal distance can't be tampered with. Swap
this module for a DB-backed implementation to add persistence later — the
public methods are the seam.

Games are kept in least-recently-used order so memory stays bounded: games
idle longer than `ttl_seconds` are dropped, and past `max_games` the oldest
are evicted first.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Callable

from .game import Game
from .sixtype.engine import TypedGame


class GameStore:
    def __init__(
        self,
        ttl_seconds: float = 24 * 3600,
        max_games: int = 100_000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        # id -> (game, last access time), oldest access first.
        self._games: OrderedDict[str, tuple[Game | TypedGame, float]] = OrderedDict()
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._max = max_games
        self._clock = clock

    def __len__(self) -> int:
        with self._lock:
            return len(self._games)

    def save(self, game: Game | TypedGame) -> None:
        with self._lock:
            now = self._clock()
            self._games[game.id] = (game, now)
            self._games.move_to_end(game.id)
            self._prune(now)

    def get(self, game_id: str) -> Game | TypedGame | None:
        with self._lock:
            now = self._clock()
            self._prune(now)
            entry = self._games.get(game_id)
            if entry is None:
                return None
            self._games[game_id] = (entry[0], now)
            self._games.move_to_end(game_id)
            return entry[0]

    def delete(self, game_id: str) -> bool:
        with self._lock:
            return self._games.pop(game_id, None) is not None

    def _prune(self, now: float) -> None:
        # Oldest-first order means expired games are all at the front.
        while self._games:
            _, touched = next(iter(self._games.values()))
            if now - touched <= self._ttl and len(self._games) <= self._max:
                break
            self._games.popitem(last=False)
