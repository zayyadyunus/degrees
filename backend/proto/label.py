"""Label word pairs with link types through the Claude Message Batches API.

Pairwise labelling covers the four direct relations (kind, part/made,
use/makes, in/with). "Same family" and "share a feature" come from lists
(categories, feature lists) and are built separately.

Calibration first: label pairs from the hand-typed prototype, whose answers
we already know, and score Claude against them before paying for the full
vocabulary.

    cd backend
    .venv/bin/python -m proto.label calibrate --dry-run      # show the prompt and size, no API call
    .venv/bin/python -m proto.label calibrate                # submit, wait, score
    .venv/bin/python -m proto.label resume NAME              # wait on / fetch a submitted run
    .venv/bin/python -m proto.label score NAME               # re-score saved results

Needs the `anthropic` package (requirements-dev.txt) and an API key in
ANTHROPIC_API_KEY. Runs are saved under proto/labels/NAME.*
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

from .typed import Links, load, look_alikes

OUT = Path(__file__).with_name("labels")
RELS = ("kind", "part", "made", "use", "makes", "in", "with")
REL_TYPE = {"kind": "kind", "part": "part", "made": "part", "use": "use", "makes": "use", "in": "found", "with": "found"}
PAIR_TYPES = ("kind", "part", "use", "found")   # the types pairwise labelling decides

# $ per million tokens, standard rate (batch is half). From the claude-api skill, cached 2026-11-03.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
BATCH_DISCOUNT = 0.5

RUBRIC = """\
You are labelling links for Degrees, a word puzzle. Players connect a start word to a target word \
through a chain of everyday nouns, and every step must be a link that most adults would accept the \
moment they see it. You decide, for each pair of words, which of these relations hold.

Relations (A and B are the two words; give the direction with "from"):
- kind:  A is a kind of B. dog -> animal, eagle -> bird, eagle -> animal (it passes up through bird), \
gold -> metal. Not for two things of the same sort (lion, tiger): that is not "kind".
- part:  A is part of B. wheel -> car, roof -> house, seed -> apple, eye -> face.
- made:  A is made of B, where B is what A is usually made of. bread -> flour, paper -> wood, \
knife -> metal, window -> glass. Not a material A can merely sometimes be made of (a bridge can \
be wooden, but most aren't, so bridge -> wood is not a link).
- use:   A is a tool or object whose job is B, or whose job is done on B. hammer -> nail, \
knife -> bread, pencil -> paper, pillow -> head, cup -> tea, wood -> fire. Things eaten, drunk or \
served together are not "use": honey and tea, butter and bread, sugar and coffee are "with".
- makes: A makes or produces B. bee -> honey, cow -> milk, tree -> apple, storm -> rain.
- in:    A is found in B, as the place it lives or belongs. sand -> beach, fish -> sea, deer -> forest, \
moon -> sky.
- with:  A goes with B: they are paired or found together so often that one calls up the other. \
salt -> pepper, egg -> breakfast, bridge -> river, knife -> table, honey -> tea, butter -> bread. \
"Both can be at the beach in summer" is not enough: one must call up the other.

Rules:
1. Be strict. Only label a relation a player would accept without arguing. "They are both about \
food" or "they can appear in the same story" is not a link. When unsure, leave it out.
2. One word, one meaning. Each word comes with a short definition in brackets: that is the only \
meaning the puzzle uses. If a relation only works through a different, unrelated meaning (nail \
defined as a metal pin, so not the fingernail; bat the animal, not the club), it is not a link. \
Closely related senses are fine (a drinking glass is made of glass).
3. Several relations can hold for one pair (knife -> metal is "made"; knife -> table is "with"). \
List every one that holds, each with its direction.
4. Ignore these, which are handled elsewhere: two things being the same sort of thing (lion, tiger), \
and shared looks or qualities (both red, both soft). Don't force them into "with".
5. A compound that names a material, part or ingredient is that relation, not a phrase: \
gold coin -> coin made of gold, carrot juice -> juice made of carrot, potato salad -> potato is \
part of salad, grass seed -> seed makes grass. Label the relation.
6. "phrase" is rare. Set it to true only when the two words make a well-known compound noun that \
names a different thing, so a player would likely try the pair as a link, and no relation above \
holds: spider monkey, wheel chair, school bus, fire truck, sea horse, heavy metal. Words that merely \
sit near each other in a saying or description (head to foot, morning sun, desk clock, root and \
branch) are not phrases. If a relation holds, "phrase" is false.
7. Rate each relation you list. "obvious": nearly every player would accept it the moment they \
see it (bee makes honey, salt goes with pepper). "arguable": true, but some players would \
hesitate or disagree (sun goes with beach, phone goes with hand). Still leave out anything most \
players would reject.

For each pair, give its id, the relations that hold (an empty list if none), and phrase.\
"""

GLOSS_PROMPT = """\
You are preparing the word list for Degrees, a word puzzle where players link everyday nouns \
(bee makes honey, wheel is part of a car, salt goes with pepper). Each word in the puzzle has \
exactly one meaning, and links may only use that meaning.

For each word, write a short definition (3 to 8 words) of the meaning the puzzle uses. When \
context words are given, they are words it already links to in the puzzle, so define the meaning \
that fits them. Otherwise define the most common everyday meaning, the one a child would give.

In "other", name a second common meaning that is unrelated to the first and that players would \
likely think of (for nail defined as a metal pin: "fingernail"; for bat the animal: "club for \
hitting a ball"). Use an empty string when there is none. Related senses don't count: glass the \
material and a drinking glass are one meaning.\
"""

GLOSS_SCHEMA = {
    "type": "object",
    "properties": {
        "words": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"word": {"type": "string"}, "gloss": {"type": "string"},
                               "other": {"type": "string"}},
                "required": ["word", "gloss", "other"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["words"],
    "additionalProperties": False,
}

SCHEMA = {
    "type": "object",
    "properties": {
        "pairs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "links": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "rel": {"type": "string", "enum": list(RELS)},
                                "from": {"type": "string"},
                                "strength": {"type": "string", "enum": ["obvious", "arguable"]},
                            },
                            "required": ["rel", "from", "strength"],
                            "additionalProperties": False,
                        },
                    },
                    "phrase": {"type": "boolean"},
                },
                "required": ["id", "links", "phrase"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pairs"],
    "additionalProperties": False,
}


