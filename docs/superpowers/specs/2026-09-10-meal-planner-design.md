# Meal Planner — Design

**Status:** approved design, not yet planned.
**Date:** 2026-09-10

## Goal

Generate a personalised meal plan for a user from (a) their stored
nutrition targets and (b) the recipe database, matching each day's plan
to the user's calorie **and** macro targets as closely as the available
recipes allow. The plan is persisted, individual meals can be swapped,
and each day can be logged to the food diary in one action.

## Decisions (from brainstorming)

| Question | Decision |
|---|---|
| Time span / structure | Configurable: **1–7 days**, **2–4 meals/day**, chosen per generation. |
| Recipe pool | Admin `is_shared` recipes **plus** the user's own recipes. |
| Diet filtering | New `User.diet_tags` field edited in Settings; the generate screen shows those as pre-ticked, per-run-overridable checkboxes. |
| Matching | Calories **and** macros (protein/fat/carbs). Best-of-random-search per day; recipe **servings are scaled** (fractional, clamped) to close the gap. |
| Meal-type appropriateness | New `Recipe.meal_type` field (`breakfast`/`lunch`/`dinner`/`snack`/`any`), set on the recipe form, backfilled once by a keyword heuristic for existing rows. |
| Plan actions | Plan is **persisted** (one active plan per user), meals can be **swapped** individually, each day can be **logged** to the diary. |

## Non-goals (v1)

- No plan history — generating replaces the current plan. No "saved plans" list.
- No shopping list / ingredient aggregation.
- No per-day or per-meal manual target overrides — the plan uses the
  user's stored daily targets, split across slots by fixed weights.
- No recipe-level "exclude these ingredients" filter (diet **tags** only).
- No calendar/date assignment beyond "day 0 = today, day 1 = tomorrow, …"
  used only by "Log this day".

## Data model (`models.py`)

### New table: `meal_plans`

| column | type | notes |
|---|---|---|
| `id` | GUID PK | |
| `user_id` | GUID FK → `users.id` `ON DELETE CASCADE`, indexed | one active plan per user (enforced in the route, not a DB constraint) |
| `created_at` | DateTime, default `utcnow` | |
| `days` | Integer, not null | 1–7 |
| `meals_per_day` | Integer, not null | 2–4 |
| `target_kcal` | Float, nullable | snapshot of the user's target at generation time |
| `target_protein_g` | Float, nullable | snapshot |
| `target_fat_g` | Float, nullable | snapshot |
| `target_carbs_g` | Float, nullable | snapshot |
| `diet_tags` | Text, not null, default `""` | comma-joined diet tags the plan was generated with; read by `swap` so a replacement respects the same filter |
| `logged_days` | Text, not null, default `"{}"` | JSON map `{ "<day_index>": "<iso-8601 timestamp>" }` — which days have been logged to the diary |

Relationship: `entries: List[MealPlanEntry]`, `cascade="all, delete-orphan"`.

### New table: `meal_plan_entries`

| column | type | notes |
|---|---|---|
| `id` | GUID PK | |
| `plan_id` | GUID FK → `meal_plans.id` `ON DELETE CASCADE`, indexed | |
| `day_index` | Integer, not null | 0 … `days-1` |
| `slot` | String(16), not null | `breakfast` / `lunch` / `dinner` / `snack` |
| `recipe_id` | GUID FK → `recipes.id` `ON DELETE SET NULL`, nullable | null ⇒ this slot could not be filled (see "unfilled slots") |
| `servings` | Float, not null, default `1.0` | multiplier applied to the recipe's per-serving nutrition; clamped 0.5–2.5 |
| `calories` | Float, nullable | recipe per-serving `total_calories` × `servings`, cached |
| `protein_g` | Float, nullable | cached |
| `fat_g` | Float, nullable | cached |
| `carbs_g` | Float, nullable | cached |
| `fiber_g` | Float, nullable | cached |

