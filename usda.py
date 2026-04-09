"""
usda.py
-------
Async USDA FoodData Central API client for PakuPaku.

Endpoints wrapped:
  - search_foods()      /foods/search
  - get_food()          /food/{fdc_id}
  - get_foods_bulk()    /foods  (batch fetch up to 20 IDs at once)
  - list_foods()        /foods/list (paginated browse)

All functions return parsed JSON as dicts/lists.
HTTPStatusError is re-raised as FastAPI HTTPException by the routes.
"""

import httpx
from typing import Optional, List, Union
from fastapi import HTTPException
from config import USDA_API_KEY

USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1"

# Data types available in FoodData Central.
# Foundation and SR Legacy are the most nutrient-complete.
# Branded covers packaged foods with barcodes.
VALID_DATA_TYPES = {
    "Foundation",       # USDA-curated, most complete nutrient data
    "SR Legacy",        # older USDA standard reference, very broad
    "Branded",          # packaged/commercial foods
    "Survey (FNDDS)",   # foods as eaten, used in dietary surveys
}


# ─────────────────────────────────────────────
#  INTERNAL HTTP HELPER
# ─────────────────────────────────────────────

async def _get(endpoint: str, params: dict) -> Union[dict, list]:
    """
    Internal helper. Makes an async GET request to the USDA API,
    injects the API key, and handles errors uniformly.
    """
    params["api_key"] = USDA_API_KEY

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{USDA_BASE_URL}/{endpoint}",
                params=params,
            )
            response.raise_for_status()
            return response.json()

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="USDA API request timed out. Please try again.",
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 403:
                raise HTTPException(
                    status_code=403,
                    detail="Invalid or missing USDA API key.",
                )
            elif status == 404:
                raise HTTPException(
                    status_code=404,
                    detail="Food item not found in USDA database.",
                )
            elif status == 429:
                raise HTTPException(
                    status_code=429,
                    detail="USDA API rate limit hit. Please slow down requests.",
                )
            else:
                raise HTTPException(
                    status_code=status,
                    detail=f"USDA API error: {e.response.text}",
                )