# ---- calibration set -------------------------------------------------------

def key_types(links: Links, a: str, b: str) -> set[str]:
    """The hand-typed answer: which pairwise types link a and b."""
    return set(links.types(a, b)) & set(PAIR_TYPES)


def calibration_pairs(links: Links, n_pos: int, n_neg: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    pos = sorted(tuple(sorted(p)) for p, t in links.edges.items() if set(t) & set(PAIR_TYPES))
    neg = sorted(tuple(sorted(p)) for p in look_alikes(links) if p not in links.edges)
    picked = rng.sample(pos, min(n_pos, len(pos))) + rng.sample(neg, min(n_neg, len(neg)))
    rng.shuffle(picked)
    out = []
    for i, (a, b) in enumerate(picked):
        if rng.random() < 0.5:
            a, b = b, a            # don't leak a direction through alphabetical order
        out.append({"id": i, "a": a, "b": b, "key": sorted(key_types(links, a, b))})
    return out


# ---- requests --------------------------------------------------------------

def chunks(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def word_text(word: str, glosses: dict[str, dict]) -> str:
    g = glosses.get(word)
    return f"{word} ({g['gloss']})" if g else word


def user_text(chunk: list[dict], glosses: dict[str, dict]) -> str:
    lines = "\n".join(f'{p["id"]}: {word_text(p["a"], glosses)} / {word_text(p["b"], glosses)}' for p in chunk)
    return f"Label these {len(chunk)} pairs.\n\n{lines}"


def params(system: str, user: str, schema: dict, model: str, effort: str) -> dict:
    return {
        "model": model,
        "max_tokens": 16000,
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": [{"role": "user", "content": user}],
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
    }


# ---- run state -------------------------------------------------------------

def paths(name: str) -> dict[str, Path]:
    return {k: OUT / f"{name}.{k}" for k in ("pairs.json", "meta.json", "results.jsonl", "review.txt")}


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1))


