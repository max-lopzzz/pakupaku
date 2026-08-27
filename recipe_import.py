"""
recipe_import.py
-----------------
Turns a recipe blog URL into a draft Recipe: fetches the page, extracts
ingredients (from schema.org/JSON-LD markup, falling back to an LLM),
parses each ingredient line into quantity/unit/food name, and matches
each one against USDA FoodData Central. Returns a RecipeImportDraft —
nothing is saved to the database here.
"""

import asyncio
import json
import re
from dataclasses import dataclass
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL


# ─────────────────────────────────────────────
#  STRUCTURED EXTRACTION (schema.org / JSON-LD)
# ─────────────────────────────────────────────

@dataclass
class RawRecipe:
    name: str
    servings: float
    image_url: Optional[str]
    ingredient_lines: List[str]


def _parse_servings(raw_yield) -> float:
    """recipeYield can be an int, a string like "4" or "4 servings", or a
    list containing either. Pull the first number out of it; default 1."""
    if isinstance(raw_yield, list):
        raw_yield = raw_yield[0] if raw_yield else None
    if raw_yield is None:
        return 1.0
    match = re.search(r"\d+(\.\d+)?", str(raw_yield))
    return float(match.group()) if match else 1.0


def _parse_image(raw_image) -> Optional[str]:
    """image can be a URL string, an ImageObject dict with a "url" key, or
    a list of either."""
    if isinstance(raw_image, list):
        raw_image = raw_image[0] if raw_image else None
    if isinstance(raw_image, dict):
        return raw_image.get("url")
    if isinstance(raw_image, str):
        return raw_image or None
    return None


def _find_recipe_node(data) -> Optional[dict]:
    """Recipe JSON-LD can be a single object, a list of objects, or
    wrapped in a top-level "@graph" list alongside unrelated node types
    (a common SEO-plugin pattern). Return the first node whose @type
    includes "Recipe", or None."""
    if isinstance(data, dict) and "@graph" in data:
        return _find_recipe_node(data["@graph"])
    if isinstance(data, list):
        for node in data:
            found = _find_recipe_node(node)
            if found:
                return found
        return None
    if isinstance(data, dict):
        node_type = data.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "Recipe" in types:
            return data
    return None