`recipe_id` uses `SET NULL` so deleting a recipe doesn't destroy the plan;
such an entry renders as unfilled and can be swapped.

### New column: `recipes.meal_type`

`Mapped[Optional[str]] = mapped_column(String(16), nullable=True)`.
Allowed values: `breakfast`, `lunch`, `dinner`, `snack`, `any`. `NULL`
is treated as `any` by the engine until backfilled. Default for
new/edited recipes via the form: `any`.

### New column: `users.diet_tags`

`Mapped[Optional[str]] = mapped_column(String(500), nullable=True)` —
same comma-joined string encoding already used by `recipes.diet_tags`
(`_split_diet_tags` / `_diet_tags_to_str` helpers in `schemas.py` /
`main.py` are reused). Validated against the existing diet-tag allow-list
in `schemas.py` (`vegan`, `vegetarian`, `pescatarian`, `flexitarian`,
`gluten_free`, `dairy_free`, `nut_free`, `soy_free`, `egg_free`,
`shellfish_free`, `keto`, `low_carb`, `paleo`, `whole30`, `low_fodmap`,
`diabetic_friendly`, `low_sodium`, `low_fat`, `high_protein`, `halal`,
`kosher`, `mediterranean`, `dash`).

## Planner engine (`meal_planner.py`)

Pure functions — no FastAPI, no session inside the scoring code. The route
loads the recipe pool and the user's targets, calls the engine, and
persists the result.

### Types

```
@dataclass
class RecipeOption:
    id: str                 # str(recipe.id)
    name: str
    meal_type: str          # normalised: NULL -> "any"
    diet_tags: FrozenSet[str]
    kcal: float             # per serving (total_calories)
    protein_g: float
    fat_g: float
    carbs_g: float
    fiber_g: float

@dataclass
class PlannedEntry:
    slot: str
    option: Optional[RecipeOption]   # None -> unfilled
    servings: float                  # 1.0 when unfilled
    kcal / protein_g / fat_g / carbs_g / fiber_g: float  # scaled, 0 when unfilled

@dataclass
class PlannedDay:
    entries: List[PlannedEntry]      # one per active slot, in slot order
    totals: Dict[str, float]         # summed kcal/protein_g/fat_g/carbs_g/fiber_g
    score: float
```

### Slots

`SLOT_ORDER = ["breakfast", "lunch", "dinner", "snack"]`. For
`meals_per_day = M`, the active slots are the first `M` of
`["breakfast", "lunch", "dinner", "snack"]` — so 2 ⇒ breakfast+lunch,
3 ⇒ +dinner, 4 ⇒ +snack.

### Per-slot calorie budget

Base weights: `{breakfast: 0.25, lunch: 0.35, dinner: 0.35, snack: 0.05}`.
Take the weights for the active slots and renormalise so they sum to 1.
`slot_budget[slot] = day_target_kcal * normalised_weight[slot]`.
Macro targets are **not** split per slot — they're scored at the day level.

### Eligible pool → buckets

Given `RecipeOption`s and the active diet-tag set `D`:

1. Keep options where `D <= option.diet_tags` (superset match; empty `D`
   keeps everything) and `kcal` is a real positive number.
2. Bucket by slot:
   - `snack` bucket: options with `meal_type == "snack"`, plus options
     with `meal_type == "any"` **and** `kcal <= 250` (a low-cal "any"
     recipe is a plausible snack).
   - `breakfast` / `lunch` / `dinner` buckets: options with that exact
     `meal_type`, plus every option with `meal_type == "any"`.
   - Options with `meal_type == "snack"` never appear in a non-snack
     bucket.

If a bucket for an active slot is empty, that slot is **structurally
unfillable** — the plan still generates, the slot's entries are all
`unfilled`, and the response flags it (see "degenerate cases").

### Servings scaling

