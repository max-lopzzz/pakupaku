from scripts.build_food_db.model import NormalisedRow
from scripts.build_food_db.match import MergeGroup
from scripts.build_food_db.aggregate import aggregate_group, sanity_ok


def _r(src, **nut):
    return NormalisedRow(source_id=src, source_food_id=src, name="x",
                         canonical_key="x", prep_state="raw", **nut)


def test_median_when_three_sources_mean_when_two():
    g = MergeGroup("x__raw", "X", [
        _r("a", calories_per_100g=10.0, protein_per_100g=1.0),
        _r("b", calories_per_100g=20.0, protein_per_100g=3.0),
        _r("c", calories_per_100g=90.0),
    ])
    out = aggregate_group(g)
    assert out.calories_per_100g == 20.0      # median(10,20,90)
    assert out.protein_per_100g == 2.0        # mean(1,3)
    assert out.source_count == 3
    assert out.source_ids == ["a", "b", "c"]


def test_impossible_calorie_value_is_dropped_before_aggregation():
    g = MergeGroup("x__raw", "X", [
        _r("a", calories_per_100g=0.0),
        _r("b", calories_per_100g=10000.0),
        _r("c", calories_per_100g=2.0),
    ])
    out = aggregate_group(g)
    assert out.calories_per_100g == 1.0       # median(0, 2) after dropping 10000

def test_group_with_no_nutrient_reaching_two_sources_returns_none():
    g = MergeGroup("x__raw", "X", [_r("a", calories_per_100g=5.0)])
    assert aggregate_group(g) is None


def test_two_rows_from_the_same_source_are_one_source_and_drop_the_food():
    """A fuzzy merge that pulled two rows out of the same national table is
    still a single source — the spec requires source_count >= 2."""
    g = MergeGroup("x__raw", "X", [
        _r("cofid", calories_per_100g=33.0),
        _r("cofid", calories_per_100g=35.0),
    ])
    assert aggregate_group(g) is None


def test_same_source_rows_are_averaged_into_one_value_before_cross_source_mean():
    g = MergeGroup("x__raw", "X", [
        _r("cofid", calories_per_100g=33.0),
        _r("cofid", calories_per_100g=35.0),   # cofid contributes mean(33,35)=34
        _r("usda", calories_per_100g=40.0),
    ])
    out = aggregate_group(g)
    assert out.calories_per_100g == 37.0       # mean(34, 40), not median(33,35,40)
    assert out.source_ids == ["cofid", "usda"]
    assert out.source_count == 2


def test_source_count_counts_only_sources_that_fed_an_emitted_nutrient():
    g = MergeGroup("x__raw", "X", [
        _r("a", calories_per_100g=10.0),
        _r("b", calories_per_100g=12.0),
        _r("c", iron_mg_per_100g=1.0),         # only source with iron -> dropped
    ])
    out = aggregate_group(g)
    assert out.calories_per_100g == 11.0
    assert out.iron_mg_per_100g is None
    assert out.source_ids == ["a", "b"]
    assert out.source_count == 2


def test_sanity_rules():
    assert sanity_ok("calories_per_100g", 500.0, {}) is True
    assert sanity_ok("calories_per_100g", 901.0, {}) is False
    assert sanity_ok("protein_per_100g", -1.0, {}) is False
    assert sanity_ok("carbs_per_100g", 60.0,
                     {"protein_per_100g": 30.0, "fat_per_100g": 20.0,
                      "carbs_per_100g": 60.0, "fiber_per_100g": 0.0}) is False
