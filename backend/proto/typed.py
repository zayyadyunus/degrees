"""The six-type prototype's entry point: links files and re-exports.

The links data, solver and board generator now live in app/sixtype/; the
proto tools (play, boards, scale, lint, label, export_web) import them from
here so they keep working unchanged. PROTO_EDGE_WINDOW and the ~240-word
links.txt are prototype-only.
"""
from __future__ import annotations

from pathlib import Path

from app.sixtype.board import (  # noqa: F401  (re-exported for proto tools)
    MAX_RANDOM_WIN, MAX_SOLUTIONS, MAX_TRAPS, NEAR_RANK, Assessment, Board, History, assess, build_board,
    distance, keeps_rules, look_alikes, random_route,
)
from app.sixtype.links import (  # noqa: F401
    BOARD, CHAIN, TYPE_NAMES, TYPES, Links, assign_types, chains, load as _load, phrase,
)

LINKS_PATH = Path(__file__).with_name("links.txt")
NEXT_PATH = Path(__file__).resolve().parent.parent / "data" / "typed_links.txt"
# The ~240-word prototype stalls at about 10 boards with History's default
# edge window of 10.
PROTO_EDGE_WINDOW = 5


def load(path: Path = LINKS_PATH) -> Links:
    """The prototype's links (links.txt by default; NEXT_PATH for the Phase 2 vocabulary)."""
    return _load(path)
