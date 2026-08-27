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


def test_match_ingredient_fallback_portions_from_sr_legacy(monkeypatch):
    """Test that _fetch_portions_map falls back to SR Legacy foods
    when the primary food has no portions."""

    # Primary food: Foundation type, no portions
    PRIMARY_FOOD = {
        "fdcId": 100,
        "description": "Flour, wheat, all-purpose",
        "dataType": "Foundation",
        "brandOwner": None,
        "foodNutrients": [
            {"nutrientId": 1008, "value": 364.0},
            {"nutrientId": 1003, "value": 10.0},
        ],
    }

    # Fallback food: SR Legacy, has portions
    SR_LEGACY_FOOD = {
        "fdcId": 200,
        "description": "Flour, wheat, all-purpose, enriched",
        "dataType": "SR Legacy",
        "brandOwner": None,
        "foodNutrients": [
            {"nutrientId": 1008, "value": 364.0},
            {"nutrientId": 1003, "value": 10.0},
        ],
    }

    async def fake_search_foods(query, page_size=5):
        # Both calls (from match_ingredient and from _fetch_portions_map fallback)
        # return the same set of candidates
        return {
            "foods": [PRIMARY_FOOD, SR_LEGACY_FOOD]
        }

    async def fake_get_food(fdc_id, format="abridged"):
        if fdc_id == 100:
            # Primary food: no portions
            return {
                "fdcId": 100,
                "description": "Flour, wheat, all-purpose",
                "dataType": "Foundation",
                "foodNutrients": PRIMARY_FOOD["foodNutrients"],
                "foodPortions": [],  # Empty!
            }
        elif fdc_id == 200:
            # Fallback food: has portions
            return {
                "fdcId": 200,
                "description": "Flour, wheat, all-purpose, enriched",
                "dataType": "SR Legacy",
                "foodNutrients": SR_LEGACY_FOOD["foodNutrients"],
                "foodPortions": [
                    {
                        "gramWeight": 125.0,
                        "amount": 1,
                        "measureUnit": {"id": 1006, "name": "cup"},
                    },
                    {
                        "gramWeight": 8.0,
                        "amount": 1,
                        "measureUnit": {"id": 1014, "name": "tbsp"},
                    }
                ],
            }

    monkeypatch.setattr(recipe_import, "search_foods", fake_search_foods)
    monkeypatch.setattr(recipe_import, "get_food", fake_get_food)

    parsed = ParsedIngredient(
        raw_line="2 cups flour", quantity=2.0, unit="cup", food_name="flour"
    )
    result = asyncio.run(match_ingredient(parsed))

    # Primary match should be the Foundation food (best ranked)
    assert result.best_match is not None
    assert result.best_match.fdc_id == 100
    # But portions should come from the SR Legacy fallback
    assert result.best_match.portions_map == {"cup": 125.0, "tbsp": 8.0}


def test_fetch_portions_map_fallback_caps_get_food_calls_at_three(monkeypatch):
    """The fallback tier in _fetch_portions_map used to loop over every
    reliable-data-type candidate in the re-search results (up to 20),
    issuing a get_food call for each one. That's an unbounded USDA
    fan-out for a single ingredient. It should stop after checking 3
    candidates, even when none of them have usable portions."""

    PRIMARY_FOOD = {
        "fdcId": 1,
        "description": "Flour, wheat, all-purpose",
        "dataType": "Foundation",
        "brandOwner": None,
        "foodNutrients": [{"nutrientId": 1008, "value": 364.0}],
    }

    # 5 SR Legacy candidates, all with empty foodPortions.
    CANDIDATES = [
        {
            "fdcId": 100 + i,
            "description": f"Flour variant {i}",
            "dataType": "SR Legacy",
            "brandOwner": None,
            "foodNutrients": [],
        }
        for i in range(5)
    ]

    async def fake_search_foods(query, page_size=5):
        if page_size == 5:
            # match_ingredient's primary search
            return {"foods": [PRIMARY_FOOD]}
        # _fetch_portions_map's fallback re-search (page_size=20)
        return {"foods": CANDIDATES}

    get_food_calls = {"count": 0}

    async def fake_get_food(fdc_id, format="abridged"):
        if fdc_id == 1:
            # Primary food detail: no portions, forces the fallback tier.
            return {
                "fdcId": 1,
                "description": "Flour, wheat, all-purpose",
                "dataType": "Foundation",
                "foodNutrients": PRIMARY_FOOD["foodNutrients"],
                "foodPortions": [],
            }
        get_food_calls["count"] += 1
        return {
            "fdcId": fdc_id,
            "description": "Flour variant",
            "dataType": "SR Legacy",
            "foodNutrients": [],
            "foodPortions": [],  # Empty — no candidate ever satisfies the fallback.
        }

    monkeypatch.setattr(recipe_import, "search_foods", fake_search_foods)
    monkeypatch.setattr(recipe_import, "get_food", fake_get_food)

    parsed = ParsedIngredient(
        raw_line="2 cups flour", quantity=2.0, unit="cup", food_name="flour"
    )
    result = asyncio.run(match_ingredient(parsed))

    assert result.best_match is not None
    assert result.best_match.portions_map == {}
    # Not counting the initial primary-food get_food call (fdc_id == 1).
    assert get_food_calls["count"] <= 3
