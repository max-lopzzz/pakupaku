# Meal Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate, persist, swap, and diary-log a personalised multi-day meal plan built from the user's stored nutrition targets and the recipe database.

**Architecture:** A pure-Python engine (`meal_planner.py`) does best-of-random-search over an eligible recipe pool, scaling servings to hit each day's calorie + macro targets. FastAPI routes in `main.py` load the pool + targets, call the engine, and persist `MealPlan` / `MealPlanEntry` rows. A new `MealPlanner.tsx` screen drives generation, per-meal swap, and per-day logging. Two small schema additions (`recipes.meal_type`, `users.diet_tags`) support meal-slot bucketing and dietary filtering.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0, Python 3.8 (`typing.Optional`/`typing.List`, no `X | None`), Pydantic v1-style `BaseModel` with `@validator`, `pytest` (`asyncio_mode = auto`), Create React App + `@testing-library/react`, plain `fetch` via `apiFetch`.

**Spec:** `docs/superpowers/specs/2026-09-10-meal-planner-design.md`

## Global Constraints

- **Python 3.8 syntax only** — `typing.Optional[X]` / `typing.List[X]` / `typing.Dict` / `typing.FrozenSet`, never `X | None` / `list[X]`.
- **Diet-tag allow-list** (copied verbatim from `schemas.py`): `vegan`, `vegetarian`, `pescatarian`, `flexitarian`, `gluten_free`, `dairy_free`, `nut_free`, `soy_free`, `egg_free`, `shellfish_free`, `keto`, `low_carb`, `paleo`, `whole30`, `low_fodmap`, `diabetic_friendly`, `low_sodium`, `low_fat`, `high_protein`, `halal`, `kosher`, `mediterranean`, `dash`.
- **Meal-type allow-list:** `breakfast`, `lunch`, `dinner`, `snack`, `any`. `NULL` is treated as `any`.
- **Diet tags stored as** a comma-joined string (`_diet_tags_to_str` / split-on-`,`), matching `recipes.diet_tags`. `""`/`NULL` ⇒ no tags.
- **Slot order:** `["breakfast", "lunch", "dinner", "snack"]`. `meals_per_day = M` ⇒ the first `M` slots are active.
- **Slot calorie weights:** `{breakfast: 0.25, lunch: 0.35, dinner: 0.35, snack: 0.05}`, renormalised over the active slots.
- **Score weights:** kcal `1.0`, protein `0.6`, carbs `0.3`, fat `0.3`; within-day duplicate-recipe penalty `0.5` each; adjacent-day repeat penalty `0.15` each; an `unfilled` slot adds a flat `1.0` to the kcal term.
- **`servings` multiplier** clamped to `[0.5, 2.5]`, rounded to 2 dp.
- **Search width:** `n = 400` candidate combinations per day and per swap.
- **`days` range** `1..7`; **`meals_per_day` range** `2..4`.
- **Day indexing:** `day_index` 0 = today; "Log this day" uses `date.today() + timedelta(days=day_index)`.
- **Nominal `amount_g`** for a logged plan entry: `servings * 100` (matches how `SharedRecipes` logs a recipe).
- **All meal-plan routes** require `get_current_user`; none are admin-only.
- **Commit** after every green test cycle. Conventional-commit subjects. No attribution lines in commit messages or PR descriptions.
- **Run backend tests:** `python -m pytest -q` (activate the venv first: `source venv/bin/activate`; if that yields "No module named pytest", use `~/.pyenv/versions/3.8.19/bin/python3 -m pytest`).
- **Run frontend tests:** from `pakupaku-frontend/`, `CI=true npx react-scripts test --watchAll=false`. `npx tsc --noEmit` must stay clean. `src/App.test.tsx` has a pre-existing CRA-boilerplate failure — ignore only that one.

---

## File structure

| File | Responsibility |
|---|---|
| `meal_planner.py` (new) | Engine: dataclasses, `infer_meal_type`, bucketing, `plan_day`, `generate_plan`, `swap_entry`, `backfill_meal_types`. No FastAPI, no session in the scoring code. |
| `models.py` (modify) | `MealPlan`, `MealPlanEntry` ORM classes; `Recipe.meal_type`, `User.diet_tags` columns. |
| `migrations.py` (modify) | `_add_meal_planner_columns(conn)` — dialect-aware additive columns for `recipes.meal_type` + `users.diet_tags`. |
| `create_tables.py` (modify) | Call `_add_meal_planner_columns` and `backfill_meal_types` after the fdc migration. |
| `backend_entry.py` (modify) | Call `backfill_meal_types` after `_add_missing_columns`. |
| `schemas.py` (modify) | `MealPlanGenerateRequest`, `MealPlanResponse` (+ nested), `MealPlanEntryResponse`, `MealPlanDayLogRequest`, `MealPlanDayLogResponse`, `MealPlanSwapResponse`; `meal_type` on recipe req/resp; `diet_tags` on `UserResponse` / `UserUpdateRequest`. |
| `main.py` (modify) | `_resolve_targets` helper; 5 meal-plan routes; `meal_type` in `create_recipe` / `update_recipe` / `RecipeResponse` mapping; `diet_tags` in `update_me`. |
| `pakupaku-frontend/src/components/MealPlanner.tsx` + `.css` + `.test.tsx` (new) | Generate form, plan view, swap, log-day. |
| `pakupaku-frontend/src/App.tsx` (modify) | `"mealPlanner"` view + render. |
| `pakupaku-frontend/src/components/Dashboard.tsx` + `.css` (modify) | `onOpenMealPlanner` prop + nav button. |
| `pakupaku-frontend/src/components/Settings.tsx` (modify) | "Dietary preferences" section. |
| `pakupaku-frontend/src/components/RecipeEditForm.tsx` (modify) | "Meal type" `<select>`. |
| `tests/test_meal_planner.py`, `tests/test_meal_plan_routes.py` (new); `tests/test_create_tables.py` (modify) | |
| `docs/deployment.md` (modify) | Note the new additive columns + one-time `meal_type` backfill. |

---

## Task 1: Models, migration, and column backfill wiring

**Files:**
- Modify: `models.py`
- Modify: `migrations.py`
- Modify: `create_tables.py`
- Modify: `backend_entry.py`
- Modify: `docs/deployment.md`
- Test: `tests/test_create_tables.py`

**Interfaces:**
- Produces: ORM classes `models.MealPlan`, `models.MealPlanEntry`; columns `models.Recipe.meal_type` (`Mapped[Optional[str]]`), `models.User.diet_tags` (`Mapped[Optional[str]]`). `migrations._add_meal_planner_columns(conn) -> None` (async, dialect-aware, idempotent). `meal_planner.backfill_meal_types` is *consumed* here but *created* in Task 2 — for this task, wire a no-op stub `async def backfill_meal_types(session) -> int: return 0` into `meal_planner.py` and replace it in Task 2.

- [ ] **Step 1: Write the failing test** — extend `tests/test_create_tables.py`

```python
async def test_create_tables_adds_meal_planner_columns_and_tables(tmp_path):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_async_engine("sqlite+aiosqlite:///%s" % db_path)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    try:
        # OLD-shape recipes/users tables without the new columns
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE recipes (id TEXT PRIMARY KEY, name TEXT)"))
            await conn.execute(text("CREATE TABLE users (id TEXT PRIMARY KEY, email TEXT)"))
            await conn.execute(text("CREATE TABLE food_logs (id TEXT, fdc_id INTEGER)"))
            await conn.execute(text("CREATE TABLE recipe_ingredients (id TEXT, fdc_id INTEGER)"))
        await create_tables_mod.create_tables(db_engine=eng, session_factory=Session, artifact_path=None)
        async with eng.begin() as conn:
            rcols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(recipes)"))).fetchall()}
            ucols = {r[1] for r in (await conn.execute(text("PRAGMA table_info(users)"))).fetchall()}
            tables = {r[0] for r in (await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'"))).fetchall()}
        assert "meal_type" in rcols
        assert "diet_tags" in ucols
        assert {"meal_plans", "meal_plan_entries"}.issubset(tables)
    finally:
        await eng.dispose()
        os.remove(db_path)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_create_tables.py::test_create_tables_adds_meal_planner_columns_and_tables -v`
Expected: FAIL — `meal_type` not in `rcols` (columns not added), or `AttributeError` on `models.MealPlan`.

- [ ] **Step 3: Add the ORM models** — in `models.py`, after `class RecipeIngredient` (keep imports: `String`, `Integer`, `Float`, `DateTime`, `ForeignKey`, `Text`, `Boolean` are already imported; add nothing new)

```python
class MealPlan(Base):
    __tablename__ = "meal_plans"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    meals_per_day: Mapped[int] = mapped_column(Integer, nullable=False)

    target_kcal:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_protein_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_fat_g:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_carbs_g:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    diet_tags:   Mapped[str] = mapped_column(Text, nullable=False, default="")
    logged_days: Mapped[str] = mapped_column(Text, nullable=False, default="{}")

    entries: Mapped[List["MealPlanEntry"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan",
    )


class MealPlanEntry(Base):
    __tablename__ = "meal_plan_entries"

    id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("meal_plans.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    slot: Mapped[str] = mapped_column(String(16), nullable=False)
    recipe_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        GUID(), ForeignKey("recipes.id", ondelete="SET NULL"), nullable=True,
    )
    servings: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)

    calories:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_g:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs_g:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber_g:   Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    plan:   Mapped["MealPlan"] = relationship(back_populates="entries")
    recipe: Mapped[Optional["Recipe"]] = relationship()
```

In `class Recipe`, add after `diet_tags`:

```python
    meal_type:    Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
```

In `class User`, add after `uses_custom_goals` (or near the other preference fields):

```python
    diet_tags: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
```

- [ ] **Step 4: Add the Postgres additive-column migration** — in `migrations.py`, after `_migrate_fdc_to_food_id_pg`

```python
_MEAL_PLANNER_COLUMNS = [
    ("recipes", "meal_type", "VARCHAR(16)"),
    ("users", "diet_tags", "VARCHAR(500)"),
]


async def _add_meal_planner_columns(conn) -> None:
    """Add recipes.meal_type / users.diet_tags to an existing DB.
    create_all() only creates whole tables, never a column on one that
    already exists. Idempotent on every dialect."""
    if conn.dialect.name == "postgresql":
        for table, col, coltype in _MEAL_PLANNER_COLUMNS:
            await conn.execute(text(
                "ALTER TABLE %s ADD COLUMN IF NOT EXISTS %s %s" % (table, col, coltype)
            ))
    else:
        for table, col, _ in _MEAL_PLANNER_COLUMNS:
            cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(%s)" % table))).fetchall()]
            if cols and col not in cols:
                await conn.execute(text("ALTER TABLE %s ADD COLUMN %s VARCHAR" % (table, col)))
```

- [ ] **Step 5: Wire the migration + backfill into `create_tables.py`**

In `create_tables.py`, add to the imports:

```python
from migrations import _migrate_fdc_to_food_id, _add_meal_planner_columns
from meal_planner import backfill_meal_types
```

In `create_tables()`, inside the `async with db_engine.begin() as conn:` block, after `await _migrate_fdc_to_food_id(conn)`:

```python
        await _add_meal_planner_columns(conn)
```

After the seed block (after `seeded = await seed_foods(...)` / its retry loop, before `return`), add — using the same `session_factory`:

```python
    async with session_factory() as s:
        await backfill_meal_types(s)
        await s.commit()
```

- [ ] **Step 6: Wire the backfill into `backend_entry.py`**

In `backend_entry.py`, add to the imports near `from migrations import _migrate_fdc_to_food_id`:

```python
from meal_planner import backfill_meal_types  # noqa: E402
from database import AsyncSessionLocal  # noqa: E402
```

In `_create_tables()`, after the `async with engine.begin()` block:

```python
    async with AsyncSessionLocal() as s:
        await backfill_meal_types(s)
        await s.commit()
```

- [ ] **Step 7: Create the stub engine module** — `meal_planner.py`

