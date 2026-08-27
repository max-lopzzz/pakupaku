import asyncio

from fastapi import HTTPException

import recipe_import
from recipe_import import ParsedIngredient, match_ingredient, rank_candidates

FLOUR_FOUNDATION = {
    "fdcId": 1,
    "description": "Flour, wheat, all-purpose",
    "dataType": "Foundation",
    "brandOwner": None,
    "foodNutrients": [
        {"nutrientId": 1008, "value": 364.0},
        {"nutrientId": 1003, "value": 10.0},
        {"nutrientId": 1004, "value": 1.0},
        {"nutrientId": 1005, "value": 76.0},
        {"nutrientId": 1079, "value": 2.7},
    ],
}
FLOUR_BRANDED = {
    "fdcId": 2,
    "description": "Flour Blend Product",
    "dataType": "Branded",
    "brandOwner": "Acme",
    "foodNutrients": [],
}


def test_rank_candidates_prefers_foundation_and_sr_legacy():
    ranked = rank_candidates([FLOUR_BRANDED, FLOUR_FOUNDATION])
    assert [f["fdcId"] for f in ranked] == [1, 2]


def test_rank_candidates_empty_list():
    assert rank_candidates([]) == []


def test_match_ingredient_returns_best_match_with_portions(monkeypatch):
    async def fake_search_foods(query, page_size=5):
        assert query == "flour"
        return {"foods": [FLOUR_FOUNDATION, FLOUR_BRANDED]}

    async def fake_get_food(fdc_id, format="abridged"):
        assert fdc_id == 1
        return {
            "fdcId": 1,
            "description": "Flour, wheat, all-purpose",
            "dataType": "Foundation",
            "foodNutrients": FLOUR_FOUNDATION["foodNutrients"],
            "foodPortions": [
                {
                    "gramWeight": 125.0,
                    "amount": 1,
                    "measureUnit": {"id": 1006, "name": "cup"},
                }
            ],
        }

    monkeypatch.setattr(recipe_import, "search_foods", fake_search_foods)
    monkeypatch.setattr(recipe_import, "get_food", fake_get_food)

    parsed = ParsedIngredient(
        raw_line="2 cups flour", quantity=2.0, unit="cup", food_name="flour"
    )
    result = asyncio.run(match_ingredient(parsed))

    assert result.raw_line == "2 cups flour"
    assert result.best_match is not None
    assert result.best_match.fdc_id == 1
    assert result.best_match.description == "Flour, wheat, all-purpose"
    assert result.best_match.calories_per_100g == 364.0
    assert result.best_match.portions_map == {"cup": 125.0}
    assert [c.fdc_id for c in result.alternates] == [2]


def test_match_ingredient_no_results_leaves_best_match_none(monkeypatch):
    async def fake_search_foods(query, page_size=5):
        return {"foods": []}

    monkeypatch.setattr(recipe_import, "search_foods", fake_search_foods)

    parsed = ParsedIngredient(
        raw_line="1 unicorn tear", quantity=1.0, unit="g", food_name="unicorn tear"
    )
    result = asyncio.run(match_ingredient(parsed))

    assert result.best_match is None
    assert result.alternates == []


def test_match_ingredient_search_error_leaves_best_match_none(monkeypatch):
    async def fake_search_foods(query, page_size=5):
        raise HTTPException(status_code=503, detail="USDA down")

    monkeypatch.setattr(recipe_import, "search_foods", fake_search_foods)

    parsed = ParsedIngredient(
        raw_line="1 cup flour", quantity=1.0, unit="cup", food_name="flour"
    )
    result = asyncio.run(match_ingredient(parsed))

    assert result.best_match is None
    assert result.alternates == []
