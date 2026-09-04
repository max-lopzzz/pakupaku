import food_index
from recipe_import import ParsedIngredient, match_ingredient
from seed_foods import seed_foods
from tests.fixtures.make_foods_mini import build as build_mini


async def _load(db_session, tmp_path):
    art = tmp_path / "foods.sqlite"
    build_mini(str(art))
    await seed_foods(db_session, str(art))
    await db_session.commit()
    await food_index.load(db_session)


async def test_match_ingredient_hits_the_generic_index(db_session, tmp_path):
    await _load(db_session, tmp_path)
    p = ParsedIngredient(raw_line="2 cups broccoli", quantity=2.0, unit="cup", food_name="broccoli")
    out = await match_ingredient(p)
    assert out.best_match.food_id == "gen:00001"
    assert out.best_match.calories_per_100g == 34.0
    assert out.best_match.portions_map == {"cup chopped": 91.0}


async def test_match_ingredient_no_hit_returns_unmatched(db_session, tmp_path):
    await _load(db_session, tmp_path)
    p = ParsedIngredient(raw_line="1 xyzzy", quantity=1.0, unit="", food_name="xyzzy nonsense plugboard")
    out = await match_ingredient(p)
    assert out.best_match is None