async def _post(endpoint: str, body: dict) -> Union[dict, list]:
    """
    Internal helper for POST requests (used by bulk fetch).
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.post(
                f"{USDA_BASE_URL}/{endpoint}",
                params={"api_key": USDA_API_KEY},
                json=body,
            )
            response.raise_for_status()
            return response.json()

        except httpx.TimeoutException:
            raise HTTPException(
                status_code=504,
                detail="USDA API request timed out. Please try again.",
            )
        except httpx.HTTPStatusError as e:
            status = e.response.status_code
            if status == 403:
                raise HTTPException(
                    status_code=403,
                    detail="Invalid or missing USDA API key.",
                )
            elif status == 429:
                raise HTTPException(
                    status_code=429,
                    detail="USDA API rate limit hit. Please slow down requests.",
                )
            else:
                raise HTTPException(
                    status_code=status,
                    detail=f"USDA API error: {e.response.text}",
                )


# ─────────────────────────────────────────────
#  FOOD SEARCH
# ─────────────────────────────────────────────

async def search_foods(
    query: str,
    page_size: int = 10,
    page_number: int = 1,
    data_types: Optional[List[str]] = None,
    brand_owner: Optional[str] = None,
) -> dict:
    """
    Search the USDA database by keyword.

    Args:
        query:        Search string, e.g. "brown rice" or "cheddar cheese"
        page_size:    Results per page (max 200, default 10)
        page_number:  Page to fetch (1-indexed, default 1)
        data_types:   Filter by source type — any of VALID_DATA_TYPES.
                      None returns all types.
        brand_owner:  Filter branded foods by brand, e.g. "General Mills"

    Returns:
        {
          "totalHits": int,
          "currentPage": int,
          "totalPages": int,
          "foods": [
            {
              "fdcId": int,
              "description": str,
              "dataType": str,
              "brandOwner": str | None,
              "foodNutrients": [
                {
                  "nutrientId": int,
                  "nutrientName": str,
                  "unitName": str,
                  "value": float
                },
                ...
              ]
            },
            ...
          ]
        }
    """
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    page_size = max(1, min(page_size, 200))

    params: dict = {
        "query":      query.strip(),
        "pageSize":   page_size,
        "pageNumber": page_number,
    }

    if data_types:
        invalid = set(data_types) - VALID_DATA_TYPES
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid data type(s): {invalid}. "
                       f"Valid options: {VALID_DATA_TYPES}",
            )
        # USDA expects repeated param: dataType=Foundation&dataType=Branded
        params["dataType"] = data_types

    if brand_owner:
        params["brandOwner"] = brand_owner.strip()

    return await _get("foods/search", params)


# ─────────────────────────────────────────────
#  SINGLE FOOD DETAIL
# ─────────────────────────────────────────────

async def get_food(
    fdc_id: int,
    format: str = "abridged",
    nutrients: Optional[List[int]] = None,
) -> dict:
    """
    Fetch full details for a single food item by its FDC ID.

    Args:
        fdc_id:    USDA FoodData Central ID (from search results)
        format:    "abridged" (default) returns key nutrients only.
                   "full" returns all available nutrient data.
        nutrients: Optional list of specific nutrient IDs to return.
                   Overrides format. Common IDs:
                     1003 = Protein
                     1004 = Total fat
                     1005 = Carbohydrates
                     1008 = Calories (Energy)
                     1079 = Fiber
                     2000 = Total sugars
                     1087 = Calcium
                     1089 = Iron
                     1091 = Phosphorus
                     1093 = Sodium
                     1095 = Zinc
                     1104 = Vitamin A
                     1162 = Vitamin C
                     1165 = Thiamin (B1)
                     1166 = Riboflavin (B2)
                     1167 = Niacin (B3)
                     1175 = Vitamin B6
                     1177 = Folate
                     1178 = Vitamin B12
                     1110 = Vitamin D
                     1109 = Vitamin E
                     1185 = Vitamin K

    Returns:
        Full food object with description, nutrients, portions, and metadata.
    """
    if fdc_id <= 0:
        raise HTTPException(status_code=400, detail="fdc_id must be a positive integer.")

    params: dict = {"format": format}

    if nutrients:
        params["nutrients"] = nutrients

    return await _get(f"food/{fdc_id}", params)


# ─────────────────────────────────────────────
#  BULK FOOD FETCH
# ─────────────────────────────────────────────

async def get_foods_bulk(
    fdc_ids: List[int],
    format: str = "abridged",
    nutrients: Optional[List[int]] = None,
) -> List[dict]:
    """
    Fetch multiple food items in a single request (max 20 IDs).
    Useful for loading a full meal log or recipe in one call.

    Args:
        fdc_ids:   List of FDC IDs (max 20)
        format:    "abridged" or "full" (see get_food())
        nutrients: Optional list of nutrient IDs to filter (see get_food())

    Returns:
        List of food objects, same structure as get_food().
    """
    if not fdc_ids:
        raise HTTPException(status_code=400, detail="fdc_ids list cannot be empty.")
    if len(fdc_ids) > 20:
        raise HTTPException(
            status_code=400,
            detail=f"Bulk fetch supports a maximum of 20 IDs. Got {len(fdc_ids)}.",
        )

    body: dict = {
        "fdcIds":  fdc_ids,
        "format":  format,
    }
    if nutrients:
        body["nutrients"] = nutrients

    return await _post("foods", body)


# ─────────────────────────────────────────────
#  PAGINATED FOOD LIST (browse by category)
# ─────────────────────────────────────────────

async def list_foods(
    data_type: str = "Foundation",
    page_size: int = 25,
    page_number: int = 1,
    sort_by: str = "description",
    sort_order: str = "asc",
) -> dict:
    """
    Browse foods by data type without a search query.
    Useful for category browsing or populating dropdowns.

    Args:
        data_type:    One of VALID_DATA_TYPES (default "Foundation")
        page_size:    Results per page (max 200, default 25)
        page_number:  Page to fetch (default 1)
        sort_by:      Field to sort by — "description", "dataType",
                      "publishedDate", "fdcId" (default "description")
        sort_order:   "asc" or "desc" (default "asc")

    Returns:
        Same structure as search_foods() but without totalHits.
    """
    if data_type not in VALID_DATA_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid data type '{data_type}'. "
                   f"Valid options: {VALID_DATA_TYPES}",
        )

    valid_sort_fields = {"description", "dataType", "publishedDate", "fdcId"}
    if sort_by not in valid_sort_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort field '{sort_by}'. "
                   f"Valid options: {valid_sort_fields}",
        )

    if sort_order not in ("asc", "desc"):
        raise HTTPException(
            status_code=400,
            detail="sort_order must be 'asc' or 'desc'.",
        )

    page_size = max(1, min(page_size, 200))

    params = {
        "dataType":   data_type,
        "pageSize":   page_size,
        "pageNumber": page_number,
        "sortBy":     sort_by,
        "sortOrder":  sort_order,
    }

    return await _get("foods/list", params)


# ─────────────────────────────────────────────
#  NUTRIENT EXTRACTION HELPER
# ─────────────────────────────────────────────

def extract_nutrients(food: dict) -> dict:
    """
    Pull the most relevant nutrients out of a raw USDA food object
    into a clean, flat dict. All values are per 100g unless the food
    object specifies otherwise.

    Handles both "abridged" and "full" format responses.
    Missing nutrients default to None.

    Returns:
        {
          "fdc_id":       int,
          "description":  str,
          "data_type":    str,
          "brand":        str | None,
          "calories":     float | None,   (kcal)
          "protein_g":    float | None,
          "fat_g":        float | None,
          "carbs_g":      float | None,
          "fiber_g":      float | None,
          "sugar_g":      float | None,
          "sodium_mg":    float | None,
          "calcium_mg":   float | None,
          "iron_mg":      float | None,
          "vitamin_c_mg": float | None,
          "vitamin_d_mcg":float | None,
          "vitamin_b12_mcg": float | None,
        }
    """
    # nutrient ID -> output key + unit label
    NUTRIENT_MAP = {
        1008: ("calories",        "kcal"),
        1003: ("protein_g",       "g"),
        1004: ("fat_g",           "g"),
        1005: ("carbs_g",         "g"),
        1079: ("fiber_g",         "g"),
        2000: ("sugar_g",         "g"),
        1093: ("sodium_mg",       "mg"),
        1087: ("calcium_mg",      "mg"),
        1089: ("iron_mg",         "mg"),
        1162: ("vitamin_c_mg",    "mg"),
        1110: ("vitamin_d_mcg",   "mcg"),
        1178: ("vitamin_b12_mcg", "mcg"),
    }

    result: dict = {
        "fdc_id":      food.get("fdcId"),
        "description": food.get("description"),
        "data_type":   food.get("dataType"),
        "brand":       food.get("brandOwner") or food.get("brandName"),
    }

    # initialise all nutrient fields to None
    for key, _ in NUTRIENT_MAP.values():
        result[key] = None

    # the nutrients list can live under "foodNutrients" in both formats
    raw_nutrients = food.get("foodNutrients", [])

    for item in raw_nutrients:
        # abridged format uses flat keys; full format nests under "nutrient"
        nutrient_id = (
            item.get("nutrientId")
            or (item.get("nutrient") or {}).get("id")
        )
        value = (
            item.get("value")
            or item.get("amount")
        )

        if nutrient_id in NUTRIENT_MAP:
            key, _ = NUTRIENT_MAP[nutrient_id]
            result[key] = value

    return result