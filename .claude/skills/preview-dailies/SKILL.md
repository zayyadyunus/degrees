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

## 3. Fix

Fixes are data changes — follow the `update-words` skill:
- Remove a word that keeps producing bad links from `data/wordlist.txt`.
- Add a missing curated link to `data/relations.json` so a natural route
  exists.

**Any data change reshuffles every daily, past and future.** Before launch
that's free. After launch it changes puzzles people already played — say so
to the user before making the change, and re-run this preview afterwards.

## Report

A table: `#`, date, `start -> target`, par, verdict (keep / fix), and for
each fix the concrete data change proposed. End with the par mix and how many
need fixing.
