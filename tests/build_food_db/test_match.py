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
