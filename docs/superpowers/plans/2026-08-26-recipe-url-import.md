# Recipe URL Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user paste a recipe blog URL and get a pre-filled, editable recipe draft (name, servings, photo, ingredients matched to USDA foods with amounts in grams) opened in the existing `RecipeBuilder` review screen.

**Architecture:** A new backend module (`recipe_import.py`) fetches the URL, extracts ingredients from schema.org/JSON-LD markup (falling back to an LLM when that's missing), parses each ingredient line into quantity/unit/food name, and matches each one against USDA FoodData Central via the existing `usda.py` client. A new `POST /recipes/import` route returns this as a draft — nothing is saved. The frontend adds an "Import from URL" control to `RecipeBuilder` that calls this endpoint and pre-fills the same ingredient-row state the manual add-ingredient flow already uses, so saving goes through the existing unchanged `POST /recipes`.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy (unchanged), httpx (already a dependency, used both for the page fetch and the LLM call — no new HTTP client library), BeautifulSoup4 (new dependency, for JSON-LD/text extraction), pytest + pytest-asyncio (new — no test framework exists in this repo yet), React/TypeScript (unchanged, extends `RecipeBuilder.tsx`).

**Spec:** [docs/superpowers/specs/2026-08-26-recipe-url-import-design.md](../specs/2026-08-26-recipe-url-import-design.md)

## Global Constraints

- Target Python is 3.8 (the project's `venv` is `python3.8`) — do not use `list[str]`/`dict[str, X]` builtin generics or `X | None` union syntax anywhere in new backend code; use `typing.List`/`typing.Dict`/`typing.Optional` instead, matching the rest of the codebase.
- Do not modify `models.py`, `schemas.py`'s existing classes, `usda.py`, or the existing `POST`/`PATCH /recipes` handlers — recipe persistence is unchanged (per spec's non-goals).
- New nutrient field names on the wire must exactly match `RecipeBuilder.tsx`'s existing `NutrientData` interface (`calories_per_100g`, `protein_per_100g`, `fat_per_100g`, `carbs_per_100g`, `fiber_per_100g`) so the frontend can reuse it directly.
- No new HTTP client dependency for the LLM call — it's a plain OpenAI-compatible REST call via `httpx`, which is already installed.
- No background job queue, no rate limiting, no image OCR — out of scope per spec.

---

### Task 1: Backend test infrastructure and LLM config

**Files:**
- Modify: `config.py` (append after line 30, the `USDA_API_KEY` line)
- Create: `pytest.ini`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Test: `tests/test_config_smoke.py`

**Interfaces:**
- Produces: `config.LLM_API_KEY: Optional[str]`, `config.LLM_BASE_URL: str` (default `"https://api.together.xyz/v1"`), `config.LLM_MODEL: str` (default `"meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"`) — consumed by Task 4.
- Produces: a working `pytest` setup with hermetic env defaults (`DATABASE_URL`, `SECRET_KEY`) so any test that imports `main.py` (which transitively imports `database.py`, which creates a SQLAlchemy engine from `DATABASE_URL` at import time) doesn't need a real `.env` file or database — consumed by Task 7.

No existing tests or test framework exist in this repo yet, so this task installs and wires that up before anything else needs it.

- [ ] **Step 1: Install test and parsing dependencies into the project's venv**

Run:
```bash
./venv/bin/pip install pytest pytest-asyncio beautifulsoup4
```

- [ ] **Step 2: Add LLM config to `config.py`**

Insert immediately after the `USDA_API_KEY = os.getenv("USDA_API_KEY")` line (line 30):

```python

# ── LLM (recipe import fallback) ──────────────
# Used only when a blog page has no schema.org/JSON-LD Recipe markup.
# Any OpenAI-compatible chat-completions endpoint works — Together.ai is
# the default because it hosts open-weight models behind that API shape.
LLM_API_KEY  = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.together.xyz/v1")
LLM_MODEL    = os.getenv("LLM_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo")
```

- [ ] **Step 3: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 4: Create `tests/__init__.py`**

Empty file (makes `tests` a package so relative fixture paths resolve consistently).

- [ ] **Step 5: Create `tests/conftest.py`**

```python
"""
conftest.py
-----------
Runs before any test module is imported. Sets safe, fake environment
values so importing `main` (and therefore `database.py`, which builds a
SQLAlchemy engine from DATABASE_URL at import time) never requires a
real .env file or a reachable database. SQLAlchemy engines are lazy —
they don't connect until a query actually runs — so a syntactically
valid but unreachable URL is enough for tests that don't touch the DB.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
```

- [ ] **Step 6: Write the smoke test**

```python
# tests/test_config_smoke.py
import importlib

import config


def test_llm_config_has_defaults(monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    importlib.reload(config)
    try:
        assert config.LLM_BASE_URL == "https://api.together.xyz/v1"
        assert config.LLM_MODEL == "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo"
    finally:
        importlib.reload(config)  # restore real env for later tests
```

- [ ] **Step 7: Run it to verify it fails first**

Run: `./venv/bin/pytest tests/test_config_smoke.py -v`
Expected: FAIL — `AttributeError: module 'config' has no attribute 'LLM_BASE_URL'` (Step 2 not yet applied when run in isolation; if you did Steps 1-6 in order it will already pass — in that case confirm it passes and move on).

- [ ] **Step 8: Run it to verify it passes**

Run: `./venv/bin/pytest tests/test_config_smoke.py -v`
Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add config.py pytest.ini tests/__init__.py tests/conftest.py tests/test_config_smoke.py
git commit -m "Add pytest setup and LLM config for recipe import"
```

---

### Task 2: Import schemas and JSON-LD structured extraction

**Files:**
- Modify: `schemas.py` (append at end of file; add `Dict` to the existing `from typing import Optional, List` import line)
- Create: `recipe_import.py`
- Create: `tests/fixtures/recipe_blog_jsonld.html`
- Create: `tests/fixtures/recipe_blog_graph.html`
- Create: `tests/fixtures/recipe_blog_none.html`
- Test: `tests/test_recipe_import_structured.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `schemas.ImportRecipeRequest(url: str)`
  - `schemas.ImportedIngredientCandidate(fdc_id: int, description: str, brand: Optional[str], calories_per_100g: Optional[float], protein_per_100g: Optional[float], fat_per_100g: Optional[float], carbs_per_100g: Optional[float], fiber_per_100g: Optional[float], portions_map: Dict[str, float])`
  - `schemas.ImportedIngredient(raw_line: str, quantity: float, unit: str, food_name: str, best_match: Optional[ImportedIngredientCandidate], alternates: List[ImportedIngredientCandidate])`
  - `schemas.RecipeImportDraft(name: str, servings: float, image_url: Optional[str], ingredients: List[ImportedIngredient], source_url: str)`
  - `recipe_import.RawRecipe` dataclass: `name: str`, `servings: float`, `image_url: Optional[str]`, `ingredient_lines: List[str]` — consumed by Task 3 (via `parse_ingredient_line`, indirectly), Task 4, and Task 6.
  - `recipe_import.extract_structured_recipe(html: str) -> Optional[RawRecipe]` — consumed by Task 6.

- [ ] **Step 1: Add the new schema classes to `schemas.py`**

First, update the typing import near the top of the file (it currently reads `from typing import Optional, List`):

```python
from typing import Optional, List, Dict
```

Then append at the end of `schemas.py`:

```python


# ─────────────────────────────────────────────
#  RECIPE IMPORT (AI extraction from a blog URL)
# ─────────────────────────────────────────────

class ImportRecipeRequest(BaseModel):
    url: str


class ImportedIngredientCandidate(BaseModel):
    fdc_id:      int
    description: str
    brand:       Optional[str] = None
    calories_per_100g: Optional[float] = None
    protein_per_100g:  Optional[float] = None
    fat_per_100g:      Optional[float] = None
    carbs_per_100g:    Optional[float] = None
    fiber_per_100g:    Optional[float] = None
    portions_map: Dict[str, float] = {}


class ImportedIngredient(BaseModel):
    raw_line:  str
    quantity:  float
    unit:      str
    food_name: str
    best_match: Optional[ImportedIngredientCandidate] = None
    alternates: List[ImportedIngredientCandidate] = []


class RecipeImportDraft(BaseModel):
    name:        str
    servings:    float
    image_url:   Optional[str] = None
    ingredients: List[ImportedIngredient]
    source_url:  str
```

- [ ] **Step 2: Create the fixture HTML files**

`tests/fixtures/recipe_blog_jsonld.html` (a top-level `Recipe` JSON-LD object, the common case):

```html
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Recipe",
  "name": "Simple Pancakes",
  "image": "https://example.com/pancakes.jpg",
  "recipeYield": "4 servings",
  "recipeIngredient": [
    "2 cups all-purpose flour",
    "1/2 tsp salt",
    "3 large eggs",
    "1 clove garlic, minced"
  ]
}
</script>
</head>
<body><h1>Simple Pancakes</h1></body>
</html>
```

`tests/fixtures/recipe_blog_graph.html` (JSON-LD wrapped in a top-level `@graph` array alongside an unrelated node type, a common WordPress SEO-plugin pattern):

```html
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Organization",
      "name": "Example Food Blog"
    },
    {
      "@type": "Recipe",
      "name": "Graph Wrapped Soup",
      "image": {"@type": "ImageObject", "url": "https://example.com/soup.jpg"},
      "recipeYield": ["6"],
      "recipeIngredient": [
        "1 cup diced carrots",
        "2 tbsp olive oil"
      ]
    }
  ]
}
</script>
</head>
<body><h1>Graph Wrapped Soup</h1></body>
</html>
```

`tests/fixtures/recipe_blog_none.html` (no Recipe markup — a blog post that isn't a recipe):

```html
<!DOCTYPE html>
<html>
<head>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "BlogPosting",
  "headline": "5 Kitchen Tips For Beginners"
}
</script>
</head>
<body><h1>5 Kitchen Tips For Beginners</h1></body>
</html>
```

- [ ] **Step 3: Write the failing tests**

```python
# tests/test_recipe_import_structured.py
from pathlib import Path

from recipe_import import extract_structured_recipe

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text()


def test_extracts_top_level_recipe_jsonld():
    raw = extract_structured_recipe(_read("recipe_blog_jsonld.html"))
    assert raw is not None
    assert raw.name == "Simple Pancakes"
    assert raw.servings == 4.0
    assert raw.image_url == "https://example.com/pancakes.jpg"
    assert raw.ingredient_lines == [
        "2 cups all-purpose flour",
        "1/2 tsp salt",
        "3 large eggs",
        "1 clove garlic, minced",
    ]


def test_extracts_recipe_wrapped_in_graph():
    raw = extract_structured_recipe(_read("recipe_blog_graph.html"))
    assert raw is not None
    assert raw.name == "Graph Wrapped Soup"
    assert raw.servings == 6.0
    assert raw.image_url == "https://example.com/soup.jpg"
    assert raw.ingredient_lines == ["1 cup diced carrots", "2 tbsp olive oil"]


def test_returns_none_when_no_recipe_markup():
    assert extract_structured_recipe(_read("recipe_blog_none.html")) is None
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_recipe_import_structured.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'recipe_import'`

- [ ] **Step 5: Create `recipe_import.py` with the structured-extraction path**

```python
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
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_recipe_import_structured.py -v`
Expected: PASS (3 passed)

- [ ] **Step 7: Commit**

```bash
git add schemas.py recipe_import.py tests/fixtures/recipe_blog_jsonld.html \
  tests/fixtures/recipe_blog_graph.html tests/fixtures/recipe_blog_none.html \
  tests/test_recipe_import_structured.py
git commit -m "Add recipe import schemas and JSON-LD structured extraction"
```

---

### Task 3: Ingredient line parser

**Files:**
- Modify: `recipe_import.py` (append; add `Optional` is already imported, no new top-level imports needed)
- Test: `tests/test_recipe_import_parser.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `recipe_import.ParsedIngredient` dataclass (`raw_line: str`, `quantity: float`, `unit: str`, `food_name: str`) and `recipe_import.parse_ingredient_line(line: str) -> Optional[ParsedIngredient]` — consumed by Task 4 (per-line LLM fallback), Task 5 (`match_ingredient` takes a `ParsedIngredient`), and Task 6 (`build_import_draft`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_recipe_import_parser.py
import pytest

from recipe_import import parse_ingredient_line


@pytest.mark.parametrize(
    "line,quantity,unit,food_name",
    [
        ("2 cups all-purpose flour", 2.0, "cup", "all-purpose flour"),
        ("1/2 tsp salt", 0.5, "tsp", "salt"),
        ("1 1/2 cups sugar", 1.5, "cup", "sugar"),
        ("3 large eggs", 3.0, "large", "eggs"),
        ("1 clove garlic, minced", 1.0, "clove", "garlic"),
        ("2 tbsp olive oil", 2.0, "tbsp", "olive oil"),
    ],
)
def test_parses_common_ingredient_lines(line, quantity, unit, food_name):
    parsed = parse_ingredient_line(line)
    assert parsed is not None
    assert parsed.raw_line == line
    assert parsed.quantity == quantity
    assert parsed.unit == unit
    assert parsed.food_name == food_name


def test_returns_none_with_no_leading_quantity():
    assert parse_ingredient_line("Salt to taste") is None


def test_defaults_to_grams_when_no_unit_word_follows():
    parsed = parse_ingredient_line("2 eggs")
    assert parsed is not None
    assert parsed.quantity == 2.0
    assert parsed.unit == "g"
    assert parsed.food_name == "eggs"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_recipe_import_parser.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_ingredient_line' from 'recipe_import'`

- [ ] **Step 3: Append the parser to `recipe_import.py`**

```python


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_recipe_import_parser.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add recipe_import.py tests/test_recipe_import_parser.py
git commit -m "Add ingredient line parser for recipe import"
```

---

### Task 4: LLM fallback extraction

**Files:**
- Modify: `recipe_import.py` (append; add `asyncio`, `httpx`, `fastapi.HTTPException`, and `config.LLM_API_KEY/LLM_BASE_URL/LLM_MODEL` to imports)
- Test: `tests/test_recipe_import_llm.py`

**Interfaces:**
- Consumes: `recipe_import.RawRecipe` (Task 2), `recipe_import.ParsedIngredient` (Task 3), `config.LLM_API_KEY`/`LLM_BASE_URL`/`LLM_MODEL` (Task 1).
- Produces:
  - `recipe_import.extract_recipe_via_llm(html: str) -> Optional[RawRecipe]` — consumed by Task 6.
  - `recipe_import.parse_ingredient_line_via_llm(line: str) -> ParsedIngredient` — consumed by Task 6.
  - Both raise `fastapi.HTTPException(503)` if `LLM_API_KEY` isn't set, or `HTTPException(502)` if the LLM request fails/times out/returns unparseable JSON.

- [ ] **Step 1: Write the failing tests**

These tests fake the network layer by monkeypatching `httpx.AsyncClient` with a minimal stand-in, so no real HTTP call happens and no `pytest-httpx`-style dependency is needed.

```python
# tests/test_recipe_import_llm.py
import json

import httpx
import pytest
from fastapi import HTTPException

import recipe_import


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error", request=None, response=self  # type: ignore[arg-type]
            )

    def json(self):
        return self._payload


class _FakeAsyncClient:
    """Stands in for httpx.AsyncClient as an async context manager."""

    last_request = None  # captured for assertions

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, headers=None, json=None):
        _FakeAsyncClient.last_request = {"url": url, "headers": headers, "json": json}
        content = _FakeAsyncClient.next_content
        return _FakeResponse(
            {"choices": [{"message": {"content": content}}]}
        )


def _install_fake_client(monkeypatch, content: str):
    _FakeAsyncClient.next_content = content
    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _FakeAsyncClient)


def test_extract_recipe_via_llm_parses_response(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")
    _install_fake_client(
        monkeypatch,
        json.dumps(
            {
                "name": "LLM Extracted Soup",
                "servings": 2,
                "ingredient_lines": ["1 cup broth", "2 carrots"],
            }
        ),
    )

    import asyncio

    raw = asyncio.run(recipe_import.extract_recipe_via_llm("<html>...</html>"))

    assert raw is not None
    assert raw.name == "LLM Extracted Soup"
    assert raw.servings == 2.0
    assert raw.ingredient_lines == ["1 cup broth", "2 carrots"]
    assert _FakeAsyncClient.last_request["json"]["model"] == recipe_import.LLM_MODEL


def test_extract_recipe_via_llm_returns_none_when_no_recipe_found(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")
    _install_fake_client(
        monkeypatch,
        json.dumps({"name": None, "servings": None, "ingredient_lines": []}),
    )

    import asyncio

    assert asyncio.run(recipe_import.extract_recipe_via_llm("<html></html>")) is None


def test_extract_recipe_via_llm_raises_503_when_not_configured(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", None)

    import asyncio

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(recipe_import.extract_recipe_via_llm("<html></html>"))
    assert exc_info.value.status_code == 503


def test_extract_recipe_via_llm_raises_502_on_request_failure(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")

    class _FailingClient(_FakeAsyncClient):
        async def post(self, url, headers=None, json=None):
            raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(recipe_import.httpx, "AsyncClient", _FailingClient)

    import asyncio

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(recipe_import.extract_recipe_via_llm("<html></html>"))
    assert exc_info.value.status_code == 502


def test_parse_ingredient_line_via_llm_parses_response(monkeypatch):
    monkeypatch.setattr(recipe_import, "LLM_API_KEY", "test-key")
    _install_fake_client(
        monkeypatch,
        json.dumps({"quantity": 1, "unit": "pinch", "food_name": "saffron"}),
    )

    import asyncio

    parsed = asyncio.run(
        recipe_import.parse_ingredient_line_via_llm("a pinch of saffron")
    )

    assert parsed.raw_line == "a pinch of saffron"
    assert parsed.quantity == 1.0
    assert parsed.unit == "pinch"
    assert parsed.food_name == "saffron"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_recipe_import_llm.py -v`
Expected: FAIL — `AttributeError: module 'recipe_import' has no attribute 'extract_recipe_via_llm'`

- [ ] **Step 3: Update imports and append the LLM fallback to `recipe_import.py`**

Change the top of the file from:

```python
import json
import re
from dataclasses import dataclass
from typing import List, Optional

from bs4 import BeautifulSoup
```

to:

```python
import asyncio
import json
import re
from dataclasses import dataclass
from typing import List, Optional

import httpx
from bs4 import BeautifulSoup
from fastapi import HTTPException

from config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL
```

Then append at the end of the file:

```python


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
    content = body["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="Recipe import's LLM returned an unparseable response.",
        )


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_recipe_import_llm.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add recipe_import.py tests/test_recipe_import_llm.py
git commit -m "Add LLM fallback extraction for recipe import"
```

---

### Task 5: USDA ingredient matching

**Files:**
- Modify: `recipe_import.py` (append; add `usda.py` and `schemas.py` imports)
- Test: `tests/test_recipe_import_matching.py`

**Interfaces:**
- Consumes: `recipe_import.ParsedIngredient` (Task 3), `schemas.ImportedIngredient`/`ImportedIngredientCandidate` (Task 2), `usda.search_foods`, `usda.get_food`, `usda.extract_nutrients` (existing, unchanged).
- Produces: `recipe_import.rank_candidates(foods: List[dict]) -> List[dict]` and `recipe_import.match_ingredient(parsed: ParsedIngredient) -> ImportedIngredient` — consumed by Task 6.

- [ ] **Step 1: Write the failing tests**

These mock `recipe_import.search_foods` and `recipe_import.get_food` directly (the names as imported into `recipe_import`'s namespace) rather than the HTTP layer, since Task's job is the matching/ranking logic, not `usda.py` itself (which is unchanged and untested here).

```python
# tests/test_recipe_import_matching.py
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_recipe_import_matching.py -v`
Expected: FAIL — `ImportError: cannot import name 'match_ingredient' from 'recipe_import'`

- [ ] **Step 3: Update imports and append matching logic to `recipe_import.py`**

Add to the import block at the top of the file (after the `from config import ...` line):

```python
from schemas import ImportedIngredient, ImportedIngredientCandidate
from usda import extract_nutrients, get_food, search_foods
```

Then append at the end of the file:

```python


# ─────────────────────────────────────────────
#  USDA MATCHING
# ─────────────────────────────────────────────

_PREFERRED_DATA_TYPES = {"Foundation", "SR Legacy"}
_RELIABLE_PORTION_DATA_TYPES = {"Survey (FNDDS)", "SR Legacy"}


def rank_candidates(foods: List[dict]) -> List[dict]:
    """Stable-sort USDA search results so Foundation/SR Legacy data (the
    most nutrient-complete) come first, preserving USDA's own relevance
    ordering within each group."""
    return sorted(
        foods, key=lambda f: 0 if f.get("dataType") in _PREFERRED_DATA_TYPES else 1
    )


async def _fetch_portions_map(fdc_id: int, description: str) -> Dict[str, float]:
    """Mirrors RecipeBuilder.tsx's tiered portion lookup: try the matched
    food's own detail first, then fall back to a Survey (FNDDS)/SR Legacy
    result for the same description (some Foundation foods 404 on the
    detail endpoint, a known USDA data inconsistency)."""
    try:
        detail = await get_food(fdc_id)
        portions = extract_nutrients(detail).get("portions", [])
        if portions:
            return {p["unit"]: p["grams_per_unit"] for p in portions}
    except HTTPException:
        pass

    try:
        research = await search_foods(description, page_size=20)
    except HTTPException:
        return {}

    for food in research.get("foods", []):
        if food.get("dataType") not in _RELIABLE_PORTION_DATA_TYPES:
            continue
        try:
            detail = await get_food(food["fdcId"])
        except HTTPException:
            continue
        portions = extract_nutrients(detail).get("portions", [])
        if portions:
            return {p["unit"]: p["grams_per_unit"] for p in portions}

    return {}


def _to_candidate(food: dict, portions_map: Dict[str, float]) -> ImportedIngredientCandidate:
    nutrients = extract_nutrients(food)
    return ImportedIngredientCandidate(
        fdc_id=food["fdcId"],
        description=food.get("description", ""),
        brand=food.get("brandOwner") or food.get("brandName"),
        calories_per_100g=nutrients.get("calories"),
        protein_per_100g=nutrients.get("protein_g"),
        fat_per_100g=nutrients.get("fat_g"),
        carbs_per_100g=nutrients.get("carbs_g"),
        fiber_per_100g=nutrients.get("fiber_g"),
        portions_map=portions_map,
    )


async def match_ingredient(parsed: ParsedIngredient) -> ImportedIngredient:
    """Search USDA for the parsed ingredient's food name and return the
    best match (with food-specific portion gram-weights) plus a few
    alternates. best_match is None if USDA has nothing plausible — the
    frontend shows that row unmatched for the user to fix manually."""
    try:
        search_result = await search_foods(parsed.food_name, page_size=5)
    except HTTPException:
        search_result = {"foods": []}

    candidates = rank_candidates(search_result.get("foods", []))
    if not candidates:
        return ImportedIngredient(
            raw_line=parsed.raw_line,
            quantity=parsed.quantity,
            unit=parsed.unit,
            food_name=parsed.food_name,
            best_match=None,
            alternates=[],
        )

    best_food, alt_foods = candidates[0], candidates[1:5]
    portions_map = await _fetch_portions_map(best_food["fdcId"], parsed.food_name)

    return ImportedIngredient(
        raw_line=parsed.raw_line,
        quantity=parsed.quantity,
        unit=parsed.unit,
        food_name=parsed.food_name,
        best_match=_to_candidate(best_food, portions_map),
        alternates=[_to_candidate(f, {}) for f in alt_foods],
    )
```

Also add `Dict` to the `typing` import (already imported as part of Task 3's `Optional`/`List` line — update it to include `Dict`):

```python
from typing import Dict, List, Optional
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_recipe_import_matching.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add recipe_import.py tests/test_recipe_import_matching.py
git commit -m "Add USDA ingredient matching for recipe import"
```

---

### Task 6: Orchestration — fetch_page and build_import_draft

**Files:**
- Modify: `recipe_import.py` (append)
- Test: `tests/test_recipe_import_draft.py`

**Interfaces:**
- Consumes: `recipe_import.extract_structured_recipe` (Task 2), `extract_recipe_via_llm` (Task 4), `parse_ingredient_line`/`parse_ingredient_line_via_llm` (Tasks 3/4), `match_ingredient` (Task 5), `schemas.RecipeImportDraft` (Task 2).
- Produces: `recipe_import.fetch_page(url: str) -> str` and `recipe_import.build_import_draft(url: str) -> RecipeImportDraft` — consumed by Task 7 (the FastAPI route).

- [ ] **Step 1: Write the failing tests**

`build_import_draft`'s test mocks every step it orchestrates (each already has its own tests from earlier tasks) to verify the wiring: structured-first, LLM-fallback-second, and the 422 when both fail.

```python
# tests/test_recipe_import_draft.py
import asyncio

import pytest
from fastapi import HTTPException

import recipe_import
from recipe_import import (
    ParsedIngredient,
    RawRecipe,
    build_import_draft,
)
from schemas import ImportedIngredient


def _stub_common(monkeypatch, *, structured=None, llm=None):
    async def fake_fetch_page(url):
        return "<html>fake page</html>"

    async def fake_extract_via_llm(html):
        return llm

    def fake_parse_line(line):
        return ParsedIngredient(raw_line=line, quantity=1.0, unit="g", food_name=line)

    async def fake_match_ingredient(parsed):
        return ImportedIngredient(
            raw_line=parsed.raw_line,
            quantity=parsed.quantity,
            unit=parsed.unit,
            food_name=parsed.food_name,
            best_match=None,
            alternates=[],
        )

    monkeypatch.setattr(recipe_import, "fetch_page", fake_fetch_page)
    monkeypatch.setattr(
        recipe_import, "extract_structured_recipe", lambda html: structured
    )
    monkeypatch.setattr(recipe_import, "extract_recipe_via_llm", fake_extract_via_llm)
    monkeypatch.setattr(recipe_import, "parse_ingredient_line", fake_parse_line)
    monkeypatch.setattr(recipe_import, "match_ingredient", fake_match_ingredient)


def test_uses_structured_extraction_when_available(monkeypatch):
    structured = RawRecipe(
        name="Structured Recipe",
        servings=2.0,
        image_url="https://example.com/img.jpg",
        ingredient_lines=["1 cup rice"],
    )
    _stub_common(monkeypatch, structured=structured)

    draft = asyncio.run(build_import_draft("https://example.com/recipe"))

    assert draft.name == "Structured Recipe"
    assert draft.servings == 2.0
    assert draft.image_url == "https://example.com/img.jpg"
    assert draft.source_url == "https://example.com/recipe"
    assert len(draft.ingredients) == 1


def test_falls_back_to_llm_when_no_structured_data(monkeypatch):
    llm_result = RawRecipe(
        name="LLM Recipe", servings=1.0, image_url=None, ingredient_lines=["1 egg"]
    )
    _stub_common(monkeypatch, structured=None, llm=llm_result)

    draft = asyncio.run(build_import_draft("https://example.com/recipe"))

    assert draft.name == "LLM Recipe"
    assert len(draft.ingredients) == 1


def test_raises_422_when_neither_extraction_finds_a_recipe(monkeypatch):
    _stub_common(monkeypatch, structured=None, llm=None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(build_import_draft("https://example.com/recipe"))
    assert exc_info.value.status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./venv/bin/pytest tests/test_recipe_import_draft.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_import_draft' from 'recipe_import'`

- [ ] **Step 3: Append orchestration to `recipe_import.py`**

Add to the import block at the top of the file:

```python
from schemas import RecipeImportDraft
```

(alongside the existing `from schemas import ImportedIngredient, ImportedIngredientCandidate` — combine into one `from schemas import (...)` line).

Then append at the end of the file:

```python


# ─────────────────────────────────────────────
#  ORCHESTRATION
# ─────────────────────────────────────────────

async def fetch_page(url: str) -> str:
    """Fetch a blog URL and return its HTML. Raises HTTPException(422) on
    any failure — dead link, timeout, non-HTML response, or a site that
    blocks the request."""
    if not url.strip().lower().startswith(("http://", "https://")):
        raise HTTPException(
            status_code=422, detail="Import URL must start with http:// or https://."
        )

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        try:
            response = await client.get(
                url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; PakuPakuBot/1.0)"},
            )
            response.raise_for_status()
        except httpx.TimeoutException:
            raise HTTPException(status_code=422, detail="Timed out fetching that URL.")
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Could not fetch that URL ({e.response.status_code}).",
            )
        except httpx.RequestError:
            raise HTTPException(status_code=422, detail="Could not fetch that URL.")

    content_type = response.headers.get("content-type", "")
    if "html" not in content_type:
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
            parsed = await parse_ingredient_line_via_llm(line)
        parsed_lines.append(parsed)

    ingredients = await asyncio.gather(*(match_ingredient(p) for p in parsed_lines))

    return RecipeImportDraft(
        name=raw.name,
        servings=raw.servings,
        image_url=raw.image_url,
        ingredients=list(ingredients),
        source_url=url,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_recipe_import_draft.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Run the full backend test suite to confirm nothing broke**

Run: `./venv/bin/pytest tests/ -v`
Expected: all tests pass (Tasks 1-6 combined)

- [ ] **Step 6: Commit**

```bash
git add recipe_import.py tests/test_recipe_import_draft.py
git commit -m "Add recipe import orchestration (fetch_page, build_import_draft)"
```

---

### Task 7: FastAPI route

**Files:**
- Modify: `main.py:35-37` (schemas import), `main.py:628` (insert new route)
- Test: `tests/test_main_recipes_import.py`

**Interfaces:**
- Consumes: `recipe_import.build_import_draft` (Task 6), `schemas.ImportRecipeRequest`/`RecipeImportDraft` (Task 2), `auth.get_current_user` (existing).
- Produces: `POST /recipes/import` — auth-protected, request body `{"url": str}`, response `RecipeImportDraft`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_main_recipes_import.py
from fastapi.testclient import TestClient

import main
from auth import get_current_user
from main import app
from schemas import RecipeImportDraft


class _FakeUser:
    id = "00000000-0000-0000-0000-000000000000"


def _override_current_user():
    return _FakeUser()


def test_import_recipe_returns_draft(monkeypatch):
    async def fake_build_import_draft(url):
        assert url == "https://example.com/recipe"
        return RecipeImportDraft(
            name="Test Recipe",
            servings=2.0,
            image_url=None,
            ingredients=[],
            source_url=url,
        )

    monkeypatch.setattr(main, "build_import_draft", fake_build_import_draft)
    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        client = TestClient(app)
        res = client.post(
            "/recipes/import", json={"url": "https://example.com/recipe"}
        )
        assert res.status_code == 200
        body = res.json()
        assert body["name"] == "Test Recipe"
        assert body["servings"] == 2.0
        assert body["ingredients"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_import_recipe_requires_auth():
    client = TestClient(app)
    res = client.post("/recipes/import", json={"url": "https://example.com/recipe"})
    assert res.status_code in (401, 403)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./venv/bin/pytest tests/test_main_recipes_import.py -v`
Expected: FAIL — `404 Not Found` (route doesn't exist yet) on the first test.

- [ ] **Step 3: Wire the schemas import**

In `main.py`, change the `RecipeCreateRequest, RecipeUpdateRequest, RecipeResponse,` line (line 35) to:

```python
    RecipeCreateRequest, RecipeUpdateRequest, RecipeResponse,
    ImportRecipeRequest, RecipeImportDraft,
```

- [ ] **Step 4: Add the `build_import_draft` import**

Immediately after the existing `from usda import search_foods, get_food, get_foods_bulk, extract_nutrients` line (line 43), add:

```python
from recipe_import import build_import_draft
```

- [ ] **Step 5: Add the route**

Insert immediately after `create_recipe`'s closing `return result.scalar_one()` (after line 627, before the blank lines preceding `@app.get("/recipes", ...)`):

```python

@app.post("/recipes/import", response_model=RecipeImportDraft)
async def import_recipe(
    payload:      ImportRecipeRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Fetch a blog URL and return a draft recipe with ingredients matched
    to USDA foods. Nothing is saved — the frontend opens this in the
    recipe builder for review before the user calls POST /recipes.
    """
    return await build_import_draft(payload.url)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `./venv/bin/pytest tests/test_main_recipes_import.py -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Run the full backend test suite**

Run: `./venv/bin/pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 8: Commit**

```bash
git add main.py tests/test_main_recipes_import.py
git commit -m "Add POST /recipes/import route"
```

---

### Task 8: Frontend — Import from URL

**Files:**
- Modify: `pakupaku-frontend/src/components/RecipeBuilder.tsx`
- Test: `pakupaku-frontend/src/components/RecipeBuilder.test.tsx`

**Interfaces:**
- Consumes: `POST /recipes/import` (Task 7), reusing existing `IngredientRow`/`blankRow()`/`NutrientData` types already in this file.
- Produces: an "Import from URL" control that pre-fills the existing recipe form; no changes to `handleSave`'s request shape or the `POST`/`PATCH /recipes` calls.

- [ ] **Step 1: Write the failing test**

```tsx
// pakupaku-frontend/src/components/RecipeBuilder.test.tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import RecipeBuilder from "./RecipeBuilder";

const draft = {
  name: "Test Pancakes",
  servings: 4,
  image_url: null,
  source_url: "https://example.com/pancakes",
  ingredients: [
    {
      raw_line: "2 cups flour",
      quantity: 2,
      unit: "cup",
      food_name: "flour",
      best_match: {
        fdc_id: 123456,
        description: "Flour, wheat, all-purpose",
        brand: null,
        calories_per_100g: 364,
        protein_per_100g: 10,
        fat_per_100g: 1,
        carbs_per_100g: 76,
        fiber_per_100g: 2.7,
        portions_map: { cup: 125 },
      },
      alternates: [],
    },
  ],
};

beforeEach(() => {
  localStorage.setItem("token", "test-token");
  global.fetch = jest.fn((url: RequestInfo | URL) => {
    const u = String(url);
    if (u === "/recipes") {
      return Promise.resolve({ ok: true, json: async () => [] } as Response);
    }
    if (u === "/recipes/import") {
      return Promise.resolve({ ok: true, json: async () => draft } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("importing a URL pre-fills the recipe form", async () => {
  render(<RecipeBuilder onBack={() => {}} />);

  const urlInput = screen.getByPlaceholderText("https://example.com/some-recipe");
  fireEvent.change(urlInput, {
    target: { value: "https://example.com/pancakes" },
  });
  fireEvent.click(screen.getByText("Import"));

  await waitFor(() => {
    expect(screen.getByDisplayValue("Test Pancakes")).toBeInTheDocument();
  });
  expect(screen.getByDisplayValue("Flour, wheat, all-purpose")).toBeInTheDocument();
  expect(screen.getByDisplayValue("2")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run (from `pakupaku-frontend/`): `CI=true npx react-scripts test RecipeBuilder --watchAll=false`
Expected: FAIL — cannot find placeholder text "https://example.com/some-recipe" (control doesn't exist yet).

- [ ] **Step 3: Add import-draft types**

In `RecipeBuilder.tsx`, immediately after the `interface RecipeResponse { ... }` block (ends around line 149), add:

```tsx
interface ImportedIngredientCandidate extends NutrientData {
  fdc_id:      number;
  description: string;
  brand:       string | null;
  portions_map: Record<string, number>;
}

interface ImportedIngredient {
  raw_line:   string;
  quantity:   number;
  unit:       string;
  food_name:  string;
  best_match: ImportedIngredientCandidate | null;
  alternates: ImportedIngredientCandidate[];
}

interface RecipeImportDraft {
  name:        string;
  servings:    number;
  image_url:   string | null;
  ingredients: ImportedIngredient[];
  source_url:  string;
}

function rowFromImportedIngredient(ing: ImportedIngredient): IngredientRow {
  const match = ing.best_match;
  return {
    mode: match ? "search" : "custom",
    query: match ? match.description : ing.food_name,
    suggestions: [], showDropdown: false,
    brandSuggestions: [], showBrandDropdown: false,
    fdc_id: match ? match.fdc_id : null,
    food_name: match ? match.description : ing.food_name,
    brand_name: match?.brand ?? "",
    calories_per_100g: match?.calories_per_100g ?? null,
    protein_per_100g:  match?.protein_per_100g  ?? null,
    fat_per_100g:      match?.fat_per_100g      ?? null,
    carbs_per_100g:    match?.carbs_per_100g    ?? null,
    fiber_per_100g:    match?.fiber_per_100g    ?? null,
    portionsMap: match?.portions_map ?? {},
    amount: String(ing.quantity),
    unit: ing.unit,
  };
}
```

- [ ] **Step 4: Add import state and the `startImport` handler**

In the `RecipeBuilder` component, immediately after the existing `const [editingId, setEditingId] = useState<string | null>(null);` line, add:

```tsx
  const [importUrl, setImportUrl]           = useState("");
  const [importing, setImporting]           = useState(false);
  const [importImageUrl, setImportImageUrl] = useState<string | null>(null);
```

Immediately before `const handleSave = async () => {`, add:

```tsx
  const startImport = async () => {
    if (!importUrl.trim()) {
      setError("Enter a recipe URL to import.");
      return;
    }
    setError(""); setMessage(""); setImporting(true);
    try {
      const token = localStorage.getItem("token");
      const res = await fetch("/recipes/import", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: token ? `Bearer ${token}` : "",
        },
        body: JSON.stringify({ url: importUrl.trim() }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        throw new Error(body?.detail || "Couldn't import that recipe.");
      }
      const draft: RecipeImportDraft = await res.json();

      setEditingId(null);
      setName(draft.name);
      setServings(String(draft.servings));
      setDescription("");
      setImportImageUrl(draft.image_url);
      setIngredients(
        draft.ingredients.length > 0
          ? draft.ingredients.map(rowFromImportedIngredient)
          : [blankRow()]
      );
      setImportUrl("");
      setMessage("Recipe imported — review the ingredients below, then save.");
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err: any) {
      setError(err.message || "Unable to import that recipe.");
    } finally {
      setImporting(false);
    }
  };

```

- [ ] **Step 5: Clear the imported image on cancel/save**

In `cancelEdit`, add `setImportImageUrl(null);` alongside its existing `setIngredients([blankRow()]);` line.

In `handleSave`'s success branch, add `setImportImageUrl(null);` alongside its existing `setIngredients([blankRow()]);` line (in the `finally`-preceding block, after `setEditingId(null);`).

- [ ] **Step 6: Add the Import UI**

In the JSX, immediately after the closing `</header>` tag and before `<section className="recipe-form-section">`, add:

```tsx
        <section className="recipe-form-section">
          <div className="recipe-form-card">
            <label className="recipe-field">
              <span>Import from a recipe blog URL</span>
              <div className="recipe-field-inline">
                <input
                  type="url"
                  value={importUrl}
                  onChange={e => setImportUrl(e.target.value)}
                  placeholder="https://example.com/some-recipe"
                />
                <button
                  type="button"
                  className="add-ingredient-button"
                  onClick={startImport}
                  disabled={importing}
                >
                  {importing ? "Importing…" : "Import"}
                </button>
              </div>
            </label>
            {importImageUrl && (
              <img src={importImageUrl} alt="" className="recipe-import-image" />
            )}
          </div>
        </section>

```

(This adds a second `<section className="recipe-form-section">` above the existing one — the existing section immediately below is untouched.)

- [ ] **Step 7: Add the small new CSS rule**

In `RecipeBuilder.css`, append:

```css

.recipe-import-image {
  max-width: 200px;
  border-radius: 8px;
  margin-top: 0.75rem;
}
```

- [ ] **Step 8: Run the test to verify it passes**

Run (from `pakupaku-frontend/`): `CI=true npx react-scripts test RecipeBuilder --watchAll=false`
Expected: PASS

- [ ] **Step 9: Run the full frontend test suite to confirm nothing broke**

Run (from `pakupaku-frontend/`): `CI=true npx react-scripts test --watchAll=false`
Expected: all tests pass

- [ ] **Step 10: Manual verification in the browser**

Start the backend (`uvicorn main:app --reload`) and frontend (`npm start` in `pakupaku-frontend/`), log in, open the recipe builder, and paste a real recipe blog URL (try one you know has visible ingredients). Confirm:
- The form pre-fills with a name, servings, and ingredient rows.
- Each ingredient row's amount/unit and matched food look reasonable and are still editable.
- Saving the imported (possibly edited) recipe works exactly as it does for a manually-built one.
- An invalid URL shows the inline error message instead of crashing the page.

- [ ] **Step 11: Commit**

```bash
git add pakupaku-frontend/src/components/RecipeBuilder.tsx \
  pakupaku-frontend/src/components/RecipeBuilder.test.tsx \
  pakupaku-frontend/src/components/RecipeBuilder.css
git commit -m "Add Import from URL to RecipeBuilder"
```