```python
"""Meal-plan generation engine. See docs/superpowers/specs/2026-09-10-meal-planner-design.md."""

from sqlalchemy.ext.asyncio import AsyncSession


async def backfill_meal_types(session: AsyncSession) -> int:
    """Replaced in Task 2."""
    return 0
```

- [ ] **Step 8: Run the test to verify it passes**

Run: `python -m pytest tests/test_create_tables.py -q`
Expected: PASS (all create_tables tests, including the new one).

- [ ] **Step 9: Run the full backend suite**

Run: `python -m pytest -q`
Expected: PASS (no regressions from the new models/columns).

- [ ] **Step 10: Update `docs/deployment.md`**

In section 5 ("Applying schema changes to an existing database"), after the `fdc_id` item, add:

```markdown
2. **`recipes.meal_type` / `users.diet_tags`** are added automatically by
   `create_tables.py` on every deploy (idempotent). `create_tables.py`
   also runs a one-time keyword backfill of `recipes.meal_type` for rows
   where it is null.
```

- [ ] **Step 11: Commit**

```bash
git add models.py migrations.py create_tables.py backend_entry.py meal_planner.py tests/test_create_tables.py docs/deployment.md
git commit -m "feat(meal-planner): schema — MealPlan/MealPlanEntry tables, recipe meal_type, user diet_tags"
```

---

## Task 2: `infer_meal_type` + `backfill_meal_types`

**Files:**
- Modify: `meal_planner.py`
- Test: `tests/test_meal_planner.py` (new)

**Interfaces:**
- Consumes: `models.Recipe` (`id`, `name`, `diet_tags`, `total_calories`, `meal_type`).
- Produces:
  - `meal_planner.infer_meal_type(name: str, kcal: Optional[float]) -> str` — returns `"breakfast"` / `"snack"` / `"any"`.
  - `meal_planner.backfill_meal_types(session: AsyncSession) -> int` — sets `meal_type` on every `Recipe` where it is `NULL`, returns the count updated. Idempotent (a second call updates 0).

- [ ] **Step 1: Write the failing test** — `tests/test_meal_planner.py`

```python
import uuid

from meal_planner import backfill_meal_types, infer_meal_type
from models import Recipe, User
from auth import hash_password


def test_infer_meal_type_breakfast_keywords():
    assert infer_meal_type("Blueberry Overnight Oats", 350) == "breakfast"
    assert infer_meal_type("Fluffy Buttermilk Pancakes", 500) == "breakfast"
    assert infer_meal_type("Green Smoothie", 180) == "breakfast"


def test_infer_meal_type_snack_by_keyword_or_low_kcal():
    assert infer_meal_type("Cookie Dough Bliss Balls", 90) == "snack"
    assert infer_meal_type("Seeded Crackers", 400) == "snack"       # keyword wins over kcal
    assert infer_meal_type("Mystery Dish", 150) == "snack"          # low kcal, no keyword
    assert infer_meal_type("Mystery Dish", None) == "any"           # no kcal, no keyword


def test_infer_meal_type_default_any():
    assert infer_meal_type("Lentil Ragu Pasta", 620) == "any"
    assert infer_meal_type("Roasted Cauliflower Bowl", 480) == "any"


async def test_backfill_only_touches_null_rows(db_session):
    u = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@e.com", username=uuid.uuid4().hex[:8],
             hashed_password=hash_password("x"), email_verified=True, safe_mode=False,
             uses_custom_goals=False, is_admin=False)
    db_session.add(u)
    await db_session.flush()
    a = Recipe(id=uuid.uuid4(), user_id=u.id, name="Overnight Oats", servings=1.0, total_calories=300)
    b = Recipe(id=uuid.uuid4(), user_id=u.id, name="Pasta Bake", servings=1.0, total_calories=700)
    c = Recipe(id=uuid.uuid4(), user_id=u.id, name="Already Set", servings=1.0,
               total_calories=700, meal_type="dinner")
    db_session.add_all([a, b, c])
    await db_session.commit()

    n = await backfill_meal_types(db_session)
    await db_session.commit()
    assert n == 2

    rows = {r.name: r.meal_type for r in (await db_session.execute(
        Recipe.__table__.select())).fetchall()}
    assert rows["Overnight Oats"] == "breakfast"
    assert rows["Pasta Bake"] == "any"
    assert rows["Already Set"] == "dinner"

    assert await backfill_meal_types(db_session) == 0   # idempotent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_meal_planner.py -q`
Expected: FAIL — `infer_meal_type` not defined / `backfill_meal_types` returns 0.

- [ ] **Step 3: Implement** — replace the stub in `meal_planner.py`

```python
"""Meal-plan generation engine. See docs/superpowers/specs/2026-09-10-meal-planner-design.md."""

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import Recipe

_BREAKFAST_KEYWORDS = (
    "oat", "oats", "overnight", "pancake", "waffle", "smoothie", "granola",
    "toast", "porridge", "cereal", "chia pudding", "french toast", "breakfast",
)
_SNACK_KEYWORDS = (
    "bites", "bliss ball", "energy ball", "bark", "crackers", "dip", "snack", "bar ",
)
_SNACK_KCAL_CEILING = 200.0


def infer_meal_type(name: str, kcal: Optional[float]) -> str:
    n = (name or "").lower()
    if any(k in n for k in _BREAKFAST_KEYWORDS):
        return "breakfast"
    if any(k in n for k in _SNACK_KEYWORDS):
        return "snack"
    if isinstance(kcal, (int, float)) and kcal <= _SNACK_KCAL_CEILING:
        return "snack"
    return "any"


async def backfill_meal_types(session: AsyncSession) -> int:
    rows = (await session.execute(
        select(Recipe.id, Recipe.name, Recipe.total_calories).where(Recipe.meal_type.is_(None))
    )).all()
    for rid, name, kcal in rows:
        await session.execute(
            update(Recipe).where(Recipe.id == rid).values(meal_type=infer_meal_type(name, kcal))
        )
    return len(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_meal_planner.py -q`
Expected: PASS.

- [ ] **Step 5: Run the create_tables + full suite**

Run: `python -m pytest tests/test_create_tables.py tests/test_meal_planner.py -q` then `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add meal_planner.py tests/test_meal_planner.py
git commit -m "feat(meal-planner): meal-type keyword heuristic + one-time backfill"
```

---

## Task 3: Engine core — dataclasses, buckets, `plan_day`

**Files:**
- Modify: `meal_planner.py`
- Test: `tests/test_meal_planner.py`

**Interfaces:**
- Produces:
  - `RecipeOption` dataclass: `id: str`, `name: str`, `meal_type: str`, `diet_tags: FrozenSet[str]`, `kcal: float`, `protein_g: float`, `fat_g: float`, `carbs_g: float`, `fiber_g: float`.
  - `PlannedEntry` dataclass: `slot: str`, `option: Optional[RecipeOption]`, `servings: float`, `kcal: float`, `protein_g: float`, `fat_g: float`, `carbs_g: float`, `fiber_g: float`. `unfilled` property = `option is None`.
  - `PlannedDay` dataclass: `entries: List[PlannedEntry]`, `totals: Dict[str, float]` (keys `kcal`/`protein_g`/`fat_g`/`carbs_g`/`fiber_g`), `score: float`.
  - `active_slots(meals_per_day: int) -> List[str]`
  - `slot_budgets(day_target_kcal: float, slots: List[str]) -> Dict[str, float]`
  - `build_buckets(options: List[RecipeOption], diet_tags: FrozenSet[str], slots: List[str]) -> Dict[str, List[RecipeOption]]`
  - `plan_day(buckets, day_target: Dict[str, Optional[float]], budgets: Dict[str, float], recent_recipe_ids: FrozenSet[str], rng: random.Random, n: int = 400) -> PlannedDay` — `day_target` keys `kcal`/`protein_g`/`fat_g`/`carbs_g`.
- Consumes: nothing from other tasks.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_meal_planner.py`

```python
import random as _random

from meal_planner import (
    RecipeOption, PlannedDay, active_slots, slot_budgets, build_buckets, plan_day,
)


def _opt(id, name, mt, kcal, p=20.0, f=20.0, c=40.0, fib=5.0, tags=()):
    return RecipeOption(id=id, name=name, meal_type=mt, diet_tags=frozenset(tags),
                        kcal=kcal, protein_g=p, fat_g=f, carbs_g=c, fiber_g=fib)


def test_active_slots():
    assert active_slots(2) == ["breakfast", "lunch"]
    assert active_slots(3) == ["breakfast", "lunch", "dinner"]
    assert active_slots(4) == ["breakfast", "lunch", "dinner", "snack"]


def test_slot_budgets_renormalise_and_sum_to_target():
    b = slot_budgets(2000.0, ["breakfast", "lunch", "dinner"])
    assert round(sum(b.values())) == 2000
    # 0.25 / 0.35 / 0.35 -> renormalised over 0.95
    assert b["breakfast"] < b["lunch"]
    assert abs(b["lunch"] - b["dinner"]) < 1e-6


def test_build_buckets_meal_type_and_diet_filter():
    opts = [
        _opt("b1", "Oats", "breakfast", 300),
        _opt("s1", "Bliss Balls", "snack", 120),
        _opt("a1", "Any Bowl", "any", 500),
        _opt("a2", "Tiny Any", "any", 150),
        _opt("d1", "Steak", "dinner", 700, tags=("vegan",) == () and () or ()),  # no tags
        _opt("v1", "Vegan Bowl", "any", 480, tags=("vegan",)),
    ]
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch", "dinner", "snack"])
    assert {o.id for o in buckets["breakfast"]} == {"b1", "a1", "a2", "v1"}
    assert {o.id for o in buckets["dinner"]} == {"d1", "a1", "a2", "v1"}
    assert {o.id for o in buckets["snack"]} == {"s1", "a2"}   # snack + low-cal any
    assert "s1" not in {o.id for o in buckets["dinner"]}

    vegan = build_buckets(opts, frozenset({"vegan"}), ["lunch"])
    assert {o.id for o in vegan["lunch"]} == {"v1"}


def test_plan_day_picks_the_closest_combination():
    rng = _random.Random(0)
    # exactly-right recipe per slot at 1x servings for a 2000 kcal day, 3 meals
    budgets = slot_budgets(2000.0, ["breakfast", "lunch", "dinner"])
    opts = [
        _opt("good_b", "Good B", "breakfast", budgets["breakfast"], p=30, f=15, c=60),
        _opt("good_l", "Good L", "lunch", budgets["lunch"], p=45, f=25, c=80),
        _opt("good_d", "Good D", "dinner", budgets["dinner"], p=45, f=25, c=80),
        _opt("bad", "Way Off", "any", 50, p=1, f=1, c=1),
    ]
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch", "dinner"])
    day = plan_day(
        buckets,
        {"kcal": 2000.0, "protein_g": 120.0, "fat_g": 65.0, "carbs_g": 220.0},
        budgets, frozenset(), rng, n=400,
    )
    chosen = {e.option.id for e in day.entries}
    assert chosen == {"good_b", "good_l", "good_d"}
    assert abs(day.totals["kcal"] - 2000.0) < 60


def test_plan_day_servings_clamped_when_pool_is_far_from_budget():
    rng = _random.Random(1)
    budgets = slot_budgets(2000.0, ["breakfast", "lunch"])
    opts = [_opt("huge", "Huge", "any", 4000)]   # 1 recipe, way over every budget
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch"])
    day = plan_day(buckets, {"kcal": 2000.0, "protein_g": None, "fat_g": None, "carbs_g": None},
                   budgets, frozenset(), rng, n=50)
    assert all(e.servings == 0.5 for e in day.entries)


def test_plan_day_unfilled_slot_when_bucket_empty():
    rng = _random.Random(2)
    budgets = slot_budgets(2000.0, ["breakfast", "lunch", "dinner", "snack"])
    opts = [_opt("b", "B", "breakfast", 500), _opt("a", "A", "any", 600)]  # nothing for snack
    buckets = build_buckets(opts, frozenset(), ["breakfast", "lunch", "dinner", "snack"])
    day = plan_day(buckets, {"kcal": 2000.0, "protein_g": None, "fat_g": None, "carbs_g": None},
                   budgets, frozenset(), rng, n=50)
    snack = [e for e in day.entries if e.slot == "snack"][0]
    assert snack.unfilled
    assert snack.kcal == 0.0
