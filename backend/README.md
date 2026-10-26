# Degrees — backend

Connect a **start** word to a **target** word by semantic association, in as
few hops as possible. The limit is **6 connections (7 words total)**.

## How it works

- Every word is a vector. Two words are **connected** iff each is among the
  other's `k` nearest words by cosine similarity (**mutual k-NN**). This avoids
  generic "hub" words (good, big, time...) creating arbitrary shortcut paths,
  and gives every word a uniform branching factor (≤ k).
- That rule defines a **graph** (words = nodes, mutual-nearest pairs = edges).
  The *same* rule validates player moves and generates puzzles, so any puzzle
  the server hands out is guaranteed solvable within the limit (its optimal
  distance comes straight from BFS).
- `k` is the difficulty knob (`DEGREES_K`): smaller `k` means fewer valid moves
  and longer paths. `k=12` is a good default for the curated wordlist.

## Setup

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"
```

`requirements.txt` lists the direct dependencies; `requirements.lock` pins
the exact versions deploys use (regenerate it from a fresh venv with
`pip freeze` after changing `requirements.txt`).

### Word vectors

`data/vectors.npy` + `data/words.json` ship in the repo: 300-d ConceptNet
Numberbatch vectors for the words in `data/wordlist.txt`. Rebuild them after
editing the wordlist:

```bash
curl -L -o data/numberbatch-en.txt.gz \
  https://conceptnet.s3.amazonaws.com/downloads/2019/numberbatch/numberbatch-en-19.08.txt.gz
