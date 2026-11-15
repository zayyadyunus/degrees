# Six-type prototype

A standalone sketch of the proposed rules. It doesn't touch the live game (`app/`).

- Every puzzle has **6 links** (start, then five words, then the target) and **10 tiles**.
- Each link spends one of six types, and **no type can be spent twice**:
  kind of · same family · part of / made of · share a feature · used for / makes · found with.
- **Share a feature** links two nouns: tomato → blood ("both red"). Adjectives are never tiles.
  As tiles they could only sit at a route's end, so every puzzle would start or end on one.
- **One word, one meaning.** Words with two unrelated meanings (orange) are left out. "Kind of"
  never passes through a word in two categories (shark → fish → food would say "shark is a kind of food").
- **Arguable links** (`?word` in `links.txt`) are true but some players would hesitate over them.
  They're accepted when played, but a puzzle's intended route only uses obvious links.
- **Back** returns the type. Playing a link whose type you've already spent costs a **strike**.
  When a link fits more than one unused type, you pick which to spend.
- The board never allows a valid chain shorter than six.
- Boards are kept varied. No start or target repeats within the last 10 boards, and no word
  appears on more than 4 of them.
- `python -m proto.lint` checks `links.txt`. Errors fail the tests (a category word in a feature list).
  Warnings list likely missing links (most of a word's category siblings have a link it lacks).
- No board pairs a decoy with a word it looks linked to but isn't (by word vector). No board
  holds both words of an `avoid:` pair (a real phrase that isn't a link, like banana / salad).

```bash
cd backend
.venv/bin/python -m proto.play               # play a random board
.venv/bin/python -m proto.play --seed 42     # a specific board
.venv/bin/python -m proto.boards --n 20      # boards with routes, alternate solutions and traps
.venv/bin/python -m proto.boards --stats     # link coverage per type
.venv/bin/python -m pytest tests/test_proto.py
```

| File | What it is |
|---|---|
| `links.txt` | Hand-typed links for about 240 nouns (syntax is at the top of the file). |
| `typed.py` | Loader, solver, board generator and board quality numbers. |
| `play.py` | The terminal game. |
| `boards.py` | Batch report. |
| `export_web.py`, `web/playtest.html` | Builds the browser playtest page from a run of boards. |
| `scale.py` | How long a vocabulary sustains fresh boards, by size. |
| `label.py` | Labels word pairs and drafts definitions through the Claude Batch API; `calibrate` scores it against `links.txt`. |
| `vocab.txt`, `glosses.json` | The Phase 2 vocabulary (735 tiles, 76 feature adjectives, cut words) and each tile's one meaning. |

**Board numbers:**

| Number | Meaning |
|---|---|
| solutions | valid 6-link chains on the board (aim: 1–2) |
| traps | chains that work only by spending a type twice |
| random win | how often random legal play solves the board (aim: under 10%) |
| apart | the fewest links between start and target over the whole vocabulary |
| look-alikes | unlinked pairs on the board that look linked; only route-to-route pairs are allowed |

Run `--gaps` for every look-alike pair, which is the to-do list of likely missing links.
