"""Preview the word boards of upcoming dailies, as players will get them.

For each day: the board as a player would see it, then each tile's role
(inferred, see app.board.board_for), the par solutions the tiles allow, and
how a greedy player and random play fare.

    python scripts/preview_boards.py                       # launch week
    python scripts/preview_boards.py --from 2026-11-21 --days 7
    python scripts/preview_boards.py --blind               # boards only, for play-testing on paper
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.board import ROLES, assess, board_for  # noqa: E402
from app.bootstrap import build_engine  # noqa: E402
from app.config import settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="start", type=dt.date.fromisoformat,
                        default=max(dt.date.today(), settings.daily_epoch))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--blind", action="store_true", help="hide roles and analysis")
    args = parser.parse_args()

    logging.disable(logging.INFO)
    engine = build_engine(settings)
    if not engine.labeler.enabled or engine.embeddings.synthetic:
        sys.exit("Needs real vectors and the WordNet corpus, like production.")
    I = engine.embeddings.index

    greedy_wins = unfair_days = 0
    sizes: list[int] = []
    for d in range(args.days):
        day = args.start + dt.timedelta(days=d)
        puzzle = engine.daily_puzzle(day)
        rng = np.random.default_rng([settings.seed, day.toordinal(), 7])
        board = board_for(engine, puzzle)
        a = assess(engine, board, rng)
        greedy_wins += a.greedy_solves_at_par
        sizes.append(len(board.tiles))

        print(f"#{engine.daily_number(day):<3} {day} {day.strftime('%a')}  "
              f"{board.start.upper()} -> {board.target.upper()}  par {board.par}")
        print(f"     tiles: {', '.join(board.tiles)}")
        if args.blind:
            print()
            continue
        by_role = {r: [w for w, role in board.roles.items() if role == r] for r in ROLES}
        print("     " + "  ".join(f"{r}: {', '.join(ws)}" for r, ws in by_role.items() if ws))
        for sol in a.par_solutions:
            links = [engine._label_edge(I[x], I[y]) for x, y in zip(sol, sol[1:])]
            print("     par: " + " ".join(f"{x} -[{l}]->" for x, l in zip(sol, links)) + f" {sol[-1]}")
        print(f"     greedy: {' -> '.join(a.greedy_path)}  "
              f"({'solves at par' if a.greedy_solves_at_par else 'misses'})  |  "
              f"random play at par: {a.random_par_rate:.0%}  |  first/last moves: {a.first_moves}/{a.last_moves}"
              + (f"  |  isolated: {', '.join(a.isolated)}" if a.isolated else ""))
        if a.unfair:
            print(f"     UNFAIR (look linked, aren't): {', '.join(f'{x}-{y}' for x, y in a.unfair)}")
            unfair_days += 1
        print()

    if not args.blind:
        print(f"Greedy solves {greedy_wins}/{args.days} at par.  Boards with unfair pairs: "
              f"{unfair_days}/{args.days}.  Tiles per board: {min(sizes)}-{max(sizes)}.")


if __name__ == "__main__":
    main()