For a chosen option and a slot budget `B`:
`servings = clamp(B / option.kcal, 0.5, 2.5)`, rounded to 2 dp. The
clamp means a slot whose only candidates are far from budget ends up
approximate, never absurd (no "0.1 serving", no "6 servings").

### Search — one day at a time

`plan_day(buckets, day_target, slot_budgets, recent_recipe_ids, n=400, rng)`:

1. Repeat `n` times: for each active slot, `rng.choice` a `RecipeOption`
   from its bucket (skip the slot ⇒ `unfilled` if the bucket is empty),
   compute `servings` and the scaled nutrients, build a candidate
   `PlannedDay` with summed `totals`.
2. `score(day)` =
   `1.0 * rel_err(totals.kcal, day_target.kcal)`
   `+ 0.6 * rel_err(totals.protein_g, day_target.protein_g)`
   `+ 0.3 * rel_err(totals.carbs_g, day_target.carbs_g)`
   `+ 0.3 * rel_err(totals.fat_g, day_target.fat_g)`
   `+ 0.5 * (number of duplicate recipe ids within the day)`
   `+ 0.15 * (number of recipe ids also in recent_recipe_ids)`
   where `rel_err(a, t) = abs(a - t) / t` if `t` is a positive number,
   else `0` (a missing macro target simply isn't scored), and an
   `unfilled` slot contributes a flat `1.0` to the kcal term so filled
   combinations always win when one exists.
3. Return the lowest-scoring candidate.

`generate_plan(options, days, meals_per_day, targets, diet_tags, seed=None)`:
build buckets once, then for `day_index` in `range(days)` call
`plan_day` with `recent_recipe_ids` = the set of recipe ids used on
`day_index-1` (empty for day 0). Deterministic given `seed` (used in
tests).

### Swap

`swap_entry(buckets, day, slot, slot_budget, day_target, exclude_recipe_id,
n=400, rng)`: hold the other slots of `day` fixed, draw `n` replacement
`RecipeOption`s for `slot` from its bucket excluding `exclude_recipe_id`,
score the resulting full day with the same `score` function, return the
best replacement `PlannedEntry`. If the bucket has no other option,
return `None` (route responds 409 "no alternative recipe available").

### Meal-type backfill heuristic

`infer_meal_type(name: str, diet_tags: FrozenSet[str], kcal: float) -> str`:

- lowercased name contains any of `oat`, `oats`, `overnight`, `pancake`,
  `waffle`, `smoothie`, `granola`, `toast`, `porridge`, `cereal`,
  `chia pudding`, `french toast`, `breakfast` ⇒ `"breakfast"`.
- else if `kcal` is a real number and `kcal <= 200`, or name contains
  `bites`, `bliss ball`, `energy ball`, `bark`, `crackers`, `dip`,
  `snack`, `bar ` ⇒ `"snack"`.
- else ⇒ `"any"`.

Never returns `lunch`/`dinner` — those are covered by `any`. Applied
once to rows where `meal_type IS NULL`.

## API (`main.py` routes; engine in `meal_planner.py`; schemas in `schemas.py`)

All routes require `get_current_user`; none are admin-only.

### `POST /meal-plan/generate`

Body `MealPlanGenerateRequest`: `{ days: int (1–7), meals_per_day: int (2–4), diet_tags: List[str] }` (`diet_tags` validated against the allow-list; `[]` allowed).

Flow:
1. Resolve the user's targets exactly as `get_daily_summary` does
   (`custom_*` when `uses_custom_goals`, else `target_kcal` /
   `protein_g` / `fat_g` / `carbs_g`). If `target_kcal` resolves to
   `None` ⇒ `422 {"detail": "Finish onboarding to set your calorie target before planning meals."}`.
2. Load the pool: `select(Recipe).where((Recipe.is_shared == True) | (Recipe.user_id == me), Recipe.total_calories.isnot(None))`, `selectinload(Recipe.ingredients)` not needed. Map to `RecipeOption`.
3. If, after diet-tag filtering, the pool is empty ⇒
   `422 {"detail": "No recipes match those dietary filters. Add recipes or loosen the filter."}`.
4. `generate_plan(...)`.
5. In one transaction: `delete` the user's existing `MealPlan` (cascade
   drops entries), insert the new `MealPlan` + `MealPlanEntry` rows
   (`logged_days = "{}"`), commit.
