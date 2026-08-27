"""
recipe_import.py
-----------------
Turns a recipe blog URL into a draft Recipe: fetches the page, extracts
ingredients (from schema.org/JSON-LD markup, falling back to an LLM),
parses each ingredient line into quantity/unit/food name, and matches
each one against USDA FoodData Central. Returns a RecipeImportDraft —
nothing is saved to the database here.
"""

import json
import re
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup


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
