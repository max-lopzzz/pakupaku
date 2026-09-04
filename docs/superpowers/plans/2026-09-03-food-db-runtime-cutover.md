# Food Database Runtime Cutover — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the offline `foods` table the single food source for the app — recipe-import matching, the RecipeEditForm ingredient autocomplete, and Dashboard food logging all query an in-memory index over it; no USDA network call on any request path.

**Architecture:** A committed `data/foods.sqlite` (produced by the build-pipeline plan) is seeded into the `foods` table of every deployment's database. On API startup `food_index.py` loads all ~15k rows into memory and builds a normalised-token + `rapidfuzz` fuzzy index. `GET /foods/search`, `GET /foods/{food_id}`, `POST /foods/bulk`, and `recipe_import.match_ingredient` all go through that index. `fdc_id` (int, USDA) becomes `food_id` (str, `gen:NNNNN`) on `food_logs` and `recipe_ingredients`; historical rows keep their denormalised nutrients and their old stringified id.

**Tech Stack:** FastAPI + async SQLAlchemy 2.0, Python 3.8 (`typing.Optional`/`typing.List`, no `X | None`), Pydantic v1-style `BaseModel`, `rapidfuzz==3.9.7`, `@testing-library/react` + CRA for the frontend, `pytest` (`asyncio_mode = auto`).

**Spec:** `docs/superpowers/specs/2026-09-03-multi-country-food-database-design.md` (§"Runtime schema & matching", §"ID migration")

**Predecessor:** `docs/superpowers/plans/2026-09-03-food-db-build-pipeline.md` — must be merged, and its Task 9 (real `data/foods.sqlite` committed) ideally done. This plan works against a tiny fixture `foods.sqlite` until then; the seed step no-ops gracefully when the artifact is absent.

## Global Constraints

