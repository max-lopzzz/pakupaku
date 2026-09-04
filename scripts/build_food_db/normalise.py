import re
from typing import Tuple

from scripts.build_food_db.model import NormalisedRow

PREP_STATES: Tuple[str, ...] = ("raw", "cooked", "dried", "unspecified")

_COOKED_WORDS = {
    "cooked", "boiled", "baked", "roasted", "fried", "grilled", "steamed",
    "braised", "stewed", "simmered", "sauteed", "microwaved", "poached",
}
_RAW_WORDS = {"raw", "fresh", "uncooked"}
_DRIED_WORDS = {"dried", "dehydrated", "sun-dried"}
_PREP_WORDS = _COOKED_WORDS | _RAW_WORDS | _DRIED_WORDS
# words removed from the canonical key (prep + filler that doesn't identify the food)
_KEY_STOPWORDS = (
    _PREP_WORDS
    | {"in", "with", "without", "and", "of", "unsalted", "salted", "water",
       "drained", "added", "no"}
)
_PUNCT = re.compile(r"[^a-z0-9\s]")
_WS = re.compile(r"\s+")


def parse_prep_state(name: str) -> str:
    tokens = set(_WS.sub(" ", _PUNCT.sub(" ", name.lower())).split())
    if tokens & _DRIED_WORDS:
        return "dried"
    if tokens & _COOKED_WORDS:
        return "cooked"
    if tokens & _RAW_WORDS:
        return "raw"
    return "unspecified"


def canonical_key(name: str) -> str:
    lowered = name.lower()
    # The head noun sits at the end of the pre-comma segment ("coconut water",
    # "Water, tap, drinking" -> head noun "water"). Keep that token even when
    # it is a stopword, so "coconut water" stays "coconut water" instead of
    # collapsing to "coconut". A prep-state word there is still dropped —
    # prep is tracked separately ("Potato, raw" / "Potato, boiled" -> "potato").
    head = lowered.split(",", 1)[0]
    head_tokens = _WS.sub(" ", _PUNCT.sub(" ", head)).split()
    head_noun = (
        head_tokens[-1]
        if head_tokens and head_tokens[-1] not in _PREP_WORDS
        else None
    )

    cleaned = _WS.sub(" ", _PUNCT.sub(" ", lowered)).strip()
    raw_tokens = [t for t in cleaned.split() if t]
    tokens = [t for t in raw_tokens if t not in _KEY_STOPWORDS or t == head_noun]
    if not tokens:
        # every token was a stopword ("raw", "in water") — fall back to the
        # full sorted token list rather than emit an empty key.
        tokens = raw_tokens
    return " ".join(sorted(tokens))


def normalise_row(row: NormalisedRow) -> NormalisedRow:
    row.prep_state = parse_prep_state(row.name)
    row.canonical_key = canonical_key(row.name)
    return row
