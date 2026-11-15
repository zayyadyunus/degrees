"""Assemble links.next.txt for the Phase 2 vocabulary from Claude's labelling runs.

    cd backend && .venv/bin/python -m proto.build_next

Reads (proto/labels/, git-ignored):
  label-candidates-next-k15   pair labels -> "A REL: b ?c" lines and avoid pairs
  categories-next.links.txt   "category" / "kinds" lines
  features-next.links.txt     "ADJ feature: ..." lines
Adds MANUAL below (links the candidate pairs missed), and writes
proto/links.next.txt with the header of links.txt, which typed.load() reads.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .label import OUT, parse

HERE = Path(__file__).parent
RUN = "label-candidates-next-k15"

# Hub links the candidate pairs never reached (found by the coverage check).
MANUAL = [
    "leg part: bed desk",
    "eagle makes: egg",
    "owl makes: egg",
    # critic round 1
    "ham made: pig",
    "avoid: drum ear",           # eardrum: a compound, not a link
]

# Line-for-line hand fixes to the generated text (critic round 1). Each old
# line must exist, so a rerun that changes it shows up as an error here.
EDITS = {
    # Animal to meat is "made of" everywhere (bacon made of pig), never "makes".
    "pig makes: ham ?meat": None,
    "meat made: animal ?muscle": "meat made: animal ?muscle ?pig",
    "sausage made: ?chicken meat ?pig": "sausage made: ?chicken meat pig",
    # Kinds players would hesitate over.
    "carrot kind: food root vegetable": "carrot kind: food ?root vegetable",
    "fog kind: cloud weather": "fog kind: ?cloud weather",
    "jungle kind: forest": "jungle kind: ?forest",
    # critic round 2: links that clash with the definitions (body: the whole
    # physical form of a person; arm: limb from shoulder to hand).
    "body part: ?human person": "body part: ?human ?person",
    "clothes use: body ?person": "clothes use: ?body ?person",
    "arm part: body human man octopus person ?robot": "arm part: body human man ?octopus person ?robot",
    # wind is a kind of weather (category weather), not part of it.
    "wind part: ?storm weather": "wind part: ?storm",
    # An event doesn't make things: sun makes light, sunrise arguably.
    "sunrise makes: light": "sunrise makes: ?light",
    # Gaps: these are obvious.
    "necklace made: ?gold ?silver": "necklace made: gold ?silver",
    "bucket use: ?milk ?paint ?sand water": "bucket use: ?milk ?paint sand water",
    "saw use: ?branch ?oak ?pine tree wood": "saw use: ?branch ?oak ?pine ?tree wood",
}


# Hand review of the drafted categories and features.
RENAME = {"~wild_dog": "~dog_family", "~wild_landscape": "~landscape"}
# Features that are a category in disguise (wild), relative (strong), or
# give odd links between weather words (storm and jungle are both rainy).
DROP_FEATURES = {"wild", "strong", "cloudy", "rainy", "windy", "busy"}
# Feature lists rewritten by hand. A feature must define the word: hard is THE
# answer for a rock, not for a nail; "light is bright" says nothing.
FEATURE_LISTS = {
    "hard": "rock stone diamond brick pebble ?bone ?tooth ?nail ?helmet ?coconut",
    "bright": "sun lightning star ?lamp ?diamond",
}


def category_words(cats: str) -> set[str]:
    return {line.split(":")[0].split()[1] for line in cats.splitlines() if line.startswith(("category", "kinds"))}


def strip_categories(feats: str, cats: set[str]) -> str:
    """No category words in feature lists: a category's members would inherit
    the feature (fruit is sweet, so lemon is sweet)."""
    out, dropped = [], []
    for line in feats.splitlines():
        head, _, rest = line.partition(":")
        keep = [w for w in rest.split() if w.lstrip("?") not in cats]
        dropped += [f"{w.lstrip('?')} ({head.split()[0]})" for w in rest.split() if w.lstrip("?") in cats]
        if len(keep) >= 2:
            out.append(f"{head}: {' '.join(keep)}")
    if dropped:
        print(f"  dropped category words from feature lists: {', '.join(dropped)}")
    return "\n".join(out)


def reviewed(text: str) -> str:
    out = []
    for line in text.splitlines():
        head, _, rest = line.partition(":")
        words = head.split()
        if len(words) == 2 and words[1] == "feature" and words[0] in DROP_FEATURES:
            continue
        if len(words) == 2 and words[1] == "feature" and words[0] in FEATURE_LISTS:
            line = f"{head}: {FEATURE_LISTS[words[0]]}"
        # A one-member category ("category hat: helmet") would make the kind
        # link obvious whatever the pair labels say (helmet kind: ?hat): leave
        # it to the pair labels.
        if words and words[0] in ("category", "kinds") and len(rest.split()) < 2:
            continue
        if len(words) == 2 and words[1] in RENAME:
            line = f"{words[0]} {RENAME[words[1]]}:{rest}"
        out.append(line)
    return "\n".join(out)


def header() -> str:
    lines = []
    for line in (HERE / "links.txt").read_text().splitlines():
        if not line.startswith("#"):
            break
        lines.append(line)
    return "\n".join(lines)


def pair_lines() -> tuple[list[str], list[str]]:
    pairs = {p["id"]: p for p in json.loads((OUT / f"{RUN}.pairs.json").read_text())}
    items, failed, _ = parse(RUN, "pairs")
    if failed:
        raise SystemExit(f"{len(failed)} failed requests in {RUN}: rerun them first")
    grouped: dict[tuple[str, str], dict[str, bool]] = defaultdict(dict)   # (from, rel) -> target -> obvious
    avoid = []
    for x in items:
        p = pairs[x["id"]]
        for l in x["links"]:
            a = l["from"]
            if a not in (p["a"], p["b"]):
                continue                      # Claude named a word not in the pair
            b = p["b"] if a == p["a"] else p["a"]
            grouped[(a, l["rel"])][b] = grouped[(a, l["rel"])].get(b, False) or l["strength"] == "obvious"
        if x["phrase"] and not x["links"]:
            avoid.append(f"avoid: {' '.join(sorted((p['a'], p['b'])))}")
    lines = [f"{a} {rel}: " + " ".join(("" if ok else "?") + b for b, ok in sorted(ts.items()))
             for (a, rel), ts in sorted(grouped.items())]
    return lines, sorted(avoid)


def people_kinds(lines: list[str]) -> list[str]:
    """"aunt is a kind of human" reads badly next to person, and "a kind of
    people" isn't English: human becomes arguable, people goes."""
    out = []
    for line in lines:
        head, _, rest = line.partition(":")
        if head.endswith(" kind"):
            ws = [w for w in rest.split() if w.lstrip("?") != "people"]
            ws = ["?human" if w == "human" else w for w in ws]
            if not ws:
                continue
            line = f"{head}: {' '.join(ws)}"
        out.append(line)
    return out