- **Python 3.8 syntax only** — `typing.Optional[X]` / `typing.List[X]` / `typing.Dict`, never `X | None` / `list[X]`.
- **No USDA network on any request path.** `usda.py` (`search_foods` / `get_food` / `get_foods_bulk`) must not be imported by `main.py` or `recipe_import.py` after this plan. The file stays in the tree (unused by runtime); the build pipeline's `scripts/build_food_db/sources/usda.py` is the only USDA reader now.
- **`foods` table schema** matches `scripts/build_food_db/build.py::FOODS_TABLE_DDL` exactly: `id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL, aliases TEXT NOT NULL, category TEXT, prep_state TEXT NOT NULL,` then the 12 nutrient columns `REAL` in `NUTRIENT_FIELDS` order (`calories_per_100g, protein_per_100g, fat_per_100g, carbs_per_100g, fiber_per_100g, sugar_per_100g, sodium_mg_per_100g, calcium_mg_per_100g, iron_mg_per_100g, vitamin_c_mg_per_100g, vitamin_d_mcg_per_100g, vitamin_b12_mcg_per_100g`), then `portions TEXT NOT NULL, source_ids TEXT NOT NULL, source_count INTEGER NOT NULL`. `aliases` / `portions` / `source_ids` are JSON strings in the row.
- **`food_id`** is `TEXT`, nullable. New rows get a `gen:NNNNN` id from the `foods` table; historical rows keep their old USDA id stringified (`173944` → `"173944"`). Never backfilled.
- **Nutrient key names on the wire:** the `foods` table, the `/foods/*` responses, and `ImportedIngredientCandidate` all use the `*_per_100g` names above. The denormalised columns on `food_logs` / `recipe_ingredients` keep their existing names (`calories`, `protein_g`, `fat_g`, `carbs_g`, `fiber_g`) — those are unchanged by this plan.
- **`portions`** on the wire is `[{"unit": str, "grams": float}]` (the `foods` row's own shape). The old `{"unit": ..., "grams_per_unit": ...}` key is gone; update every reader.
- **Matching** is pure Python over the in-memory index — no `pg_trgm`, no SQLite FTS — so behaviour is identical on Neon Postgres, desktop SQLite, and Capacitor SQLite.
- New Python deps pinned in `requirements.txt` with a one-line comment. `rapidfuzz==3.9.7` is already there (build pipeline).
- Backend tests under `tests/`, run `python -m pytest -q` (125 passing at plan start). Frontend tests `CI=true npm test -- --watchAll=false` from `pakupaku-frontend/`.
- **Task order keeps `main` working:** each endpoint's server change and its frontend callers land in the same task. Do not merge a task that leaves the app half-cut-over.

## Preflight corrections (apply to EVERY task — the code sketches below predate this)

The plan's test sketches were written before checking `tests/conftest.py`. Reality:

- **Session factory is `database.AsyncSessionLocal`** (an `async_sessionmaker`), NOT `async_session`. There is no `async_session` export.
- **`database.engine` points at an unreachable dummy Postgres URL in tests** and is never connected. Tests must NEVER call `create_all` / seed / load against `database.engine` or `database.AsyncSessionLocal`.
- **The test harness** (`tests/conftest.py`) gives you: a `db_session` fixture — a live `AsyncSession` on a fresh temp-file SQLite DB with **every table already created** via `Base.metadata.create_all` (so once `models.Food` exists, the `foods` table exists in every `db_session`); and a `client` fixture — a `TestClient(app)` (no `with`, so **FastAPI startup events do NOT fire in tests**) whose `get_db` yields that same `db_session`.
- Therefore the seed/index functions take a **live `AsyncSession`**, not a factory or engine:
  - `async def seed_foods(session: AsyncSession, artifact_path: str = ARTIFACT_PATH) -> int` — `delete(Food)` + `insert(Food)` on `session`, caller commits. Missing artifact → log + return 0.
  - `async def load(session: AsyncSession) -> None` in `food_index` — `select(Food)` on `session`.
  - Tests: `await seed_foods(db_session, str(art)); await db_session.commit(); await food_index.load(db_session)`.
  - Startup hook (`main.py`): `async with AsyncSessionLocal() as s: await seed_foods(s); await s.commit(); await food_index.load(s)` — wrapped in `try/except` so a missing artifact or a cold DB never crashes boot; log and continue with an empty index.
- **`backend_entry.py`** already imports `from database import Base, engine` and runs its own `engine.begin()` block — the desktop path (Task 9) uses `engine` directly there, which is correct because desktop's `DATABASE_URL` is a real local SQLite file. Only *pytest* must avoid `database.engine`.
- Task 1: confirm `models.py`'s `from sqlalchemy import ...` line has `Float` / `String` / `Text`; add whichever is missing.

---

## File Structure

**Create:**
- `food_index.py` — the in-memory food index: `Food` dataclass, `load()`, `search()`, `best_match()`, module singleton.
- `seed_foods.py` — read `data/foods.sqlite`, replace the `foods` table contents in `DATABASE_URL`.
- `migrate_fdc_to_food_id.sql` — one-off Neon Postgres migration.
- `tests/test_food_index.py`, `tests/test_seed_foods.py`, `tests/fixtures/foods_mini.sqlite` (tiny, ~6 rows, built by a test helper or committed).

**Modify:**
- `models.py` — add `Food` model; `FoodLog.fdc_id` / `RecipeIngredient.fdc_id` → `food_id` (`Integer` → `String`).
- `schemas.py` — `fdc_id: Optional[int]` → `food_id: Optional[str]` on `FoodLogCreateRequest`, `FoodLogResponse`, `RecipeIngredientRequest`, `RecipeIngredientResponse`; `ImportedIngredientCandidate.fdc_id: int` → `food_id: str`.
- `main.py` — rewrite `GET /foods/search`, `GET /foods/{food_id}`, `POST /foods/bulk`; drop the `usda` imports; add a startup hook that calls `food_index.load()`; `/logs` + `/recipes` handlers read `payload.food_id`.
- `recipe_import.py` — delete `rank_candidates`, `_fetch_portions_map`, `_PREFERRED_DATA_TYPES`, `_RELIABLE_PORTION_DATA_TYPES`; rewrite `_to_candidate` and `match_ingredient` against `food_index`; drop the `usda` import.
- `config.py`, `.env.example`, `docs/deployment.md` — remove `USDA_API_KEY`; add the `python seed_foods.py` build step.
- `backend_entry.py` — after `create_all`, run the fdc→food_id additive migration and `seed_foods` for the desktop SQLite DB.
- `create_tables.py` — no code change (it imports `models`, which now registers `foods`), but the deploy runbook gains the seed step.
- `pakupaku-frontend/src/components/RecipeEditForm.tsx`, `Dashboard.tsx` — consume the new `/foods/*` shape; `fdc_id: number` → `food_id: string`.
- `pakupaku-frontend/src/services/api.ts`, `services/db.ts` — `fdc_id` → `food_id` column; replace direct `api.nal.usda.gov` calls with local `foods`-table queries.

**Do NOT touch:** the `scripts/build_food_db/` pipeline, `data/foods.sqlite` itself, the bulk-import feature, the shared-recipes feature.

---

## Task 1: `Food` ORM model + `foods` table creation

**Files:**
- Modify: `models.py`
- Test: `tests/test_food_model.py`

**Interfaces:**
- Produces: `models.Food` — SQLAlchemy model, table `foods`, columns exactly as Global Constraints. `id: Mapped[str]` PK; `aliases: Mapped[str]`, `portions: Mapped[str]`, `source_ids: Mapped[str]` (JSON text); 12 nutrient `Mapped[Optional[float]]`; `source_count: Mapped[int]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_food_model.py
import asyncio
from sqlalchemy import inspect
from database import Base, engine
import models  # noqa: F401


def test_foods_table_has_the_pipeline_schema():
    async def _cols():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            return await conn.run_sync(
                lambda sync: [c["name"] for c in inspect(sync).get_columns("foods")]
            )
    cols = asyncio.get_event_loop().run_until_complete(_cols())
    assert cols == [
        "id", "canonical_name", "aliases", "category", "prep_state",
        "calories_per_100g", "protein_per_100g", "fat_per_100g", "carbs_per_100g",
        "fiber_per_100g", "sugar_per_100g", "sodium_mg_per_100g", "calcium_mg_per_100g",
        "iron_mg_per_100g", "vitamin_c_mg_per_100g", "vitamin_d_mcg_per_100g",
        "vitamin_b12_mcg_per_100g", "portions", "source_ids", "source_count",
    ]
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `python -m pytest tests/test_food_model.py -v`
Expected: FAIL — `NoSuchTableError: foods` / no `Food` model.

- [ ] **Step 3: Add the model**

```python
# models.py — near the other models
class Food(Base):
    __tablename__ = "foods"

    id:             Mapped[str]            = mapped_column(String, primary_key=True)
    canonical_name: Mapped[str]            = mapped_column(String, nullable=False)
    aliases:        Mapped[str]            = mapped_column(Text, nullable=False, default="[]")
    category:       Mapped[Optional[str]]  = mapped_column(String, nullable=True)
    prep_state:     Mapped[str]            = mapped_column(String, nullable=False, default="unspecified")

    calories_per_100g:      Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    protein_per_100g:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fat_per_100g:           Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    carbs_per_100g:         Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    fiber_per_100g:         Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sugar_per_100g:         Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sodium_mg_per_100g:     Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    calcium_mg_per_100g:    Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    iron_mg_per_100g:       Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vitamin_c_mg_per_100g:  Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vitamin_d_mcg_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vitamin_b12_mcg_per_100g: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    portions:     Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_ids:   Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

Add `Float`, `String`, `Text` to the `sqlalchemy` import line if not present. Confirm the column ORDER in the model matches the test's list (SQLAlchemy emits columns in declaration order).

- [ ] **Step 4: Run it — expect PASS**

Run: `python -m pytest tests/test_food_model.py -v` — Expected: PASS.

- [ ] **Step 5: Full suite**

Run: `python -m pytest -q` — Expected: 126 passing (125 + this).

- [ ] **Step 6: Commit**

```bash
git add models.py tests/test_food_model.py
git commit -m "feat: add Food ORM model for the offline foods table"
```

---

## Task 2: `seed_foods.py` — load the artifact into the DB

**Files:**
- Create: `seed_foods.py`, `tests/test_seed_foods.py`, `tests/fixtures/make_foods_mini.py`

**Interfaces:**
- Consumes: `models.Food` (Task 1), `database.engine`.
- Produces:
  - `ARTIFACT_PATH = "data/foods.sqlite"` (module constant, overridable via arg).
  - `async def seed_foods(artifact_path: str = ARTIFACT_PATH) -> int` — replaces every row of the DB `foods` table with the artifact's rows; returns the count. If `artifact_path` doesn't exist: log a warning, return `0`, do not raise (so CI/deploy before build-pipeline Task 9 still works).
  - `main()` — `asyncio.run(seed_foods())`, prints the count.

- [ ] **Step 1: Test-fixture helper**

```python
# tests/fixtures/make_foods_mini.py
import json, sqlite3, sys
from scripts.build_food_db.build import FOODS_TABLE_DDL
from scripts.build_food_db.model import NUTRIENT_FIELDS

def build(path):
    con = sqlite3.connect(path)
    con.execute(FOODS_TABLE_DDL)
    rows = [
        ("gen:00001", "Broccoli, raw", json.dumps(["Broccoli, raw", "raw broccoli"]),
         None, "raw", 34.0, 2.8, 0.4, 7.0, 2.6, 1.7, 33.0, 47.0, 0.7, 89.2, None, None,
         json.dumps([{"unit": "cup chopped", "grams": 91.0}]), json.dumps(["cofid", "usda"]), 2),
        ("gen:00002", "Water, tap, drinking", json.dumps(["Water, tap, drinking"]),
         None, "unspecified", 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 4.0, 3.0, 0.0, 0.0, None, None,
         json.dumps([]), json.dumps(["cofid", "usda"]), 2),
    ]
    ph = ",".join(["?"] * (8 + len(NUTRIENT_FIELDS)))
    con.executemany("INSERT INTO foods VALUES (%s)" % ph, rows)
    con.commit(); con.close()

if __name__ == "__main__":
    build(sys.argv[1])
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_seed_foods.py
import asyncio
from sqlalchemy import select
from database import Base, engine, async_session          # match this repo's session factory name
from tests.fixtures.make_foods_mini import build as build_mini
import models
from seed_foods import seed_foods


def test_seed_replaces_foods_table_from_artifact(tmp_path):
    art = tmp_path / "foods.sqlite"
    build_mini(str(art))

    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        n = await seed_foods(str(art))
        async with async_session() as s:
            names = (await s.execute(select(models.Food.canonical_name).order_by(models.Food.id))).scalars().all()
        return n, names

    n, names = asyncio.get_event_loop().run_until_complete(_run())
    assert n == 2
    assert names == ["Broccoli, raw", "Water, tap, drinking"]


def test_seed_missing_artifact_is_a_noop(tmp_path):
    result = asyncio.get_event_loop().run_until_complete(seed_foods(str(tmp_path / "nope.sqlite")))
    assert result == 0
```

(First check `database.py` for the real session-factory export name and fix the import in both this test and `seed_foods.py`.)

- [ ] **Step 3: Run it — expect FAIL** (`ModuleNotFoundError: seed_foods`).

- [ ] **Step 4: Implement `seed_foods.py`**

```python
# seed_foods.py
import asyncio
import logging
import os
import sqlite3

from sqlalchemy import delete, insert

from database import engine
from models import Food

logger = logging.getLogger(__name__)
ARTIFACT_PATH = "data/foods.sqlite"
_COLS = [c.name for c in Food.__table__.columns]


async def seed_foods(artifact_path: str = ARTIFACT_PATH) -> int:
    if not os.path.exists(artifact_path):
        logger.warning("seed_foods: %s not found — foods table left untouched", artifact_path)
        return 0

    src = sqlite3.connect(artifact_path)
    src.row_factory = sqlite3.Row
    rows = [dict(r) for r in src.execute("SELECT %s FROM foods" % ",".join(_COLS))]
    src.close()

    async with engine.begin() as conn:
        await conn.execute(delete(Food))
        if rows:
            await conn.execute(insert(Food), rows)
    logger.info("seed_foods: loaded %d rows from %s", len(rows), artifact_path)
    return len(rows)


def main() -> None:
    n = asyncio.run(seed_foods())
    print("seeded %d foods" % n)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests — expect PASS.** Then `python -m pytest -q` — 128 passing.

- [ ] **Step 6: Commit**

```bash
git add seed_foods.py tests/test_seed_foods.py tests/fixtures/make_foods_mini.py
git commit -m "feat: seed_foods.py loads data/foods.sqlite into the foods table"
```

---

## Task 3: `food_index.py` — in-memory search + match

**Files:**
- Create: `food_index.py`, `tests/test_food_index.py`

**Interfaces:**
- Consumes: `models.Food` (Task 1), `scripts.build_food_db.normalise.canonical_key`, `rapidfuzz`.
- Produces:
  - `@dataclass class Food` — `id: str`, `description: str` (= `canonical_name`), `prep_state: str`, `portions: List[Dict[str, float]]`, and the 12 `Optional[float]` `*_per_100g` fields. `.as_search_result() -> Dict` (the `/foods/search` item shape) and `.as_detail() -> Dict` (the `/foods/{id}` shape).
  - `MATCH_CONFIDENCE_FLOOR = 60` — module constant.
  - `async def load(session_factory) -> None` — read every `foods` row, build `_by_id: Dict[str, Food]`, `_by_key: Dict[str, List[Food]]` (canonical_key of `canonical_name` + each alias → foods), and `_keys: List[str]` for fuzzy. Idempotent; safe to call again after a re-seed.
  - `def search(query: str, limit: int = 25) -> List[Food]` — exact canonical-key hit, then alias-key hits, then `rapidfuzz.process.extract` over `_keys` above `MATCH_CONFIDENCE_FLOOR`; dedup by `id`, preserve that priority order, cap at `limit`. Empty list if the index is empty or nothing clears the floor.
  - `def best_match(name: str) -> Optional[Food]` — `search(name, 1)[0]` or `None`.
  - `def _loaded() -> bool` — for a startup guard / tests.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_food_index.py
import asyncio
import food_index
from database import Base, engine, async_session
from tests.fixtures.make_foods_mini import build as build_mini
from seed_foods import seed_foods


def _load(tmp_path):
    art = tmp_path / "foods.sqlite"
    build_mini(str(art))
    async def _run():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await seed_foods(str(art))
        await food_index.load(async_session)
    asyncio.get_event_loop().run_until_complete(_run())


def test_exact_and_alias_match(tmp_path):
    _load(tmp_path)
    assert food_index.best_match("broccoli").id == "gen:00001"
    assert food_index.best_match("raw broccoli").id == "gen:00001"     # via alias


def test_fuzzy_match_within_floor(tmp_path):
    _load(tmp_path)
    assert food_index.best_match("brocolli").id == "gen:00001"          # misspelling


def test_junk_query_returns_none(tmp_path):
    _load(tmp_path)
    assert food_index.best_match("xyzzy nonsense plugboard") is None


def test_water_resolves_to_the_generic_zero_kcal_entry(tmp_path):
    _load(tmp_path)
    m = food_index.best_match("water")
    assert m.id == "gen:00002"
    assert m.calories_per_100g == 0.0


def test_search_result_shape(tmp_path):
    _load(tmp_path)
    r = food_index.search("broccoli", 5)[0].as_search_result()
    assert r["food_id"] == "gen:00001"
    assert r["description"] == "Broccoli, raw"
    assert r["calories_per_100g"] == 34.0
    assert r["portions"] == [{"unit": "cup chopped", "grams": 91.0}]
    assert "dataType" not in r and "brandOwner" not in r
```

- [ ] **Step 2: Run — expect FAIL** (`ModuleNotFoundError: food_index`).

- [ ] **Step 3: Implement `food_index.py`**

```python
# food_index.py
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from rapidfuzz import fuzz, process
from sqlalchemy import select

from scripts.build_food_db.normalise import canonical_key
from models import Food as FoodRow

MATCH_CONFIDENCE_FLOOR = 60

_NUTRIENTS = (
    "calories_per_100g", "protein_per_100g", "fat_per_100g", "carbs_per_100g",
    "fiber_per_100g", "sugar_per_100g", "sodium_mg_per_100g", "calcium_mg_per_100g",
    "iron_mg_per_100g", "vitamin_c_mg_per_100g", "vitamin_d_mcg_per_100g",
    "vitamin_b12_mcg_per_100g",
)


@dataclass
class Food:
    id: str
    description: str
    prep_state: str
    portions: List[Dict[str, float]] = field(default_factory=list)
    calories_per_100g: Optional[float] = None
    protein_per_100g: Optional[float] = None
    fat_per_100g: Optional[float] = None
    carbs_per_100g: Optional[float] = None
    fiber_per_100g: Optional[float] = None
    sugar_per_100g: Optional[float] = None
    sodium_mg_per_100g: Optional[float] = None
    calcium_mg_per_100g: Optional[float] = None
    iron_mg_per_100g: Optional[float] = None
    vitamin_c_mg_per_100g: Optional[float] = None
    vitamin_d_mcg_per_100g: Optional[float] = None
    vitamin_b12_mcg_per_100g: Optional[float] = None

    def _nutrients(self) -> Dict[str, Optional[float]]:
        return {n: getattr(self, n) for n in _NUTRIENTS}

    def as_search_result(self) -> Dict:
        out = {"food_id": self.id, "description": self.description, "portions": self.portions}
        out.update(self._nutrients())
        return out

    def as_detail(self) -> Dict:
        return self.as_search_result()


_by_id: Dict[str, Food] = {}
_by_key: Dict[str, List[Food]] = {}
_keys: List[str] = []


def _loaded() -> bool:
    return bool(_by_id)


async def load(session_factory) -> None:
    global _keys
    _by_id.clear()
    _by_key.clear()
    async with session_factory() as s:
        rows = (await s.execute(select(FoodRow))).scalars().all()
    for r in rows:
        f = Food(
            id=r.id, description=r.canonical_name, prep_state=r.prep_state,
            portions=json.loads(r.portions or "[]"),
            **{n: getattr(r, n) for n in _NUTRIENTS},
        )
        _by_id[f.id] = f
        names = [r.canonical_name] + json.loads(r.aliases or "[]")
        for name in names:
            _by_key.setdefault(canonical_key(name), []).append(f)
    _keys = list(_by_key)


def _ranked(query: str, limit: int) -> List[Food]:
    key = canonical_key(query)
    seen = set()
    out: List[Food] = []

    def _add(foods):
        for f in foods:
            if f.id not in seen:
                seen.add(f.id)
                out.append(f)

    if key in _by_key:
        _add(_by_key[key])
    for cand, score, _ in process.extract(
        key, _keys, scorer=fuzz.token_set_ratio, limit=limit * 3
    ):
        if score < MATCH_CONFIDENCE_FLOOR:
            break
        _add(_by_key[cand])
    return out[:limit]


def search(query: str, limit: int = 25) -> List[Food]:
    if not _loaded() or not query.strip():
        return []
    return _ranked(query, limit)


def best_match(name: str) -> Optional[Food]:
    hits = search(name, 1)
    return hits[0] if hits else None


def get(food_id: str) -> Optional[Food]:
    return _by_id.get(food_id)
```

- [ ] **Step 4: Run tests — expect PASS.** Adjust `MATCH_CONFIDENCE_FLOOR` only if `test_junk_query_returns_none` and `test_fuzzy_match_within_floor` can't both hold with the mini fixture — document any change.

- [ ] **Step 5: `python -m pytest -q`** — Expected: 133 passing.

- [ ] **Step 6: Commit**

```bash
git add food_index.py tests/test_food_index.py
git commit -m "feat: in-memory food_index over the foods table (exact/alias/fuzzy)"
```

---

## Task 4: startup load + `GET /foods/search` rewrite + both frontend callers

**Files:**
- Modify: `main.py` (startup hook, `food_search`), `pakupaku-frontend/src/components/RecipeEditForm.tsx`, `pakupaku-frontend/src/components/Dashboard.tsx`
- Test: `tests/test_foods_routes.py` (new), `pakupaku-frontend/src/components/RecipeEditForm.test.tsx`, `Dashboard.test.tsx`

**Interfaces:**
- Consumes: `food_index.load` / `search` (Task 3), `seed_foods` (Task 2).
- Produces: `GET /foods/search?query=&page_size=` → `{"foods": [<Food.as_search_result()>...]}`. `data_types` / `brand_owner` / `page_number` params removed. Startup: FastAPI `@app.on_event("startup")` runs `await seed_foods()` then `await food_index.load(async_session)` (seed is a no-op if the artifact is absent; load then has 0 rows and `/foods/search` returns `{"foods": []}`).

- [ ] **Step 1: Backend test (failing)**

```python
# tests/test_foods_routes.py
import asyncio, uuid
from auth import get_current_user, hash_password
from main import app
from models import User
import food_index
from tests.fixtures.make_foods_mini import build as build_mini
from database import Base, engine, async_session
from seed_foods import seed_foods


def _user(db_session):
    u = User(id=uuid.uuid4(), email=f"{uuid.uuid4()}@e.com", username="u"+uuid.uuid4().hex[:6],
             hashed_password=hash_password("x"), email_verified=True, safe_mode=False,
             uses_custom_goals=False, is_admin=False)
    db_session.add(u); return u


def test_foods_search_returns_index_results(client, db_session, tmp_path):
    art = tmp_path / "foods.sqlite"; build_mini(str(art))
    asyncio.get_event_loop().run_until_complete(seed_foods(str(art)))
    asyncio.get_event_loop().run_until_complete(food_index.load(async_session))
    u = _user(db_session)
    app.dependency_overrides[get_current_user] = lambda: u
    try:
        r = client.get("/foods/search?query=broccoli")
        assert r.status_code == 200
        body = r.json()["foods"]
        assert body[0]["food_id"] == "gen:00001"
        assert body[0]["calories_per_100g"] == 34.0
        assert "dataType" not in body[0]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run — expect FAIL** (old route returns USDA shape / calls the network).

- [ ] **Step 3: Rewrite `food_search` + add startup hook in `main.py`**

```python
# main.py — replace the /foods/search handler
from database import async_session          # if not already imported
import food_index
from seed_foods import seed_foods

@app.on_event("startup")
async def _load_food_index() -> None:
    await seed_foods()
    await food_index.load(async_session)

@app.get("/foods/search")
async def food_search(
    query:     str,
    page_size: int = Query(25, ge=1, le=200),
    _: User = Depends(get_current_user),
):
    """Search the offline generic-food index. Nutrients are per 100 g."""
    return {"foods": [f.as_search_result() for f in food_index.search(query, page_size)]}
```

Remove `from usda import search_foods` (keep `get_food` / `get_foods_bulk` imports only until Tasks 5–6 remove them).

- [ ] **Step 4: Run backend test — expect PASS.**

- [ ] **Step 5: Frontend — `RecipeEditForm.tsx` `runSearch`**

Replace the body: fetch `/foods/search?query=…&page_size=50` (drop `brand_owner`), then

```ts
const suggestions: FoodSuggestion[] = (data.foods ?? []).map((f: any) => ({
  fdc_id:      undefined,          // replaced by food_id below in the same task's type change
  food_id:     f.food_id,
  description: f.description,
  brand:       null,
  calories_per_100g: f.calories_per_100g,
  protein_per_100g:  f.protein_per_100g,
  fat_per_100g:      f.fat_per_100g,
  carbs_per_100g:    f.carbs_per_100g,
  fiber_per_100g:    f.fiber_per_100g,
}));
```

Delete the `generic`/`branded`/`dedupeByDescription` split and the `extractNutrients(f.foodNutrients)` call (the index has no brands). Change the `FoodSuggestion` / row types: `fdc_id: number | null` → `food_id: string | null`. `handleQueryChange` sets `food_id: null`. Leave `runBrandSearch` as a no-op stub or delete the brand-name UI path (it only ever worked against USDA Branded rows) — **delete it**, and remove the brand input if nothing else uses it; if that's too wide, leave the input inert and note it.

- [ ] **Step 6: Frontend — `Dashboard.tsx` food-log search**

Same shape change at `Dashboard.tsx:164` — map `f.food_id` / `f.description` / `f.*_per_100g` directly, drop any `dataType`/brand handling.

- [ ] **Step 7: Update frontend tests** — `RecipeEditForm.test.tsx` and `Dashboard.test.tsx`: mock `/foods/search` to return `{ foods: [{ food_id: "gen:00001", description: "Broccoli, raw", calories_per_100g: 34, ... , portions: [] }] }`; assert selection stores `food_id`. Run `CI=true npm test -- --watchAll=false`.

- [ ] **Step 8: `python -m pytest -q`** (backend still green) + frontend suite green.

- [ ] **Step 9: Commit**

```bash
git add main.py tests/test_foods_routes.py pakupaku-frontend/src/components/RecipeEditForm.tsx pakupaku-frontend/src/components/RecipeEditForm.test.tsx pakupaku-frontend/src/components/Dashboard.tsx pakupaku-frontend/src/components/Dashboard.test.tsx
git commit -m "feat: /foods/search backed by the offline index; frontend consumes the new shape"
```

---

## Task 5: `GET /foods/{food_id}` rewrite + portion readers

**Files:**
- Modify: `main.py` (`food_detail`), `RecipeEditForm.tsx` (`fetchPortions`), `Dashboard.tsx` (`fetchPortions`)
- Test: `tests/test_foods_routes.py` (extend), frontend tests

**Interfaces:**
- Produces: `GET /foods/{food_id}` (path param `str`) → `Food.as_detail()` = `{food_id, description, portions: [{unit, grams}], <12 *_per_100g>}`. 404 when `food_index.get(food_id)` is `None`.

- [ ] **Step 1: Failing test** — `client.get("/foods/gen:00001")` → 200, `body["portions"] == [{"unit": "cup chopped", "grams": 91.0}]`; `client.get("/foods/gen:99999")` → 404.

- [ ] **Step 2: Run — FAIL** (route takes `fdc_id: int`, calls `get_food`).

- [ ] **Step 3: Rewrite**

```python
@app.get("/foods/{food_id}")
async def food_detail(food_id: str, _: User = Depends(get_current_user)):
    f = food_index.get(food_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Food not found.")
    return f.as_detail()
```

Remove `from usda import get_food`.

- [ ] **Step 4: Run — PASS.**

- [ ] **Step 5: Frontend `fetchPortions` (both files)**

```ts
const fetchPortions = async (foodId: string): Promise<Record<string, number> | null> => {
  try {
    const res = await apiFetch(`/foods/${encodeURIComponent(foodId)}`, { headers });
    if (!res.ok) return null;
    const detail = await res.json();
    const map: Record<string, number> = {};
    for (const p of detail.portions ?? []) if (p.unit && p.grams) map[p.unit] = p.grams;
    return Object.keys(map).length > 0 ? map : null;
  } catch { return null; }
};
```

Delete the "Tier 2 re-search filtered to Survey (FNDDS)/SR Legacy" fallback block in both files — the index row already carries its portions. `selectFood` passes `food.food_id`.

- [ ] **Step 6: Frontend tests** — mock `/foods/gen:00001` → `{ portions: [{ unit: "cup", grams: 120 }] }`; assert the unit→grams map is applied. Run the frontend suite.

- [ ] **Step 7: `python -m pytest -q`** + frontend green.

- [ ] **Step 8: Commit**

```bash
git add main.py tests/test_foods_routes.py pakupaku-frontend/src/components/RecipeEditForm.tsx pakupaku-frontend/src/components/RecipeEditForm.test.tsx pakupaku-frontend/src/components/Dashboard.tsx pakupaku-frontend/src/components/Dashboard.test.tsx
git commit -m "feat: /foods/{food_id} served from the index with inline portions"
```

---

## Task 6: `POST /foods/bulk` rewrite

**Files:** Modify `main.py` (`food_bulk`); Test `tests/test_foods_routes.py`

**Interfaces:** `POST /foods/bulk` body `List[str]` (food ids) → `[Food.as_detail(), ...]`, skipping unknown ids.

- [ ] **Step 1: Failing test** — `client.post("/foods/bulk", json=["gen:00001", "gen:99999"])` → 200, one result, `[0]["food_id"] == "gen:00001"`.
- [ ] **Step 2: Run — FAIL.**
- [ ] **Step 3: Rewrite**

```python
@app.post("/foods/bulk")
async def food_bulk(food_ids: List[str], _: User = Depends(get_current_user)):
    return [f.as_detail() for f in (food_index.get(i) for i in food_ids) if f is not None]
```

Remove `from usda import get_foods_bulk, extract_nutrients` (grep `main.py` — `extract_nutrients` must have no remaining uses; if it does, keep that import until they're gone).

- [ ] **Step 4: Run — PASS.** Then `python -m pytest -q`.
- [ ] **Step 5: Commit** `feat: /foods/bulk served from the index`.

---

## Task 7: collapse `recipe_import.py` matching onto `food_index`

**Files:**
- Modify: `recipe_import.py`, `schemas.py` (`ImportedIngredientCandidate`)
- Test: `tests/test_recipe_import_matching.py` (rewrite), `tests/test_recipe_import_draft.py` (adjust)

**Interfaces:**
- Consumes: `food_index.best_match` (Task 3).
- Produces: `match_ingredient(parsed) -> ImportedIngredient` with `best_match` built from a `food_index.Food` (or `None`); `alternates` = `food_index.search(parsed.food_name, 4)[1:]`. `_to_candidate(food: food_index.Food) -> ImportedIngredientCandidate`. `rank_candidates`, `_fetch_portions_map`, `_PREFERRED_DATA_TYPES`, `_RELIABLE_PORTION_DATA_TYPES` deleted. `schemas.ImportedIngredientCandidate.fdc_id: int` → `food_id: str`; `portions_map` stays `Dict[str, float]` (built from the food's `portions` list: `{p["unit"]: p["grams"] for p in food.portions}`).

- [ ] **Step 1: Rewrite the test file**

```python
# tests/test_recipe_import_matching.py
import asyncio
import food_index
from recipe_import import match_ingredient
from schemas import ParsedIngredient
from database import Base, engine, async_session
from seed_foods import seed_foods
from tests.fixtures.make_foods_mini import build as build_mini


def _load(tmp_path):
    art = tmp_path / "foods.sqlite"; build_mini(str(art))
    async def _r():
        async with engine.begin() as c:
            await c.run_sync(Base.metadata.create_all)
        await seed_foods(str(art)); await food_index.load(async_session)
    asyncio.get_event_loop().run_until_complete(_r())


def test_match_ingredient_hits_the_generic_index(tmp_path):
    _load(tmp_path)
    p = ParsedIngredient(raw_line="2 cups broccoli", quantity=2.0, unit="cup", food_name="broccoli")
    out = asyncio.get_event_loop().run_until_complete(match_ingredient(p))
    assert out.best_match.food_id == "gen:00001"
    assert out.best_match.calories_per_100g == 34.0
    assert out.best_match.portions_map == {"cup chopped": 91.0}


def test_match_ingredient_no_hit_returns_unmatched(tmp_path):
    _load(tmp_path)
    p = ParsedIngredient(raw_line="1 xyzzy", quantity=1.0, unit="", food_name="xyzzy nonsense")
    out = asyncio.get_event_loop().run_until_complete(match_ingredient(p))
    assert out.best_match is None
```

- [ ] **Step 2: Run — expect FAIL** (still calls `search_foods`).

- [ ] **Step 3: Rewrite the matching section of `recipe_import.py`**

```python
import food_index
# delete: from usda import extract_nutrients, get_food, search_foods
# delete: rank_candidates, _fetch_portions_map, _PREFERRED_DATA_TYPES, _RELIABLE_PORTION_DATA_TYPES

def _to_candidate(food: "food_index.Food") -> ImportedIngredientCandidate:
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
    hits = food_index.search(parsed.food_name, 5)
    return ImportedIngredient(
        raw_line=parsed.raw_line, quantity=parsed.quantity, unit=parsed.unit,
        food_name=parsed.food_name,
        best_match=_to_candidate(hits[0]) if hits else None,
        alternates=[_to_candidate(f) for f in hits[1:5]],
    )
```

`_safe_match_ingredient` is unchanged (still a defensive wrapper; a malformed index row shouldn't sink `gather`). Update `schemas.ImportedIngredientCandidate` (`fdc_id: int` → `food_id: str`).

- [ ] **Step 4: Run the matching + draft tests — expect PASS.** Fix any `test_recipe_import_draft.py` / `test_main_recipes_import.py` fixture that assumed `fdc_id` on a candidate.

- [ ] **Step 5: `python -m pytest -q`** — all green. `grep -rn "from usda import\|import usda\|search_foods\|get_food\|_fetch_portions_map\|rank_candidates" recipe_import.py main.py` → no hits.

- [ ] **Step 6: Commit**

```bash
git add recipe_import.py schemas.py tests/test_recipe_import_matching.py tests/test_recipe_import_draft.py tests/test_main_recipes_import.py
git commit -m "refactor: recipe-import matching goes through food_index, USDA calls removed"
```

---

## Task 8: `food_id` on `food_logs` + `recipe_ingredients` (schemas + models + handlers)

**Files:**
- Modify: `schemas.py`, `models.py`, `main.py` (log-create + recipe-create/update handlers that read `payload.fdc_id`)
- Test: `tests/test_db_fixtures.py` / relevant route tests; new `tests/test_food_id_migration.py` is Task 9.

**Interfaces:**
- Produces: `FoodLogCreateRequest.food_id: Optional[str]`, `FoodLogResponse.food_id: Optional[str]`, `RecipeIngredientRequest.food_id: Optional[str]`, `RecipeIngredientResponse.food_id: Optional[str]`. `models.FoodLog.food_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)`, same on `RecipeIngredient`. Every handler that did `fdc_id=payload.fdc_id` now does `food_id=payload.food_id`.

- [ ] **Step 1: Failing test** — a `/logs` POST with `{"food_id": "gen:00001", "food_name": "Broccoli", "amount_g": 100, "meal": "lunch"}` returns 201 and the response has `food_id == "gen:00001"`; a `/recipes` POST with an ingredient carrying `food_id` round-trips it.

- [ ] **Step 2: Run — FAIL** (`food_id` unknown field / column).

- [ ] **Step 3: Rename in `schemas.py` and `models.py`**

`schemas.py`: the 4 models — `fdc_id: Optional[int]` → `food_id: Optional[str]`. Keep field order; update any docstring/comment mentioning `fdc_id`.
`models.py`: `FoodLog` line 201 and `RecipeIngredient` line 300 — `fdc_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)` → `food_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)`. Update the `# For USDA foods: fdc_id is set` comments.

