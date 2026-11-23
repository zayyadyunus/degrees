"""The six-type game rules (app/sixtype/engine.py) on a small hand-made board."""
import pytest

from app.sixtype.engine import STATUS_LOST, STATUS_WON, SixTypeEngine, TypedPuzzle
from app.sixtype.links import TYPES, Links, load

# s -kind- a -family- b -part- c -feature- d -use/found- e -found- t
# Spending "found" on d-e leaves e-t with nothing: a dead end. x links to a
# by "kind" only (a trap once kind is spent); y links to nothing.
ROUTE = ("s", "a", "b", "c", "d", "e", "t")
ROUTE_TYPES = ("kind", "family", "part", "feature", "use", "found")


@pytest.fixture
def engine():
    links = Links()
    for (a, b), t in zip(zip(ROUTE, ROUTE[1:]), ROUTE_TYPES):
        links.add(a, b, t, f"{a} {t} {b}")
    links.add("d", "e", "found", "d found e")
    links.add("x", "a", "kind", "x kind a")
    links.words |= {"y"}
    return SixTypeEngine(links)


@pytest.fixture
def game(engine):
    return engine.start_game(TypedPuzzle("s", "t", ROUTE, ROUTE_TYPES, ("a", "b", "c", "d", "e", "x", "y")))


def play(engine, game, *words):
    for w in words:
        r = engine.submit(game, w, "use" if (game.current_word, w) == ("d", "e") else None)
        assert r.accepted, r.reason
    return r


def test_full_route_wins_spending_every_type_once(engine, game):
    r = play(engine, game, "a", "b", "c", "d", "e", "t")
    assert game.status == STATUS_WON and r.status == STATUS_WON
    assert sorted(game.spent) == sorted(TYPES)
    assert engine.score(game)["clean"]


def test_two_free_types_asks_which_to_spend(engine, game):
    play(engine, game, "a", "b", "c", "d")
    r = engine.submit(game, "e")
    assert not r.accepted and not r.strike
    assert [c.type for c in r.choices] == ["use", "found"]
    assert game.path[-1] == "d" and game.strikes == 0


def test_picking_a_type_the_link_lacks_is_refused_without_a_strike(engine, game):
    play(engine, game, "a")
    r = engine.submit(game, "b", "part")
    assert not r.accepted and not r.strike and [c.type for c in r.choices] == ["family"]


def test_unlinked_tile_is_a_strike(engine, game):
    r = engine.submit(game, "y")
    assert r.strike and "doesn't link" in r.reason and game.strikes == 1


def test_spent_type_is_a_strike(engine, game):
    play(engine, game, "a")                      # spends kind
    r = engine.submit(game, "x")                 # a-x is kind only, already spent
    assert r.strike and "already spent" in r.reason


def test_off_board_and_repeat_words_are_free(engine, game):
    assert not engine.submit(game, "zebra").strike
    play(engine, game, "a")
    assert not engine.submit(game, "a").strike
    assert game.strikes == 0


def test_back_refunds_the_type(engine, game):
    play(engine, game, "a")
    assert "kind" not in game.types_left
    assert engine.back(game)
    assert "kind" in game.types_left and game.path == ["s"]
    assert not engine.back(game)                 # nothing left to take back


def test_hint_names_the_type_and_is_counted_once(engine, game):
    assert engine.hint(game) == "kind"
    assert engine.hint(game) == "kind"
    assert game.hints_used == 1


def test_hint_at_a_dead_end_is_none(engine, game):
    play(engine, game, "a", "b", "c", "d")
    assert engine.submit(game, "e", "found").accepted   # leaves e-t unplayable
    assert engine.hint(game) is None


def test_three_strikes_loses(engine, game):
    for _ in range(3):
        engine.submit(game, "y")
    assert game.status == STATUS_LOST
    assert not engine.submit(game, "a").accepted


def test_solution_reads_link_by_link(engine, game):
    sol = engine.solution(game)
    assert [s["type"] for s in sol] == list(ROUTE_TYPES)
    assert sol[0]["why"] == "s kind a"


def test_shipped_links_load():
    links = load()
    assert len(links.words) > 700
    assert all(n >= 50 for n in links.count_by_type().values())
