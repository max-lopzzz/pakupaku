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
# words removed from the canonical key (prep + filler that doesn't identify the food)
_KEY_STOPWORDS = (
    _COOKED_WORDS | _RAW_WORDS | _DRIED_WORDS
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
    cleaned = _WS.sub(" ", _PUNCT.sub(" ", name.lower())).strip()
    tokens = [t for t in cleaned.split() if t and t not in _KEY_STOPWORDS]
    return " ".join(sorted(tokens))


def normalise_row(row: NormalisedRow) -> NormalisedRow:
    row.prep_state = parse_prep_state(row.name)
    row.canonical_key = canonical_key(row.name)
    return row