- [ ] **Step 4: `main.py`** — `grep -n "fdc_id" main.py`; every `fdc_id=…` / `payload.fdc_id` / `.fdc_id` in the `/logs` and `/recipes` (create, patch, copy) handlers → `food_id`. The bulk-import save path (`RecipeIngredient(... fdc_id=ing.fdc_id ...)` around line 730/880/972) → `food_id=ing.food_id`.

- [ ] **Step 5: Run the log + recipe + bulk-import route tests — PASS.** `python -m pytest -q` all green.

- [ ] **Step 6: Commit**

```bash
git add schemas.py models.py main.py tests/
git commit -m "feat: food_id (TEXT) replaces fdc_id on food_logs and recipe_ingredients"
```

---

## Task 9: database migrations (Neon SQL + desktop SQLite)

**Files:**
- Create: `migrate_fdc_to_food_id.sql`, `tests/test_food_id_migration.py`
- Modify: `backend_entry.py`

**Interfaces:**
- Produces: `migrate_fdc_to_food_id.sql` (Postgres, run once against Neon). `backend_entry._migrate_fdc_to_food_id(conn)` — for the desktop SQLite DB: if `food_logs` / `recipe_ingredients` still have an `fdc_id` column and no `food_id`, `ALTER TABLE … ADD COLUMN food_id TEXT` then `UPDATE … SET food_id = CAST(fdc_id AS TEXT) WHERE fdc_id IS NOT NULL`. Leaves `fdc_id` in place (SQLite drop-column is version-fragile). Called from `backend_entry` after `create_all`, before `seed_foods`.

