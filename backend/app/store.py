"""In-memory game session store.

v1 keeps games server-side so optimal distance can't be tampered with. Swap
this module for a DB-backed implementation to add persistence later — the
public methods are the seam.
"""
from __future__ import annotations

import threading

from .game import Game


class GameStore:
    def __init__(self) -> None:
        self._games: dict[str, Game] = {}
        self._lock = threading.Lock()

    def save(self, game: Game) -> None:
        with self._lock:
            self._games[game.id] = game

    def get(self, game_id: str) -> Game | None:
        with self._lock:
            return self._games.get(game_id)

    def delete(self, game_id: str) -> bool:
        with self._lock:
            return self._games.pop(game_id, None) is not None
