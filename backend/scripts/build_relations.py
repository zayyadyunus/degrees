"""Build the typed-relation overlay (data/relations.json) from a ConceptNet dump.

ConceptNet ships assertions as a gzipped TSV, one edge per line:

    <uri>\t/r/<Rel>\t/c/en/<start>\t/c/en/<end>\t{json metadata}

Download once (~1.2 GB):
    curl -LO https://s3.amazonaws.com/conceptnet/downloads/2019/edges/conceptnet-assertions-5.7.0.csv.gz

Then build, keeping only English single-token edges whose BOTH endpoints are in
the curated wordlist and whose relation is one the game explains to players:

    python scripts/build_relations.py --assertions conceptnet-assertions-5.7.0.csv.gz

This is the production source for the overlay the game already loads; the shipped
data/relations.json is a small hand-authored stand-in with the same schema.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"

# ConceptNet /r/<Rel>  ->  the label the game shows. Only relations that map to
# one of the player-facing "ways to connect" are kept; the rest (RelatedTo,
# DerivedFrom, EtymologicallyRelatedTo, FormOf, ...) are too loose or lexical.
RELATION_MAP = {
    "Synonym": "Synonym",
    "Antonym": "Antonym",
    "IsA": "IsA",
    "PartOf": "PartOf",
    "HasA": "PartOf",
    "MadeOf": "MadeOf",
    "UsedFor": "UsedFor",
    "CapableOf": "UsedFor",
    "AtLocation": "AtLocation",
    "LocatedNear": "AtLocation",
    "Causes": "Causes",
    "HasSubevent": "Causes",
    "SymbolOf": "SymbolOf",
    "HasProperty": "HasProperty",
}


def read_wordlist(path: Path) -> set[str]:
    words = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        w = line.strip().lower()
        if w and not w.startswith("#"):
            words.add(w)
    return words


def en_term(uri: str) -> str | None:
    """/c/en/dog or /c/en/dog/n -> 'dog'; non-English or multiword -> None."""
    parts = uri.split("/")
    if len(parts) < 4 or parts[1] != "c" or parts[2] != "en":
        return None
    term = parts[3]
    return term if "_" not in term else None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--assertions", required=True, type=Path, help="conceptnet-assertions-*.csv.gz")
    p.add_argument("--wordlist", type=Path, default=DATA_DIR / "wordlist.txt")
    p.add_argument("--out", type=Path, default=DATA_DIR / "relations.json")
    p.add_argument("--min-weight", type=float, default=1.0, help="drop low-confidence edges")
    args = p.parse_args()

    wanted = read_wordlist(args.wordlist)
    print(f"Wordlist has {len(wanted)} words; scanning {args.assertions} ...")

    # Keep the best (highest-weight) edge per undirected pair.
    best: dict[frozenset[str], tuple[float, str, str, str]] = {}
    scanned = 0
    opener = gzip.open if args.assertions.suffix == ".gz" else open
    with opener(args.assertions, "rt", encoding="utf-8") as fh:
        for line in fh:
            scanned += 1
            cols = line.rstrip("\n").split("\t")
            if len(cols) < 5:
                continue
            rel = cols[1].rsplit("/", 1)[-1]
            label = RELATION_MAP.get(rel)
            if label is None:
                continue
            a, b = en_term(cols[2]), en_term(cols[3])
            if a is None or b is None or a == b:
                continue
            if a not in wanted or b not in wanted:
                continue
            try:
                weight = float(json.loads(cols[4]).get("weight", 1.0))
            except (ValueError, KeyError):
                weight = 1.0
            if weight < args.min_weight:
                continue
            key = frozenset((a, b))
            if key not in best or weight > best[key][0]:
                best[key] = (weight, label, a, b)

    edges = [
        {"rel": label, "a": a, "b": b, "weight": round(w, 2)}
        for (w, label, a, b) in sorted(best.values(), key=lambda t: -t[0])
    ]
    args.out.write_text(json.dumps({"relations": edges}, indent=2) + "\n", encoding="utf-8")
    print(f"Scanned {scanned:,} assertions.")
    print(f"Wrote {len(edges)} typed edges to {args.out}")
    by_rel: dict[str, int] = {}
    for e in edges:
        by_rel[e["rel"]] = by_rel.get(e["rel"], 0) + 1
    for rel, n in sorted(by_rel.items(), key=lambda t: -t[1]):
        print(f"   {rel:12} {n}")


if __name__ == "__main__":
    main()
