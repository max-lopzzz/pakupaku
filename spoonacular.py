"""
spoonacular.py
--------------
Async Spoonacular Food API client for PakuPaku.

Endpoints wrapped:
  - search_ingredients()        /food/ingredients/search
  - get_ingredient()            /food/ingredients/{id}/information
  - get_ingredient_unit_weight() fetches gram weight for a single unit
  - generate_meal_plan()        /mealplanner/generate
"""

import asyncio
import httpx
from typing import Dict, List, Optional, Set, Tuple, Union
from fastapi import HTTPException
from config import SPOONACULAR_API_KEY

SPOONACULAR_BASE = "https://api.spoonacular.com"

# Gram weights for standard units — no extra API call needed
STANDARD_UNIT_GRAMS: Dict[str, float] = {
    "g":    1.0,
    "kg":   1000.0,
    "oz":   28.3495,
    "lb":   453.592,
    "ml":   1.0,
    "l":    1000.0,
    "cup":  240.0,
    "tbsp": 15.0,
    "tsp":  5.0,
    "fl oz": 29.5735,
}

# Spoonacular nutrient name → internal field name
NUTRIENT_NAME_MAP: Dict[str, str] = {
    "calories":        "calories",
    "energy":          "calories",
    "protein":         "protein_g",
    "fat":             "fat_g",
    "carbohydrates":   "carbs_g",
    "carbs":           "carbs_g",
    "fiber":           "fiber_g",
    "sugar":           "sugar_g",
    "sugars":          "sugar_g",
    "sodium":          "sodium_mg",
    "calcium":         "calcium_mg",
    "iron":            "iron_mg",
    "vitamin c":       "vitamin_c_mg",
    "vitamin d":       "vitamin_d_mcg",
    "vitamin b12":     "vitamin_b12_mcg",
}


def _require_api_key() -> str:
    key = (SPOONACULAR_API_KEY or "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Spoonacular API key is not configured on the server.",
        )
    return key


async def _get(endpoint: str, params: dict) -> Union[Dict, List]:
    """Async GET helper with uniform error handling."""
    params["apiKey"] = _require_api_key()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{SPOONACULAR_BASE}/{endpoint}",
                params=params,
            )
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="Spoonacular API request timed out. Please try again.",
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status in (401, 403):
                raise HTTPException(
                    status_code=403,
                    detail="Invalid or missing Spoonacular API key.",
                )
            elif status == 402:
                raise HTTPException(
                    status_code=429,
                    detail="Spoonacular API daily quota exceeded.",
                )
            elif status == 404:
                raise HTTPException(
                    status_code=404,
                    detail="Food item not found in Spoonacular database.",
                )
            else:
                raise HTTPException(
                    status_code=status,
                    detail=f"Spoonacular API error: {e.response.text}",
                )


# ─────────────────────────────────────────────
#  INGREDIENT SEARCH
# ─────────────────────────────────────────────