def client():
    try:
        import anthropic
    except ImportError:
        sys.exit("The anthropic package isn't installed: .venv/bin/pip install -r requirements-dev.txt")
    return anthropic.Anthropic()


def submit(name: str, items: list, reqs: list[dict], meta: dict) -> str:
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request

    batch = client().messages.batches.create(requests=[
        Request(custom_id=f"chunk-{k}", params=MessageCreateParamsNonStreaming(**r)) for k, r in enumerate(reqs)])
    p = paths(name)
    save_json(p["pairs.json"], items)
    save_json(p["meta.json"], {**meta, "batch": batch.id, "requests": len(reqs),
                               "submitted": time.strftime("%Y-%m-%d %H:%M:%S")})
    print(f"submitted {len(reqs)} requests ({len(items)} items) as batch {batch.id}; run name {name}", flush=True)
    return batch.id


def wait_and_fetch(name: str, poll: int = 20) -> None:
    p = paths(name)
    meta = json.loads(p["meta.json"].read_text())
    c = client()
    while True:
        b = c.messages.batches.retrieve(meta["batch"])
        n = b.request_counts
        print(f"  {time.strftime('%H:%M:%S')} {b.processing_status}: {n.succeeded} done, "
              f"{n.processing} processing, {n.errored} errored", flush=True)
        if b.processing_status == "ended":
            break
        time.sleep(poll)
    with p["results.jsonl"].open("w") as f:
        for r in c.messages.batches.results(meta["batch"]):
            row = {"custom_id": r.custom_id, "type": r.result.type}
            if r.result.type == "succeeded":
                msg = r.result.message
                u = msg.usage
                row["usage"] = {"input": u.input_tokens, "output": u.output_tokens,
                                "cache_read": u.cache_read_input_tokens or 0,
                                "cache_write": u.cache_creation_input_tokens or 0}
                row["stop_reason"] = msg.stop_reason
                if msg.stop_reason == "end_turn":
                    row["text"] = next((blk.text for blk in msg.content if blk.type == "text"), "")
            else:
                row["error"] = str(getattr(r.result, "error", ""))
            f.write(json.dumps(row) + "\n")
    print(f"saved results to {p['results.jsonl']}")


def parse(name: str, key: str) -> tuple[list[dict], list[dict], dict]:
    """The items Claude returned under `key`, the failed requests, and token totals."""
    items, failed, tokens = [], [], Counter()
    for line in paths(name)["results.jsonl"].read_text().splitlines():
        row = json.loads(line)
        tokens.update(row.get("usage", {}))
        if "text" not in row:
            failed.append(row)
            continue
        items.extend(json.loads(row["text"])[key])
    return items, failed, dict(tokens)


def cost(tokens: dict, model: str) -> float:
    pin, pout = PRICES.get(model, (0, 0))
    # cache writes bill at 1.25x input, cache reads at 0.1x input
    dollars = (tokens.get("input", 0) * pin + tokens.get("cache_write", 0) * pin * 1.25
               + tokens.get("cache_read", 0) * pin * 0.1 + tokens.get("output", 0) * pout) / 1e6
    return dollars * BATCH_DISCOUNT


# ---- definitions -----------------------------------------------------------

def gloss_items(links: Links | None, words: list[str]) -> list[dict]:
    """Words to define, with the words each already links to (prototype) as context."""
    out = []
    for w in words:
        ctx = sorted(links.adj.get(w, ()))[:10] if links else []
        out.append({"word": w, "context": ctx})
    return out


def gloss_text(chunk: list[dict]) -> str:
    lines = "\n".join(f'{x["word"]}' + (f' (links to: {", ".join(x["context"])})' if x["context"] else "")
                      for x in chunk)
    return f"Define these {len(chunk)} words.\n\n{lines}"


def glosses_path(name: str) -> Path:
    return OUT / f"{name}.glosses.json"


