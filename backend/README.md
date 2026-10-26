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
| POST   | `/games`                 | new puzzle (optional `min/max_distance`) |
| GET    | `/games/{id}`            | current game state                       |
| POST   | `/games/{id}/moves`      | submit a word `{ "word": "..." }`        |
| GET    | `/games/{id}/hint`       | a valid next word on a shortest path     |
| GET    | `/games/{id}/score`      | connections used vs. optimal             |

### Example

```bash
GAME=$(curl -s -X POST localhost:8000/games)
echo "$GAME"            # -> start, target, optimal_distance, ...
ID=$(echo "$GAME" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")
curl -s -X POST localhost:8000/games/$ID/moves -H 'content-type: application/json' \
     -d '{"word":"ocean"}'
curl -s localhost:8000/games/$ID/hint
```

A move is rejected (with a reason) when the word is out of vocabulary, already
used in the chain, or not similar enough to the current word. The game ends as
`won` when you reach the target, or `lost` if you use all 6 connections first.
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
| `DEGREES_MOVES_PER_MIN`   | `120`   | moves per client IP per minute (`0` = off) |

## Tests

```bash
python -m pytest        # needs requirements-dev.txt
```

## Not yet built (future)

Persistence (games are in-memory), daily puzzle, accounts/streaks, LLM-judge
fallback for borderline connections.
