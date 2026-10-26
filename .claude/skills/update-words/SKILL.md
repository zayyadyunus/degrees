---
name: update-words
description: Change Degrees' vocabulary or curated links — add/remove words in the word list, rebuild vectors, edit relations.json — and verify puzzles still work. Use when asked to add or remove words, fix a bad link or puzzle, or expand the vocabulary.
---

# Update words and links

Game data lives in `backend/data/`:

| File | What | How it changes |
|---|---|---|
| `wordlist.txt` | the curated vocabulary (one word per line, `#` comments) | edit by hand |
| `vectors.npy` + `words.json` | Numberbatch vectors for the wordlist | rebuilt from the wordlist |
| `relations.json` | **hand-authored** curated links (MadeOf, SymbolOf, ...) | edit by hand |

## 0. Warn first if live

**Any change here reshuffles every daily puzzle, past and future** (dailies
are seeded by date over the current data). If the game is deployed, tell the
user before changing anything.

## 1. Make the change

**Words** — edit `backend/data/wordlist.txt`, then rebuild vectors. The
Numberbatch source is git-ignored (~310 MB); download it if missing:

```bash
cd backend
[ -f data/numberbatch-en.txt.gz ] || curl -L -o data/numberbatch-en.txt.gz \
  https://conceptnet.s3.amazonaws.com/downloads/2019/numberbatch/numberbatch-en-19.08.txt.gz
.venv/bin/python scripts/build_vectors.py --glove data/numberbatch-en.txt.gz
```

The build prints words missing from Numberbatch (dropped). Report them; a
word that's dropped isn't playable.

**Links** — edit `backend/data/relations.json` directly:
`{"rel": "MadeOf", "a": "glass", "b": "sand"}`. Use only labels the UI
explains (see `RELATION_LABELS` in `frontend/src/components/Board.tsx`).
Both words must be in the vocabulary or the edge is silently dropped.

To **demote** a link WordNet mislabels through a rare meaning (e.g.
`coat/paint`), add it with `"rel": "Related"`: it stays a valid move but can
never be part of a par route. To **relabel**, add the correct relation.
Either way, first check the pair is already a link (`engine.graph.connected`
via `app.bootstrap.build_engine`) — a curated entry for an unlinked pair
*creates* a new move.

Prefer demoting specific links over lowering `DEGREES_WORDNET_SENSES`: going
from 3 to 2 un-names ~100 links, most of them fair.

Do **not** run `scripts/build_relations.py` unless the user explicitly wants
to replace the hand-authored file with a ConceptNet build — it overwrites
`relations.json`.

## 2. Verify

```bash
cd backend && .venv/bin/python -m pytest -q
```

`tests/test_content.py` fails if any example in `docs/RULES.md` or the
How to Play modal stops connecting — fix the example or the data, never skip
the test. Then:

```bash
.venv/bin/python scripts/preview_dailies.py --days 14
```

and compare against the previous preview if you have it. Run the
`playtest` skill if the vocabulary size changed a lot.

## Report

Words added/removed/dropped, links added/removed, vocabulary size before and
after (`/health` or `len(words.json)`), test result, and a note that dailies
changed.