```

> Note: the `d1` line above is deliberately awkward — replace it with a plain `_opt("d1", "Steak", "dinner", 700)` when implementing; the intent is "a dinner recipe with no diet tags".

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_meal_planner.py -q`
Expected: FAIL — `RecipeOption` / `active_slots` / etc. not defined.

- [ ] **Step 3: Implement** — append to `meal_planner.py` (add imports `import random`, `from dataclasses import dataclass, field`, `from typing import Dict, FrozenSet, List, Optional`)

```python
SLOT_ORDER = ["breakfast", "lunch", "dinner", "snack"]
_SLOT_WEIGHTS = {"breakfast": 0.25, "lunch": 0.35, "dinner": 0.35, "snack": 0.05}
_SERVINGS_MIN, _SERVINGS_MAX = 0.5, 2.5
_SNACK_ANY_KCAL_CEILING = 250.0
_SCORE_W = {"kcal": 1.0, "protein_g": 0.6, "carbs_g": 0.3, "fat_g": 0.3}
_DUP_PENALTY = 0.5
_RECENT_PENALTY = 0.15


@dataclass(frozen=True)
class RecipeOption:
    id: str
    name: str
    meal_type: str
    diet_tags: FrozenSet[str]
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    fiber_g: float


@dataclass
class PlannedEntry:
    slot: str
    option: Optional[RecipeOption]
    servings: float
    kcal: float
    protein_g: float
    fat_g: float
    carbs_g: float
    fiber_g: float

    @property
    def unfilled(self) -> bool:
        return self.option is None


@dataclass
class PlannedDay:
    entries: List[PlannedEntry]
    totals: Dict[str, float]
    score: float


def active_slots(meals_per_day: int) -> List[str]:
    return SLOT_ORDER[:meals_per_day]


def slot_budgets(day_target_kcal: float, slots: List[str]) -> Dict[str, float]:
    total_w = sum(_SLOT_WEIGHTS[s] for s in slots)
    return {s: day_target_kcal * (_SLOT_WEIGHTS[s] / total_w) for s in slots}


def build_buckets(options, diet_tags: FrozenSet[str], slots: List[str]) -> Dict[str, List[RecipeOption]]:
    eligible = [o for o in options
               if diet_tags <= o.diet_tags and isinstance(o.kcal, (int, float)) and o.kcal > 0]
    buckets: Dict[str, List[RecipeOption]] = {s: [] for s in slots}
    for o in eligible:
        for s in slots:
            if s == "snack":
                if o.meal_type == "snack" or (o.meal_type == "any" and o.kcal <= _SNACK_ANY_KCAL_CEILING):
                    buckets[s].append(o)
            else:
                if o.meal_type == s or o.meal_type == "any":
                    buckets[s].append(o)
    return buckets


def _scaled_entry(slot: str, option: Optional[RecipeOption], budget: float) -> PlannedEntry:
    if option is None:
        return PlannedEntry(slot, None, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    servings = min(max(budget / option.kcal, _SERVINGS_MIN), _SERVINGS_MAX)
    servings = round(servings, 2)
    return PlannedEntry(
        slot, option, servings,
        round(option.kcal * servings, 2),
        round(option.protein_g * servings, 2),
        round(option.fat_g * servings, 2),
        round(option.carbs_g * servings, 2),
        round(option.fiber_g * servings, 2),
    )


def _rel_err(actual: float, target: Optional[float]) -> float:
    if not isinstance(target, (int, float)) or target <= 0:
        return 0.0
    return abs(actual - target) / target


def _day_totals(entries: List[PlannedEntry]) -> Dict[str, float]:
    return {k: round(sum(getattr(e, k) for e in entries), 2)
            for k in ("kcal", "protein_g", "fat_g", "carbs_g", "fiber_g")}


def _score(entries, totals, day_target, recent_recipe_ids: FrozenSet[str]) -> float:
    s = 0.0
    for key in ("kcal", "protein_g", "fat_g", "carbs_g"):
        tgt = day_target.get(key)
        w = _SCORE_W[key]
        if key == "kcal":
            unfilled_penalty = sum(1.0 for e in entries if e.unfilled)
            s += w * (_rel_err(totals["kcal"], tgt) + unfilled_penalty)
        else:
            s += w * _rel_err(totals[key], tgt)
    ids = [e.option.id for e in entries if e.option is not None]
    s += _DUP_PENALTY * (len(ids) - len(set(ids)))
    s += _RECENT_PENALTY * len(set(ids) & recent_recipe_ids)
    return s


def plan_day(buckets, day_target, budgets, recent_recipe_ids: FrozenSet[str],
             rng: random.Random, n: int = 400) -> PlannedDay:
    slots = list(budgets.keys())
    best: Optional[PlannedDay] = None
    for _ in range(n):
        entries = []
        for slot in slots:
            bucket = buckets.get(slot) or []
            option = rng.choice(bucket) if bucket else None
            entries.append(_scaled_entry(slot, option, budgets[slot]))
        totals = _day_totals(entries)
        sc = _score(entries, totals, day_target, recent_recipe_ids)
        if best is None or sc < best.score:
            best = PlannedDay(entries, totals, sc)
    return best
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_meal_planner.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add meal_planner.py tests/test_meal_planner.py
git commit -m "feat(meal-planner): engine core — buckets, slot budgets, per-day search"
```

---

## Task 4: Engine — `generate_plan` and `swap_entry`

**Files:**
- Modify: `meal_planner.py`
- Test: `tests/test_meal_planner.py`

**Interfaces:**
- Produces:
  - `generate_plan(options: List[RecipeOption], days: int, meals_per_day: int, targets: Dict[str, Optional[float]], diet_tags: FrozenSet[str], seed: Optional[int] = None, n: int = 400) -> List[PlannedDay]` — `targets` keys `kcal`/`protein_g`/`fat_g`/`carbs_g`; `targets["kcal"]` is guaranteed non-null by the caller.
  - `swap_entry(options, day_entries: List[PlannedEntry], slot: str, budgets: Dict[str, float], day_target: Dict[str, Optional[float]], diet_tags: FrozenSet[str], exclude_recipe_id: Optional[str], seed: Optional[int] = None, n: int = 400) -> Optional[PlannedEntry]` — returns the best replacement `PlannedEntry` for `slot`, or `None` if no other recipe is eligible.
- Consumes: everything from Task 3.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_meal_planner.py`

```python
from meal_planner import generate_plan, swap_entry


def test_generate_plan_shape_and_determinism():
    opts = [
        _opt("b", "Oats", "breakfast", 450, p=20, f=12, c=70),
        _opt("l", "Salad", "lunch", 650, p=35, f=25, c=70),
        _opt("d", "Curry", "dinner", 700, p=40, f=25, c=80),
        _opt("d2", "Stew", "dinner", 680, p=38, f=22, c=78),
    ]
    tgt = {"kcal": 1900.0, "protein_g": 110.0, "fat_g": 60.0, "carbs_g": 220.0}
    a = generate_plan(opts, days=2, meals_per_day=3, targets=tgt, diet_tags=frozenset(), seed=7)
    b = generate_plan(opts, days=2, meals_per_day=3, targets=tgt, diet_tags=frozenset(), seed=7)
    assert len(a) == 2
    assert all(len(day.entries) == 3 for day in a)
    assert [[e.option.id for e in d.entries] for d in a] == [[e.option.id for e in d.entries] for d in b]


def test_generate_plan_empty_bucket_leaves_slot_unfilled_not_crash():
    opts = [_opt("b", "Oats", "breakfast", 450)]   # nothing for lunch/dinner/snack
    tgt = {"kcal": 1800.0, "protein_g": None, "fat_g": None, "carbs_g": None}
    plan = generate_plan(opts, days=1, meals_per_day=3, targets=tgt, diet_tags=frozenset(), seed=1)
    slots = {e.slot: e for e in plan[0].entries}
    assert not slots["breakfast"].unfilled
    assert slots["lunch"].unfilled and slots["dinner"].unfilled


def test_swap_entry_excludes_current_and_returns_best_alternative():
    opts = [
        _opt("keep_b", "B", "breakfast", 450),
        _opt("cur_l", "Cur L", "lunch", 640),
        _opt("alt_l", "Alt L", "lunch", 650, p=40, f=20, c=75),
        _opt("keep_d", "D", "dinner", 700),
    ]
    budgets = slot_budgets(1900.0, ["breakfast", "lunch", "dinner"])
    day_target = {"kcal": 1900.0, "protein_g": 110.0, "fat_g": 60.0, "carbs_g": 220.0}
    # a day whose lunch is cur_l
    from meal_planner import _scaled_entry
    day_entries = [
        _scaled_entry("breakfast", opts[0], budgets["breakfast"]),
        _scaled_entry("lunch", opts[1], budgets["lunch"]),
        _scaled_entry("dinner", opts[3], budgets["dinner"]),
    ]
    repl = swap_entry(opts, day_entries, "lunch", budgets, day_target,
                      frozenset(), exclude_recipe_id="cur_l", seed=3)
    assert repl is not None
    assert repl.option.id == "alt_l"


def test_swap_entry_returns_none_when_no_alternative():
    opts = [_opt("only_l", "Only", "lunch", 640)]
    budgets = slot_budgets(1900.0, ["breakfast", "lunch"])
    from meal_planner import _scaled_entry
    day_entries = [
        _scaled_entry("breakfast", None, budgets["breakfast"]),
        _scaled_entry("lunch", opts[0], budgets["lunch"]),
    ]
    repl = swap_entry(opts, day_entries, "lunch", budgets,
                      {"kcal": 1900.0, "protein_g": None, "fat_g": None, "carbs_g": None},
                      frozenset(), exclude_recipe_id="only_l", seed=1)
    assert repl is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_meal_planner.py -q`
Expected: FAIL — `generate_plan` / `swap_entry` not defined.

- [ ] **Step 3: Implement** — append to `meal_planner.py`

```python
def generate_plan(options, days: int, meals_per_day: int, targets, diet_tags: FrozenSet[str],
                  seed: Optional[int] = None, n: int = 400) -> List[PlannedDay]:
    rng = random.Random(seed)
    slots = active_slots(meals_per_day)
    budgets = slot_budgets(targets["kcal"], slots)
    buckets = build_buckets(options, diet_tags, slots)
    day_target = {"kcal": targets["kcal"], "protein_g": targets.get("protein_g"),
                  "fat_g": targets.get("fat_g"), "carbs_g": targets.get("carbs_g")}
    plan: List[PlannedDay] = []
    recent: FrozenSet[str] = frozenset()
    for _ in range(days):
        day = plan_day(buckets, day_target, budgets, recent, rng, n=n)
        plan.append(day)
        recent = frozenset(e.option.id for e in day.entries if e.option is not None)
    return plan


def swap_entry(options, day_entries, slot: str, budgets, day_target, diet_tags: FrozenSet[str],
               exclude_recipe_id: Optional[str], seed: Optional[int] = None,
               n: int = 400) -> Optional[PlannedEntry]:
    rng = random.Random(seed)
    slots = list(budgets.keys())
    bucket = [o for o in build_buckets(options, diet_tags, slots).get(slot, [])
              if o.id != exclude_recipe_id]
    if not bucket:
        return None
    others = [e for e in day_entries if e.slot != slot]
    best_entry: Optional[PlannedEntry] = None
    best_score = None
    for _ in range(n):
        cand = _scaled_entry(slot, rng.choice(bucket), budgets[slot])
        entries = others + [cand]
        totals = _day_totals(entries)
        sc = _score(entries, totals, day_target, frozenset())
        if best_score is None or sc < best_score:
            best_score, best_entry = sc, cand
    return best_entry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_meal_planner.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add meal_planner.py tests/test_meal_planner.py
