"""The six-type prototype (proto/): boards follow the rules, every time."""
import random
import subprocess
import sys

import pytest

from proto.typed import PROTO_EDGE_WINDOW, BOARD, CHAIN, MAX_SOLUTIONS, MAX_TRAPS, TYPES, History, Links, assess, assign_types, build_board, load, look_alikes


@pytest.fixture(scope="module")
def links():
    return load()


@pytest.fixture(scope="module")
def boards(links):
    rng, history = random.Random(0), History(edge_window=PROTO_EDGE_WINDOW)
    return [build_board(links, rng, history=history) for _ in range(15)]


def test_links_pass_lint(links):
    from proto.lint import errors
    assert errors(links) == []


def test_every_type_has_links(links):
    counts = links.count_by_type()
    assert set(counts) == set(TYPES)
    assert all(n >= 50 for n in counts.values()), counts


def test_kind_passes_up_but_family_does_not(links):
    assert "kind" in links.types("eagle", "animal")       # via bird
    assert "family" in links.types("eagle", "owl")        # both birds
    assert not links.types("eagle", "dog")                # both animals, not family


def test_kind_does_not_switch_meaning(links):
    # fish is an animal and a food: shark -> fish -> food would be a pun.
    assert "kind" in links.types("shark", "fish") and "kind" in links.types("fish", "food")
    assert not links.types("shark", "food")


def test_features_link_nouns_and_adjectives_are_not_tiles(links):
    assert links.types("snow", "paper") == {"feature": "paper and snow are both white"}
    assert not links.adjectives & links.words


def test_arguable_links_are_links_but_not_obvious(links):
    # "category vegetable: ... ?tomato": tomato is a kind of vegetable, arguably.
    assert "kind" in links.types("tomato", "vegetable")
    assert "kind" not in links.obvious("tomato", "vegetable")
    assert "kind" not in links.obvious("tomato", "food")      # passes up through the arguable step
    assert "family" in links.obvious("carrot", "potato")      # the rest of the line is obvious


def test_arguable_loses_to_obvious(tmp_path):
    f = tmp_path / "links.txt"
    f.write_text("knife with: ?table\nknife with: table\nfork with: ?table\n")
    links = load(f)
    assert "found" in links.obvious("knife", "table")
    assert "found" not in links.obvious("fork", "table") and "found" in links.types("fork", "table")


def test_routes_use_only_obvious_links(links, boards):
    for board, _ in boards:
        for a, b, t in zip(board.route, board.route[1:], board.route_types):
            assert t in links.obvious(a, b), (a, b, t)


def test_assign_types_needs_distinct_types():
    links = Links()
    links.add("a", "b", "family", "")
    links.add("b", "c", "family", "")
    assert assign_types(links, ["a", "b", "c"]) is None
    links.add("b", "c", "part", "")
    assert assign_types(links, ["a", "b", "c"]) == ["family", "part"]
    assert assign_types(links, ["a", "b", "c"], used=frozenset({"part"})) is None


def test_boards_follow_the_rules(links, boards):
    assert all(boards), "a board failed to build"
    for board, a in boards:
        assert len(board.tiles) == BOARD and len(set(board.tiles)) == BOARD
        assert len(board.route) == CHAIN + 1
        assert sorted(board.route_types) == sorted(TYPES)      # each type once
        assert assign_types(links, board.route) is not None
        assert a.solutions and not a.short_valid               # six links, no shortcut
        assert not a.isolated
        assert a.first_moves >= 2 and a.last_moves >= 2
        assert board.start not in links.categories and board.target not in links.categories
        assert sum(w in links.categories for w in board.tiles) <= 1
        assert len(a.solutions) <= MAX_SOLUTIONS and 0 < len(a.traps) <= MAX_TRAPS


def test_decoys_never_look_linked(links, boards):
    near = look_alikes(links)
    for board, _ in boards:
        words = [board.start, board.target, *board.tiles]
        for d in (w for w, r in board.roles.items() if r == "decoy"):
            assert not any(frozenset((d, w)) in near for w in words if w != d), (board.start, d)


def test_avoid_pairs_never_share_a_board(links, boards):
    for board, _ in boards:
        words = {board.start, board.target, *board.tiles}
        assert not any(pair <= words for pair in links.avoid), board.start


def test_no_word_carries_recent_boards(boards):
    history = History()
    for board, _ in boards:
        on_board = {board.start, board.target, *board.tiles}
        assert not on_board & history.overused, board.start
        history.record(board)


def test_recent_boards_never_repeat_a_route_link_or_feature(links, boards):
    h = History(edge_window=PROTO_EDGE_WINDOW)
    for i, (board, _) in enumerate(boards):
        edges = {frozenset(p) for p in zip(board.route, board.route[1:])}
        assert not edges & h.edges, i
        feats = set().union(*(links.shared_features(a, b) for (a, b), t in
                              zip(zip(board.route, board.route[1:]), board.route_types) if t == "feature"))
        assert not feats & h.recent_features, (i, feats)
        h.record(board, links)


def test_kind_pairs_are_not_family(links):
    assert not any("kind" in t and "family" in t for t in links.edges.values())


def test_recent_boards_never_repeat_an_end(boards):
    window = History().window
    for i in range(len(boards)):
        recent = boards[max(0, i - window + 1): i + 1]
        ends = [w for board, _ in recent for w in (board.start, board.target)]
        assert len(ends) == len(set(ends)), i


def test_assessment_is_repeatable(links, boards):
    board, a = boards[0]
    again = assess(links, board, random.Random(0))
    assert again.solutions == a.solutions and again.traps == a.traps


def test_same_seed_same_board_across_processes():
    # Set order differs between processes (string hashing), so check two.
    code = ("import random; from proto.typed import build_board, load;"
            "b, _ = build_board(load(), random.Random(7)); print(b.start, b.target, *b.tiles)")
    runs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout
            for _ in range(2)}
    assert len(runs) == 1
