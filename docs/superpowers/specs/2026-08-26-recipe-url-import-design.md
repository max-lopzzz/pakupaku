# Recipe URL Import — Design

## Problem

Building a custom recipe in PakuPaku today means manually searching USDA
for every ingredient and typing in an amount, one row at a time in
`RecipeBuilder`. Users who find a recipe on a blog have to retype the
whole ingredient list by hand.

This feature lets a user paste a blog URL and get a recipe draft —
name, servings, photo, and ingredients pre-matched to USDA foods with
amounts already converted to grams — opened directly in the existing
`RecipeBuilder` review screen, where they can fix anything before
saving.

## Goals / non-goals

- **Goal:** turn a blog URL into a pre-filled, editable recipe draft in
  `RecipeBuilder`. Saving still goes through the existing
  `POST /recipes` / `PATCH /recipes/{id}` flow, unchanged.
- **Goal:** work on the common case (schema.org `Recipe` JSON-LD, which
  most recipe blogs publish for SEO) without calling an LLM, and fall
  back to an LLM only when that markup is missing.
- **Non-goal:** no vision/OCR extraction. The blog's photo is only used
  for display (pulled from `og:image` / JSON-LD `image`), never
  analyzed.
- **Non-goal:** no background job queue. The import is one synchronous
  request; ingredient USDA lookups run concurrently within it to keep
  latency reasonable.
- **Non-goal:** no rate limiting on the new endpoint in this pass.

## Existing pieces this reuses (unchanged)

- [`models.py`](../../../models.py) `Recipe` / `RecipeIngredient`,
  [`schemas.py`](../../../schemas.py) `RecipeCreateRequest` /
  `RecipeIngredientRequest`, and the `POST/PATCH /recipes` handlers in
  [`main.py`](../../../main.py) — recipe persistence is not touched.
- [`usda.py`](../../../usda.py) `search_foods()` — ingredient matching
  reuses this as-is.
- [`RecipeBuilder.tsx`](../../../pakupaku-frontend/src/components/RecipeBuilder.tsx)
  — `UNIT_TO_G`, `toGrams()`, `scale()`, and the per-100g `IngredientRow`
  state shape are reused unchanged. `startEdit()` already shows the
  pattern for turning a nutrient payload into `IngredientRow[]`; the
  import flow adds a sibling function that does the same from a draft
  instead of a saved `RecipeResponse`.

## Data flow

```
blog URL
  → fetch HTML (httpx)
  → try schema.org/JSON-LD Recipe markup
      found  → {name, servings, image_url, ingredient_lines[]}
      absent → send visible page text to LLM fallback
               → {name, servings, image_url, ingredient_lines[]}
  → parse each ingredient_line → {quantity, unit, food_name}
      (regex for common patterns; LLM fallback per-line if regex can't split it)
  → for each parsed ingredient, concurrently call usda.search_foods(food_name)
      → take top candidate (+ up to 4 alternates) per ingredient
  → assemble RecipeImportDraft, return to frontend (nothing saved yet)
  → frontend opens RecipeBuilder pre-filled from the draft
  → user reviews/edits rows exactly like manual entry
  → existing POST /recipes saves it (unchanged)
```

## Backend

### New module: `recipe_import.py`

- `fetch_page(url: str) -> str` — `httpx.AsyncClient` GET with a
  browser-like `User-Agent` and a timeout; raises `HTTPException(422)`
  on fetch failure (dead link, blog blocks bots, non-HTML response).
- `extract_structured_recipe(html: str) -> Optional[RawRecipe]` —
  parses `<script type="application/ld+json">` blocks, looks for a
  `@type: "Recipe"` object (handling the common `@graph` wrapper), and
  reads `name`, `recipeIngredient`, `recipeYield`, `image`. Returns
  `None` if no valid Recipe object is found.
- `extract_recipe_via_llm(html: str) -> Optional[RawRecipe]` — strips
  HTML to visible text (reuse `BeautifulSoup.get_text()`), sends it to
  the configured LLM with a prompt constraining output to
  `{name, servings, ingredient_lines: [str], image_url}` as JSON.
  Called only when `extract_structured_recipe` returns `None`.
- `parse_ingredient_line(line: str) -> ParsedIngredient` —
  regex-based `{quantity, unit, food_name}` parser covering
  "2 cups flour", "1/2 tsp salt", "3 large eggs", "1 clove garlic,
  minced" (trailing prep notes after a comma are dropped from
  `food_name`). Unit is normalized to the same unit strings
  `RecipeBuilder`'s `UNIT_TO_G` already understands (`g`, `ml`, `oz`,
  `cup`, `tbsp`, `tsp`); anything else is passed through as a natural
  unit (e.g. `clove`, `slice`) the same way `RecipeBuilder` already
  handles USDA `portionsMap` units. On regex failure, one LLM call
  parses just that line into the same shape.
- `match_ingredient(parsed: ParsedIngredient) -> IngredientMatch` —
  calls `usda.search_foods(parsed.food_name, page_size=5)`, ranks
  results (prefer `Foundation`/`SR Legacy` data types, then string
  similarity to `food_name`), returns the top match plus alternates.
