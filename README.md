# Degrees

Connect a **start** word to a **target** word by semantic association, in as
few hops as possible.

```
ocean → … → … → … → forest
```

You get **6 connections** (7 words total) to make it across. There's a new
**daily puzzle** every day (the same for everyone), plus unlimited practice
puzzles.

## How to play

1. The game gives you two words: a `start` and a `target`.
2. Type a word that is **semantically related** to the current word in the
   chain. If the association is close enough, the word is accepted and becomes
   the new "current" word.
3. Keep going. Each accepted word is one connection used.
4. Reach the `target` word before you run out of connections to **win**.

The full player-facing rules, including the ten kinds of connection, are in
`docs/RULES.md`.

### What counts as a "connection"?

Two words are connected when they are **mutual nearest neighbors** in a
word-embedding space — each is among the other's top-`k` closest words by
cosine similarity (default `k=12`). This blocks generic shortcut words
("good", "thing", "time"…) from linking everything to everything, so links
have to be genuine associations.

Every puzzle the game hands out is guaranteed solvable within the 6-hop
limit, and its **par** (shortest path length) is shown up front. Puzzles are
only chosen when a par route exists made entirely of links the game can name
(synonym, is-a, part-of, made-of, ...), so the solution revealed at the end
always reads as sensible.

### Rules of thumb

- A move is **rejected** if the word is:
  - not in the game's vocabulary (free),
  - already used in your chain (free), or
  - not connected to your current word — this costs a **strike**. Three
    strikes and the puzzle is lost.
- Each accepted move shows the relation behind it (same category, part of,
  stands for, ...).
- You can ask for a **hint** at any time. The hint is a valid next word that
  lies on a shortest path to the target; hints are recorded on your result.
- The refresh button starts a **practice** puzzle (it asks first if that
  would abandon one in progress). Games survive a page refresh.

### Scoring

- **Par ⛳**: you tied the shortest path without hints.
- **Connected**: you won, over par or with hints.
- **Lost**: you used all 6 connections or 3 strikes. Either way the end
  screen reveals a par route.
- **Share** copies a spoiler-free result: 🟩 move, 🟥 strike, 💡 hint.

## Running the game

The game is a Python (FastAPI) backend and a React (Vite) frontend.

### 1. Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # pinned deps + pytest
```

#### Word vectors

Real vectors (`data/vectors.npy` + `data/words.json`, built from ConceptNet
Numberbatch) ship in the repo, so this step is only needed to rebuild them,
e.g. after editing `data/wordlist.txt`:

```bash
curl -L -o data/numberbatch-en.txt.gz \
  https://conceptnet.s3.amazonaws.com/downloads/2019/numberbatch/numberbatch-en-19.08.txt.gz
python scripts/build_vectors.py --glove data/numberbatch-en.txt.gz
```

Without a vectors file, the server falls back to **synthetic** embeddings —
the API works, but "connections" are meaningless (dev/testing only).

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

# Ask for a hint (recorded on the game)
curl -s -X POST localhost:8000/games/$ID/hint

# Final score
curl -s localhost:8000/games/$ID/score
```

| Method | Path                  | Purpose                                 |
|--------|-----------------------|-----------------------------------------|
| GET    | `/health`             | vocab size, threshold, synthetic flag   |
| GET    | `/vocabulary`         | all playable words                      |
| POST   | `/games`              | new puzzle; `{"daily": true, "date": "YYYY-MM-DD"}` for the daily |
| GET    | `/games/{id}`         | current game state                      |
| POST   | `/games/{id}/moves`   | submit a word `{ "word": "..." }`       |
| POST   | `/games/{id}/hint`    | a valid next word on a shortest path    |
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

Smaller `k` = fewer valid moves and longer paths = harder game. The full list
of settings is in `backend/README.md`.

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
cd ../backend && pip install -r requirements.lock
python -c "import nltk; nltk.download('wordnet'); nltk.download('omw-1.4')"

# Run — one worker only: games are kept in process memory
DEGREES_ALLOW_SYNTHETIC=0 DEGREES_STATIC_DIR=../frontend/dist DEGREES_DOCS=0 \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Ship `backend/data/vectors.npy`, `words.json` and `relations.json`; the raw
`numberbatch-en.txt.gz` is only needed to rebuild vectors. Check `/health`
reports `"synthetic_embeddings": false` after deploy.

Sizing: startup takes ~4 s and ~230 MB RAM; a full game store (100k games)
adds ~65 MB, so a 512 MB instance is plenty.

| Var                         | Default | Meaning                                              |
|-----------------------------|---------|------------------------------------------------------|
| `DEGREES_STATIC_DIR`        | unset   | serve the built frontend from this directory         |
| `DEGREES_CORS_ORIGINS`      | unset   | comma-separated extra origins, if the UI is hosted elsewhere |
| `DEGREES_DOCS`              | `1`     | expose `/docs` and `/openapi.json` (Docker image: `0`) |
| `DEGREES_GAME_TTL_HOURS`    | `24`    | drop games idle this long                            |
| `DEGREES_MAX_GAMES`         | `100000`| evict least-recently-used games past this count      |
| `DEGREES_NEW_GAMES_PER_MIN` | `30`    | new games per client IP per minute (`0` = off)       |
| `DEGREES_MOVES_PER_MIN`     | `120`   | moves + hints per client IP per minute (`0` = off)   |
| `DEGREES_CLIENT_IP_HEADER`  | unset   | proxy header with the real client IP (`fly.toml`: `Fly-Client-IP`) |
| `FORWARDED_ALLOW_IPS`       | `127.0.0.1` | uvicorn: proxies trusted for the client IP (Docker image: `*`) |

Rate limits key on the client IP. Behind a platform proxy, uvicorn must
trust it via `FORWARDED_ALLOW_IPS` or every player shares the proxy's
address and one budget.

## Repo layout

```
backend/    FastAPI app, game engine, vector + graph code, tests
frontend/   Vite + React UI (the playable game)
```

See `backend/README.md` for more on the engine internals.