def save_glosses(name: str) -> None:
    """Write NAME.glosses.json ({word: {gloss, other}}) and a list of the two-meaning words."""
    meta = json.loads(paths(name)["meta.json"].read_text())
    items, failed, tokens = parse(name, "words")
    data = {x["word"]: {"gloss": x["gloss"], "other": x["other"]} for x in items}
    save_json(glosses_path(name), dict(sorted(data.items())))
    wanted = {x["word"] for x in json.loads(paths(name)["pairs.json"].read_text())}
    two = sorted(w for w, g in data.items() if g["other"])
    print(f"\n{name}: {len(data)}/{len(wanted)} words defined"
          f"{f', {len(failed)} failed requests' if failed else ''}; cost ${cost(tokens, meta['model']):.2f}")
    print(f"  {len(two)} words with a second meaning players might think of:")
    for w in two:
        print(f"    {w:<12} {data[w]['gloss']}  |  other: {data[w]['other']}")
    print(f"  saved to {glosses_path(name)}")


# ---- scoring ---------------------------------------------------------------

def link_text(pr: dict, l: dict) -> str:
    other = pr["b"] if l["from"] == pr["a"] else pr["a"]
    return f'{l["from"]} {l["rel"]} {other}' + (" (arguable)" if l["strength"] == "arguable" else "")


def score(name: str) -> None:
    p = paths(name)
    pairs = json.loads(p["pairs.json"].read_text())
    meta = json.loads(p["meta.json"].read_text())
    items, failed, tokens = parse(name, "pairs")
    labels = {x["id"]: x for x in items}

    tp = fp = fn = tn = exact = arguable_only = 0
    per_type = {t: Counter() for t in PAIR_TYPES}
    review, missing = [], 0
    for pr in pairs:
        got = labels.get(pr["id"])
        if got is None:
            missing += 1
            continue
        # Only obvious links count; arguable ones are dropped, as they would be in the game.
        mine = {REL_TYPE[l["rel"]] for l in got["links"] if l["strength"] == "obvious"}
        key = set(pr["key"])
        if key and not mine and got["links"]:
            arguable_only += 1
        if key and mine: tp += 1
        elif key: fn += 1
        elif mine: fp += 1
        else: tn += 1
        if key and mine == key:
            exact += 1
        for t in PAIR_TYPES:
            per_type[t]["tp" if t in key and t in mine else "fn" if t in key else "fp" if t in mine else "tn"] += 1
        if mine != key or got["phrase"]:
            said = ", ".join(link_text(pr, l) for l in got["links"]) or "none"
            tag = "MISSED" if key and not mine else "EXTRA" if mine and not key else "PHRASE" if mine == key else "TYPE"
            review.append(f'{tag:<7} {pr["a"]} / {pr["b"]}\n'
                          f'        hand:   {", ".join(sorted(key)) or "none"}\n'
                          f'        claude: {said}{"  [phrase]" if got["phrase"] else ""}')

    pos, neg = tp + fn, fp + tn
    print(f"\n{name}: {meta['model']}, effort {meta['effort']}, {len(pairs)} pairs"
          f"{', with definitions' if meta.get('glosses') else ''}"
          f"{f', {missing} unanswered ({len(failed)} failed requests)' if missing else ''}")
    print("  (only links Claude rates obvious count)")
    print(f"  hand-linked pairs Claude also links:      {tp}/{pos} ({tp / max(pos, 1):.0%})"
          f"{f'; {arguable_only} more only as arguable' if arguable_only else ''}")
    print(f"  ...with exactly the hand-typed types:     {exact}/{pos} ({exact / max(pos, 1):.0%})")
    print(f"  look-alike non-links Claude leaves alone: {tn}/{neg} ({tn / max(neg, 1):.0%})")
    print("  per type (precision / recall vs hand labels):")
    for t, c in per_type.items():
        prec = c["tp"] / max(c["tp"] + c["fp"], 1)
        rec = c["tp"] / max(c["tp"] + c["fn"], 1)
        print(f"    {t:<6} {prec:.0%} / {rec:.0%}   ({c['tp']} agree, {c['fp']} extra, {c['fn']} missed)")
    strengths = Counter(l["strength"] for x in items for l in x["links"])
    print(f"  links rated: {strengths['obvious']} obvious, {strengths['arguable']} arguable")
    spent = cost(tokens, meta["model"])
    print(f"  tokens: {tokens.get('input', 0) + tokens.get('cache_read', 0) + tokens.get('cache_write', 0):,} in, "
          f"{tokens.get('output', 0):,} out; cost ${spent:.2f} (batch rate), "
          f"${spent / max(len(pairs), 1) * 12000:.2f} per 12,000 pairs")
    p["review.txt"].write_text("\n".join(review) + "\n")
    print(f"  {len(review)} disagreements to review: {p['review.txt']}")


