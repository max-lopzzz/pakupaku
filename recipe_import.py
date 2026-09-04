"""
recipe_import.py
-----------------
Turns a recipe blog URL into a draft Recipe: fetches the page, extracts
ingredients (from schema.org/JSON-LD markup, falling back to an LLM),
parses each ingredient line into quantity/unit/food name, and matches
each one against the in-memory food_index. Returns a RecipeImportDraft —
nothing is saved to the database here.
"""

import asyncio
import html
import ipaddress
import json
import logging
import re
import socket
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

import food_index
from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
from schemas import ImportedIngredient, ImportedIngredientCandidate, RecipeImportDraft

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────
#  STRUCTURED EXTRACTION (schema.org / JSON-LD)
# ─────────────────────────────────────────────

@dataclass
class RawRecipe:
    name: str
    servings: float
    image_url: Optional[str]
    ingredient_lines: List[str]
    instructions: Optional[str] = None


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


def _parse_instructions(raw_instructions) -> Optional[str]:
    """recipeInstructions can be a bare string, a list of strings, or a
    list of HowToStep objects (each with a "text" key). Nested
    HowToSection groupings (a list of sections, each containing its own
    itemListElement) aren't handled - rare enough on real recipe blogs
    that falling back to no instructions for that shape is an acceptable
    gap, same tradeoff this file already makes elsewhere for uncommon
    markup variants."""
    if isinstance(raw_instructions, str):
        return raw_instructions.strip() or None
    if not isinstance(raw_instructions, list):
        return None
    steps = []
    for item in raw_instructions:
        if isinstance(item, str):
            text = item.strip()
        elif isinstance(item, dict):
            text = str(item.get("text", "")).strip()
        else:
            text = ""
        if text:
            steps.append(text)
    return "\n".join(steps) if steps else None


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
            instructions=_parse_instructions(node.get("recipeInstructions")),
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
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    "l": "l", "liter": "l", "liters": "l", "litre": "l", "litres": "l",
}

_UNICODE_FRACTIONS = {
    "¼": "1/4", "½": "1/2", "¾": "3/4",
    "⅓": "1/3", "⅔": "2/3",
    "⅛": "1/8", "⅜": "3/8", "⅝": "5/8", "⅞": "7/8",
}


