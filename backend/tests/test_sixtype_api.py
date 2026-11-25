"""The API serving six-type dailies from settings.sixtype_from on, classic before."""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings  # noqa: E402
from app.sixtype.dailies import TypedDailies, problem  # noqa: E402
from app.sixtype.engine import SixTypeEngine, TypedPuzzle  # noqa: E402
from app.sixtype.links import Links  # noqa: E402

pytestmark = pytest.mark.skipif(not settings.vectors_path.exists(), reason="real vectors not built")

# s -kind- a -family- b -part- c -feature- d -use/found- e -found- t,
# plus decoys: x links to a by kind only, f1..f3 link to nothing.
ROUTE = ("s", "a", "b", "c", "d", "e", "t")
ROUTE_TYPES = ("kind", "family", "part", "feature", "use", "found")
TILES = ("a", "b", "c", "d", "e", "x", "f1", "f2", "f3", "f4")


def make_links() -> Links:
    links = Links()
    for (a, b), t in zip(zip(ROUTE, ROUTE[1:]), ROUTE_TYPES):
        links.add(a, b, t, f"{a} {t} {b}")
    links.add("d", "e", "found", "d found e")
    links.add("x", "a", "kind", "x kind a")
    links.words |= {"f1", "f2", "f3", "f4"}
    return links


PUZZLE = TypedPuzzle("s", "t", ROUTE, ROUTE_TYPES, TILES)


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from app import main

    today = dt.datetime.now(dt.timezone.utc).date()
    links = make_links()
    monkeypatch.setattr(settings, "daily_epoch", today - dt.timedelta(days=50))
    monkeypatch.setattr(settings, "sixtype_from", today)
    monkeypatch.setattr(main, "_sixtype", SixTypeEngine(links))
    monkeypatch.setattr(main, "_typed_dailies",
                        TypedDailies(links, settings.daily_epoch, {today: PUZZLE}, practice=[PUZZLE]))
    return TestClient(main.app)


def new_daily(client, day=None):
    body = {"daily": True} | ({"date": day.isoformat()} if day else {})
    r = client.post("/games", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def move(client, gid, word, type_=None):
    r = client.post(f"/games/{gid}/moves", json={"word": word} | ({"type": type_} if type_ else {}))
    assert r.status_code == 200, r.text
    return r.json()


def test_today_is_a_sixtype_daily(client):
    g = new_daily(client)
    assert g["rules"] == "sixtype" and g["daily_number"] == 51
    assert (g["start"], g["target"]) == ("s", "t")
    assert len(g["types_left"]) == 6 and g["spent"] == []
    assert g["max_moves"] is None and g["solution"] is None


def test_yesterday_is_still_classic(client, monkeypatch):
    from app import main
    # The classic schedule keeps the real epoch, so stand in for its daily.
    asked = []
    monkeypatch.setattr(main._engine, "daily_game", lambda day: asked.append(day) or main._engine.new_game())
    yesterday = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    g = new_daily(client, yesterday)
    assert asked == [yesterday]
    assert g["rules"] == "classic" and g["spent"] is None and g["max_moves"] == settings.max_moves


def test_full_solve_with_a_type_choice(client):
    gid = new_daily(client)["id"]
    for w in ("a", "b", "c", "d"):
        assert move(client, gid, w)["accepted"]
    r = move(client, gid, "e")
    assert not r["accepted"] and not r["strike"]
    assert [c["type"] for c in r["choices"]] == ["use", "found"]
    r = move(client, gid, "e", "use")
    assert r["accepted"] and r["type"] == "use" and r["why"] == "d use e"
    r = move(client, gid, "t")
    g = r["game"]
    assert g["status"] == "won" and g["solution"] == list(ROUTE)
    assert g["solution_types"] == list(ROUTE_TYPES)
    assert g["whys"][4] == "d use e" and g["solution_whys"][0] == "s kind a"
    score = client.get(f"/games/{gid}/score").json()
    assert score["rules"] == "sixtype" and score["clean"] and score["connections_used"] == 6


def test_strike_back_and_hint(client):
    gid = new_daily(client)["id"]
    assert move(client, gid, "f1")["strike"]
    move(client, gid, "a")
    r = move(client, gid, "x")                       # kind is spent
    assert r["strike"] and "already spent" in r["reason"]
    g = client.post(f"/games/{gid}/back").json()
    assert g["path"] == ["s"] and g["whys"] == [] and any(t["type"] == "kind" for t in g["types_left"])
    h = client.post(f"/games/{gid}/hint").json()
    assert h["hint"] == "kind" and h["message"] == "Spend kind of next"
    score = client.get(f"/games/{gid}/score").json()
    assert score["strikes"] == 2 and score["backs"] == 1 and not score["clean"]


def test_missing_sixtype_daily_is_unavailable(client):
    from app import main
    main._typed_dailies.dailies.clear()
    assert client.post("/games", json={"daily": True}).status_code == 503


def test_practice_is_sixtype_after_the_switch(client):
    r = client.post("/games", json={})
    assert r.status_code == 201 and r.json()["rules"] == "sixtype" and r.json()["daily_number"] is None


def test_practice_is_classic_before_the_switch(client, monkeypatch):
    monkeypatch.setattr(settings, "sixtype_from", dt.datetime.now(dt.timezone.utc).date() + dt.timedelta(days=1))
    r = client.post("/games", json={})
    assert r.status_code == 201 and r.json()["rules"] == "classic"


def test_health_reports_the_switch(client):
    h = client.get("/health").json()
    assert h["sixtype_from"] == dt.datetime.now(dt.timezone.utc).date().isoformat()


# -- stored-board checks -------------------------------------------------------
def test_sound_board_passes():
    assert problem(make_links(), PUZZLE) is None


def test_wrong_type_on_route_is_caught():
    bad = TypedPuzzle("s", "t", ROUTE, ("family", "kind", *ROUTE_TYPES[2:]), TILES)
    assert "isn't a family link" in problem(make_links(), bad)


def test_shortcut_on_board_is_caught():
    links = make_links()
    links.add("b", "t", "use", "b use t")            # s a b t: kind family use
    assert "shorter than six" in problem(links, PUZZLE)


def test_broken_practice_board_is_caught():
    bad = TypedPuzzle("s", "t", ROUTE, ROUTE_TYPES, TILES[:-1])
    d = TypedDailies(make_links(), dt.date(2027, 1, 1), {}, practice=[PUZZLE, bad])
    assert list(d.problems()) == ["practice #1"]


def test_unknown_tile_is_caught():
    bad = TypedPuzzle("s", "t", ROUTE, ROUTE_TYPES, (*TILES[:-1], "zebra"))
    assert "unknown tiles" in problem(make_links(), bad)


def test_arguable_link_on_route_is_caught():
    links = make_links()
    pair = frozenset(("b", "c"))
    links.arguable.add((pair, "part"))           # b-c demoted after the board was built
    assert "arguable part link" in problem(links, PUZZLE)