- [ ] **Step 1: `migrate_fdc_to_food_id.sql`**

```sql
-- Run once against the Neon production database, after deploying the code
-- that expects food_id. Existing integer fdc_ids stringify.
ALTER TABLE food_logs           ALTER COLUMN fdc_id TYPE text USING fdc_id::text;
ALTER TABLE food_logs           RENAME COLUMN fdc_id TO food_id;
ALTER TABLE recipe_ingredients  ALTER COLUMN fdc_id TYPE text USING fdc_id::text;
ALTER TABLE recipe_ingredients  RENAME COLUMN fdc_id TO food_id;
```

- [ ] **Step 2: Failing test for the desktop path**

```python
# tests/test_food_id_migration.py
import asyncio
from sqlalchemy import text
from database import engine
from backend_entry import _migrate_fdc_to_food_id


def test_desktop_migration_copies_int_fdc_id_to_text_food_id():
    async def _run():
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE food_logs (id TEXT, fdc_id INTEGER)"))
            await conn.execute(text("INSERT INTO food_logs VALUES ('a', 173944), ('b', NULL)"))
            await conn.execute(text("CREATE TABLE recipe_ingredients (id TEXT, fdc_id INTEGER)"))
            await _migrate_fdc_to_food_id(conn)
            return (await conn.execute(text("SELECT id, food_id FROM food_logs ORDER BY id"))).fetchall()
    rows = asyncio.get_event_loop().run_until_complete(_run())
    assert rows == [("a", "173944"), ("b", None)]
```