git commit -m "feat(meal-planner): engine — generate_plan (multi-day) + swap_entry"
```

---

## Task 5: API — schemas + generate / get / delete

**Files:**
- Modify: `schemas.py`
- Modify: `main.py`
- Test: `tests/test_meal_plan_routes.py` (new)

**Interfaces:**
- Consumes: `meal_planner.generate_plan`, `meal_planner.RecipeOption`, `models.MealPlan`, `models.MealPlanEntry`, `models.Recipe`.
- Produces:
  - Schemas `MealPlanGenerateRequest`, `MealPlanRecipeMini`, `MealPlanEntryResponse`, `MealPlanDayResponse`, `MealPlanResponse`.
  - `main._resolve_targets(user: User) -> Dict[str, Optional[float]]` (keys `kcal`/`protein_g`/`fat_g`/`carbs_g`).
  - `main._plan_to_response(plan: MealPlan) -> MealPlanResponse` (async; expects `plan.entries` and each `entry.recipe` eager-loaded).
  - Routes `POST /meal-plan/generate`, `GET /meal-plan`, `DELETE /meal-plan`.

- [ ] **Step 1: Add schemas** — in `schemas.py`, near the other recipe/plan schemas

```python
class MealPlanGenerateRequest(BaseModel):
    days:          int = Field(..., ge=1, le=7)
    meals_per_day: int = Field(..., ge=2, le=4)
    diet_tags:     List[str] = Field(default_factory=list)

    @validator("diet_tags")
    def _validate(cls, v):
        valid = {
            "vegan", "vegetarian", "pescatarian", "flexitarian",
            "gluten_free", "dairy_free", "nut_free", "soy_free",
            "egg_free", "shellfish_free",
            "keto", "low_carb", "paleo", "whole30", "low_fodmap",
            "diabetic_friendly", "low_sodium", "low_fat", "high_protein",
            "halal", "kosher", "mediterranean", "dash",
        }
        bad = set(v) - valid
        if bad:
            raise ValueError("Unknown diet tag(s): %s" % sorted(bad))
        return v


class MealPlanRecipeMini(BaseModel):
    id:              uuid.UUID
    name:            str
    image_url:       Optional[str]
    servings:        float
    meal_type:       Optional[str]
    total_calories:  Optional[float]
    total_protein_g: Optional[float]
    total_fat_g:     Optional[float]
    total_carbs_g:   Optional[float]
    total_fiber_g:   Optional[float]


class MealPlanEntryResponse(BaseModel):
    id:        uuid.UUID
    slot:      str
    servings:  float
    unfilled:  bool
    recipe:    Optional[MealPlanRecipeMini]
    calories:  Optional[float]
    protein_g: Optional[float]
    fat_g:     Optional[float]
    carbs_g:   Optional[float]
    fiber_g:   Optional[float]


class MealPlanDayResponse(BaseModel):
    day_index:  int
    logged_at:  Optional[datetime]
    entries:    List[MealPlanEntryResponse]
    totals:     Dict[str, float]
    structurally_unfilled_slots: List[str]


class MealPlanTargets(BaseModel):
    kcal:      Optional[float]
    protein_g: Optional[float]
    fat_g:     Optional[float]
    carbs_g:   Optional[float]


class MealPlanResponse(BaseModel):
    id:            uuid.UUID
    days:          int
    meals_per_day: int
    created_at:    datetime
    targets:       MealPlanTargets
    plan_days:     List[MealPlanDayResponse]
```

Add `from typing import Dict` to `schemas.py` imports if not present.

- [ ] **Step 2: Write the failing route tests** — `tests/test_meal_plan_routes.py`

```python
import asyncio
import json
import uuid

from auth import get_current_user, hash_password
from main import app
from models import MealPlan, Recipe, User


async def _user(db_session, *, kcal=2000.0, protein=120.0, fat=65.0, carbs=220.0, custom=False):
    u = User(
        id=uuid.uuid4(), email=f"{uuid.uuid4()}@e.com", username=uuid.uuid4().hex[:8],
        hashed_password=hash_password("x"), email_verified=True, safe_mode=False,
        uses_custom_goals=custom, is_admin=False,
    )
    if custom:
        u.custom_kcal, u.custom_protein, u.custom_fat, u.custom_carbs = kcal, protein, fat, carbs
    else:
        u.target_kcal, u.protein_g, u.fat_g, u.carbs_g = kcal, protein, fat, carbs
    db_session.add(u)
    await db_session.flush()
    return u


async def _recipe(db_session, user, *, name, kcal, mt="any", shared=True, tags=None,
                  p=25.0, f=20.0, c=60.0):
    r = Recipe(
        id=uuid.uuid4(), user_id=user.id, name=name, servings=1.0, is_shared=shared,
        meal_type=mt, diet_tags=(",".join(tags) if tags else None),
        total_calories=kcal, total_protein_g=p, total_fat_g=f, total_carbs_g=c, total_fiber_g=6.0,
    )
    db_session.add(r)
    await db_session.flush()
    return r


def _as(client, user):
    app.dependency_overrides[get_current_user] = lambda: user
    return client


