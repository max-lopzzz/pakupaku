# Bulk Recipe Import — Design

## Problem

`recipe_import.py` already turns one blog URL into one recipe draft
(`build_import_draft()`): fetch the page, extract via schema.org
JSON-LD or an LLM fallback, parse and USDA-match every ingredient line,
return a `RecipeImportDraft` for review — nothing saved until the admin
(or any user, for personal recipes) reviews it in `RecipeBuilder.tsx`
and calls `POST /recipes`.

Populating the shared recipe library (added in the
[shared-recipes design](2026-08-27-shared-recipes-design.md)) one URL at
a time doesn't scale for an admin who wants to seed it from an existing
recipe blog. This adds a bulk path: paste a link to a blog's index/
category/archive page, discover the individual recipe posts linked from
it, run the *existing* per-URL extraction pipeline over each one, and
let the admin review/save them one at a time.

## Goals / non-goals

- **Goal:** given one blog index URL, find the individual recipe post
  URLs linked from it and extract a draft for each, reusing
  `build_import_draft()` unchanged — no new extraction logic, only new
  discovery and orchestration around the existing pipeline.
- **Goal:** admin sees the candidate link count before the (potentially
  slow, LLM-calling) extraction pass runs, and confirms before it starts.
- **Goal:** review and save each extracted draft through the same
  ingredient-matching/editing UI single-recipe import already uses,
  one at a time, defaulting to shared.
- **Non-goal:** a link-count cap. Every same-domain candidate the
  discovery filter finds gets attempted; concurrency is bounded instead
  (see Backend below) so a link-heavy page can't hammer the source site
  or the LLM provider all at once, but there's no hard ceiling on batch
  size.
- **Non-goal:** streaming/progress feedback during extraction. The admin
  waits for the whole batch synchronously, same request/response shape
  as every other route in this app. A streaming mechanism (SSE/
  WebSocket) would be new infrastructure this codebase doesn't have
  anywhere else, for a UX nicety this feature doesn't need at v1.
- **Non-goal:** following pagination ("next page") links automatically.
  One index page's links per run; an admin covering a blog with many
  archive pages runs the tool again with the next page's URL.
- **Non-goal:** auto-classifying which links are recipes via an LLM
  call. A same-domain + URL-shape heuristic filter picks candidates;
  the *existing* extraction pipeline is the real recipe/non-recipe
  filter, since it already fails cleanly (`HTTPException(422)`) on a
  page with no recipe — reusing that instead of building a second,
  separate classifier.

## Backend

New module `recipe_bulk_import.py`, built on top of `recipe_import.py`
without modifying it.

### Discovery

```python
async def discover_recipe_links(index_url: str) -> List[str]
```

- Fetches `index_url` via `recipe_import.py`'s existing `fetch_page()`
  (unchanged — same SSRF host validation, same redirect handling, same
  timeout/error behavior admins already see from single-recipe import).
- Parses every `<a href>` with BeautifulSoup, resolves relative URLs
  with `urljoin(index_url, href)`.
- Keeps a link only if:
  - its host matches `index_url`'s host (cross-domain links — ads,
    social share buttons, footer links to other sites — are dropped)
  - it isn't `index_url` itself and isn't a bare fragment (`#...`)
  - its path doesn't match a common non-post shape: `/tag/`,
    `/category/`, `/author/`, `/page/\d+`, `/search`, or a non-HTML
    file extension (`.jpg`, `.png`, `.pdf`, `.xml`, etc.)
- Dedupes (a post is often linked twice — title and "read more").
- Returns the deduped list, in the order first encountered on the page.

This filter is deliberately permissive: false negatives (silently
missing a real recipe link) are worse than false positives (letting a
non-recipe link through), because a false positive is caught for free
by the next step, and a false negative isn't caught at all.

### Extraction

```python
async def bulk_extract_drafts(urls: List[str]) -> List[RecipeImportDraft]
```

- Runs `build_import_draft(url)` (unchanged, from `recipe_import.py`)
  over every URL, concurrency-bounded to 5 in-flight extractions via an
  `asyncio.Semaphore` — enough to be fast on a normal batch, low enough
  not to hammer the source site or the LLM endpoint on a link-heavy one.
- Each call is wrapped to catch `HTTPException` (no recipe found, fetch
  failed, timeout, private-address rejection, anything
  `build_import_draft` already raises for a single import) and drop
  that URL from the results — mirroring the `_safe_match_ingredient`
  pattern already in `recipe_import.py`, for the same reason: one bad
  URL can't be allowed to sink the whole batch.