(Use an in-memory/temp SQLite engine — check `tests/conftest.py` for how the suite points `DATABASE_URL` at SQLite.)

- [ ] **Step 3: Run — FAIL** (`_migrate_fdc_to_food_id` missing).

- [ ] **Step 4: Implement in `backend_entry.py`**

```python
async def _migrate_fdc_to_food_id(conn):
    for table in ("food_logs", "recipe_ingredients"):
        cols = [r[1] for r in (await conn.execute(text(f"PRAGMA table_info({table})"))).fetchall()]
        if not cols or "food_id" in cols or "fdc_id" not in cols:
            continue
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN food_id TEXT"))
        await conn.execute(text(
            f"UPDATE {table} SET food_id = CAST(fdc_id AS TEXT) WHERE fdc_id IS NOT NULL"
        ))
```

Wire it into the launch sequence next to `_add_missing_columns` (after `create_all`). Then call `await seed_foods()` and `await food_index.load(...)` there too (desktop has no FastAPI startup event unless `backend_entry` starts uvicorn with the app — if it does, the `@app.on_event("startup")` from Task 4 already covers it; verify and avoid double-seeding).

- [ ] **Step 5: Run — PASS.** `python -m pytest -q` green.

- [ ] **Step 6: Commit**

```bash
git add migrate_fdc_to_food_id.sql backend_entry.py tests/test_food_id_migration.py
git commit -m "feat: fdc_id -> food_id migration (Neon SQL + desktop SQLite path)"
```