def _normalize_unicode_fractions(text: str) -> str:
    """"1½ cups" -> "1 1/2 cups" (mixed number); "½ cup" -> "1/2 cup" (bare)."""
    for char, replacement in _UNICODE_FRACTIONS.items():
        text = re.sub(r"(?<=\d)" + char, " " + replacement, text)
        text = text.replace(char, replacement)
    return text


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
    # Some recipe-plugin JSON-LD ships fractions as unescaped HTML entities
    # (e.g. "&frac12;") rather than real Unicode characters — decode those
    # before looking for a leading quantity.
    line = html.unescape(line)
    line = _normalize_unicode_fractions(line)
    match = _QTY_RE.match(line)
    if not match:
        return None

    try:
        quantity = _parse_quantity(match.group("qty"))
    except (ValueError, ZeroDivisionError):
        return None
    rest = match.group("rest").strip()
    rest = re.sub(r"\([^)]*\)", "", rest).strip()
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
    '"ingredient_lines": [string, ...], "steps": [string, ...]}. '
    "ingredient_lines should be the ingredient list exactly as written "
    "on the page, one string per ingredient, including quantities and "
    "units. steps should be the cooking instructions, one step per "
    "string, in order — omit steps entirely (empty list) if the page "
    'has no instructions. If the page has no recipe, respond with '
    '{"name": null, "servings": null, "ingredient_lines": [], "steps": []}.'
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
    except (json.JSONDecodeError, TypeError):
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

    steps = data.get("steps") or []
    return RawRecipe(
        name=str(data["name"]).strip(),
        servings=float(data.get("servings") or 1),
        image_url=None,
        instructions="\n".join(str(s).strip() for s in steps if str(s).strip()) or None,
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


# ─────────────────────────────────────────────
#  INGREDIENT MATCHING (food_index)
# ─────────────────────────────────────────────

def _to_candidate(food: food_index.Food) -> ImportedIngredientCandidate:
    return ImportedIngredientCandidate(
        food_id=food.id,
        description=food.description,
        brand=None,
        calories_per_100g=food.calories_per_100g,
        protein_per_100g=food.protein_per_100g,
        fat_per_100g=food.fat_per_100g,
        carbs_per_100g=food.carbs_per_100g,
        fiber_per_100g=food.fiber_per_100g,
        portions_map={p["unit"]: p["grams"] for p in food.portions},
    )


async def match_ingredient(parsed: ParsedIngredient) -> ImportedIngredient:
    """Look the parsed ingredient's food name up in the in-memory
    ``food_index`` and return the best match plus a few alternates.
    best_match is None if the index has nothing plausible — the frontend
    shows that row unmatched for the user to fix manually."""
    hits = food_index.search(parsed.food_name, 5)
    return ImportedIngredient(
        raw_line=parsed.raw_line,
        quantity=parsed.quantity,
        unit=parsed.unit,
        food_name=parsed.food_name,
        best_match=_to_candidate(hits[0]) if hits else None,
        alternates=[_to_candidate(f) for f in hits[1:5]],
    )


async def _safe_match_ingredient(parsed: ParsedIngredient) -> ImportedIngredient:
    """Wraps match_ingredient so a malformed index row for one ingredient
    can't sink the whole asyncio.gather() and fail the entire import.
    Mirrors match_ingredient's own no-match return shape so the caller
    can't tell the difference."""
    try:
        return await match_ingredient(parsed)
    except Exception:
        logger.exception("match_ingredient failed for ingredient %r", parsed.food_name)
        return ImportedIngredient(
            raw_line=parsed.raw_line,
            quantity=parsed.quantity,
            unit=parsed.unit,
            food_name=parsed.food_name,
            best_match=None,
            alternates=[],
        )


# ─────────────────────────────────────────────
#  ORCHESTRATION
# ─────────────────────────────────────────────

_MAX_REDIRECTS = 5


async def _resolve_and_validate_host(url: str) -> None:
    """Raises HTTPException(422) if url's host resolves to a private,
    loopback, link-local, reserved, or otherwise internal address.

    Blocks SSRF-style abuse of an authenticated user pointing this
    importer at an internal service. This checks the resolved address at
    validation time — it does not defend against DNS-rebinding attacks,
    where a hostname resolves differently between this check and the
    actual connection a moment later. A fully airtight guard would need a
    custom transport that pins the resolved IP for the connection itself;
    that's a bigger change than this warrants right now.
    """
    try:
        hostname = urlparse(url).hostname
    except ValueError:
        raise HTTPException(status_code=422, detail="That doesn't look like a valid URL.")
    if not hostname:
        raise HTTPException(status_code=422, detail="That doesn't look like a valid URL.")

    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(hostname, None)
    except (socket.gaierror, UnicodeError, ValueError):
        raise HTTPException(status_code=422, detail="Could not resolve that URL's host.")

    for _family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise HTTPException(
                status_code=422,
                detail="That URL points to a private or internal address, which isn't allowed.",
            )


async def fetch_page(url: str) -> str:
    """Fetch a blog URL and return its HTML. Raises HTTPException(422) on
    any failure — dead link, timeout, non-HTML response, a site that
    blocks the request, or a URL/redirect that resolves to a private or
    internal address (see _resolve_and_validate_host).

    Redirects are followed manually (rather than via httpx's built-in
    follow_redirects) so each hop's host can be validated before the
    request for it goes out — a redirect to an internal address is
    rejected instead of silently followed.
    """
    if not url.strip().lower().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422, detail="Import URL must start with http:// or https://."
        )

    current_url = url
    async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
        for _ in range(_MAX_REDIRECTS + 1):
            await _resolve_and_validate_host(current_url)
            try:
                response = await client.get(
                    current_url,
                    headers={"User-Agent": "Mozilla/5.0 (compatible; PakuPakuBot/1.0)"},
                )
            except httpx.TimeoutException:
                raise HTTPException(status_code=422, detail="Timed out fetching that URL.")
            except httpx.RequestError:
                raise HTTPException(status_code=422, detail="Could not fetch that URL.")
            except (httpx.InvalidURL, UnicodeError, ValueError):
                raise HTTPException(
                    status_code=422, detail="That doesn't look like a valid URL."
                )

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise HTTPException(status_code=422, detail="Could not fetch that URL.")
                current_url = urljoin(current_url, location)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                raise HTTPException(
                    status_code=422,
                    detail=f"Could not fetch that URL ({e.response.status_code}).",
                )
            break
        else:
            raise HTTPException(status_code=422, detail="Too many redirects.")

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type.lower():
        raise HTTPException(
            status_code=422, detail="That URL doesn't look like a web page."
        )
    return response.text


async def build_import_draft(url: str) -> RecipeImportDraft:
    """Fetch the URL, extract a recipe (structured markup first, LLM
    fallback second), parse and match every ingredient line, and return
    the assembled draft. Raises HTTPException(422) if no recipe could be
    found at all."""
    html = await fetch_page(url)

    raw = extract_structured_recipe(html)
    if raw is None:
        raw = await extract_recipe_via_llm(html)
    if raw is None:
        raise HTTPException(status_code=422, detail="Couldn't find a recipe on that page.")

    parsed_lines = []
    for line in raw.ingredient_lines:
        parsed = parse_ingredient_line(line)
        if parsed is None:
            try:
                parsed = await parse_ingredient_line_via_llm(line)
            except HTTPException:
                parsed = ParsedIngredient(
                    raw_line=line, quantity=1.0, unit="g", food_name=line
                )
        parsed_lines.append(parsed)

    ingredients = await asyncio.gather(*(_safe_match_ingredient(p) for p in parsed_lines))

    return RecipeImportDraft(
        name=raw.name,
        servings=raw.servings,
        image_url=raw.image_url,
        instructions=raw.instructions,
        ingredients=list(ingredients),
        source_url=url,
    )