6. Return the plan in the `MealPlanResponse` shape below.

### `GET /meal-plan`

Returns `MealPlanResponse` or `null` (200 with body `null`) if the user
has no plan.

`MealPlanResponse`:
```
{
  id: uuid,
  days: int,
  meals_per_day: int,
  created_at: datetime,
  targets: { kcal: float|null, protein_g: float|null, fat_g: float|null, carbs_g: float|null },
  plan_days: [
    {
      day_index: int,
      logged_at: datetime|null,
      structurally_unfilled_slots: [str],   # slots whose bucket was empty at generation
      entries: [
        {
          id: uuid,
          slot: str,
          servings: float,
          unfilled: bool,
          recipe: {                          # null when unfilled
            id: uuid, name: str, image_url: str|null, servings: float,
            total_calories: float|null, total_protein_g: float|null,
            total_fat_g: float|null, total_carbs_g: float|null, total_fiber_g: float|null,
            meal_type: str|null, diet_tags: [str]
          }|null,
          calories: float|null, protein_g: float|null, fat_g: float|null,
          carbs_g: float|null, fiber_g: float|null
        }
      ],
      totals: { calories: float, protein_g: float, fat_g: float, carbs_g: float, fiber_g: float }
    }
  ]
}
```
`totals` and `targets` are the only things the frontend needs to draw
"vs target" bars. `structurally_unfilled_slots` lets the UI explain why a
tile is empty.

### `POST /meal-plan/entries/{entry_id}/swap`

No body. 404 if the entry's plan isn't the caller's. Rebuilds the pool +
buckets (same query as generate) filtered by the plan's stored
`diet_tags`, recomputes that slot's budget from the plan's snapshot
`target_kcal`, runs `swap_entry`, updates the `MealPlanEntry` in place
(recipe_id, servings, cached nutrients), commits, and returns the updated
entry object (same shape as an `entries[]` element) plus the day's
recomputed `totals`. `409 {"detail": "No alternative recipe available for that slot."}` when `swap_entry` returns `None`.

### `POST /meal-plan/days/{day_index}/log`

Body `{ force?: bool }`. 404 if no plan or `day_index` out of range.
- If `str(day_index)` is already a key in `logged_days` and not `force`
  ⇒ `409 {"detail": "Day already logged. Send force to log it again.", "logged_at": "<iso>"}`.
- Otherwise, for each **filled** entry on that day, create a `FoodLog`:
  `user_id = me`, `log_date = date.today() + timedelta(days=day_index)`,
  `meal = entry.slot`, `recipe_id = entry.recipe_id`,
  `food_name = recipe.name`, `amount_g = entry.servings * 100`
  (nominal — matches how `SharedRecipes` logs a recipe), and the cached
  `calories/protein_g/fat_g/carbs_g/fiber_g` copied straight from the
  entry. Set `logged_days[str(day_index)] = now.isoformat()`. Commit.
- Returns `{ "created": n, "logged_at": "<iso>" }`.

### `DELETE /meal-plan`

Deletes the caller's `MealPlan` (cascade). `204`. `404` if none.

### Existing endpoints — one new field each

- **`PATCH /users/me`**: accepts optional `diet_tags: List[str]`
  (validated against the allow-list, stored comma-joined). `UserResponse`
  / `GET /users/me` include `diet_tags: List[str]` (split from the
  stored string; `[]` when null).
- **`POST /recipes`** and **`PATCH /recipes/{id}`**: accept optional
  `meal_type` (one of the 5 allowed strings; rejected otherwise).
  `RecipeResponse` includes `meal_type: str | null`.