---

## Task 10: retire `USDA_API_KEY`, wire the seed into deploy

**Files:** Modify `config.py`, `.env.example`, `docs/deployment.md`

**Interfaces:** none (config/doc only).

- [ ] **Step 1** — `config.py`: delete the `USDA_API_KEY = os.getenv("USDA_API_KEY")` line and its section comment. `grep -rn "USDA_API_KEY" .` (excluding `venv`, `node_modules`, `scripts/build_food_db`) → only `.env.example` / `docs` left.
- [ ] **Step 2** — `.env.example`: remove the `USDA_API_KEY` line; add a comment that food data is now the committed `data/foods.sqlite`, seeded at deploy.
- [ ] **Step 3** — `docs/deployment.md`: in the Render **Build Command** step, change `pip install -r requirements.txt && python3 create_tables.py` to `… && python3 create_tables.py && python3 seed_foods.py`. Remove `USDA_API_KEY` from the env-var list. Add a line: `seed_foods.py` is a no-op until `data/foods.sqlite` is committed (build-pipeline Task 9).
- [ ] **Step 4** — `python -m pytest -q` (nothing should break; `config` import must still succeed). `grep -rn "USDA_API_KEY" config.py main.py recipe_import.py` → nothing.
- [ ] **Step 5: Commit** `chore: drop USDA_API_KEY, add seed_foods to the deploy build`.

