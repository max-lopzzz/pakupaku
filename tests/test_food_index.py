"""
tests/test_food_index.py
------------------------
Exercises the in-memory exact/alias/fuzzy search+match index over the
``foods`` table. Each test re-``load``s the index from a fresh 2-row
mini artifact, so ``food_index.load`` must clear any prior state first.
"""

import food_index
from seed_foods import seed_foods
from tests.fixtures.make_foods_mini import build as build_mini


async def _load(db_session, tmp_path):
    art = tmp_path / "foods.sqlite"
    build_mini(str(art))
    await seed_foods(db_session, str(art))
    await db_session.commit()
    await food_index.load(db_session)


async def test_exact_and_alias_match(db_session, tmp_path):
    await _load(db_session, tmp_path)
    assert food_index.best_match("broccoli").id == "gen:00001"
    assert food_index.best_match("raw broccoli").id == "gen:00001"


async def test_fuzzy_match_within_floor(db_session, tmp_path):
    await _load(db_session, tmp_path)
    assert food_index.best_match("brocolli").id == "gen:00001"


async def test_junk_query_returns_none(db_session, tmp_path):
    await _load(db_session, tmp_path)
    assert food_index.best_match("xyzzy nonsense plugboard") is None


async def test_water_resolves_to_the_generic_zero_kcal_entry(db_session, tmp_path):
    await _load(db_session, tmp_path)
    m = food_index.best_match("water")
    assert m.id == "gen:00002"
    assert m.calories_per_100g == 0.0


async def test_water_prefers_plain_tap_water_over_coconut_water(db_session, tmp_path):
    # "coconut water" is a token-superset of the query, so token_set_ratio
    # ties it at 100 with "tap water"; the re-rank must not let it win —
    # "tap water" has fewer extra tokens beyond the query ("tap" vs "coconut"
    # are both single extra tokens, so it comes down to token_sort_ratio).
    await _load(db_session, tmp_path)
    assert food_index.best_match("water").id == "gen:00002"


async def test_water_does_not_match_an_unrelated_long_product_name(db_session, tmp_path):
    # "Coconut milk (liquid from grated meat and water), canned" head-nouns
    # to "water" and is a token-superset of the query, so token_set_ratio
    # ties it at 100 too — but it drags in 8 extra tokens, so the
    # extra-token cap must demote it out of contention entirely.
    await _load(db_session, tmp_path)
    assert food_index.best_match("water").id == "gen:00002"


async def test_butter_beans_does_not_collapse_to_butter(db_session, tmp_path):
    # token_set_ratio("beans butter", "butter") == 100 because "butter" is a
    # subset of the query — but it is MISSING the "beans" token, so the fuzzy
    # re-rank must rank "butter beans, canned" (covers both tokens) first.
    await _load(db_session, tmp_path)
    m = food_index.best_match("butter beans")
    assert m.id == "gen:00005"
    assert m.description == "Butter beans, canned"


async def test_search_result_shape(db_session, tmp_path):
    await _load(db_session, tmp_path)
    r = food_index.search("broccoli", 5)[0].as_search_result()
    assert r["food_id"] == "gen:00001"
    assert r["description"] == "Broccoli, raw"
    assert r["calories_per_100g"] == 34.0
    assert r["portions"] == [{"unit": "cup chopped", "grams": 91.0}]
    assert "dataType" not in r and "brandOwner" not in r
