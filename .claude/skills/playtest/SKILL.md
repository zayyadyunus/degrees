---
name: playtest
description: Play Degrees end to end in production mode — API smoke test plus a Chrome UI run with screenshots — and report what passed, what failed, and how it looks. Use after any gameplay, API or UI change, before committing or deploying, or when asked to "playtest", "try the game", or "check it still works".
---

# Playtest Degrees

Runs the real game the way players get it: built UI served by the backend,
real vectors, docs off. Covers daily determinism, the word board
(off-board words vs strikes, back), hints,
win/lose, solution reveal, refresh-resume, share text and the practice
confirm dialog.

## Run

From the repo root:

```bash
scripts/playtest.sh                    # screenshots -> playtest-output/
```

It builds `frontend/dist`, starts uvicorn on port 8799 (`PLAYTEST_PORT` to
change), runs `backend/scripts/smoke_api.py` then
`frontend/scripts/ui-playtest.mjs`, and stops the server. Exit code is
non-zero if any check failed. Server logs land in `playtest-output/server.log`.

If it can't start: the backend venv needs `pip install -r
backend/requirements-dev.txt` plus the WordNet corpus, the frontend needs
`npm install`, and Google Chrome must be installed (the UI script drives it
via `playwright-core`; no browser download).

## Report

1. List any FAIL lines with their detail, and the likely cause from the diff
   you're testing. Read `server.log` for 500s.
2. Look at the screenshots in `playtest-output/` (Read them) — at minimum
   `2-strike-and-hint.png` and `3-result.png` on mobile and `5-desktop.png`.
   Call out layout breakage, overlapping elements, clipped text, or anything
   a player would find confusing, not just test failures.
3. Note today's daily (`#N start -> target, par P`) and its par route from
   the smoke output, so the user sees what players will get.

## When adding features

Add a check to `smoke_api.py` (API behavior) or `ui-playtest.mjs` (what the
player sees) for every new rule, in the same `check(ok, label, detail)` style,
so the next playtest covers it.