---

## Task 11: device-local path — `services/api.ts` + `services/db.ts`

**Files:** Modify `pakupaku-frontend/src/services/api.ts`, `pakupaku-frontend/src/services/db.ts`; Test the service-layer tests if any.

**Interfaces:** the Capacitor/SQLite service layer stops calling `api.nal.usda.gov` and reads the bundled `foods` table; its `fdc_id` column becomes `food_id TEXT`.

- [ ] **Step 1** — `services/db.ts`: the local SQLite schema — `food_logs` / `recipe_ingredients` `fdc_id` column → `food_id TEXT`. Add a `foods` table matching the Global-Constraints DDL. Add a one-time import step that copies `data/foods.sqlite` rows into it (bundle the artifact under `public/` and `fetch()` it as an ArrayBuffer on first launch, or ship it as a Capacitor asset — pick whichever this repo's `@capacitor-community/sqlite` setup supports; document the choice inline).
- [ ] **Step 2** — `services/api.ts`: delete `USDA_BASE` / `USDA_KEY` and the `searchFoods` / `getFood` functions that hit USDA. Replace with local queries over the `foods` table (same normalised-token + `LIKE` / in-JS fuzzy approach as `food_index`, or a thin JS port). Every insert/select that named `fdc_id` → `food_id`.
- [ ] **Step 3** — `grep -rn "usda\|fdcId\|fdc_id\|nal.usda.gov" pakupaku-frontend/src` → only comments / historical migration strings remain.
- [ ] **Step 4** — `CI=true npm test -- --watchAll=false` green; `npx tsc --noEmit` clean; `CI=true npm run build` clean.
- [ ] **Step 5: Commit** `feat: device-local food lookup uses the bundled foods table, not the USDA API`.

---

## Task 12: cleanup sweep

**Files:** Modify `main.py` (dead imports), possibly delete nothing.

- [ ] **Step 1** — `grep -rn "from usda import\|import usda" main.py recipe_import.py` → nothing. `usda.py` stays in the tree (only `scripts/build_food_db` territory references its concepts now); add a one-line module docstring note that it is no longer on any request path.
- [ ] **Step 2** — `grep -rn "extract_nutrients" main.py` → nothing (all three `/foods/*` handlers now use `food_index`).
- [ ] **Step 3** — `python -m pytest -q` (full backend) + `CI=true npm test -- --watchAll=false` (full frontend) + `npx tsc --noEmit` + `CI=true npm run build`. All green.
- [ ] **Step 4** — update `README.md` / `pakupaku-frontend/README.md` "Frontend Overview" + the root README's `/foods` route-group description to say the food source is the offline `foods` table, not USDA.
- [ ] **Step 5: Commit** `chore: docs + dead-import sweep for the food-DB runtime cutover`.

---

## Self-Review

**Spec coverage (spec §"Runtime schema & matching", §"ID migration"):**

- `foods` table in all three DBs → Task 1 (`models.Food`, picked up by `create_tables.py` + `backend_entry` `create_all`); Task 11 (Capacitor). ✓
- In-memory `food_index.py` with `search` / `best_match`, pure-Python, no FTS/trgm → Task 3. ✓
- `GET /foods/search` new shape, `data_types`/`brandOwner` dropped → Task 4. ✓
- `GET /foods/{food_id}` string param, inline `portions` → Task 5. ✓
- `POST /foods/bulk` `List[str]` → Task 6. ✓
- `recipe_import` collapse (`rank_candidates` / `_fetch_portions_map` / `_to_candidate` / `match_ingredient`) → Task 7. ✓
- `usda.py` off every request path → Tasks 4–7 remove imports, Task 12 verifies. ✓
- `schemas.py` `fdc_id → food_id` → Task 8. ✓
- `models.py` `fdc_id → food_id` (Integer→String) → Task 8. ✓
- Neon migration SQL + desktop SQLite additive migration → Task 9. ✓
- Frontend `fdc_id → food_id`, `RecipeEditForm` / `Dashboard` / `services/api.ts` → Tasks 4, 5, 11. ✓
- `USDA_API_KEY` out of `config.py` / `.env.example` / runbook → Task 10. ✓
- Historical rows keep denormalised nutrients + stringified id, no backfill → Task 9 (migration copies, doesn't re-match). ✓
- Startup seed + index load → Task 4 (`@app.on_event("startup")`), Task 9 (desktop). ✓

**Placeholder scan:** Task 11 (Capacitor asset bundling) is described at lower fidelity than the rest — the mechanism (`fetch` an ArrayBuffer vs Capacitor asset) genuinely depends on this repo's `@capacitor-community/sqlite` wiring, which the executor must read first. Flagged, not hidden. Everything else has concrete code.

**Type consistency:** `food_index.Food` (Task 3) is the single currency for Tasks 4–7. `Food.as_search_result()` / `as_detail()` shape (`food_id`, `description`, 12 `*_per_100g`, `portions`) is defined once in Task 3 and consumed verbatim in Tasks 4/5/6 and the frontend. `food_id` is `str` everywhere (schemas Task 8, models Task 8, `ImportedIngredientCandidate` Task 7, frontend Tasks 4/5/11). `portions` is `[{"unit","grams"}]` end to end (Task 3 dataclass → Task 5 response → Task 5 frontend reader → Task 7 `portions_map`). `MATCH_CONFIDENCE_FLOOR` defined once (Task 3).

**Scope note:** This is one plan but a large cutover across backend + 3 client surfaces + 3 databases. The task order is designed so `main` compiles and both test suites pass after every task — each endpoint's server change ships with its frontend callers. If executing with subagent-driven-development, expect Tasks 4, 7, and 11 to be the heavy ones.