# ---- cli -------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    def model_args(sp):
        sp.add_argument("--model", default="claude-opus-5-5", choices=sorted(PRICES))
        sp.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
        sp.add_argument("--name", default=None)
        sp.add_argument("--dry-run", action="store_true")

    gl = sub.add_parser("glosses", help="draft a one-meaning definition for every word")
    gl.add_argument("words", choices=["proto", "next"], help="prototype nouns, or data/wordlist.next.txt")
    gl.add_argument("--chunk", type=int, default=60, help="words per request")
    model_args(gl)
    cal = sub.add_parser("calibrate", help="label prototype pairs and score against the hand labels")
    cal.add_argument("--pos", type=int, default=300, help="hand-linked pairs")
    cal.add_argument("--neg", type=int, default=200, help="look-alike pairs with no link")
    cal.add_argument("--chunk", type=int, default=25, help="pairs per request")
    cal.add_argument("--seed", type=int, default=0)
    cal.add_argument("--glosses", default="glosses-proto", help="run name of the definitions to use ('' for none)")
    model_args(cal)
    for cmd in ("resume", "score"):
        sub.add_parser(cmd).add_argument("name")
    args = ap.parse_args()

    if args.cmd == "glosses":
        links = load() if args.words == "proto" else None
        words = sorted(links.words) if links else [
            w.strip() for w in (Path(__file__).parents[1] / "data" / "wordlist.next.txt").read_text().splitlines()
            if w.strip() and not w.startswith("#")]
        items = gloss_items(links, words)
        name = args.name or f"glosses-{args.words}"
        reqs = [params(GLOSS_PROMPT, gloss_text(c), GLOSS_SCHEMA, args.model, args.effort) for c in chunks(items, args.chunk)]
        if args.dry_run:
            print(GLOSS_PROMPT, "\n\n--- first request ---\n" + reqs[0]["messages"][0]["content"][:1500])
            print(f"\n{len(items)} words in {len(reqs)} requests; would save as {name}")
            return
        submit(name, items, reqs, {"kind": "glosses", "model": args.model, "effort": args.effort})
        wait_and_fetch(name)
        save_glosses(name)
    elif args.cmd == "calibrate":
        glosses = {}
        if args.glosses:
            gp = glosses_path(args.glosses)
            if not gp.exists():
                sys.exit(f"no definitions at {gp}: run `python -m proto.label glosses proto` first, or pass --glosses ''")
            glosses = json.loads(gp.read_text())
        pairs = calibration_pairs(load(), args.pos, args.neg, args.seed)
        name = args.name or f"calibrate-{args.model.removeprefix('claude-')}-{args.effort}"
        reqs = [params(RUBRIC, user_text(c, glosses), SCHEMA, args.model, args.effort) for c in chunks(pairs, args.chunk)]
        if args.dry_run:
            print(RUBRIC, "\n\n--- first request ---\n" + reqs[0]["messages"][0]["content"])
            pos = sum(1 for p in pairs if p["key"])
            print(f"\n{len(pairs)} pairs ({pos} hand-linked, {len(pairs) - pos} look-alikes) in {len(reqs)} requests; "
                  f"model {args.model}, effort {args.effort}; would save as {name}")
            return
        submit(name, pairs, reqs, {"kind": "pairs", "model": args.model, "effort": args.effort,
                                   "glosses": args.glosses})
        wait_and_fetch(name)
        score(name)
    else:
        meta = json.loads(paths(args.name)["meta.json"].read_text())
        if args.cmd == "resume":
            wait_and_fetch(args.name)
        (save_glosses if meta.get("kind") == "glosses" else score)(args.name)


if __name__ == "__main__":
    main()
