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
pip install -r requirements.txt
```

### Real embeddings (recommended for real gameplay)

Without a vectors file the server falls back to **synthetic** embeddings: the
API works end-to-end, but "connections" are meaningless (dev/testing only).
Build real vectors from GloVe:

```bash
curl -LO https://nlp.stanford.edu/data/glove.6B.zip
unzip glove.6B.zip
python scripts/build_vectors.py --glove glove.6B.100d.txt
```

This writes `data/vectors.npy` + `data/words.json`, which the server loads
automatically on next start.

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

## Tests

```bash
python -m pytest        # or: python tests/test_engine.py
```

## Not yet built (future)

Persistence (games are in-memory), daily puzzle, accounts/streaks, LLM-judge
fallback for borderline connections.
