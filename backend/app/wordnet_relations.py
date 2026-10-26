"""Name the relation behind an embedding edge, using WordNet.

The typed overlay (relations.py) labels the curated cross-domain edges. For the
many ordinary embedding edges (dog-cat, big-small, oak-tree) we derive a label
on the fly from WordNet so every accepted move can say *why* it connects.

Returned labels match the overlay vocabulary so the UI maps them uniformly:
    Synonym, Antonym, IsA, PartOf, SameCategory

If WordNet (nltk) is unavailable the labeler degrades gracefully to None, and
moves simply show "Connected" — the game is unaffected.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("degrees.wordnet")


class WordNetLabeler:
    def __init__(self, max_senses_per_pos: int | None = 3) -> None:
        # WordNet lists each word's senses most-common first. Matching on
        # rare senses produces links players read as nonsense (crown "is a"
        # head: the crown of the head; foot ~ minute: units), so only the top
        # senses per part of speech count. Per part of speech, not overall:
        # "cold" lists the illness (noun) before the temperature (adjective).
        # None considers every sense.
        self._max_senses = max_senses_per_pos
        self._wn = None
        self._cache: dict[tuple[str, str], str | None] = {}
        try:
            from nltk.corpus import wordnet as wn
            wn.synsets("dog")  # force corpus load; raises if not downloaded
            self._wn = wn
            logger.info("WordNet labeler enabled.")
        except Exception as exc:  # missing nltk or corpus
            logger.warning("WordNet unavailable (%s); embedding edges unlabeled.", exc)

    @property
    def enabled(self) -> bool:
        return self._wn is not None

    def classify(self, a: str, b: str) -> str | None:
        """Best relation label for the undirected pair (a, b), or None."""
        if self._wn is None or a == b:
            return None
        key = (a, b) if a <= b else (b, a)
        if key in self._cache:
            return self._cache[key]
        label = self._classify(*key)
        self._cache[key] = label
        return label

    # -- internals -------------------------------------------------------
    def _synsets(self, word: str) -> list:
        """The word's most common senses, up to max_senses per part of speech."""
        senses = self._wn.synsets(word)
        if self._max_senses is None:
            return senses
        kept, per_pos = [], {}
        for s in senses:
            pos = "a" if s.pos() in ("a", "s") else s.pos()  # satellites are adjectives
            if per_pos.get(pos, 0) < self._max_senses:
                kept.append(s)
                per_pos[pos] = per_pos.get(pos, 0) + 1
        return kept

    def _classify(self, a: str, b: str) -> str | None:
        A, B = self._synsets(a), self._synsets(b)
        if not A or not B:
            return None
        setA, setB = set(A), set(B)

        # 1. Synonym: the words share a sense.
        if setA & setB:
            return "Synonym"

        # 2. Antonym: a lemma of one is an antonym of the other.
        for src, dst in ((A, setB), (B, setA)):
            for s in src:
                for lemma in s.lemmas():
                    if any(ant.synset() in dst for ant in lemma.antonyms()):
                        return "Antonym"

        # 3. Is-a: one is an ancestor of the other in the hypernym tree.
        def hyper_closure(synsets):
            out: set = set()
            for s in synsets:
                out |= set(s.closure(lambda x: x.hypernyms()))
            return out

        if (setB & hyper_closure(A)) or (setA & hyper_closure(B)):
            return "IsA"

        # 4. Part-of: meronym/holonym either direction.
        def parts(s):
            return set(
                s.part_meronyms() + s.member_meronyms() + s.substance_meronyms()
                + s.part_holonyms() + s.member_holonyms() + s.substance_holonyms()
            )

        if any(parts(s) & setB for s in A) or any(parts(s) & setA for s in B):
            return "PartOf"

        # 5. Same category: share a near hypernym (siblings/cousins), or, for
        #    adjectives, a shared attribute (red/blue -> chromatic color).
        if self._near_hypernyms(A) & self._near_hypernyms(B):
            return "SameCategory"
        attrsA = {at for s in A for at in s.attributes()}
        attrsB = {at for s in B for at in s.attributes()}
        if (attrsA & setB) or (attrsB & setA) or (attrsA & attrsB):
            return "SameCategory"

        return None

    @staticmethod
    def _near_hypernyms(synsets, depth: int = 2) -> set:
        """Hypernyms within `depth` levels (excludes the synsets themselves)."""
        out: set = set()
        for s in synsets:
            frontier = [s]
            for _ in range(depth):
                nxt = []
                for f in frontier:
                    for h in f.hypernyms():
                        out.add(h)
                        nxt.append(h)
                frontier = nxt
        return out
