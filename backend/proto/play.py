"""Play a prototype board in the terminal.

    cd backend && .venv/bin/python -m proto.play [--seed N]

Type a tile to play it. Commands: back, hint, show, quit.
"""
from __future__ import annotations

import argparse
import random

from .typed import CHAIN, TYPE_NAMES, TYPES, assign_types, build_board, chains, load, phrase

STRIKES = 3


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    seed = args.seed if args.seed is not None else random.randrange(10_000)
    links = load()
    made = build_board(links, random.Random(seed))
    if made is None:
        print("couldn't build a board; try another --seed")
        return
    board, _ = made
    path, used, strikes, backs, hints = [board.start], [], 0, 0, 0

    def show() -> None:
        left = [TYPE_NAMES[t] for t in TYPES if t not in used]
        print(f"\n  {' -> '.join(path)}  ...  {board.target}")
        print(f"  tiles: {'  '.join(w for w in board.tiles if w not in path)}")
        print(f"  types left: {' | '.join(left)}   strikes {strikes}/{STRIKES}")

    print(f"Board seed {seed}. Get from {board.start.upper()} to {board.target.upper()} in {CHAIN} links,")
    print("spending each type once:", ", ".join(TYPE_NAMES[t] for t in TYPES))
    show()
    while True:
        try:
            cmd = input("> ").strip().lower()
        except EOFError:
            return
        here = path[-1]
        if cmd in ("quit", "q"):
            break
        if cmd == "show":
            show()
            continue
        if cmd == "back":
            if len(path) > 1:
                path.pop()
                print(f"  took back; {TYPE_NAMES[used.pop()]} is free again")
                backs += 1
            show()
            continue
        if cmd == "hint":
            hint = _hint(links, board, path, used)
            hints += 1
            print(f"  hint: {hint}")
            continue
        if cmd != board.target and cmd not in board.tiles:
            print("  not on the board")
            continue
        if cmd in path:
            print("  already in your chain")
            continue
        fits = links.types(here, cmd)
        free = [t for t in fits if t not in used]
        if not fits or not free:
            strikes += 1
            if fits:
                print(f"  strike: that's a {' / '.join(TYPE_NAMES[t] for t in fits)} link, already spent")
            else:
                print(f"  strike: {cmd} doesn't link to {here}")
            if strikes >= STRIKES:
                print("  three strikes. A route was: " + _route(links, board))
                return
            continue
        if len(free) == 1:
            t = free[0]
        else:
            for k, t in enumerate(free, 1):
                print(f"  {k}. {TYPE_NAMES[t]}: {phrase(links, here, cmd, t)}")
            try:
                pick = input("  spend which? ").strip()
            except EOFError:
                return
            if not pick.isdigit() or not 1 <= int(pick) <= len(free):
                print("  cancelled")
                continue
            t = free[int(pick) - 1]
        path.append(cmd)
        used.append(t)
        print(f"  ✓ {TYPE_NAMES[t]}: {phrase(links, here, cmd, t)}")
        if cmd == board.target:
            clean = "clean solve!" if not (strikes or backs or hints) else f"{strikes} strikes, {backs} backs, {hints} hints"
            print(f"\nConnected in {len(path) - 1} links: {clean}")
            return
        show()


def _hint(links, board, path, used) -> str:
    """Name the type to spend next on a way through from here (not the tile)."""
    for n, t in next_steps(links, board, path, used):
        return f"spend {TYPE_NAMES[t]} next"
    return f"no way through from {path[-1]}: go back"


def next_steps(links, board, path, used) -> list[tuple[str, str]]:
    """(tile, type) moves from here that still lead to a full six-link solve."""
    out = []
    need = CHAIN - (len(path) - 1)
    pool = (set(board.tiles) | {board.target}) - set(path)
    for rest in chains(links, path[-1], board.target, list(pool - {board.target}), max_len=need):
        if len(rest) - 1 != need:
            continue
        types = assign_types(links, rest, frozenset(used))
        if types is not None:
            out.append((rest[1], types[0]))
    return out


def _route(links, board) -> str:
    return " -> ".join(board.route)


if __name__ == "__main__":
    main()