- Returns only the successful drafts. Each `RecipeImportDraft` already
  carries its own `source_url` (existing field), so the review queue
  can show which page each draft came from.
- **Known risk, to verify during implementation rather than assume
  away:** Render's free-tier HTTP proxy may have a response timeout
  shorter than a large uncapped batch could take in the worst case
  (candidates × up to ~40s each, partly offset by concurrency=5). If
  real testing against a large batch shows this is a problem, the fix
  is revisiting the "synchronous wait is fine" decision below — not
  something to silently hope works in production.

### Routes

Both new, in `main.py`, both admin-gated the same way `is_shared`
already is (`403` unless `current_user.is_admin`):

- **`POST /recipes/bulk-import/discover`** — body `{url: str}` →
  `{urls: List[str]}`. Calls `discover_recipe_links(url)`.
- **`POST /recipes/bulk-import/extract`** — body `{urls: List[str]}` →
  `{drafts: List[RecipeImportDraft]}`. Calls `bulk_extract_drafts(urls)`.
  Reuses the existing `RecipeImportDraft` schema unchanged.

Splitting discovery and extraction into two calls is what makes the
"show the count, then confirm" UI possible. Neither route saves
anything — saving still goes through the existing `POST /recipes`, one
draft at a time, exactly as single-recipe import already works.

## Frontend

### `RecipeEditForm.tsx` (new, extracted from `RecipeBuilder.tsx`)

`RecipeBuilder.tsx` already has the entire per-recipe editing UI this
feature needs for its review queue: ingredient rows with USDA
autocomplete/alternates (including this session's branded-food dedup
fix), the diet-tag grid, image/source/instructions fields, and the
admin-only `is_shared` checkbox. Rather than duplicate that logic —
which is real, non-trivial matching/state logic, not boilerplate — it
moves into a shared `RecipeEditForm.tsx` component taking a draft (or
existing recipe) plus a save callback as props. `RecipeBuilder.tsx`
renders it for its own add/edit/single-import flows; the new bulk-import
queue renders it per draft. This is a refactor of existing, working
code, done because the alternative (forking the ingredient-matching UI)
would be real duplication, not because the file needed a scope-creeping
rewrite — behavior for `RecipeBuilder.tsx`'s existing flows must not
change.

### `BulkRecipeImport.tsx` (new)

- Entry point: a "Bulk Import" button on `Dashboard.tsx`, visible only
  when `userProfile.is_admin` — same visibility guard already used for
  the `is_shared` checkbox.
- **Discovery step:** URL input + "Find Recipes" button, calls
  `POST /recipes/bulk-import/discover`, shows "Found N candidate links"
  with Extract / Cancel. Zero links found shows "No recipe links found
  on that page — for a single recipe, use Import instead" rather than a
  bare empty state.
- **Extraction step:** "Extract" calls
  `POST /recipes/bulk-import/extract`, shows a loading state for the
  whole batch (no incremental progress, per the non-goal above). Zero
  successful drafts shows "Found 0 recipes in that batch" rather than
  an empty review queue.
- **Review queue:** one `RecipeEditForm` at a time ("Recipe 3 of 12"),
  pre-filled from the draft, `is_shared` pre-checked (unlike
  single-recipe import, where it defaults unchecked — the whole point
  of this feature is populating the shared library, so the common case
  needs no extra click, but it's still per-recipe editable). Save &
  Next calls `POST /recipes` then advances; Skip & Next just advances.
  Ends in a summary: "Saved X of Y."

## Testing

- **Backend:**
  - `discover_recipe_links` against fixture HTML: same-domain filtering,
    dedup, exclusion of tag/category/author/pagination-shaped URLs,
    rejection of cross-domain links.
  - `bulk_extract_drafts` with `build_import_draft` mocked: some URLs
    succeed, some raise `HTTPException`, confirm failures are dropped
    and successes are returned; confirm concurrency never exceeds the
    configured bound.
  - `POST /recipes/bulk-import/discover` and `/extract`: `403` for a
    non-admin, happy path for an admin, empty-result shapes for both.
- **Frontend:**
  - `RecipeEditForm` extraction is behavior-preserving: `RecipeBuilder.tsx`'s
    existing add/edit/single-import tests continue passing unchanged
    after the refactor — this is the part to be most careful with,
    since it's a refactor of working code, not new functionality.
  - `BulkRecipeImport.tsx`: discover → count shown → extract → queue
    navigation → save/skip → final summary.