python scripts/build_vectors.py --glove data/numberbatch-en.txt.gz
```

Any GloVe-format file works (plain or `.gz`). Without a vectors file the
server falls back to **synthetic** embeddings: the API works end-to-end, but
"connections" are meaningless (dev/testing only).

### Typed-relation overlay (cross-domain links)

The mutual-kNN graph reliably covers same-meaning / opposite / is-a / category /
part-of, but ranks *cross-domain* links (made-of, symbol-of, causes, has-property)
too low to ever connect — e.g. `glass↔sand`, `gold↔money`, `white↔peace`. A sparse
**typed overlay** (`data/relations.json`) is unioned onto the graph to supply
those. Because it's sparse it recovers the links without creating hub shortcuts
(audit: 87% → 99% relation recall, max degree 12 → 15).

A small hand-authored `data/relations.json` ships by default. To build the full
overlay from ConceptNet (the same knowledge graph behind the Numberbatch vectors):

```bash
curl -LO https://s3.amazonaws.com/conceptnet/downloads/2019/edges/conceptnet-assertions-5.7.0.csv.gz
python scripts/build_relations.py --assertions conceptnet-assertions-5.7.0.csv.gz
```

Audit/experiment scripts that characterize coverage: `scripts/audit_relations.py`,
`scripts/rule_experiment.py`, `scripts/prototype_typed_overlay.py`.

### Naming the relation on each move

Every accepted move reports the relation behind the edge (shown in the UI instead
of a raw cosine), resolved in precedence order:

1. **Typed overlay** — precise curated labels (MadeOf, SymbolOf, ...).
2. **WordNet** (`app/wordnet_relations.py`) — derives Synonym / Antonym / IsA /
   PartOf / SameCategory for ordinary embedding edges (dog↔cat → SameCategory).
   Requires `nltk` + the `wordnet` corpus (see `requirements.txt`); optional —
   without it these edges fall back to the generic label.
3. **`Related`** — generic fallback for topical edges WordNet can't type.

## Run

```bash
uvicorn app.main:app --reload
# docs: http://localhost:8000/docs
```

## API

| Method | Path                     | Purpose                                  |
|--------|--------------------------|------------------------------------------|
| GET    | `/health`                | vocab size, threshold, synthetic flag    |
| GET    | `/vocabulary`            | all playable words (for autocomplete)    |
| POST   | `/games`                 | new puzzle (optional `min/max_distance`); `{"daily": true, "date": "YYYY-MM-DD"}` for the daily |
| GET    | `/games/{id}`            | current game state                       |
| POST   | `/games/{id}/moves`      | submit a word `{ "word": "..." }`        |
| POST   | `/games/{id}/hint`       | a valid next word on a shortest path (recorded) |
| GET    | `/games/{id}/score`      | connections used vs. optimal             |

### Example

```bash
GAME=$(curl -s -X POST localhost:8000/games)
echo "$GAME"            # -> start, target, optimal_distance, ...
ID=$(echo "$GAME" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST localhost:8000/games/$ID/moves -H 'content-type: application/json' \
     -d '{"word":"ocean"}'
curl -s -X POST localhost:8000/games/$ID/hint
```

A move is rejected (with a reason) when the word is out of vocabulary, already
used in the chain, or not connected to the current word. Only the last costs a
strike. The game ends as `won` when you reach the target, or `lost` after 6
connections or 3 strikes. Once it's over, `solution` in the game state reveals
a par route.

Puzzles are only generated when a par route exists using links the labeler can
name (anything but `Related`), so revealed solutions read as sensible. Daily
puzzles are the same for everyone on a date. Each day is seeded by its date
but also avoids words recent dailies used (see the `DEGREES_DAILY_FRESH_*`
settings), so the schedule is generated in order from the epoch and cached;
Each weekday aims for its own par
(easy Monday, hard Saturday). `scripts/preview_dailies.py` shows what's
coming.

Reviewed days are frozen in `data/dailies.json` (`scripts/freeze_dailies.py`)
and served exactly as stored; only days past the frozen range are generated,
and those change whenever the word data does. The app refuses to start if a
data change breaks a frozen day (a word removed, a link gone, par changed);
`freeze_dailies.py --reroll-invalid` repairs it.

Links are named by the typed overlay first, then WordNet using only each
word's most common senses (`DEGREES_WORDNET_SENSES`), so rare meanings
(crown = top of the head) don't produce links players read as nonsense.
Curated `"Related"` entries in `relations.json` demote a link that WordNet
still mislabels: it stays a valid move but never appears in a par route.
Words longer than 64 characters are rejected with a 422. `POST /games` and
`POST /games/{id}/moves` are rate-limited per client IP (429 when exceeded).

## Config (env vars)

| Var                       | Default | Meaning                                  |
|---------------------------|---------|------------------------------------------|
| `DEGREES_K`               | `12`    | mutual-kNN neighbors per word (difficulty) |
| `DEGREES_MAX_CONNECTIONS` | `6`     | hop limit                                |
| `DEGREES_MIN_DISTANCE`    | `3`     | min optimal distance for a puzzle        |
| `DEGREES_MAX_DISTANCE`    | `5`     | max optimal distance for a puzzle        |
| `DEGREES_ALLOW_SYNTHETIC` | `1`     | allow synthetic fallback vectors         |
| `DEGREES_USE_RELATIONS`   | `1`     | union the typed-relation overlay onto the graph |
| `DEGREES_RELATIONS`       | `data/relations.json` | overlay edge file          |
| `DEGREES_VECTORS`         | `data/vectors.npy` | embedding matrix              |
| `DEGREES_WORDS`           | `data/words.json` | words aligned with vector rows |
| `DEGREES_WORDLIST`        | `data/wordlist.txt` | source list for synthetic vectors |
| `DEGREES_MAX_WORDS`       | `5000`  | cap on vocabulary size (dense similarity matrix) |
| `DEGREES_SEED`            | `1234`  | RNG seed for puzzle generation           |
| `DEGREES_STATIC_DIR`      | unset   | serve the built frontend from this directory |
| `DEGREES_CORS_ORIGINS`    | unset   | comma-separated extra allowed origins    |
| `DEGREES_DOCS`            | `1`     | expose `/docs`, `/redoc`, `/openapi.json` |
| `DEGREES_GAME_TTL_HOURS`  | `24`    | drop games idle this long                |
| `DEGREES_MAX_GAMES`       | `100000`| evict least-recently-used games past this |
| `DEGREES_NEW_GAMES_PER_MIN` | `30`  | new games per client IP per minute (`0` = off) |
| `DEGREES_MOVES_PER_MIN`   | `120`   | moves + hints per client IP per minute (`0` = off) |
| `DEGREES_CLIENT_IP_HEADER` | unset  | proxy header carrying the real client IP |
| `DEGREES_MAX_STRIKES`     | `3`     | unconnected guesses allowed before losing |
| `DEGREES_DAILY_EPOCH`     | `2026-10-26` | date of daily puzzle #1 |
| `DEGREES_DAILY_FRESH_ENDS_DAYS` | `14` | a daily's start/target can't have started/ended a daily this recently |
| `DEGREES_DAILY_FRESH_ROUTE_DAYS` | `7` | words on a route this recently can't appear in today's daily |
| `DEGREES_WORDNET_SENSES`  | `3`     | WordNet senses per part of speech used to name links (`0` = all) |
| `DEGREES_DAILY_PAR_BY_WEEKDAY` | `3,3,4,4,4,5,4` | par each weekday's daily aims for, Monday first |
| `DEGREES_DAILIES`         | `data/dailies.json` | frozen (reviewed) daily puzzles |

## Tests

```bash
python -m pytest        # needs requirements-dev.txt
```

## Not yet built (future)

Persistence (games are in-memory), daily puzzle, accounts/streaks, LLM-judge
fallback for borderline connections.