## Frontend

### New screen: `MealPlanner.tsx`

`AppView` gains `"mealPlanner"`. `App.tsx` renders
`<MealPlanner onBack={() => setView("dashboard")} userProfile={userProfile} />`
for that view; `Dashboard` gets an `onOpenMealPlanner` prop + a button
(next to "Shared Recipes" / "Recipe Builder").

On mount: `GET /meal-plan`.

**State A — no plan (generate form):**
- Days: number stepper 1–7 (default 3).
- Meals per day: segmented 2 / 3 / 4 (default 3).
- Diet tags: the same checkbox list used elsewhere, **pre-checked from
  `userProfile.diet_tags`**, freely toggled.
- "Generate plan" → `POST /meal-plan/generate`. On 422, show
  `detail` inline. On success, go to State C.

**State B — generating:** spinner + "Building your plan…" (the search is
~400 combos × up to 7 days server-side; typically well under a second,
but show feedback).

**State C — plan view:**
- Header: "Your meal plan — {days} days" + a **Regenerate** button
  (→ State A, form prefilled with the current plan's `days` /
  `meals_per_day` / `diet_tags`).
- One card per `plan_day`:
  - Day label ("Today", "Tomorrow", "Day 3", …).
  - For each entry: recipe image (or a placeholder), recipe name, slot
    label, `servings` shown as e.g. "1.25 servings", and the entry's
    `calories` + macros. A **Swap** button → `POST .../swap`, replaces
    that entry in place and updates the day's totals from the response.
    An **unfilled** entry renders as a muted tile: "No {slot} recipe
    available" (+ "— add one with meal type '{slot}'" when the slot is
    in `structurally_unfilled_slots`).
  - A **totals-vs-target** row: mini progress bars for kcal / protein /
    fat / carbs using `totals` vs `targets` (reuse Dashboard's
    `.overall-progress-bar` / `.category-progress-bar` styles). When
    `userProfile.safe_mode` is true, render the bars without numeric
    labels (consistent with Dashboard's safe-mode behaviour).
  - **"Log this day"** button. Disabled/greyed with a "Logged ✓" label
    when `logged_at` is set. On click → `POST .../log`; on 409, a
    confirm dialog ("Already logged earlier — log again?") → retry with
    `{ force: true }`. On success, mark the day logged and toast
    "{created} items added to your diary".

Width: use the wide layout pattern (`max-width: 1200px`, responsive
`clamp()` padding) matching the other screens.

### `Settings.tsx`

New "Dietary preferences" section: the diet-tag checkbox list, "Save"
→ `PATCH /users/me` with `diet_tags`. Reflect the saved value on
`userProfile` so the meal-planner form picks it up.

### `RecipeEditForm.tsx`

Add a "Meal type" `<select>` (`Any` / `Breakfast` / `Lunch` / `Dinner` /
`Snack`, default `Any` ⇒ sent as `"any"`), wired into the existing
`RecipeSavePayload` and `formValuesFromRecipe` / `formValuesFromDraft`
(drafts default to `"any"`).

## Migration / deploy

- `models.py`: two new tables + `recipes.meal_type` + `users.diet_tags` +
  `meal_plans.diet_tags`.
- Hosted (`create_tables.py` → `create_all` + `migrations`): `create_all`
  makes the two new tables. Extend `migrations.py` with a dialect-aware
  additive-column step for `recipes.meal_type` and `users.diet_tags`
  (SQLite path mirrors the existing `_add_missing_columns` in
  `backend_entry.py`; Postgres path added next to
  `_migrate_fdc_to_food_id_pg` — `ALTER TABLE ... ADD COLUMN IF NOT
  EXISTS`). `create_tables.py` calls it (already calls
  `_migrate_fdc_to_food_id`).
- **One-time `meal_type` backfill**: after the column exists,
  `create_tables.py` runs a helper (in `meal_planner.py`) that
  `SELECT id, name, diet_tags, total_calories FROM recipes WHERE
  meal_type IS NULL`, applies `infer_meal_type`, and `UPDATE`s each row.
  Chunked + wrapped like `seed_foods` so a Neon disconnect mid-backfill
  is retried, not fatal.
- Desktop (`backend_entry.py`): `create_all` + the existing
  `_migrate_fdc_to_food_id` + `_add_missing_columns` already add the new
  tables/columns; add the same `infer_meal_type` backfill call after
  `_add_missing_columns`.

## Testing

**`tests/test_meal_planner.py`** (engine, deterministic via `seed`):
- `plan_day` picks the combination closest to a day target from a tiny
  fixture pool (assert the chosen recipes / total kcal within tolerance).
- `servings` clamp: a pool of only very-high-kcal recipes ⇒ every
  `servings` == 0.5; only very-low-kcal ⇒ == 2.5.
- diet-tag filter: a `vegan`-tagged request excludes non-vegan options.
- meal_type bucketing: a `snack`-only recipe never lands in breakfast;
  an `any` recipe with kcal ≤ 250 is a snack candidate; `NULL` treated
  as `any`.
- empty bucket for an active slot ⇒ that slot's entry is `unfilled`,
  the day still returns, `structurally_unfilled_slots` names it.
- `swap_entry` excludes the current recipe and returns the best of the
  rest; returns `None` when nothing else is eligible.
- `infer_meal_type`: "Blueberry Overnight Oats" ⇒ breakfast;
  "Cookie Dough Bliss Balls" ⇒ snack; "Lentil Ragu Pasta" ⇒ any.

**`tests/test_meal_plan_routes.py`** (route, `client` + `db_session` style):
- generate with no `target_kcal` ⇒ 422 onboarding message.
- generate with an over-restrictive diet filter (no matching recipes)
  ⇒ 422 empty-pool message.
- happy path: generate ⇒ rows written, `GET /meal-plan` returns the
  shape; a second generate replaces (old plan id gone).
- swap: 200 updates the entry; 404 for someone else's entry; 409 when
  no alternative.
- day log: creates N `FoodLog`s with the right `log_date` / `meal` /
  nutrients; second call ⇒ 409; `force` ⇒ logs again; sets `logged_at`.
- `PATCH /users/me` with `diet_tags` round-trips through `GET /users/me`;
  invalid tag ⇒ 422.
- `POST /recipes` with `meal_type` round-trips; invalid ⇒ 422.

**`tests/test_create_tables.py`**: the new additive columns get added to
a pre-existing SQLite `recipes` / `users` table, and `meal_type` is
backfilled by the heuristic.

**Frontend** (`MealPlanner.test.tsx`, existing style, mocked `fetch`):
- generate form renders, checkboxes pre-checked from `userProfile.diet_tags`.
- successful generate ⇒ plan view renders day cards + totals bars.
- Swap button calls the swap endpoint and re-renders that entry.
- "Log this day" calls the log endpoint; 409 ⇒ confirm ⇒ retry with force.
- `safe_mode` hides numeric labels on the totals bars.

## Files touched

- **New:** `meal_planner.py`, `tests/test_meal_planner.py`,
  `tests/test_meal_plan_routes.py`,
  `pakupaku-frontend/src/components/MealPlanner.tsx` (+ `.css`, `.test.tsx`).
- **Modified:** `models.py`, `schemas.py`, `main.py`, `migrations.py`,
  `create_tables.py`, `backend_entry.py`,
  `pakupaku-frontend/src/App.tsx`,
  `pakupaku-frontend/src/components/Dashboard.tsx` (+ `.css`),
  `pakupaku-frontend/src/components/Settings.tsx` (+ `.css`),
  `pakupaku-frontend/src/components/RecipeEditForm.tsx`,
  `tests/test_create_tables.py`, `docs/deployment.md`.
