# Degrees

Connect a **start** word to a **target** word by semantic association, in as
few hops as possible.

```
ocean → … → … → … → forest
```

You get **6 connections** (7 words total) to make it across.

## How to play

1. The game gives you two words: a `start` and a `target`.
2. Type a word that is **semantically related** to the current word in the
   chain. If the association is close enough, the word is accepted and becomes
   the new "current" word.
3. Keep going. Each accepted word is one connection used.
4. Reach the `target` word before you run out of connections to **win**.

### What counts as a "connection"?

Two words are connected when they are **mutual nearest neighbors** in a
word-embedding space — each is among the other's top-`k` closest words by
cosine similarity (default `k=12`). This blocks generic shortcut words
("good", "thing", "time"…) from linking everything to everything, so links
have to be genuine associations.

Every puzzle the game hands out is guaranteed solvable within the 6-hop
limit, and you can see the **best possible** (shortest) path length next to
your remaining connections.

### Rules of thumb

- A move is **rejected** if the word is:
  - not in the game's vocabulary,
  - already used in your chain, or
  - not similar enough to your current word.
- "Connected (87% match)" feedback is the cosine similarity to the previous
  word — higher means a tighter link, but anything above the threshold
  counts equally for hops.
- You can ask for a **hint** at any time. The hint is a valid next word that
  lies on a shortest path to the target.
- **New puzzle** starts a fresh game.

### Scoring

- **Optimal**: you tied the best possible path length.
- **Over optimal**: you won, but used more hops than necessary.
- **Lost**: you used all 6 connections without reaching the target. The game
  tells you the distance it *could* have been solved in.

## Running the game

The game is a Python (FastAPI) backend and a React (Vite) frontend.

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

#### Real embeddings (recommended)

Without a vectors file, the server falls back to **synthetic** embeddings —
the API works, but "connections" are meaningless (dev/testing only). Build
real vectors from GloVe:

```bash
curl -LO https://nlp.stanford.edu/data/glove.6B.zip
unzip glove.6B.zip
python scripts/build_vectors.py --glove glove.6B.100d.txt
```

This writes `data/vectors.npy` + `data/words.json`, which the server loads
on next start.

#### Start the server

```bash
uvicorn app.main:app --reload
# API:  http://localhost:8000
# Docs: http://localhost:8000/docs
```

### 2. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`) and play.

## Playing from the terminal (no UI)

If you'd rather use the API directly:

```bash
GAME=$(curl -s -X POST localhost:8000/games)
echo "$GAME"            # start, target, optimal_distance, ...
ID=$(echo "$GAME" | python -c "import sys,json;print(json.load(sys.stdin)['id'])")

# Submit a move
curl -s -X POST localhost:8000/games/$ID/moves \
  -H 'content-type: application/json' \
  -d '{"word":"ocean"}'

# Ask for a hint
curl -s localhost:8000/games/$ID/hint

# Final score
curl -s localhost:8000/games/$ID/score
```

| Method | Path                  | Purpose                                 |
|--------|-----------------------|-----------------------------------------|
| GET    | `/health`             | vocab size, threshold, synthetic flag   |
| GET    | `/vocabulary`         | all playable words                      |
| POST   | `/games`              | new puzzle (optional min/max_distance)  |
| GET    | `/games/{id}`         | current game state                      |
| POST   | `/games/{id}/moves`   | submit a word `{ "word": "..." }`       |
| GET    | `/games/{id}/hint`    | a valid next word on a shortest path    |
| GET    | `/games/{id}/score`   | connections used vs. optimal            |

## Difficulty knobs

All settable as environment variables on the backend:

| Var                       | Default | Meaning                                    |
|---------------------------|---------|--------------------------------------------|
| `DEGREES_K`               | `12`    | mutual-kNN neighbors per word (difficulty) |
| `DEGREES_MAX_CONNECTIONS` | `6`     | hop limit                                  |
| `DEGREES_MIN_DISTANCE`    | `3`     | min optimal distance for a puzzle          |
| `DEGREES_MAX_DISTANCE`    | `5`     | max optimal distance for a puzzle          |
| `DEGREES_ALLOW_SYNTHETIC` | `1`     | allow synthetic fallback vectors           |

Smaller `k` = fewer valid moves and longer paths = harder game.

## Deploying

In production the backend serves the built frontend, so UI and API share one
origin (no CORS or API URL config needed). The `Dockerfile` does all of the
below; it honors `$PORT` if your platform sets one:

```bash
docker build -t degrees .
docker run -p 8000:8000 degrees
```

Or by hand:

```bash
# Build the UI (calls its own origin by default; set VITE_API_URL to override)
cd frontend && npm ci && npm run build

# Backend deps + WordNet corpus (for relation labels)
cd ../backend && pip install -r requirements.txt
python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"

# Run — one worker only: games are kept in process memory
DEGREES_ALLOW_SYNTHETIC=0 DEGREES_STATIC_DIR=../frontend/dist \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ship `backend/data/vectors.npy`, `words.json` and `relations.json`; the raw
`numberbatch-en.txt.gz` is only needed to rebuild vectors. Check `/health`
reports `"synthetic_embeddings": false` after deploy.

| Var                    | Meaning                                                   |
|------------------------|-----------------------------------------------------------|
| `DEGREES_STATIC_DIR`   | serve the built frontend from this directory              |
| `DEGREES_CORS_ORIGINS` | comma-separated extra origins, if the UI is hosted elsewhere |

## Repo layout

```
backend/    FastAPI app, game engine, vector + graph code, tests
frontend/   Vite + React UI (the playable game)
```

See `backend/README.md` for more on the engine internals.