def apply_edits(lines: list[str]) -> list[str]:
    missing = [old for old in EDITS if old not in lines]
    if missing:
        raise SystemExit("EDITS lines not found (the data changed?):\n  " + "\n  ".join(missing))
    return [EDITS.get(l, l) for l in lines if EDITS.get(l, l) is not None]


def drop_redundant_found(text: str) -> tuple[str, int]:
    """Drop "found" (in / with) where the pair has an obvious, more specific
    type: stage is part of a theater, so it needn't also "go with" it. Found
    is the loosest type, and every extra found link is a trap on the board."""
    import tempfile
    from .typed import load
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text)
    links = load(Path(f.name))
    Path(f.name).unlink()
    redundant = {pair for pair, types in links.edges.items()
                 if "found" in types and set(links.obvious(*pair)) & {"kind", "family", "part", "use"}}
    out, dropped = [], 0
    for line in text.split("\n"):
        head, _, rest = line.partition(":")
        hw = head.split()
        if len(hw) == 2 and hw[1] in ("in", "with") and not line.startswith("#"):
            keep = [w for w in rest.split() if frozenset((hw[0], w.lstrip("?"))) not in redundant]
            dropped += len(rest.split()) - len(keep)
            if not keep:
                continue
            line = f"{head}: {' '.join(keep)}"
        out.append(line)
    return "\n".join(out), dropped


def main() -> None:
    rel_lines, avoid = pair_lines()
    rel_lines = people_kinds(rel_lines)
    cats = reviewed((OUT / "categories-next.links.txt").read_text().strip())
    feats = strip_categories(reviewed((OUT / "features-next.links.txt").read_text().strip()), category_words(cats))
    text = "\n".join([
        header(),
        "#",
        "# GENERATED by proto/build_next.py from Claude's labelling runs. Edit by",
        "# changing the runs or MANUAL there, or hand-edit and stop regenerating.",
        "",
        "# ---- categories ------------------------------------------------------",
        cats,
        "",
        "# ---- features --------------------------------------------------------",
        feats,
        "",
        "# ---- avoid: compound phrases that aren't links -------------------------",
        *avoid,
        "",
        "# ---- added by hand ---------------------------------------------------",
        *MANUAL,
        "",
        "# ---- pair labels -----------------------------------------------------",
        *rel_lines,
        "",
    ])
    text = "\n".join(apply_edits(text.split("\n")))
    text, dropped = drop_redundant_found(text)
    print(f"  dropped {dropped} found links where the pair has a more specific obvious type")
    out = HERE / "links.next.txt"
    out.write_text(text)
    print(f"wrote {out}: {len(rel_lines)} relation lines, {len(avoid)} avoid pairs, "
          f"{cats.count(chr(10)) + 1} category lines, {feats.count(chr(10)) + 1} feature lines")


if __name__ == "__main__":
    main()