async def search_ingredients(query: str, number: int = 25) -> dict:
    """
    Search for ingredients by keyword.

    Returns:
        {
          "results": [{"id": int, "name": str, "image": str, "possibleUnits": [...]}],
          "totalResults": int,
        }
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")
    return await _get("food/ingredients/search", {
        "query":           query.strip(),
        "number":          min(max(1, number), 100),
        "metaInformation": True,
    })


# ─────────────────────────────────────────────
#  INGREDIENT DETAIL
# ─────────────────────────────────────────────

async def get_ingredient(spoonacular_id: int) -> dict:
    """
    Fetch per-100g nutrition info for a single ingredient.

    Returns the raw Spoonacular response — pass through extract_nutrients()
    to get a clean flat dict.
    """
    if spoonacular_id <= 0:
        raise HTTPException(
            status_code=400,
            detail="spoonacular_id must be a positive integer.",
        )
    return await _get(
        f"food/ingredients/{spoonacular_id}/information",
        {"amount": 100, "unit": "g"},
    )


async def get_ingredient_unit_weight(
    spoonacular_id: int,
    unit: str,
) -> Optional[float]:
    """
    Returns the gram weight of exactly 1 unit of this ingredient.
    e.g. get_ingredient_unit_weight(9003, "piece") → 182.0

    Returns None if the API call fails or returns no weight.
    """
    try:
        data = await _get(
            f"food/ingredients/{spoonacular_id}/information",
            {"amount": 1, "unit": unit},
        )
        wps = (data.get("nutrition") or {}).get("weightPerServing", {})
        weight = wps.get("amount")
        return float(weight) if weight else None
    except HTTPException:
        return None


# ─────────────────────────────────────────────
#  NUTRIENT EXTRACTION
# ─────────────────────────────────────────────

async def extract_nutrients(ingredient: dict) -> dict:
    """
    Parse a Spoonacular ingredient information response into a clean flat dict.
    Nutrient values are per 100g (as requested from the API).

    Also fetches gram weights for non-standard possible units (piece, medium,
    large, small, slice, serving) via concurrent API calls.

    Returns:
        {
          "spoonacular_id": int,
          "description":    str,
          "calories":       float | None,
          "protein_g":      float | None,
          "fat_g":          float | None,
          "carbs_g":        float | None,
          "fiber_g":        float | None,
          "sugar_g":        float | None,
          "sodium_mg":      float | None,
          "calcium_mg":     float | None,
          "iron_mg":        float | None,
          "vitamin_c_mg":   float | None,
          "vitamin_d_mcg":  float | None,
          "vitamin_b12_mcg":float | None,
          "possible_units": list[str],
          "portions":       list[{"unit": str, "grams_per_unit": float}],
        }
    """
    result: dict = {
        "spoonacular_id":   ingredient.get("id"),
        "description":      ingredient.get("name"),
        "calories":         None,
        "protein_g":        None,
        "fat_g":            None,
        "carbs_g":          None,
        "fiber_g":          None,
        "sugar_g":          None,
        "sodium_mg":        None,
        "calcium_mg":       None,
        "iron_mg":          None,
        "vitamin_c_mg":     None,
        "vitamin_d_mcg":    None,
        "vitamin_b12_mcg":  None,
    }

    # Parse nutrients by name (Spoonacular uses names, not numeric IDs)
    nutrition = ingredient.get("nutrition") or {}
    for nutrient in nutrition.get("nutrients", []):
        name_key = (nutrient.get("name") or "").strip().lower()
        field = NUTRIENT_NAME_MAP.get(name_key)
        if field and nutrient.get("amount") is not None:
            result[field] = round(float(nutrient["amount"]), 4)

    possible_units: List[str] = ingredient.get("possibleUnits", [])
    result["possible_units"] = possible_units

    # Build portions map
    portions: List[Dict] = []
    seen: Set[str] = set()

    # Standard units — gram weight already known
    for unit in possible_units:
        key = unit.strip().lower()
        if key in STANDARD_UNIT_GRAMS and key not in seen:
            portions.append({"unit": key, "grams_per_unit": STANDARD_UNIT_GRAMS[key]})
            seen.add(key)

    # Non-standard units (piece, medium, large, small, slice, serving …)
    # Fetch their gram weights concurrently via the Spoonacular API.
    spoonacular_id = ingredient.get("id")
    non_standard = [
        u for u in possible_units
        if u.strip().lower() not in STANDARD_UNIT_GRAMS
        and u.strip().lower() not in seen
    ]

    if spoonacular_id and non_standard:
        weights = await asyncio.gather(
            *[get_ingredient_unit_weight(spoonacular_id, u) for u in non_standard],
            return_exceptions=True,
        )
        for unit, weight in zip(non_standard, weights):
            key = unit.strip().lower()
            if isinstance(weight, float) and weight > 0 and key not in seen:
                portions.append({"unit": key, "grams_per_unit": round(weight, 2)})
                seen.add(key)

    result["portions"] = portions
    return result


# ─────────────────────────────────────────────
#  MEAL PLAN GENERATION
# ─────────────────────────────────────────────

async def search_recipes_for_meal(
    meal_type: str,
    target_calories: int,
    number: int = 7,
    diet: Optional[str] = None,
    exclude: Optional[str] = None,
    offset: int = 0,
) -> List[dict]:
    """
    Search for recipes matching a meal type and calorie target.
    Uses ±30% tolerance around target_calories.

    meal_type: "breakfast", "main course", "snack", etc.

    Returns a list of dicts, each with:
      id, title, image, ready_in_minutes, servings, source_url,
      calories, protein_g, fat_g, carbs_g, fiber_g, ingredients
    """
    margin  = 0.30
    min_cal = max(50, round(target_calories * (1 - margin)))
    max_cal = round(target_calories * (1 + margin))

    params: dict = {
        "type":                 meal_type,
        "number":               number,
        "offset":               offset,
        "addRecipeNutrition":   True,
        "addRecipeInformation": True,
        "minCalories":          min_cal,
        "maxCalories":          max_cal,
        "sort":                 "random",
    }
    if diet:
        params["diet"] = diet.strip()
    if exclude:
        params["excludeIngredients"] = exclude.strip()

    data = await _get("recipes/complexSearch", params)
    results: List[dict] = []

    for r in data.get("results", []):
        nutrients: Dict[str, float] = {
            n["name"].lower(): float(n.get("amount", 0))
            for n in r.get("nutrition", {}).get("nutrients", [])
        }

        ingredients: List[dict] = []
        seen_names: set = set()
        for ing in r.get("extendedIngredients", []):
            name = (ing.get("nameClean") or ing.get("name") or "").strip()
            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            metric = ing.get("measures", {}).get("metric", {})
            amount = metric.get("amount") or ing.get("amount") or 0
            unit   = (metric.get("unitShort") or ing.get("unit") or "").strip()
            if amount:
                ingredients.append({
                    "name":   name,
                    "amount": round(float(amount), 1),
                    "unit":   unit,
                })

        results.append({
            "id":               r["id"],
            "title":            r.get("title", ""),
            "image":            r.get("image", ""),
            "ready_in_minutes": r.get("readyInMinutes"),
            "servings":         r.get("servings"),
            "source_url":       r.get("sourceUrl", ""),
            "calories":         round(nutrients.get("calories", 0)),
            "protein_g":        round(nutrients.get("protein", 0), 1),
            "fat_g":            round(nutrients.get("fat", 0), 1),
            "carbs_g":          round(nutrients.get("carbohydrates", 0), 1),
            "fiber_g":          round(nutrients.get("fiber", 0), 1),
            "ingredients":      ingredients,
        })

    return results


async def generate_weekly_plan(
    target_calories: int,
    diet: Optional[str] = None,
    exclude: Optional[str] = None,
) -> dict:
    """
    Generate a 7-day meal plan tailored to the given calorie target.

    Calorie distribution:
      Breakfast  25%  |  Lunch  30%  |  Dinner  35%  |  Snack  10%

    Makes 4 concurrent Spoonacular calls (one per meal type), then
    assembles 7 days and aggregates a shopping list.

    Returns:
        {
          "week": [
            {
              "day": str,
              "meals": {
                "breakfast": MealItem | None,
                "lunch":     MealItem | None,
                "dinner":    MealItem | None,
                "snack":     MealItem | None,
              },
              "total_calories": int,
            },
            ...  (7 items)
          ],
          "shopping_list": [
            {"name": str, "amount": float, "unit": str},
            ...
          ]
        }
    """
    breakfast_cals = round(target_calories * 0.25)
    lunch_cals     = round(target_calories * 0.30)
    dinner_cals    = round(target_calories * 0.35)
    snack_cals     = round(target_calories * 0.10)

    # Fetch recipe pools concurrently.
    # Lunch and dinner both use "main course" but with different offsets
    # so Spoonacular returns different results.
    breakfasts, lunches, dinners, snacks = await asyncio.gather(
        search_recipes_for_meal("breakfast",   breakfast_cals, 7, diet, exclude, offset=0),
        search_recipes_for_meal("main course", lunch_cals,     7, diet, exclude, offset=0),
        search_recipes_for_meal("main course", dinner_cals,    7, diet, exclude, offset=7),
        search_recipes_for_meal("snack",       snack_cals,     7, diet, exclude, offset=0),
    )

    def _pad(lst: List[dict], n: int = 7) -> List[Optional[dict]]:
        """Cycle through results to fill 7 days; return None slots if empty."""
        if not lst:
            return [None] * n
        return [lst[i % len(lst)] for i in range(n)]

    b_week = _pad(breakfasts)
    l_week = _pad(lunches)
    d_week = _pad(dinners)
    s_week = _pad(snacks)

    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

    week: List[dict] = []
    # Shopping list keyed by (name_lower, unit) to aggregate quantities
    shopping: Dict[tuple, dict] = {}

    for i, day in enumerate(DAYS):
        b, l, d, s = b_week[i], l_week[i], d_week[i], s_week[i]
        meals = {"breakfast": b, "lunch": l, "dinner": d, "snack": s}

        for meal in (b, l, d, s):
            if not meal:
                continue
            for ing in meal.get("ingredients", []):
                key = (ing["name"].lower(), ing["unit"])
                if key not in shopping:
                    shopping[key] = {
                        "name":   ing["name"],
                        "amount": ing["amount"],
                        "unit":   ing["unit"],
                    }
                else:
                    shopping[key]["amount"] = round(
                        shopping[key]["amount"] + ing["amount"], 1
                    )

        total_cals = sum(m.get("calories", 0) for m in (b, l, d, s) if m)
        week.append({
            "day":            day,
            "meals":          meals,
            "total_calories": round(total_cals),
        })

    shopping_list = sorted(shopping.values(), key=lambda x: x["name"].lower())
    return {"week": week, "shopping_list": shopping_list}


async def generate_meal_plan(
    target_calories: int,
    time_frame: str = "week",
    diet: Optional[str] = None,
    exclude: Optional[str] = None,
) -> dict:
    """
    Generate a meal plan using Spoonacular.

    Args:
        target_calories: Daily calorie target
        time_frame:      "day" or "week"
        diet:            Optional diet label (vegetarian, vegan, gluten free,
                         ketogenic, paleo, etc.)
        exclude:         Comma-separated ingredients to avoid (e.g. "shellfish,olives")

    Returns (day):
        {
          "meals": [{"id", "title", "readyInMinutes", "servings", "sourceUrl", "imageType"}, ...],
          "nutrients": {"calories", "protein", "fat", "carbohydrates"}
        }

    Returns (week):
        {
          "week": {
            "monday": {"meals": [...], "nutrients": {...}},
            ...
          }
        }
    """
    if time_frame not in ("day", "week"):
        raise HTTPException(
            status_code=400,
            detail="time_frame must be 'day' or 'week'.",
        )
    if target_calories < 500 or target_calories > 10000:
        raise HTTPException(
            status_code=400,
            detail="target_calories must be between 500 and 10000.",
        )

    params: dict = {
        "timeFrame":      time_frame,
        "targetCalories": target_calories,
    }
    if diet:
        params["diet"] = diet.strip()
    if exclude:
        params["exclude"] = exclude.strip()

    return await _get("mealplanner/generate", params)
