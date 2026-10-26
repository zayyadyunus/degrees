"""Tests for the bounded game store and the rate limiter.

Run from backend/:  python -m pytest
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.game import Game  # noqa: E402
from app.ratelimit import RateLimiter  # noqa: E402
from app.store import GameStore  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make_game(game_id: str) -> Game:
    return Game(
        id=game_id, start="a", target="b", optimal_distance=1,
        optimal_path=["a", "b"], max_connections=6, path=["a"],
    )


def test_store_expires_idle_games():
    clock = FakeClock()
    store = GameStore(ttl_seconds=100, clock=clock)
    store.save(make_game("old"))
    clock.now = 50
    store.save(make_game("new"))
    clock.now = 120  # "old" idle 120s, "new" idle 70s
    assert store.get("old") is None
    assert store.get("new") is not None


def test_store_access_refreshes_ttl():
    clock = FakeClock()
    store = GameStore(ttl_seconds=100, clock=clock)
    store.save(make_game("g"))
    clock.now = 90
    assert store.get("g") is not None
    clock.now = 180  # idle 90s since last access
    assert store.get("g") is not None


def test_store_evicts_least_recently_used_past_cap():
    store = GameStore(max_games=2)
    store.save(make_game("a"))
    store.save(make_game("b"))
    store.get("a")  # "b" is now least recently used
    store.save(make_game("c"))
    assert len(store) == 2
    assert store.get("b") is None
    assert store.get("a") is not None


def test_rate_limiter_blocks_then_resets():
    clock = FakeClock()
    limiter = RateLimiter(limit=2, window_seconds=60, clock=clock)
    assert limiter.allow("ip1") and limiter.allow("ip1")
    assert not limiter.allow("ip1")
    assert limiter.allow("ip2")  # separate client, separate budget
    clock.now = 60
    assert limiter.allow("ip1")


def test_rate_limiter_zero_disables():
    limiter = RateLimiter(limit=0)
    assert all(limiter.allow("ip") for _ in range(1000))
