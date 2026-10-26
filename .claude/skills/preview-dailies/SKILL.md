---
name: preview-dailies
description: Preview upcoming Degrees daily puzzles (start, target, par route with link labels) and get them reviewed for fairness before players see them. Use when asked about upcoming dailies, before deploying, after any word-list/relations/vectors change, or to find puzzles that need fixing.
---

# Preview upcoming dailies

Daily puzzles are seeded by date (`Engine.daily_game`), so every future
puzzle is known today. Review them before players do.

## 1. Generate

```bash
cd backend && .venv/bin/python scripts/preview_dailies.py --days 14
# or: --from YYYY-MM-DD --days 30
```

Each day shows the par route with every link's relation label and cosine
similarity. FLAGS mark `weak` links (non-curated, bottom 15% similarity) and
`repeat` words (same start/target as another daily in the window).

## 2. Review

For more than a handful of days, hand the full output to the
`puzzle-critic` agent and ask for a verdict per puzzle — it knows the rules
and the common failure patterns. For a few days, review inline using the
same rubric (see `.claude/agents/puzzle-critic.md`).

Common real problems, beyond the automatic flags:
- **WordNet sense mix-ups**: a label that's true for a different meaning of
  the word (`foot -[SameCategory]-> minute` as units of measure,
  `ice -[Synonym]-> glass`, `fire -[IsA]-> gun`). Players read the everyday
  meaning, so these feel like nonsense.
- **Obscure targets** or a par route a player couldn't reconstruct even after
  seeing it.

## 3. Fix and freeze

Days in `backend/data/dailies.json` are **frozen**: served exactly as stored,
so later data changes can't reshuffle them (the preview marks them
`[frozen]`). Unfrozen days are generated, and *any* data change reshuffles
all of them — so fix by re-rolling individual days, not by regenerating:

```bash
cd backend
# swap specific bad days (neighbours unchanged, no-repeat rules kept)
.venv/bin/python scripts/freeze_dailies.py --reroll 2026-11-25 2026-12-02
# first freeze of a window: freeze it, then re-roll the bad days in it
.venv/bin/python scripts/freeze_dailies.py --through 2026-12-20
```

Re-rolled days are new and unreviewed: preview them again (or ask
`puzzle-critic` about just those days) before calling the month done.

Data fixes (`update-words` skill) are still worth making for *future*
months — e.g. demoting a mislabelled link the critic keeps hitting. After
one, run the tests: if a frozen day no longer works with the new data, the
app refuses to start; repair with `freeze_dailies.py --reroll-invalid`.
Never edit or regenerate already-played (past) frozen days without telling
the user.

## Report

A table: `#`, date, `start -> target`, par, verdict (keep / fix), and for
each fix the concrete data change proposed. End with the par mix and how many
need fixing.