- `build_import_draft(url: str) -> RecipeImportDraft` — orchestrates
  the above; ingredient parsing + matching for all lines runs via
  `asyncio.gather`.

### New schemas (`schemas.py`)

```python
class ImportRecipeRequest(BaseModel):
    url: str

class ImportedIngredientCandidate(BaseModel):
    fdc_id: int
    description: str
    brand: Optional[str] = None
    calories_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    fiber_per_100g: Optional[float] = None
    portions_map: dict[str, float] = {}  # USDA food-specific unit -> grams

class ImportedIngredient(BaseModel):
    raw_line: str
    quantity: float
    unit: str
    food_name: str
    best_match: Optional[ImportedIngredientCandidate] = None
    alternates: List[ImportedIngredientCandidate] = []

class RecipeImportDraft(BaseModel):
    name: str
    servings: float
    image_url: Optional[str] = None
    ingredients: List[ImportedIngredient]
    source_url: str
```

`ImportedIngredientCandidate` mirrors the `FoodSuggestion` shape
`RecipeBuilder` already builds from USDA search results (same nutrient
fields, plus `portions_map`), so the frontend can drop it straight into
`IngredientRow` without reshaping.

### New route (`main.py`)

```python
@app.post("/recipes/import", response_model=RecipeImportDraft)
async def import_recipe(
    payload: ImportRecipeRequest,
    current_user: User = Depends(get_current_user),
):
```

Auth-protected like the rest of `/recipes`. Returns the draft; does
**not** write to the database. Errors:

- `422` — URL couldn't be fetched, or no recipe could be extracted
  (neither JSON-LD nor LLM fallback produced ingredients).
- `503` — LLM fallback needed but not configured (missing API key),
  mirroring how `usda.py` handles a missing `USDA_API_KEY`.
- `502` — LLM fallback needed, is configured, but the request to it
  failed or timed out.

### Config (`config.py`)

```python
LLM_API_KEY  = os.getenv("LLM_API_KEY")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.together.xyz/v1")
LLM_MODEL    = os.getenv("LLM_MODEL", "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo")
```

Together.ai is the recommended default host (OpenAI-compatible chat
API, so the client code is a plain `httpx` POST — no new SDK
dependency); any OpenAI-compatible open-weight provider works by
changing `LLM_BASE_URL`/`LLM_MODEL`.

## Frontend

### Entry point

A new "Import from URL" control on `RecipeBuilder`'s header (next to
"Save recipe"): a URL text input + "Import" button. On click:

1. `POST /recipes/import` with the URL, show a loading state (this can
   take a few seconds — page fetch + possibly an LLM call + N USDA
   lookups).
2. On success, call a new `startImport(draft: RecipeImportDraft)`
   function — a sibling to the existing `startEdit()` — that sets
   `name`, `servings`, and builds `IngredientRow[]` from
   `draft.ingredients` (using each `best_match`'s nutrient/portions
   data, `quantity` as `amount`, `unit` as `unit`), leaving
   `editingId` unset so Save creates a new recipe. Rows with no
   `best_match` start in `custom` mode with the parsed `food_name`
   filled in and nutrients blank, so the user notices and fixes them.
   The image URL is shown above the form (display only — not part of
   `RecipeCreateRequest`, so it's dropped on save, matching today's
   schema).
3. On failure, show the error inline (same `setError` pattern already
   used) — user can still build the recipe manually.

No changes to `handleSave`, `startEdit`, or the saved-recipes list.

## Error handling summary

| Failure | Behavior |
|---|---|
| URL unreachable / not HTML | `422` from backend, shown inline, user can retry or go manual |
| No JSON-LD and LLM fallback also finds nothing | `422`, same as above |
| LLM configured but request fails/times out | `502` from backend with a clear message; if JSON-LD *did* find a recipe but a line-level LLM parse fails, that one line still comes back with `best_match: null` rather than failing the whole import |
| USDA search errors for one ingredient | that ingredient comes back with `best_match: null` and empty `alternates`; rest of the draft still returns |
| LLM not configured (`LLM_API_KEY` unset) and JSON-LD absent | `503`, same convention as `usda.py`'s missing-key handling |

## Testing

- **Backend unit tests:** `extract_structured_recipe` against a couple
  of fixture HTML snippets (with JSON-LD, with `@graph`-wrapped
  JSON-LD, without any) — `tests/fixtures/recipe_blog_*.html`.
  `parse_ingredient_line` against a table of representative strings.
  `match_ingredient` and `extract_recipe_via_llm` with the USDA client
  and LLM HTTP call mocked.
- **Frontend test:** given a mocked `RecipeImportDraft` response,
  `startImport` produces the expected `IngredientRow[]`/`name`/
  `servings` state (extending `App.test.tsx`'s existing patterns).
- **Manual:** run the import against 2-3 real recipe blog URLs
  end-to-end (one with JSON-LD, one without, if a suitable example is
  found) and confirm the review screen looks sane before saving.
