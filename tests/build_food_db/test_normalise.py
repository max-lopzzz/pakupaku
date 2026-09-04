from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import (
    canonical_key, parse_prep_state, normalise_row,
)


def test_prep_state_detection():
    assert parse_prep_state("Potato, raw") == "raw"
    assert parse_prep_state("Potato, boiled, drained") == "cooked"
    assert parse_prep_state("Potato, baked") == "cooked"
    assert parse_prep_state("Apricot, dried") == "dried"
    assert parse_prep_state("Olive oil") == "unspecified"


def test_canonical_key_is_order_and_punctuation_insensitive():
    assert canonical_key("Broccoli, raw") == canonical_key("raw broccoli")
    assert canonical_key("Rice, white, long-grain") == canonical_key("long grain white rice")


def test_canonical_key_drops_prep_words():
    # prep state is tracked separately, not part of the key
    assert canonical_key("Potato, raw") == canonical_key("Potato, boiled")
    assert canonical_key("Potato") == "potato"


def test_normalise_row_populates_both_fields():
    row = NormalisedRow(source_id="cofid", source_food_id="12-345",
                        name="Carrots, boiled in unsalted water")
    out = normalise_row(row)
    assert out.prep_state == "cooked"
    assert out.canonical_key == canonical_key("carrots")