def test_generate_422_without_calorie_target(client, db_session):
    u = asyncio.get_event_loop().run_until_complete(_user(db_session, kcal=None))
    try:
        res = _as(client, u).post("/meal-plan/generate", json={"days": 2, "meals_per_day": 3, "diet_tags": []})
        assert res.status_code == 422
        assert "onboarding" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_generate_422_when_no_recipes_match_filters(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    loop.run_until_complete(_recipe(db_session, u, name="Meat Stew", kcal=600, tags=None))
    loop.run_until_complete(db_session.commit())
    try:
        res = _as(client, u).post("/meal-plan/generate",
                                  json={"days": 1, "meals_per_day": 3, "diet_tags": ["vegan"]})
        assert res.status_code == 422
        assert "no recipes" in res.json()["detail"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_generate_get_and_regenerate_replaces(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    for i, (name, kcal, mt) in enumerate([
        ("Oats", 450, "breakfast"), ("Salad", 650, "lunch"),
        ("Curry", 700, "dinner"), ("Stew", 680, "dinner"), ("Bowl", 600, "any"),
    ]):
        loop.run_until_complete(_recipe(db_session, u, name=name, kcal=kcal, mt=mt))
    loop.run_until_complete(db_session.commit())
    try:
        c = _as(client, u)
        res = c.post("/meal-plan/generate", json={"days": 2, "meals_per_day": 3, "diet_tags": []})
        assert res.status_code == 200
        body = res.json()
        assert body["days"] == 2 and len(body["plan_days"]) == 2
        assert len(body["plan_days"][0]["entries"]) == 3
        assert body["targets"]["kcal"] == 2000.0
        first_id = body["id"]

        got = c.get("/meal-plan").json()
        assert got["id"] == first_id

        res2 = c.post("/meal-plan/generate", json={"days": 1, "meals_per_day": 2, "diet_tags": []})
        assert res2.status_code == 200
        assert res2.json()["id"] != first_id
        plans = loop.run_until_complete(db_session.execute(MealPlan.__table__.select())).fetchall()
        assert len(plans) == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_get_meal_plan_null_when_none(client, db_session):
    u = asyncio.get_event_loop().run_until_complete(_user(db_session))
    try:
        assert _as(client, u).get("/meal-plan").json() is None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_meal_plan(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    for name, kcal, mt in [("Oats", 450, "breakfast"), ("Salad", 650, "lunch"), ("Curry", 700, "dinner")]:
        loop.run_until_complete(_recipe(db_session, u, name=name, kcal=kcal, mt=mt))
    loop.run_until_complete(db_session.commit())
    try:
        c = _as(client, u)
        assert c.post("/meal-plan/generate", json={"days": 1, "meals_per_day": 3, "diet_tags": []}).status_code == 200
        assert c.delete("/meal-plan").status_code == 204
        assert c.get("/meal-plan").json() is None
        assert c.delete("/meal-plan").status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_meal_plan_routes.py -q`
Expected: FAIL — 404 on `/meal-plan/generate` (route not defined).

- [ ] **Step 4: Implement the helpers + routes** — in `main.py`

Add to the schema import line: `MealPlanGenerateRequest, MealPlanResponse, MealPlanRecipeMini, MealPlanEntryResponse, MealPlanDayResponse, MealPlanTargets`. Add near the other imports: `from meal_planner import generate_plan, swap_entry, RecipeOption` and `from datetime import timedelta` (if not already imported — `date` and `datetime` already are).

Add the helpers (near `_diet_tags_to_str`):

```python
def _resolve_targets(user: User) -> dict:
    if user.uses_custom_goals:
        return {"kcal": user.custom_kcal, "protein_g": user.custom_protein,
                "fat_g": user.custom_fat, "carbs_g": user.custom_carbs}
    return {"kcal": user.target_kcal, "protein_g": user.protein_g,
            "fat_g": user.fat_g, "carbs_g": user.carbs_g}


def _recipe_to_option(r: Recipe) -> RecipeOption:
    return RecipeOption(
        id=str(r.id), name=r.name,
        meal_type=(r.meal_type or "any"),
        diet_tags=frozenset(t for t in (r.diet_tags or "").split(",") if t),
        kcal=r.total_calories or 0.0,
        protein_g=r.total_protein_g or 0.0, fat_g=r.total_fat_g or 0.0,
        carbs_g=r.total_carbs_g or 0.0, fiber_g=r.total_fiber_g or 0.0,
    )


async def _load_plan(db: AsyncSession, user_id) -> Optional[MealPlan]:
    res = await db.execute(
        select(MealPlan).where(MealPlan.user_id == user_id)
        .options(selectinload(MealPlan.entries).selectinload(MealPlanEntry.recipe))
    )
    return res.scalars().first()


def _plan_to_response(plan: MealPlan) -> MealPlanResponse:
    by_day: dict = {}
    for e in plan.entries:
        by_day.setdefault(e.day_index, []).append(e)
    plan_days = []
    for di in range(plan.days):
        entries = sorted(by_day.get(di, []), key=lambda e: SLOT_ORDER_INDEX.get(e.slot, 9))
        ent_resp, unfilled_slots = [], []
        totals = {"calories": 0.0, "protein_g": 0.0, "fat_g": 0.0, "carbs_g": 0.0, "fiber_g": 0.0}
        for e in entries:
            unfilled = e.recipe_id is None
            if unfilled:
                unfilled_slots.append(e.slot)
            rec = None
            if e.recipe is not None:
                rec = MealPlanRecipeMini(
                    id=e.recipe.id, name=e.recipe.name, image_url=e.recipe.image_url,
                    servings=e.recipe.servings, meal_type=e.recipe.meal_type,
                    total_calories=e.recipe.total_calories, total_protein_g=e.recipe.total_protein_g,
                    total_fat_g=e.recipe.total_fat_g, total_carbs_g=e.recipe.total_carbs_g,
                    total_fiber_g=e.recipe.total_fiber_g,
                )
            ent_resp.append(MealPlanEntryResponse(
                id=e.id, slot=e.slot, servings=e.servings, unfilled=unfilled, recipe=rec,
                calories=e.calories, protein_g=e.protein_g, fat_g=e.fat_g,
                carbs_g=e.carbs_g, fiber_g=e.fiber_g,
            ))
            for tk, ek in (("calories", "calories"), ("protein_g", "protein_g"),
                           ("fat_g", "fat_g"), ("carbs_g", "carbs_g"), ("fiber_g", "fiber_g")):
                totals[tk] += getattr(e, ek) or 0.0
        totals = {k: round(v, 1) for k, v in totals.items()}
        first_day_logged = json.loads(plan.logged_days or "{}").get(str(di))
        plan_days.append(MealPlanDayResponse(
            day_index=di,
            logged_at=(datetime.fromisoformat(first_day_logged) if first_day_logged else None),
            entries=ent_resp, totals=totals, structurally_unfilled_slots=unfilled_slots,
        ))
    return MealPlanResponse(
        id=plan.id, days=plan.days, meals_per_day=plan.meals_per_day, created_at=plan.created_at,
        targets=MealPlanTargets(kcal=plan.target_kcal, protein_g=plan.target_protein_g,
                                fat_g=plan.target_fat_g, carbs_g=plan.target_carbs_g),
        plan_days=plan_days,
    )
```

Add near the top of `main.py` (module scope): `import json` (if not already), and `SLOT_ORDER_INDEX = {"breakfast": 0, "lunch": 1, "dinner": 2, "snack": 3}`.

Add the routes (place them after the recipe routes, before or after `/recipes/shared`):

```python
@app.post("/meal-plan/generate", response_model=MealPlanResponse)
async def generate_meal_plan(
    payload:      MealPlanGenerateRequest,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    targets = _resolve_targets(current_user)
    if targets["kcal"] is None:
        raise HTTPException(status_code=422,
                            detail="Finish onboarding to set your calorie target before planning meals.")

    pool_rows = (await db.execute(
        select(Recipe).where(
            (Recipe.is_shared == True) | (Recipe.user_id == current_user.id),  # noqa: E712
            Recipe.total_calories.isnot(None),
        )
    )).scalars().all()
    diet = frozenset(payload.diet_tags)
    options = [_recipe_to_option(r) for r in pool_rows]
    if not [o for o in options if diet <= o.diet_tags]:
        raise HTTPException(status_code=422,
                            detail="No recipes match those dietary filters. Add recipes or loosen the filter.")

    planned = generate_plan(options, payload.days, payload.meals_per_day, targets, diet)

    existing = await _load_plan(db, current_user.id)
    if existing is not None:
        await db.delete(existing)
        await db.flush()

    plan = MealPlan(
        user_id=current_user.id, days=payload.days, meals_per_day=payload.meals_per_day,
        target_kcal=targets["kcal"], target_protein_g=targets["protein_g"],
        target_fat_g=targets["fat_g"], target_carbs_g=targets["carbs_g"],
        diet_tags=",".join(payload.diet_tags), logged_days="{}",
    )
    db.add(plan)
    await db.flush()
    for di, day in enumerate(planned):
        for e in day.entries:
            db.add(MealPlanEntry(
                plan_id=plan.id, day_index=di, slot=e.slot,
                recipe_id=(uuid.UUID(e.option.id) if e.option is not None else None),
                servings=e.servings,
                calories=(e.kcal or None), protein_g=(e.protein_g or None),
                fat_g=(e.fat_g or None), carbs_g=(e.carbs_g or None), fiber_g=(e.fiber_g or None),
            ))
    await db.flush()
    plan = await _load_plan(db, current_user.id)
    return _plan_to_response(plan)


@app.get("/meal-plan", response_model=Optional[MealPlanResponse])
async def get_meal_plan(
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    plan = await _load_plan(db, current_user.id)
    return _plan_to_response(plan) if plan is not None else None


@app.delete("/meal-plan", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meal_plan(
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    plan = await _load_plan(db, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No meal plan to delete.")
    await db.delete(plan)
```

Add `MealPlan, MealPlanEntry` to the `from models import ...` line in `main.py`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_meal_plan_routes.py -q`
Expected: PASS.

- [ ] **Step 6: Run the full backend suite + openapi sanity**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add schemas.py main.py tests/test_meal_plan_routes.py
git commit -m "feat(meal-planner): POST /meal-plan/generate, GET /meal-plan, DELETE /meal-plan"
```

---

## Task 6: API — swap and day-log

**Files:**
- Modify: `schemas.py`
- Modify: `main.py`
- Test: `tests/test_meal_plan_routes.py`

**Interfaces:**
- Consumes: `_load_plan`, `_recipe_to_option`, `_plan_to_response`, `SLOT_ORDER_INDEX`, `meal_planner.swap_entry`, `meal_planner.slot_budgets`, `meal_planner.PlannedEntry`, `models.FoodLog`.
- Produces:
  - Schemas `MealPlanSwapResponse` (`entry: MealPlanEntryResponse`, `day_totals: Dict[str, float]`), `MealPlanDayLogRequest` (`force: bool = False`), `MealPlanDayLogResponse` (`created: int`, `logged_at: datetime`).
  - Routes `POST /meal-plan/entries/{entry_id}/swap`, `POST /meal-plan/days/{day_index}/log`.

- [ ] **Step 1: Add schemas** — `schemas.py`

```python
class MealPlanSwapResponse(BaseModel):
    entry:      MealPlanEntryResponse
    day_totals: Dict[str, float]


class MealPlanDayLogRequest(BaseModel):
    force: bool = False


class MealPlanDayLogResponse(BaseModel):
    created:   int
    logged_at: datetime
```

- [ ] **Step 2: Write the failing tests** — append to `tests/test_meal_plan_routes.py`

```python
from datetime import date, timedelta
from models import FoodLog


def _generate(client, u, db_session, days=1, meals=3):
    loop = asyncio.get_event_loop()
    for name, kcal, mt in [
        ("Oats", 450, "breakfast"), ("Toast", 400, "breakfast"),
        ("Salad", 650, "lunch"), ("Wrap", 600, "lunch"),
        ("Curry", 700, "dinner"), ("Stew", 680, "dinner"),
    ]:
        loop.run_until_complete(_recipe(db_session, u, name=name, kcal=kcal, mt=mt))
    loop.run_until_complete(db_session.commit())
    return client.post("/meal-plan/generate",
                       json={"days": days, "meals_per_day": meals, "diet_tags": []}).json()


def test_swap_replaces_a_single_entry(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    c = _as(client, u)
    body = _generate(c, u, db_session)
    lunch = [e for e in body["plan_days"][0]["entries"] if e["slot"] == "lunch"][0]
    old_recipe_id = lunch["recipe"]["id"]

    res = c.post("/meal-plan/entries/%s/swap" % lunch["id"])
    assert res.status_code == 200
    swapped = res.json()
    assert swapped["entry"]["slot"] == "lunch"
    assert swapped["entry"]["recipe"]["id"] != old_recipe_id
    assert "calories" in swapped["day_totals"]


def test_swap_404_for_another_users_entry(client, db_session):
    loop = asyncio.get_event_loop()
    u1 = loop.run_until_complete(_user(db_session))
    u2 = loop.run_until_complete(_user(db_session))
    body = _generate(_as(client, u1), u1, db_session)
    entry_id = body["plan_days"][0]["entries"][0]["id"]
    _as(client, u2)
    assert client.post("/meal-plan/entries/%s/swap" % entry_id).status_code == 404
    app.dependency_overrides.pop(get_current_user, None)


def test_swap_409_when_no_alternative(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    # exactly one breakfast recipe -> nothing to swap it for
    loop.run_until_complete(_recipe(db_session, u, name="Only Oats", kcal=450, mt="breakfast"))
    loop.run_until_complete(_recipe(db_session, u, name="Lunch A", kcal=650, mt="lunch"))
    loop.run_until_complete(_recipe(db_session, u, name="Dinner A", kcal=700, mt="dinner"))
    loop.run_until_complete(db_session.commit())
    c = _as(client, u)
    body = c.post("/meal-plan/generate", json={"days": 1, "meals_per_day": 3, "diet_tags": []}).json()
    bfast = [e for e in body["plan_days"][0]["entries"] if e["slot"] == "breakfast"][0]
    assert c.post("/meal-plan/entries/%s/swap" % bfast["id"]).status_code == 409
    app.dependency_overrides.pop(get_current_user, None)


def test_day_log_creates_food_logs_then_409_then_force(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    c = _as(client, u)
    _generate(c, u, db_session, days=2, meals=3)

    res = c.post("/meal-plan/days/1/log", json={})
    assert res.status_code == 200
    assert res.json()["created"] == 3
    logs = loop.run_until_complete(db_session.execute(
        FoodLog.__table__.select().where(FoodLog.user_id == u.id))).fetchall()
    assert len(logs) == 3
    assert all(row.log_date == date.today() + timedelta(days=1) for row in logs)
    assert {row.meal for row in logs} == {"breakfast", "lunch", "dinner"}

    assert c.post("/meal-plan/days/1/log", json={}).status_code == 409
    assert c.post("/meal-plan/days/1/log", json={"force": True}).status_code == 200
    logs2 = loop.run_until_complete(db_session.execute(
        FoodLog.__table__.select().where(FoodLog.user_id == u.id))).fetchall()
    assert len(logs2) == 6

    app.dependency_overrides.pop(get_current_user, None)


def test_day_log_404_for_out_of_range_day(client, db_session):
    loop = asyncio.get_event_loop()
    u = loop.run_until_complete(_user(db_session))
    c = _as(client, u)
    _generate(c, u, db_session, days=1, meals=3)
    assert c.post("/meal-plan/days/5/log", json={}).status_code == 404
    app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_meal_plan_routes.py -q`
Expected: FAIL — 404 on the swap/log routes.

- [ ] **Step 4: Implement the routes** — `main.py` (add `MealPlanSwapResponse, MealPlanDayLogRequest, MealPlanDayLogResponse` to the schema import; add `active_slots, slot_budgets, PlannedEntry` to the `from meal_planner import` line; ensure `FoodLog` is in the `from models import` line — it already is)

```python
@app.post("/meal-plan/entries/{entry_id}/swap", response_model=MealPlanSwapResponse)
async def swap_meal_plan_entry(
    entry_id:     uuid.UUID,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    plan = await _load_plan(db, current_user.id)
    if plan is None:
        raise HTTPException(status_code=404, detail="No meal plan.")
    entry = next((e for e in plan.entries if e.id == entry_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not on your plan.")

    slots = active_slots(plan.meals_per_day)
    budgets = slot_budgets(plan.target_kcal, slots)
    day_target = {"kcal": plan.target_kcal, "protein_g": plan.target_protein_g,
                  "fat_g": plan.target_fat_g, "carbs_g": plan.target_carbs_g}
    diet = frozenset(t for t in (plan.diet_tags or "").split(",") if t)

    pool_rows = (await db.execute(
        select(Recipe).where(
            (Recipe.is_shared == True) | (Recipe.user_id == current_user.id),  # noqa: E712
            Recipe.total_calories.isnot(None),
        )
    )).scalars().all()
    options = [_recipe_to_option(r) for r in pool_rows]

    day_entries = []
    for e in plan.entries:
        if e.day_index != entry.day_index:
            continue
        opt = next((o for o in options if e.recipe_id is not None and o.id == str(e.recipe_id)), None)
        day_entries.append(PlannedEntry(
            slot=e.slot, option=opt, servings=e.servings,
            kcal=e.calories or 0.0, protein_g=e.protein_g or 0.0, fat_g=e.fat_g or 0.0,
            carbs_g=e.carbs_g or 0.0, fiber_g=e.fiber_g or 0.0,
        ))

    replacement = swap_entry(
        options, day_entries, entry.slot, budgets, day_target, diet,
        exclude_recipe_id=(str(entry.recipe_id) if entry.recipe_id else None),
    )
    if replacement is None:
        raise HTTPException(status_code=409, detail="No alternative recipe available for that slot.")

    entry.recipe_id = uuid.UUID(replacement.option.id)
    entry.servings = replacement.servings
    entry.calories = replacement.kcal or None
    entry.protein_g = replacement.protein_g or None
    entry.fat_g = replacement.fat_g or None
    entry.carbs_g = replacement.carbs_g or None
    entry.fiber_g = replacement.fiber_g or None
    await db.flush()

    plan = await _load_plan(db, current_user.id)
    resp = _plan_to_response(plan)
    day = next(d for d in resp.plan_days if d.day_index == entry.day_index)
    ent = next(e for e in day.entries if e.id == entry_id)
    return MealPlanSwapResponse(entry=ent, day_totals=day.totals)


@app.post("/meal-plan/days/{day_index}/log", response_model=MealPlanDayLogResponse)
async def log_meal_plan_day(
    day_index:    int,
    payload:      MealPlanDayLogRequest,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    plan = await _load_plan(db, current_user.id)
    if plan is None or day_index < 0 or day_index >= plan.days:
        raise HTTPException(status_code=404, detail="Day not in your plan.")

    logged = json.loads(plan.logged_days or "{}")
    if str(day_index) in logged and not payload.force:
        raise HTTPException(status_code=409, detail="Day already logged. Send force to log it again.")

    log_date = date.today() + timedelta(days=day_index)
    created = 0
    for e in plan.entries:
        if e.day_index != day_index or e.recipe_id is None:
            continue
        recipe = e.recipe
        db.add(FoodLog(
            user_id=current_user.id, log_date=log_date, meal=e.slot,
            recipe_id=e.recipe_id, food_name=(recipe.name if recipe else "Recipe"),
            amount_g=round((e.servings or 1.0) * 100, 1),
            calories=e.calories, protein_g=e.protein_g, fat_g=e.fat_g,
            carbs_g=e.carbs_g, fiber_g=e.fiber_g,
        ))
        created += 1

    now = datetime.utcnow()
    logged[str(day_index)] = now.isoformat()
    plan.logged_days = json.dumps(logged)
    await db.flush()
    return MealPlanDayLogResponse(created=created, logged_at=now)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_meal_plan_routes.py -q`
Expected: PASS.

- [ ] **Step 6: Full backend suite**

Run: `python -m pytest -q`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add schemas.py main.py tests/test_meal_plan_routes.py
git commit -m "feat(meal-planner): entry swap + per-day diary logging routes"
```

---

## Task 7: API — `meal_type` on recipes, `diet_tags` on the user

**Files:**
- Modify: `schemas.py`
- Modify: `main.py`
- Test: `tests/test_meal_plan_routes.py`

**Interfaces:**
- Produces: `RecipeCreateRequest.meal_type` / `RecipeUpdateRequest.meal_type` / `RecipeResponse.meal_type`; `UserUpdateRequest.diet_tags` / `UserResponse.diet_tags`.

- [ ] **Step 1: Write the failing tests** — append to `tests/test_meal_plan_routes.py`

```python
def test_recipe_meal_type_round_trips_and_rejects_bad_values(client, db_session):
    u = asyncio.get_event_loop().run_until_complete(_user(db_session))
    u.is_admin = False
    try:
        c = _as(client, u)
        res = c.post("/recipes", json={
            "name": "Test Oats", "servings": 1,
            "ingredients": [{"food_name": "oats", "amount_g": 50}],
            "meal_type": "breakfast",
        })
        assert res.status_code == 201
        rid = res.json()["id"]
        assert res.json()["meal_type"] == "breakfast"

        assert c.patch("/recipes/%s" % rid, json={"meal_type": "dinner"}).json()["meal_type"] == "dinner"
        assert c.post("/recipes", json={
            "name": "Bad", "servings": 1,
            "ingredients": [{"food_name": "x", "amount_g": 1}], "meal_type": "brunch",
        }).status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_user_diet_tags_round_trip(client, db_session):
    u = asyncio.get_event_loop().run_until_complete(_user(db_session))
    try:
        c = _as(client, u)
        assert c.get("/users/me").json()["diet_tags"] == []
        res = c.patch("/users/me", json={"diet_tags": ["vegan", "gluten_free"]})
        assert res.status_code == 200
        assert sorted(res.json()["diet_tags"]) == ["gluten_free", "vegan"]
        assert sorted(c.get("/users/me").json()["diet_tags"]) == ["gluten_free", "vegan"]
        assert c.patch("/users/me", json={"diet_tags": ["carnivore"]}).status_code == 422
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_meal_plan_routes.py -k "meal_type or diet_tags" -v`
Expected: FAIL — `meal_type` not on response / `diet_tags` rejected by `UserUpdateRequest`.

- [ ] **Step 3: Implement — schemas** (`schemas.py`)

`RecipeCreateRequest` and `RecipeUpdateRequest`: add

```python
    meal_type:    Optional[str] = None

    @validator("meal_type")
    def _validate_meal_type(cls, v):
        if v is None:
            return v
        if v not in {"breakfast", "lunch", "dinner", "snack", "any"}:
            raise ValueError("meal_type must be one of breakfast, lunch, dinner, snack, any")
        return v
```

`RecipeResponse`: add `meal_type: Optional[str]`.

`UserResponse`: add `diet_tags: List[str]` and, near the other validators:

```python
    @validator("diet_tags", pre=True)
    def _split_user_diet_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [t for t in v.split(",") if t]
        return v
```

`UserUpdateRequest`: add

```python
    diet_tags: Optional[List[str]] = None

    @validator("diet_tags")
    def _validate_user_diet_tags(cls, v):
        if v is None:
            return v
        valid = {
            "vegan", "vegetarian", "pescatarian", "flexitarian",
            "gluten_free", "dairy_free", "nut_free", "soy_free",
            "egg_free", "shellfish_free",
            "keto", "low_carb", "paleo", "whole30", "low_fodmap",
            "diabetic_friendly", "low_sodium", "low_fat", "high_protein",
            "halal", "kosher", "mediterranean", "dash",
        }
        bad = set(v) - valid
        if bad:
            raise ValueError("Unknown diet tag(s): %s" % sorted(bad))
        return v
```

- [ ] **Step 4: Implement — routes** (`main.py`)

In `create_recipe`, add to the `Recipe(...)` constructor: `meal_type = payload.meal_type,`.

In `update_recipe`, add alongside the other `if payload.X is not None:` lines:

```python
    if payload.meal_type    is not None: recipe.meal_type    = payload.meal_type
```

In `update_me`, add before `await db.flush()`:

```python
    if payload.diet_tags is not None:
        current_user.diet_tags = _diet_tags_to_str(payload.diet_tags)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_meal_plan_routes.py -q`
Expected: PASS.

- [ ] **Step 6: Full backend suite**

Run: `python -m pytest -q`
Expected: PASS (existing recipe/user route tests still green — the new fields are optional).

- [ ] **Step 7: Commit**

```bash
git add schemas.py main.py tests/test_meal_plan_routes.py
git commit -m "feat(meal-planner): meal_type on recipe API, diet_tags on user API"
```

---

## Task 8: Frontend — Meal Planner screen (generate + view)

**Files:**
- Create: `pakupaku-frontend/src/components/MealPlanner.tsx`
- Create: `pakupaku-frontend/src/components/MealPlanner.css`
- Create: `pakupaku-frontend/src/components/MealPlanner.test.tsx`
- Modify: `pakupaku-frontend/src/App.tsx`
- Modify: `pakupaku-frontend/src/components/Dashboard.tsx`
- Modify: `pakupaku-frontend/src/components/Dashboard.css`

**Interfaces:**
- Consumes: `apiFetch` from `../apiBase`; the `MealPlanResponse` shape from Task 5.
- Produces: `<MealPlanner onBack userProfile />` default export; `AppView` includes `"mealPlanner"`; `DashboardProps.onOpenMealPlanner: () => void`.

- [ ] **Step 1: Write the failing test** — `pakupaku-frontend/src/components/MealPlanner.test.tsx`

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import MealPlanner from "./MealPlanner";

const planResponse = {
  id: "11111111-1111-1111-1111-111111111111",
  days: 1,
  meals_per_day: 3,
  created_at: "2026-09-10T00:00:00Z",
  targets: { kcal: 2000, protein_g: 120, fat_g: 65, carbs_g: 220 },
  plan_days: [
    {
      day_index: 0,
      logged_at: null,
      structurally_unfilled_slots: [],
      totals: { calories: 1950, protein_g: 118, fat_g: 62, carbs_g: 210, fiber_g: 30 },
      entries: [
        { id: "e1", slot: "breakfast", servings: 1.1, unfilled: false,
          recipe: { id: "r1", name: "Overnight Oats", image_url: null, servings: 1,
                    meal_type: "breakfast", total_calories: 450, total_protein_g: 20,
                    total_fat_g: 10, total_carbs_g: 70, total_fiber_g: 8 },
          calories: 495, protein_g: 22, fat_g: 11, carbs_g: 77, fiber_g: 9 },
        { id: "e2", slot: "lunch", servings: 1, unfilled: false,
          recipe: { id: "r2", name: "Chickpea Salad", image_url: null, servings: 1,
                    meal_type: "lunch", total_calories: 650, total_protein_g: 40,
                    total_fat_g: 25, total_carbs_g: 60, total_fiber_g: 12 },
          calories: 650, protein_g: 40, fat_g: 25, carbs_g: 60, fiber_g: 12 },
        { id: "e3", slot: "dinner", servings: 1.2, unfilled: false,
          recipe: { id: "r3", name: "Lentil Curry", image_url: null, servings: 1,
                    meal_type: "dinner", total_calories: 700, total_protein_g: 45,
                    total_fat_g: 22, total_carbs_g: 78, total_fiber_g: 14 },
          calories: 805, protein_g: 56, fat_g: 26, carbs_g: 73, fiber_g: 9 },
      ],
    },
  ],
};

beforeEach(() => {
  localStorage.setItem("token", "t");
  global.fetch = jest.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/meal-plan") && (!init || !init.method || init.method === "GET")) {
      return Promise.resolve({ ok: true, json: async () => null } as Response);
    }
    if (u.endsWith("/meal-plan/generate")) {
      return Promise.resolve({ ok: true, json: async () => planResponse } as Response);
    }
    return Promise.reject(new Error("unexpected " + u));
  }) as jest.Mock;
});
afterEach(() => { jest.restoreAllMocks(); localStorage.clear(); });

test("shows the generate form, then renders the plan with day totals", async () => {
  render(<MealPlanner onBack={() => {}} userProfile={{ diet_tags: [], safe_mode: false }} />);
  await waitFor(() => expect(screen.getByText("Generate plan")).toBeInTheDocument());

  fireEvent.click(screen.getByText("Generate plan"));

  await waitFor(() => expect(screen.getByText("Overnight Oats")).toBeInTheDocument());
  expect(screen.getByText("Chickpea Salad")).toBeInTheDocument();
  expect(screen.getByText("Lentil Curry")).toBeInTheDocument();
  // per-day totals vs target visible (calories number rendered somewhere)
  expect(screen.getByText(/1950/)).toBeInTheDocument();
});

test("pre-checks diet tags from the user profile", async () => {
  render(<MealPlanner onBack={() => {}} userProfile={{ diet_tags: ["vegan"], safe_mode: false }} />);
  await waitFor(() => expect(screen.getByText("Generate plan")).toBeInTheDocument());
  const vegan = screen.getByLabelText("vegan") as HTMLInputElement;
  expect(vegan.checked).toBe(true);
});

test("generate error is shown inline", async () => {
  (global.fetch as jest.Mock).mockImplementation((url: RequestInfo | URL) => {
    const u = String(url);
    if (u.endsWith("/meal-plan/generate")) {
      return Promise.resolve({ ok: false, json: async () => ({ detail: "Finish onboarding to set your calorie target before planning meals." }) } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => null } as Response);
  });
  render(<MealPlanner onBack={() => {}} userProfile={{ diet_tags: [], safe_mode: false }} />);
  await waitFor(() => expect(screen.getByText("Generate plan")).toBeInTheDocument());
  fireEvent.click(screen.getByText("Generate plan"));
  await waitFor(() => expect(screen.getByText(/Finish onboarding/)).toBeInTheDocument());
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `pakupaku-frontend/`): `CI=true npx react-scripts test --testPathPattern=MealPlanner --watchAll=false`
Expected: FAIL — cannot find module `./MealPlanner`.

- [ ] **Step 3: Implement `MealPlanner.tsx`**

```tsx
import { useEffect, useState } from "react";
import "./MealPlanner.css";
import { apiFetch } from "../apiBase";

const DIET_TAGS = [
  "vegan", "vegetarian", "pescatarian", "flexitarian",
  "gluten_free", "dairy_free", "nut_free", "soy_free", "egg_free", "shellfish_free",
  "keto", "low_carb", "paleo", "whole30", "low_fodmap",
  "diabetic_friendly", "low_sodium", "low_fat", "high_protein",
  "halal", "kosher", "mediterranean", "dash",
];

interface RecipeMini {
  id: string; name: string; image_url: string | null;
}
interface Entry {
  id: string; slot: string; servings: number; unfilled: boolean;
  recipe: RecipeMini | null;
  calories: number | null; protein_g: number | null; fat_g: number | null; carbs_g: number | null;
}
interface Day {
  day_index: number; logged_at: string | null;
  structurally_unfilled_slots: string[];
  totals: Record<string, number>;
  entries: Entry[];
}
interface Plan {
  id: string; days: number; meals_per_day: number;
  targets: { kcal: number | null; protein_g: number | null; fat_g: number | null; carbs_g: number | null };
  plan_days: Day[];
}

interface Props { onBack: () => void; userProfile: any; }

function authHeaders(extra: Record<string, string> = {}) {
  const token = localStorage.getItem("token");
  return { Authorization: token ? `Bearer ${token}` : "", ...extra };
}

const dayLabel = (i: number) => (i === 0 ? "Today" : i === 1 ? "Tomorrow" : `Day ${i + 1}`);
const num = (v: number | null | undefined) => (v == null ? "–" : Math.round(v).toString());
const bar = (actual: number | undefined, target: number | null) => {
  if (!target || !actual) return 0;
  return Math.min(100, Math.round((actual / target) * 100));
};

export default function MealPlanner({ onBack, userProfile }: Props) {
  const safeMode = !!userProfile?.safe_mode;
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  const [days, setDays] = useState(3);
  const [mealsPerDay, setMealsPerDay] = useState(3);
  const [tags, setTags] = useState<string[]>(userProfile?.diet_tags ?? []);
  const [showForm, setShowForm] = useState(false);

  useEffect(() => {
    apiFetch("/meal-plan", { headers: authHeaders() })
      .then(r => (r.ok ? r.json() : null))
      .then((p: Plan | null) => { setPlan(p); setShowForm(p == null); })
      .catch(() => setError("Couldn't load your meal plan."))
      .finally(() => setLoading(false));
  }, []);

  const toggleTag = (t: string) =>
    setTags(ts => (ts.includes(t) ? ts.filter(x => x !== t) : [...ts, t]));

  const generate = async () => {
    setError("");
    setGenerating(true);
    try {
      const res = await apiFetch("/meal-plan/generate", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ days, meals_per_day: mealsPerDay, diet_tags: tags }),
      });
      const body = await res.json();
      if (!res.ok) { setError(body?.detail || "Couldn't generate a plan."); return; }
      setPlan(body);
      setShowForm(false);
    } catch {
      setError("Couldn't generate a plan.");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="meal-planner-root">
      <div className="meal-planner-container">
        <header className="meal-planner-header">
          <button type="button" className="back-button" onClick={onBack}>← Back</button>
          <h1 className="meal-planner-title">Meal Planner</h1>
          {plan && !showForm && (
            <button type="button" className="meal-planner-regen" onClick={() => setShowForm(true)}>
              Regenerate
            </button>
          )}
        </header>

        {error && <p className="meal-planner-error">{error}</p>}
        {loading && <p className="empty-state">Loading…</p>}

        {!loading && showForm && (
          <div className="meal-planner-form">
            <label className="meal-planner-field">
              <span>Days</span>
              <input type="number" min={1} max={7} value={days}
                onChange={e => setDays(Math.min(7, Math.max(1, Number(e.target.value) || 1)))} />
            </label>
            <label className="meal-planner-field">
              <span>Meals per day</span>
              <select value={mealsPerDay} onChange={e => setMealsPerDay(Number(e.target.value))}>
                <option value={2}>2</option><option value={3}>3</option><option value={4}>4</option>
              </select>
            </label>
            <fieldset className="meal-planner-tags">
              <legend>Dietary filters</legend>
              {DIET_TAGS.map(t => (
                <label key={t}>
                  <input type="checkbox" checked={tags.includes(t)} onChange={() => toggleTag(t)} />
                  {t.replace(/_/g, " ")}
                </label>
              ))}
            </fieldset>
            <button type="button" className="meal-planner-generate" disabled={generating} onClick={generate}>
              {generating ? "Building your plan…" : "Generate plan"}
            </button>
          </div>
        )}

        {!loading && !showForm && plan && (
          <div className="meal-planner-days">
            {plan.plan_days.map(day => (
              <section key={day.day_index} className="meal-planner-day">
                <h2>{dayLabel(day.day_index)}</h2>
                <div className="meal-planner-entries">
                  {day.entries.map(e => (
                    <div key={e.id} className="meal-planner-entry" data-slot={e.slot}>
                      {e.unfilled ? (
                        <div className="meal-planner-entry-empty">
                          No {e.slot} recipe available
                          {day.structurally_unfilled_slots.includes(e.slot)
                            ? ` — add one with meal type "${e.slot}"` : ""}
                        </div>
                      ) : (
                        <>
                          {e.recipe?.image_url && (
                            <img src={e.recipe.image_url} alt="" className="meal-planner-entry-img" />
                          )}
                          <div className="meal-planner-entry-body">
                            <span className="meal-planner-slot">{e.slot}</span>
                            <span className="meal-planner-recipe-name">{e.recipe?.name}</span>
                            <span className="meal-planner-servings">
                              {e.servings} serving{e.servings === 1 ? "" : "s"}
                            </span>
                            {!safeMode && (
                              <span className="meal-planner-entry-macros">
                                {num(e.calories)} kcal · {num(e.protein_g)}p · {num(e.fat_g)}f · {num(e.carbs_g)}c
                              </span>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  ))}
                </div>
                <div className="meal-planner-totals">
                  {(["calories", "protein_g", "fat_g", "carbs_g"] as const).map(k => {
                    const tgt = k === "calories" ? plan.targets.kcal : (plan.targets as any)[k];
                    return (
                      <div key={k} className="meal-planner-total">
                        <span className="meal-planner-total-label">
                          {k === "calories" ? "kcal" : k.replace("_g", "")}
                        </span>
                        <div className="meal-planner-total-bar">
                          <div className="meal-planner-total-fill"
                               style={{ width: `${bar(day.totals[k], tgt)}%` }} />
                        </div>
                        {!safeMode && (
                          <span className="meal-planner-total-num">
                            {num(day.totals[k])}{tgt ? ` / ${num(tgt)}` : ""}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Add `MealPlanner.css`** (mirror the wide-layout pattern)

```css
.meal-planner-root { min-height: 100vh; padding: 2rem clamp(1rem, 3vw, 2.5rem); font-family: "MorningBreeze"; }
.meal-planner-container { max-width: 1200px; margin: 0 auto; }
.meal-planner-header { display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; }
.meal-planner-title { font-size: 2rem; margin: 0; color: #3a2a2a; }
.meal-planner-regen { margin-left: auto; padding: 0.45rem 0.9rem; border: 2px solid #badfdb;
  border-radius: 999px; background: #fff; color: #3a6b66; font-weight: 600; cursor: pointer; }
.meal-planner-error { color: #c0607a; margin: 0 0 1rem; }
.meal-planner-form { display: flex; flex-direction: column; gap: 1rem; max-width: 560px; }
.meal-planner-field { display: flex; flex-direction: column; gap: 0.25rem; }
.meal-planner-field input, .meal-planner-field select { border: 2px solid #badfdb; border-radius: 10px;
  padding: 0.5rem 0.75rem; font-family: inherit; }
.meal-planner-tags { border: 2px solid #badfdb; border-radius: 12px; display: flex; flex-wrap: wrap;
  gap: 0.4rem 1rem; padding: 0.75rem; }
.meal-planner-tags label { font-size: 0.85rem; display: flex; gap: 0.3rem; align-items: center; }
.meal-planner-generate { border: none; background: #badfdb; color: #3a2a2a; border-radius: 10px;
  padding: 0.7rem 1rem; font-weight: 700; cursor: pointer; }
.meal-planner-days { display: flex; flex-direction: column; gap: 1.5rem; }
.meal-planner-day { border: 2px solid #badfdb; border-radius: 16px; padding: 1rem; }
.meal-planner-day h2 { margin: 0 0 0.75rem; color: #3a2a2a; }
.meal-planner-entries { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 0.75rem; }
.meal-planner-entry { border: 1px solid #d8ede9; border-radius: 12px; overflow: hidden; background: #fff; }
.meal-planner-entry-img { width: 100%; height: 110px; object-fit: cover; display: block; }
.meal-planner-entry-body { display: flex; flex-direction: column; gap: 0.2rem; padding: 0.6rem 0.75rem; }
.meal-planner-slot { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.04em; color: #8a6060; }
.meal-planner-recipe-name { font-weight: 600; color: #3a2a2a; }
.meal-planner-servings, .meal-planner-entry-macros { font-size: 0.8rem; color: #6a4f4f; }
.meal-planner-entry-empty { padding: 0.75rem; font-size: 0.85rem; color: #8a6060; }
.meal-planner-totals { display: flex; flex-wrap: wrap; gap: 0.75rem; margin-top: 0.9rem; }
.meal-planner-total { display: flex; align-items: center; gap: 0.4rem; font-size: 0.8rem; color: #6a4f4f; }
.meal-planner-total-bar { width: 90px; height: 8px; background: #eaf5f3; border-radius: 999px; overflow: hidden; }
.meal-planner-total-fill { height: 100%; background: #7cc0b8; }
@media (max-width: 640px) { .meal-planner-root { padding: 1rem 0.75rem; } }
```

- [ ] **Step 5: Wire into `App.tsx`**

Add the import: `import MealPlanner from "./components/MealPlanner";`
Extend `AppView`: `... | "mealPlanner"`.
Add before the `dashboard` block:

```tsx
  if (view === "mealPlanner") {
    return <MealPlanner onBack={() => setView("dashboard")} userProfile={userProfile} />;
  }
```

Add to the `<Dashboard ... />` props: `onOpenMealPlanner={() => setView("mealPlanner")}`.

- [ ] **Step 6: Wire into `Dashboard.tsx` + `.css`**

In `DashboardProps`, add `onOpenMealPlanner: () => void;`.
In the function signature destructure, add `onOpenMealPlanner`.
Next to the "Shared recipes" button (~line 642), add:

```tsx
              <button type="button" className="secondary-button" onClick={onOpenMealPlanner}>Meal planner</button>
```

`Dashboard.css`: no new rule needed (reuses `.secondary-button`). If the button row wraps oddly, that's acceptable for this task.

- [ ] **Step 7: Run the test + tsc**

Run (from `pakupaku-frontend/`):
`CI=true npx react-scripts test --testPathPattern=MealPlanner --watchAll=false`
`npx tsc --noEmit`
Expected: MealPlanner tests PASS; tsc clean.

- [ ] **Step 8: Run the whole frontend suite**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: green except the pre-existing `App.test.tsx` boilerplate failure. If a Dashboard test asserts an exact button list, update it to include "Meal planner".

- [ ] **Step 9: Commit**

```bash
git add pakupaku-frontend/src/components/MealPlanner.tsx pakupaku-frontend/src/components/MealPlanner.css pakupaku-frontend/src/components/MealPlanner.test.tsx pakupaku-frontend/src/App.tsx pakupaku-frontend/src/components/Dashboard.tsx pakupaku-frontend/src/components/Dashboard.css
git commit -m "feat(meal-planner): Meal Planner screen — generate form + plan view"
```

---

## Task 9: Frontend — swap + log-day actions

**Files:**
- Modify: `pakupaku-frontend/src/components/MealPlanner.tsx`
- Modify: `pakupaku-frontend/src/components/MealPlanner.test.tsx`

**Interfaces:**
- Consumes: `POST /meal-plan/entries/{id}/swap` → `{ entry, day_totals }`; `POST /meal-plan/days/{i}/log` → `{ created, logged_at }` or 409.

- [ ] **Step 1: Write the failing tests** — append to `MealPlanner.test.tsx`

```tsx
test("Swap replaces one entry in place and updates day totals", async () => {
  const swapResp = {
    entry: { id: "e2", slot: "lunch", servings: 1, unfilled: false,
      recipe: { id: "r9", name: "Tofu Poke Bowl", image_url: null, servings: 1,
                meal_type: "lunch", total_calories: 640, total_protein_g: 42,
                total_fat_g: 20, total_carbs_g: 62, total_fiber_g: 10 },
      calories: 640, protein_g: 42, fat_g: 20, carbs_g: 62, fiber_g: 10 },
    day_totals: { calories: 1940, protein_g: 120, fat_g: 57, carbs_g: 212, fiber_g: 28 },
  };
  (global.fetch as jest.Mock).mockImplementation((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/meal-plan") && (!init || !init.method || init.method === "GET"))
      return Promise.resolve({ ok: true, json: async () => planResponse } as Response);
    if (u.includes("/entries/e2/swap"))
      return Promise.resolve({ ok: true, json: async () => swapResp } as Response);
    return Promise.reject(new Error("unexpected " + u));
  });
  render(<MealPlanner onBack={() => {}} userProfile={{ diet_tags: [], safe_mode: false }} />);
  await waitFor(() => expect(screen.getByText("Chickpea Salad")).toBeInTheDocument());
  const lunchCard = screen.getByText("Chickpea Salad").closest(".meal-planner-entry") as HTMLElement;
  fireEvent.click(lunchCard.querySelector("button")!);   // the Swap button
  await waitFor(() => expect(screen.getByText("Tofu Poke Bowl")).toBeInTheDocument());
  expect(screen.queryByText("Chickpea Salad")).not.toBeInTheDocument();
});

test("Log this day posts, then shows a logged state; 409 prompts a force retry", async () => {
  let logCalls = 0;
  (global.fetch as jest.Mock).mockImplementation((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/meal-plan") && (!init || !init.method || init.method === "GET"))
      return Promise.resolve({ ok: true, json: async () => planResponse } as Response);
    if (u.includes("/days/0/log")) {
      logCalls += 1;
      const body = init && init.body ? JSON.parse(String(init.body)) : {};
      if (logCalls === 1)
        return Promise.resolve({ ok: false, status: 409,
          json: async () => ({ detail: "Day already logged. Send force to log it again." }) } as Response);
      return Promise.resolve({ ok: true, json: async () => ({ created: 3, logged_at: "2026-09-10T10:00:00Z" }) } as Response);
    }
    return Promise.reject(new Error("unexpected " + u));
  });
  window.confirm = jest.fn(() => true) as any;
  render(<MealPlanner onBack={() => {}} userProfile={{ diet_tags: [], safe_mode: false }} />);
  await waitFor(() => expect(screen.getByText("Log this day")).toBeInTheDocument());
  fireEvent.click(screen.getByText("Log this day"));
  await waitFor(() => expect(logCalls).toBe(2));
  await waitFor(() => expect(screen.getByText(/Logged/)).toBeInTheDocument());
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `CI=true npx react-scripts test --testPathPattern=MealPlanner --watchAll=false`
Expected: FAIL — no Swap button / no "Log this day" button.

- [ ] **Step 3: Implement — add to `MealPlanner.tsx`**

Add state near the others: `const [busyEntry, setBusyEntry] = useState<string | null>(null);`
Add handlers:

```tsx
  const swap = async (entryId: string) => {
    setBusyEntry(entryId);
    setError("");
    try {
      const res = await apiFetch(`/meal-plan/entries/${entryId}/swap`, {
        method: "POST", headers: authHeaders(),
      });
      const body = await res.json();
      if (!res.ok) { setError(body?.detail || "Couldn't swap that meal."); return; }
      setPlan(p => {
        if (!p) return p;
        return {
          ...p,
          plan_days: p.plan_days.map(d => ({
            ...d,
            totals: d.entries.some(e => e.id === entryId) ? body.day_totals : d.totals,
            entries: d.entries.map(e => (e.id === entryId ? body.entry : e)),
          })),
        };
      });
    } catch {
      setError("Couldn't swap that meal.");
    } finally {
      setBusyEntry(null);
    }
  };

  const logDay = async (dayIndex: number, force = false) => {
    setError("");
    try {
      const res = await apiFetch(`/meal-plan/days/${dayIndex}/log`, {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({ force }),
      });
      const body = await res.json();
      if (res.status === 409 && !force) {
        if (window.confirm("This day was already logged. Log it again?")) return logDay(dayIndex, true);
        return;
      }
      if (!res.ok) { setError(body?.detail || "Couldn't log that day."); return; }
      setPlan(p => p && {
        ...p,
        plan_days: p.plan_days.map(d =>
          d.day_index === dayIndex ? { ...d, logged_at: body.logged_at } : d),
      });
    } catch {
      setError("Couldn't log that day.");
    }
  };
```

In the entry render, inside the filled branch's `.meal-planner-entry-body`, after the macros span, add:

```tsx
                            <button type="button" className="meal-planner-swap"
                              disabled={busyEntry === e.id} onClick={() => swap(e.id)}>
                              {busyEntry === e.id ? "Swapping…" : "Swap"}
                            </button>
```

After the `.meal-planner-totals` div in each day `<section>`, add:

```tsx
                <button type="button" className="meal-planner-logday"
                  disabled={!!day.logged_at} onClick={() => logDay(day.day_index)}>
                  {day.logged_at ? "Logged ✓" : "Log this day"}
                </button>
```

Add to `MealPlanner.css`:

```css
.meal-planner-swap { align-self: flex-start; margin-top: 0.3rem; border: 1px solid #badfdb;
  background: transparent; border-radius: 8px; padding: 0.25rem 0.6rem; font-size: 0.78rem; cursor: pointer; }
.meal-planner-logday { margin-top: 0.9rem; border: none; background: #badfdb; color: #3a2a2a;
  border-radius: 10px; padding: 0.55rem 1rem; font-weight: 700; cursor: pointer; }
.meal-planner-logday:disabled { opacity: 0.6; cursor: default; }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `CI=true npx react-scripts test --testPathPattern=MealPlanner --watchAll=false` then `npx tsc --noEmit`
Expected: PASS; tsc clean.

- [ ] **Step 5: Commit**

```bash
git add pakupaku-frontend/src/components/MealPlanner.tsx pakupaku-frontend/src/components/MealPlanner.css pakupaku-frontend/src/components/MealPlanner.test.tsx
git commit -m "feat(meal-planner): swap a meal + log a day from the plan view"
```

---

## Task 10: Frontend — Settings diet prefs + recipe meal-type select

**Files:**
- Modify: `pakupaku-frontend/src/components/Settings.tsx`
- Modify: `pakupaku-frontend/src/components/RecipeEditForm.tsx`
- Modify: `pakupaku-frontend/src/components/Settings.test.tsx` (if it exists; else create a minimal one)
- Modify: `pakupaku-frontend/src/components/RecipeBuilder.test.tsx` (only if a save-payload assertion needs the new field)

**Interfaces:**
- Consumes: `PATCH /users/me` accepting `diet_tags`; `POST`/`PATCH /recipes` accepting `meal_type`; `UserResponse.diet_tags`; `RecipeResponse.meal_type`.

- [ ] **Step 1: Settings — read current shape**

Run: `sed -n '1,60p' pakupaku-frontend/src/components/Settings.tsx` and locate where it renders editable prefs and calls `PATCH /users/me`. Note the prop that carries the user object and the save handler name.

- [ ] **Step 2: Write the failing Settings test**

If `Settings.test.tsx` exists, append; else create it with the file's existing render pattern. Assert: given `userProfile.diet_tags = ["vegan"]`, the "vegan" checkbox is checked; ticking "keto" and clicking Save issues `PATCH /users/me` with `diet_tags` containing `"vegan"` and `"keto"`.

```tsx
test("dietary preferences: pre-checked, editable, saved", async () => {
  const patched: any[] = [];
  global.fetch = jest.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u.endsWith("/users/me") && init?.method === "PATCH") {
      patched.push(JSON.parse(String(init.body)));
      return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    }
    return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
  }) as jest.Mock;

  render(<Settings onBack={() => {}} userProfile={{ diet_tags: ["vegan"], safe_mode: false }} onUpdated={() => {}} />);
  const vegan = screen.getByLabelText("vegan") as HTMLInputElement;
  expect(vegan.checked).toBe(true);
  fireEvent.click(screen.getByLabelText("keto"));
  fireEvent.click(screen.getByText("Save dietary preferences"));
  await waitFor(() => expect(patched.length).toBe(1));
  expect(patched[0].diet_tags.sort()).toEqual(["keto", "vegan"]);
});
```

Adjust `Settings` prop names in the test to match the real component (from Step 1). If `Settings` takes the whole user via a different prop, use that.

- [ ] **Step 3: Run to verify it fails**

Run: `CI=true npx react-scripts test --testPathPattern=Settings --watchAll=false`
Expected: FAIL — no "vegan" checkbox.

- [ ] **Step 4: Implement in `Settings.tsx`**

Add the same `DIET_TAGS` array used in `MealPlanner.tsx` (import from a shared spot if one exists; otherwise copy the constant — it's already duplicated in `RecipeEditForm` per the codebase's pattern). Add a "Dietary preferences" section: a checkbox per tag pre-checked from the user's `diet_tags`, local state, and a "Save dietary preferences" button that calls `PATCH /users/me` with `{ diet_tags: selected }` and then refreshes the user (call whatever `onUpdated`/refetch mechanism Settings already uses for `safe_mode`).

- [ ] **Step 5: Implement in `RecipeEditForm.tsx`**

- Add `mealType: string` to `RecipeFormValues` (default `"any"` in `blankFormValues`).
- In `formValuesFromRecipe`: `mealType: recipe.meal_type ?? "any"`.
- In `formValuesFromDraft`: `mealType: "any"`.
- Add `meal_type: string` to `RecipeSavePayload`; in `payloadFromFormValues`, set `meal_type: values.mealType`.
- In the component: `const [mealType, setMealType] = useState(initialValues.mealType);` and a `<select>` in the form:

```tsx
      <label className="recipe-field recipe-field-inline">
        <span>Meal type</span>
        <select value={mealType} onChange={e => setMealType(e.target.value)}>
          <option value="any">Any</option>
          <option value="breakfast">Breakfast</option>
          <option value="lunch">Lunch</option>
          <option value="dinner">Dinner</option>
          <option value="snack">Snack</option>
        </select>
      </label>
```

- Pass `mealType` into the `payloadFromFormValues({ ... })` call in `handleSubmit`.

- [ ] **Step 6: Run the touched frontend tests + tsc**

Run: `CI=true npx react-scripts test --testPathPattern="Settings|RecipeBuilder|RecipeEditForm|BulkRecipeImport" --watchAll=false` then `npx tsc --noEmit`
Expected: PASS; tsc clean. If a `RecipeBuilder`/`BulkRecipeImport` test asserts the exact save payload, add `meal_type: "any"` to its expectation.

- [ ] **Step 7: Full frontend suite**

Run: `CI=true npx react-scripts test --watchAll=false`
Expected: green except the pre-existing `App.test.tsx` failure.

- [ ] **Step 8: Commit**

```bash
git add pakupaku-frontend/src/components/Settings.tsx pakupaku-frontend/src/components/Settings.test.tsx pakupaku-frontend/src/components/RecipeEditForm.tsx pakupaku-frontend/src/components/RecipeBuilder.test.tsx pakupaku-frontend/src/components/BulkRecipeImport.test.tsx
git commit -m "feat(meal-planner): diet prefs in Settings, meal type on the recipe form"
```

---

## Self-review notes (already reconciled)

- **Spec coverage:** data model → T1; `meal_type` heuristic/backfill → T2; buckets/budgets/`plan_day`/servings clamp/scoring → T3; `generate_plan` variety + `swap_entry` → T4; generate/get/delete + degenerate 422s → T5; swap 404/409 + day-log 409/force → T6; `meal_type`/`diet_tags` API → T7; generate form + plan view + safe_mode bars + `structurally_unfilled_slots` → T8; swap + log-day UI → T9; Settings prefs + recipe form select → T10; migration/backfill deploy wiring → T1 (+ docs). Frontend width pattern → T8 CSS.
- **Type consistency:** `RecipeOption` fields, `PlannedEntry`/`PlannedDay` shapes, `slot_budgets`/`active_slots`/`build_buckets`/`plan_day`/`generate_plan`/`swap_entry` signatures are defined in T3–T4 and consumed unchanged in T5–T6. `MealPlanResponse` nested shape defined in T5, consumed verbatim by the T8 frontend interfaces and the T9 swap-merge.
- **Known follow-ups (out of scope, do not implement):** plan history; shopping list; per-meal manual targets; excluding ingredients; a shared `DIET_TAGS` constant module (currently duplicated per the codebase's existing pattern).
