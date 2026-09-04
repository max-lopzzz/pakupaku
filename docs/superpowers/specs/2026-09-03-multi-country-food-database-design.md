# Multi-Country Averaged Food Database — Design

## Problem

Recipe import matches parsed ingredient names against the live USDA
FoodData Central search API (`recipe_import.py::match_ingredient`), and
the same `/foods/search` endpoint backs the manual ingredient
autocomplete in `RecipeEditForm.tsx` and food logging in
`Dashboard.tsx`. The matching heuristic is weak and the underlying data
is dirty, producing wrong matches in the wild:

- **Nonsensical branded matches.** "water" → *WATER, IGA (Iga, Inc.)* at
  ~10,000 kcal/100 g; 210 ml of it logged as 21,168 kcal. USDA's Branded
  Foods dataset routinely stores per-serving values as per-100 g, mislabels
  units, and carries data-entry errors, and nothing rejects a physically
  impossible calorie value.
- **Branded chosen over generic.** *McIlhenny Company POTATOES*,
  *Wal-Mart Stores, Inc. BROCCOLI*, *WENDY'S Frosty Dairy Dessert* for
  plain recipe ingredients, because `match_ingredient` pulls only 5
  results, never restricts to generic data types, and `rank_candidates`
  is a two-bucket sort (`Foundation`/`SR Legacy` first, *everything else
  including Branded* second) with no lexical agreement check against the
  query.

Hardening the live-search heuristic reduces but never eliminates this —
it stays dependent on USDA's relevance ranking, USDA's data quality, and
the FDC API being reachable and fast on every import.

This spec replaces live USDA lookups with a **pre-built, offline,
multi-country averaged generic-food database**: one canonical entry per
food, each nutrient the median across the national food-composition
tables that report it, shipped in the repo as a compact artifact and
loaded into a `foods` table at deploy time. All three flows (recipe
import, ingredient autocomplete, food logging) search this table.

## Goals / non-goals

- **Goal:** one generic entry per food, nutrients averaged across
  national food-composition tables from multiple continents, with an
  ingest-time sanity filter that drops physically impossible values.
- **Goal:** fully offline at runtime — no external food API on any
  request path. A parsed ingredient with no match comes back as an
  unmatched row for manual entry.
- **Goal:** the generic DB is the single food source — recipe import,
  `RecipeEditForm` autocomplete, and `Dashboard` logging all query it;
  `usda.py` is retired from request paths.
- **Goal:** deterministic, reproducible build — same sources in, same
  `foods` artifact out, with human conflict-resolution decisions
  checked into the repo.
- **Goal:** every source's licence permits redistribution *and*
  commercial use (PakuPaku has paid membership), with attribution
  carried in the repo and surfaced in-app.
- **Non-goal:** national tables that can't be redistributed or that are
  non-commercial-only — Japan (MEXT), China (CDC), South Africa
  (SAFOODS), and any CC BY-NC FAO regional table are **excluded**.
- **Non-goal:** re-deriving historical `food_logs` / `recipe_ingredients`
  rows. They already store denormalised calories/macros and render
  unchanged forever; only re-editing an old row requires re-picking the
  food.
- **Non-goal:** per-user country weighting or preference.
- **Non-goal:** automated source refresh. National tables update every
  few years; rebuilding is a manual, documented operation.
- **Non-goal:** a DB-engine full-text/trigram dependency. Matching is
  pure-Python over an in-memory index so it is identical on Neon
  Postgres, desktop SQLite, and Capacitor SQLite.

## Architecture

```
  build time (manual, occasional)
  ────────────────────────────────
  raw source files (not committed)
    USDA FDC · CoFID · CIQUAL · AFCD · CNF · Frida · FAO regional*
        │  per-source extractor  →  normalised rows
        ▼
  scripts/build_food_db/
    normalise names → English canonical + prep_state
    fuzzy-match foods across sources (rapidfuzz)
    conflicts → review CSV → human decisions (committed)
    per-nutrient sanity filter → drop impossible values
    aggregate: median across sources (mean when only 2)
    attach USDA FNDDS household portions by name
        │
        ▼
  data/foods.sqlite   (committed, ~2–5 MB, ~15k rows)
  docs/food-data-sources.md   (sources, versions, licences, attribution)

  deploy / runtime
  ────────────────
  data/foods.sqlite ──seed──▶ foods table (Neon PG / desktop SQLite / Capacitor SQLite)
                                   │
                     load ~15k rows into memory on API startup
                                   │
        ┌──────────────────────────┼───────────────────────────┐
   match_ingredient()      GET /foods/search           GET /foods/{food_id}
   (recipe import)     (RecipeEditForm, Dashboard)     (portion lookup)
```