def extract_structured_recipe(html: str) -> Optional[RawRecipe]:
    """Look for a schema.org Recipe object in the page's JSON-LD script
    tags. Returns None if none is found or it's missing a name/ingredients
    (the caller falls back to the LLM extractor in that case)."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue

        node = _find_recipe_node(data)
        if not node:
            continue

        name = node.get("name")
        ingredients = node.get("recipeIngredient") or node.get("ingredients")
        if not name or not ingredients:
            continue

        return RawRecipe(
            name=str(name).strip(),
            servings=_parse_servings(node.get("recipeYield")),
            image_url=_parse_image(node.get("image")),
            ingredient_lines=[
                str(i).strip() for i in ingredients if str(i).strip()
            ],
        )
    return None


# ─────────────────────────────────────────────
#  INGREDIENT LINE PARSING
# ─────────────────────────────────────────────

# Standard units RecipeBuilder.tsx's UNIT_TO_G already knows how to
# convert to grams. Anything else parses through as a "natural unit"
# (e.g. "clove", "large", "slice") the same way RecipeBuilder already
# handles USDA food-specific portion units.
_UNIT_ALIASES = {
    "g": "g", "gram": "g", "grams": "g",
    "ml": "ml", "milliliter": "ml", "milliliters": "ml",
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "cup": "cup", "cups": "cup", "c": "cup",
    "tbsp": "tbsp", "tbs": "tbsp",
    "tablespoon": "tbsp", "tablespoons": "tbsp",
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
}

_QTY_RE = re.compile(
    r"""^\s*
    (?P<qty>
        \d+\s+\d+/\d+     # mixed number, e.g. "1 1/2"
        |\d+/\d+          # fraction, e.g. "1/2"
        |\d+(?:\.\d+)?    # integer or decimal, e.g. "2", "0.5"
    )
    \s*
    (?P<rest>.*)$
    """,
    re.VERBOSE,
)


def _parse_quantity(qty_str: str) -> float:
    qty_str = qty_str.strip()
    if " " in qty_str:
        whole, frac = qty_str.split(" ", 1)
        num, den = frac.split("/")
        return float(whole) + float(num) / float(den)
    if "/" in qty_str:
        num, den = qty_str.split("/")
        return float(num) / float(den)
    return float(qty_str)


@dataclass
class ParsedIngredient:
    raw_line: str
    quantity: float
    unit: str
    food_name: str


def parse_ingredient_line(line: str) -> Optional[ParsedIngredient]:
    """
    Parse a single ingredient line into quantity/unit/food_name, e.g.
    "2 cups flour" -> (2.0, "cup", "flour").

    Returns None when there's no leading quantity to parse (e.g. "Salt
    to taste") — the caller falls back to an LLM for that one line.
    """
    match = _QTY_RE.match(line)
    if not match:
        return None

    quantity = _parse_quantity(match.group("qty"))
    rest = match.group("rest").strip()
    if not rest:
        return None

    tokens = rest.split(None, 1)
    first_word = tokens[0].lower().strip(",.")
    unit = _UNIT_ALIASES.get(first_word)

    if unit:
        remainder = tokens[1] if len(tokens) > 1 else ""
    elif len(tokens) > 1:
        # No recognized standard unit, but there's more text after the
        # first word — treat it as a natural unit (e.g. "clove", "large").
        unit = first_word
        remainder = tokens[1]
    else:
        # Just a quantity and a food name with no unit word at all.
        unit = "g"
        remainder = rest

    food_name = remainder.split(",")[0].strip()
    if not food_name:
        return None

    return ParsedIngredient(
        raw_line=line, quantity=quantity, unit=unit, food_name=food_name
    )


# ─────────────────────────────────────────────
#  LLM FALLBACK
# ─────────────────────────────────────────────

_EXTRACT_SYSTEM_PROMPT = (
    "You extract recipe data from a web page's visible text. Respond "
    "with ONLY a JSON object of the form "
    '{"name": string or null, "servings": number or null, '
    '"ingredient_lines": [string, ...]}. ingredient_lines should be the '
    "ingredient list exactly as written on the page, one string per "
    "ingredient, including quantities and units. If the page has no "
    'recipe, respond with {"name": null, "servings": null, '
    '"ingredient_lines": []}.'
)

_LINE_SYSTEM_PROMPT = (
    "You split one recipe ingredient line into quantity, unit, and food "
    "name. Respond with ONLY a JSON object of the form "
    '{"quantity": number, "unit": string, "food_name": string}. unit '
    "should be one of g, ml, oz, cup, tbsp, tsp, or a short natural unit "
    'like "clove" or "slice" if no standard unit applies. If the line '
    'has no usable quantity (e.g. "salt to taste"), respond with '
    'quantity 1, unit "g", and food_name set to the food itself.'
)


async def _call_llm_json(system_prompt: str, user_content: str) -> dict:
    """POST a chat-completion request to the configured OpenAI-compatible
    LLM endpoint and parse its JSON content. Raises HTTPException(503) if
    no LLM_API_KEY is configured, or HTTPException(502) if the request
    fails or the model doesn't return valid JSON."""
    api_key = (LLM_API_KEY or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Recipe import's LLM fallback is not configured on the server.",
        )

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(
                f"{LLM_BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": LLM_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0,
                },
            )
            response.raise_for_status()
        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
            raise HTTPException(
                status_code=502, detail=f"Recipe import's LLM request failed: {e}"
            )

    body = response.json()
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        raise HTTPException(
            status_code=502,
            detail="Recipe import's LLM returned an unexpected response shape.",
        )

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="Recipe import's LLM returned an unparseable response.",
        )

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=502,
            detail="Recipe import's LLM returned an unexpected response shape.",
        )

    return parsed


def _visible_text(html: str, max_chars: int = 8000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(separator=" ").split())
    return text[:max_chars]


async def extract_recipe_via_llm(html: str) -> Optional[RawRecipe]:
    """Called only when extract_structured_recipe() finds no JSON-LD
    Recipe markup. Sends the page's visible text to the LLM."""
    text = _visible_text(html)
    data = await _call_llm_json(_EXTRACT_SYSTEM_PROMPT, text)

    lines = data.get("ingredient_lines") or []
    if not data.get("name") or not lines:
        return None

    return RawRecipe(
        name=str(data["name"]).strip(),
        servings=float(data.get("servings") or 1),
        image_url=None,
        ingredient_lines=[str(l).strip() for l in lines if str(l).strip()],
    )


async def parse_ingredient_line_via_llm(line: str) -> ParsedIngredient:
    """Called only when parse_ingredient_line() can't find a leading
    quantity in a line (e.g. "a pinch of saffron")."""
    data = await _call_llm_json(_LINE_SYSTEM_PROMPT, line)
    return ParsedIngredient(
        raw_line=line,
        quantity=float(data.get("quantity") or 1),
        unit=str(data.get("unit") or "g").strip(),
        food_name=str(data.get("food_name") or line).strip(),
    )
