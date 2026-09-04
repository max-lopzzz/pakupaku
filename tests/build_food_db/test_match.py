# tests/build_food_db/test_match.py
import pytest
from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.normalise import normalise_row
from scripts.build_food_db.match import (
    group_foods, apply_decisions, load_decisions, write_conflicts,
)


def _row(src, name, **nut):
    return normalise_row(NormalisedRow(source_id=src, source_food_id=src + "1", name=name, **nut))


def test_identical_keys_group_and_auto_accept_when_nutrients_agree():
    rows = [
        _row("usda", "Broccoli, raw", calories_per_100g=34.0),
        _row("cofid", "raw broccoli", calories_per_100g=33.0),
    ]
    groups = group_foods(rows)
    assert len(groups) == 1
    assert groups[0].auto_accepted is True
    assert len(groups[0].rows) == 2


def test_disagreeing_nutrients_block_auto_accept():
    rows = [
        _row("usda", "Broccoli, raw", calories_per_100g=34.0),
        _row("ciqual", "raw broccoli", calories_per_100g=250.0),
    ]
    groups = group_foods(rows)
    assert groups[0].auto_accepted is False


def test_micronutrient_spread_is_tolerated_more_than_a_macro_spread():
    """Vitamin C 6 vs 10 mg is ordinary cross-country variation (spread 4 on a
    median of 8 = 0.5, inside MICRO_TOLERANCE) — the same relative spread on a
    macro is a conflict."""
    micro = group_foods([
        _row("usda", "Broccoli, raw", vitamin_c_mg_per_100g=6.0),
        _row("ciqual", "raw broccoli", vitamin_c_mg_per_100g=10.0),
    ])
    assert micro[0].auto_accepted is True

    macro = group_foods([
        _row("usda", "Broccoli, raw", protein_per_100g=6.0),
        _row("ciqual", "raw broccoli", protein_per_100g=10.0),
    ])
    assert macro[0].auto_accepted is False


def test_a_wide_micronutrient_spread_still_conflicts():
    rows = [
        _row("usda", "Broccoli, raw", vitamin_c_mg_per_100g=6.0),
        _row("ciqual", "raw broccoli", vitamin_c_mg_per_100g=20.0),
    ]
    assert group_foods(rows)[0].auto_accepted is False


def test_spread_is_measured_against_the_median_not_the_minimum():
    """10/13/13 kcal: spread 3 is 3/10 = 0.30 against the minimum (would
    conflict) but 3/13 = 0.23 against the median (inside MACRO_TOLERANCE)."""
    rows = [
        _row("usda", "Broccoli, raw", calories_per_100g=10.0),
        _row("cofid", "raw broccoli", calories_per_100g=13.0),
        _row("ciqual", "broccoli raw", calories_per_100g=13.0),
    ]
    assert group_foods(rows)[0].auto_accepted is True


def test_zero_median_with_a_real_spread_still_conflicts():
    rows = [
        _row("usda", "Broccoli, raw", calories_per_100g=0.0),
        _row("cofid", "raw broccoli", calories_per_100g=0.0),
        _row("ciqual", "broccoli raw", calories_per_100g=30.0),
    ]
    assert group_foods(rows)[0].auto_accepted is False


def test_different_prep_state_never_groups():
    rows = [
        _row("usda", "Potato, raw", calories_per_100g=77.0),
        _row("cofid", "Potato, boiled", calories_per_100g=87.0),
    ]
    groups = group_foods(rows)
    assert len(groups) == 2


def test_apply_decisions_requires_a_decision_for_every_conflict(tmp_path):
    rows = [
        _row("usda", "Broccoli, raw", calories_per_100g=34.0),
        _row("ciqual", "raw broccoli", calories_per_100g=250.0),
    ]
    groups = group_foods(rows)
    with pytest.raises(ValueError):
        apply_decisions(groups, {})

    p = tmp_path / "d.csv"
    p.write_text("group_id,decision,canonical_name,note\n%s,separate,,\n" % groups[0].group_id)
    resolved = apply_decisions(groups, load_decisions(str(p)))
    assert len(resolved) == 2