\* FAO regional tables included only if their licence clears commercial
redistribution — see below.

## Sources & licensing

Included only if the licence permits **redistribution + commercial use +
attribution**. Each is recorded in `docs/food-data-sources.md` with
version, retrieval URL, licence, and the exact attribution string the
licence requires.

| Region | Source | Licence | Status |
|---|---|---|---|
| US | USDA FoodData Central — Foundation, SR Legacy, FNDDS | Public domain | **Included** |
| UK | CoFID (McCance & Widdowson's *The Composition of Foods*) | Open Government Licence v3 | **Included** |
| France | CIQUAL (ANSES) | Licence Ouverte / Etalab 2.0 | **Included** |
| Australia | Australian Food Composition Database (FSANZ) | CC BY 3.0 AU | **Included** |
| Canada | Canadian Nutrient File | Open Government Licence – Canada | **Included** |
| Denmark | Frida (DTU National Food Institute) | Free reuse w/ citation | **Included** |
| West Africa | FAO/INFOODS West African Food Composition Table | **Verify** — several FAO datasets are CC BY-NC | Pending licence check |
| Central/East Africa | FAO/INFOODS FCT for Central & Eastern Africa | **Verify** | Pending licence check |
| SE Asia | FAO/INFOODS ASEAN Food Composition Database | **Verify** | Pending licence check |
| South Korea | Korea Food Composition Database (RDA / data.go.kr) | Likely KOGL Type 1 (commercial OK) | **Verify**, then include |

**Excluded (cannot redistribute or NC-only):** Japan MEXT Standard
Tables, China CDC food composition tables, South Africa SAFOODS/SAMRC,
New Zealand FOODfiles.

The pending rows are resolved during implementation: each is either
promoted to **Included** with its attribution string recorded, or
dropped. North America + Europe + Oceania coverage does not depend on
any pending row.

### Attribution

Licences that require attribution (all except USDA public domain) get
their required credit line in:

1. `docs/food-data-sources.md` (full detail), and
2. an in-app credits surface — a "Food data sources" line in Settings,
   listing each source and licence.

## Aggregation method

### Cross-source food identity

Every source row is normalised to a **canonical key**:

- English name. Sources that publish English or INFOODS names
  (USDA, CoFID, AFCD, CNF, FAO, CIQUAL bilingual export) use those;
  Korean names are translated via a committed translation table.
- Lowercased, punctuation-stripped, token-sorted.
- **Preparation state** (`raw` / `cooked` / `dried` / `unspecified`) is
  parsed from the name and kept as part of the identity — "potato, raw"
  and "potato, boiled" are different foods, never merged.

Rows whose canonical keys match exactly are the same food. Rows that
don't match exactly are compared with `rapidfuzz` token-set ratio; pairs
above a tuned threshold (starting point: 92) are candidate merges.

### Conflict review

A candidate merge is **auto-accepted** when the sources' per-nutrient
values agree within tolerance (starting point: ±25% relative, or within
a small absolute floor for trace nutrients). Otherwise the pair is
written to `scripts/build_food_db/review/conflicts.csv` with both names,
both nutrient vectors, and the ratio. A human resolves each row
(`merge` / `separate` / `rename`), and the resolved file
(`review/decisions.csv`) is **committed** so every subsequent rebuild is
deterministic. Unresolved conflicts fail the build.

### Sanity filter (before aggregation)

Each source value is dropped, per nutrient, if:

- `calories_per_100g` > 900 (pure fat is 884 kcal/100 g) or < 0
- any macro < 0, or `protein + fat + carbs + fiber` > 105 g/100 g
- `calories_per_100g` present but all macros zero/absent, or vice versa

A food with **≥ 2 surviving sources** for a given nutrient emits that
nutrient; a food with < 2 surviving sources for *every* nutrient is not
emitted at all (matches the "≥ 2 databases" rule).

### Averaging

Per nutrient, across the sources that survive the filter for that
food+nutrient:

- **median** when ≥ 3 sources
- **mean** when exactly 2 sources
- nutrient is `null` when < 2 sources

Nutrient set matches today's `extract_nutrients` output: calories,
protein_g, fat_g, carbs_g, fiber_g, sugar_g, sodium_mg, calcium_mg,
iron_mg, vitamin_c_mg, vitamin_d_mcg, vitamin_b12_mcg. National tables
vary in coverage; missing → `null`, same as today.

### Portions

National composition tables don't carry household measures. USDA FNDDS
(public domain) does. FNDDS portion rows (`1 cup`, `1 medium`,
`1 slice`, … → grams) are name-matched onto the canonical foods with the
same normalisation + fuzzy step. A food with no FNDDS match has only
mass/volume units available (`g`, `kg`, `oz`, `lb`, `ml`, `l`, and
`cup`/`tbsp`/`tsp` at water density); anything else prompts the user for
grams — the current `RecipeEditForm` / `Dashboard` behaviour when a
portion is unknown.

## Build pipeline

New directory `scripts/build_food_db/`:

```
scripts/build_food_db/
  README.md            fetch instructions + licence notes per source
  sources/
    usda.py            each: raw file(s) → list[NormalisedRow]
    cofid.py
    ciqual.py
    afcd.py
    cnf.py
    frida.py
    fao_regional.py
    korea.py
  normalise.py         name → canonical key + prep_state
  match.py             cross-source fuzzy matching → merge groups
  aggregate.py         sanity filter + median/mean
  portions.py          FNDDS name-match
  build.py             orchestrates; writes data/foods.sqlite
  review/
    conflicts.csv      generated, git-ignored
    decisions.csv      committed
  translations/
    korea_en.csv       committed
```

- Raw source files are **not committed** (size + licence). `README.md`
  documents where to download each and any format quirks (CIQUAL ships
  xlsx; some FAO tables are xlsx behind a PDF report; FNDDS is a large
  multi-file release — only the portion and food tables are needed).
- `build.py` is idempotent: same raw inputs + `decisions.csv` +
  `translations/` → byte-identical `data/foods.sqlite`.
- Output committed to the repo: `data/foods.sqlite`, one table `foods`
  (schema below), ~15k rows, roughly 2–5 MB. A gzipped JSONL fallback is
  acceptable if the SQLite file is awkward for the Capacitor seed step.
- Rebuild cadence: manual, when a source publishes a new edition.

## Runtime schema & matching

### `foods` table

Created in all three databases (Neon Postgres via `create_tables.py`;
desktop SQLite via the existing additive-migration path used in
`backend_entry.py`; Capacitor SQLite via a seeded copy shipped with the
mobile build).

| column | type | notes |
|---|---|---|
| `id` | TEXT PK | `gen:00001` … — namespaced, never collides with old int `fdc_id` |
| `canonical_name` | TEXT | display name |
| `aliases` | TEXT (JSON array) | alternate names from source rows, for matching |
| `category` | TEXT | coarse group (e.g. `vegetable`, `grain`) where a source provides one |
| `prep_state` | TEXT | `raw` / `cooked` / `dried` / `unspecified` |
| `calories_per_100g` … `vitamin_b12_mcg` | REAL nullable | the averaged nutrient set |
| `portions` | TEXT (JSON) | `[{ "unit": "cup", "grams": 120 }, …]`, may be `[]` |
| `source_ids` | TEXT (JSON array) | which sources contributed |
| `source_count` | INTEGER | ≥ 2 |

### In-memory match index

On API startup the process loads all `foods` rows and builds a
normalised-token index plus a `rapidfuzz` candidate pool (~15k rows is
small; well under a few MB resident). One module — `food_index.py` —
owns this and exposes:

- `search(query, limit) -> list[Food]` — exact canonical hit, then alias
  hits, then fuzzy, dedup, ranked; backs `GET /foods/search`.
- `best_match(name) -> Food | None` — top `search()` result above a
  confidence floor, else `None`; backs `match_ingredient`.

No Postgres `pg_trgm` / SQLite FTS — identical behaviour on every
deployment. Desktop and mobile builds run the same `food_index.py`
against their local `foods` table.

### Endpoint changes (`main.py`)

- `GET /foods/search` — same query params (`query`, `page_size`,
  `page_number`); results now come from `food_index.search()`. Response
  shape keeps `fdcId` → renamed `food_id` (string); `dataType` /
  `brandOwner` fields drop out (no brands). Frontend callers updated.
- `GET /foods/{food_id}` — path param becomes a string; returns the
  `foods` row including `portions`. Replaces the per-food USDA detail
  fetch and the `_fetch_portions_map` fallback dance in
  `recipe_import.py` (portions are now inline on the row).
- `POST /foods/bulk` — takes `list[str]` of `food_id`s.
- `recipe_import.py::match_ingredient` / `rank_candidates` /
  `_fetch_portions_map` / `_to_candidate` collapse to a call to
  `food_index.best_match()` plus the existing draft assembly. The
  sanity ceiling is now a build-time filter, so no impossible value can
  reach a draft.

### `usda.py`

Retired from request paths. `search_foods` / `get_food` /
`get_foods_bulk` move under `scripts/build_food_db/sources/usda.py` as a
build-time extractor (the FDC bulk download is preferred over the API
for the build; the API wrapper is kept only if convenient for FNDDS).
`USDA_API_KEY` drops from `config.py`, `.env.example`, and the
deployment runbook.

## ID migration

`food_logs.fdc_id` and `recipe_ingredients.fdc_id` currently hold USDA
integer IDs. Both become **`food_id TEXT`**, nullable.

- **Neon Postgres:** `ALTER TABLE … ALTER COLUMN fdc_id TYPE text USING
  fdc_id::text`, then `ALTER TABLE … RENAME COLUMN fdc_id TO food_id`.
  Existing integer values stringify (`173944` → `"173944"`). One-off
  migration SQL committed alongside, run once (same pattern as
  `migrate_fdc_to_spoonacular.sql`).
- **Desktop SQLite:** additive-migration path already in
  `backend_entry.py` — add `food_id TEXT`, copy `cast(fdc_id as text)`,
  keep the old column dormant (SQLite drop-column is fussy across
  versions).
- **`schemas.py`** — `fdc_id: int | None` → `food_id: str | None` on
  ingredient and log request/response models.
- **Frontend** — `fdc_id: number` → `food_id: string` in
  `RecipeEditForm.tsx`, `Dashboard.tsx`, `services/api.ts`, and shared
  types.

Existing rows keep their denormalised nutrients and render unchanged.
Editing an old row re-runs matching against the `foods` table and
re-links to a `gen:` id. No backfill from old `fdc_id` values.

## Repo changes summary

- **New:** `scripts/build_food_db/` (pipeline), `data/foods.sqlite`
  (artifact), `docs/food-data-sources.md`, `food_index.py`
  (runtime index), one Postgres migration SQL.
- **Changed:** `main.py` (`/foods*` routes), `recipe_import.py`
  (matching collapses to `food_index`), `schemas.py` (`fdc_id` →
  `food_id`), `config.py` / `.env.example` / `docs/deployment.md`
  (`USDA_API_KEY` removed), `create_tables.py` (seed `foods`),
  `backend_entry.py` (desktop `foods` seed + column migration),
  frontend `RecipeEditForm.tsx` / `Dashboard.tsx` / `services/api.ts`
  (`food_id`, response shape), mobile build (ship seeded `foods`).
- **Retired from runtime:** `usda.py` (moves to the build pipeline).

## Testing

- **Pipeline unit tests** (`tests/build_food_db/`): each source
  extractor against a small committed fixture slice; `normalise` key
  cases (prep-state parsing, punctuation, token sort); `aggregate`
  (median vs mean by source count, every sanity-filter rule, the
  `< 2 sources` drop); `portions` name-matching; a golden test that a
  fixed fixture set produces a fixed `foods` artifact.
- **`food_index` tests:** exact/alias/fuzzy ranking; `best_match`
  confidence floor returns `None` on junk; the reported bugs as
  regression cases — "water" resolves to a generic ~0 kcal entry,
  "broccoli"/"potatoes" resolve to generic entries, no result exceeds
  the calorie ceiling.
- **Route tests:** `/foods/search`, `/foods/{food_id}`, `/foods/bulk`
  against a seeded test `foods` table; `recipe_import` draft assembly
  end-to-end with a stub index.
- **Migration test:** a fixture DB with integer `fdc_id` rows migrates
  to string `food_id`, values preserved, old rows still render.
- **Frontend:** `RecipeEditForm` / `Dashboard` autocomplete tests
  updated for `food_id` strings and the brand-less response shape.

## Risks & open questions

- **FAO / Korea licences (blocking for those rows only).** Resolved
  during implementation; Africa/Asia coverage depends on the outcome.
  Everything else proceeds regardless.
- **Cross-source name reconciliation quality.** ~15k merged foods means
  a non-trivial `decisions.csv`. Mitigation: tune the auto-accept
  tolerance so the review list is hundreds, not thousands; ship the
  first version with a conservative threshold and grow coverage later.
- **Korean-name translation.** A committed translation table is a
  maintenance item; keep the Korean source's food list scoped to items
  that actually co-occur with ≥ 1 other source (the `≥ 2` rule prunes
  most of it anyway).
- **Artifact in git.** 2–5 MB binary in the repo. Acceptable; revisit
  Git LFS only if it grows past ~10 MB.
- **Desktop/mobile seed timing.** The Capacitor build must ship the
  `foods` table pre-seeded; wiring that into `build:ios` / `build:android`
  is part of implementation, not yet spec'd in detail.
