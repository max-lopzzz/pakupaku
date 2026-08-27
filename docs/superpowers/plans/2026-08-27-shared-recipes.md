# Shared Recipe Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an admin-curated shared recipe library that every user can browse, log directly, or copy into their own personal collection — reusing the existing `Recipe`/`RecipeIngredient` tables and routes, plus close a real gap where `image_url`/`source_url` are already extracted by recipe-import but discarded on save.

**Architecture:** One new boolean (`is_shared`) on `Recipe` plus four new columns (`image_url`, `source_url`, `instructions`, `diet_tags`) turn a personal recipe and a shared recipe into the same row shape — the only difference is who can see it. One new boolean (`is_admin`) on `User` gates who can set `is_shared = True`, enforced server-side regardless of what a client sends. Two new routes (`GET /recipes/shared`, `POST /recipes/{id}/copy`) and one relaxed check (`POST /logs`) are the entire new backend surface.

**Tech Stack:** FastAPI, SQLAlchemy async (Postgres in production, SQLite for tests and the desktop build), Pydantic v2 (using the codebase's existing `@validator` v1-compat style, not `@field_validator`), React 19 + TypeScript, `@testing-library/react`.

**Spec:** [docs/superpowers/specs/2026-08-27-shared-recipes-design.md](../specs/2026-08-27-shared-recipes-design.md)

## Global Constraints

- `is_shared` is never trusted from the client — every write path that could set it to `True` re-checks `current_user.is_admin` server-side, unconditionally.
- No self-service admin promotion. Promoting an account is a manual SQL command (given at the end of this plan), never a route or UI element.
- `diet_tags` values are validated against a fixed set (given below) — invalid values are a 422, not silently dropped.
- One image per recipe (`image_url`), not a gallery.
- `instructions` is stored as a single newline-separated text block (portability: Postgres has array types, the desktop build's SQLite driver doesn't, and this app runs on both) — rendered as an ordered list by splitting on newlines wherever it's displayed.
- Full diet tag set: `vegan, vegetarian, pescatarian, flexitarian, gluten_free, dairy_free, nut_free, soy_free, egg_free, shellfish_free, keto, low_carb, paleo, whole30, low_fodmap, diabetic_friendly, low_sodium, low_fat, high_protein, halal, kosher, mediterranean, dash`.

---

### Task 1: Real database test fixtures

**Files:**
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: two pytest fixtures every later backend task uses —
  `db_session` (an `AsyncSession` backed by a real, isolated temp-file
  SQLite database with every table created) and `client` (a
  `fastapi.testclient.TestClient` with `get_db` overridden to yield
  `db_session`). Both are plain functions decorated
  `@pytest_asyncio.fixture` / `@pytest.fixture`, `async def` for
  `db_session`, sync `def` for `client` (it doesn't need to be async
  itself — it only sets up an override and yields a `TestClient`).

No existing test in this repo touches a real database — every test
either avoids the DB entirely or mocks around it (see
`tests/test_main_recipes_import.py`). Testing ownership/visibility
rules (who can see a shared recipe, who can log one) needs real
round-trips through actual queries; mocking SQLAlchemy's async
`execute`/`scalar` chain call-by-call is fragile and doesn't catch real
bugs the way a real database does. This plan introduces that
infrastructure once, here, so every later task just uses it.

`pytest-asyncio` is already a pinned dependency (`requirements.txt`) but
check whether it's actually installed in this worktree's venv before
running anything:

```bash
./venv/bin/python3 -c "import pytest_asyncio" 2>&1 || ./venv/bin/python3 -m pip install pytest-asyncio==0.24.0
```

- [ ] **Step 1: Add the fixtures to `tests/conftest.py`**

Append to the existing file (keep the existing `os.environ.setdefault(...)`
lines at the top untouched — they still matter for any test module that
imports `main` before these fixtures run):

```python
import tempfile
import os as _os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


@pytest_asyncio.fixture
async def db_session():
    """A real, isolated SQLite-backed session for one test.

    Creates a fresh temp-file database (not :memory: — an in-memory
    SQLite database is scoped to a single connection, and SQLAlchemy's
    async engine uses a connection pool by default, so a second
    connection would see an empty database; a temp file sidesteps that
    entirely), builds every table via Base.metadata.create_all, yields
    a session, then disposes the engine and deletes the file.

    `import models` is required before create_all() — Base.metadata is
    only populated by the side effect of every model class being
    defined, and importing only `database` (which defines Base but not
    the models) leaves it empty. This exact mistake was made once
    already this session in a very similar script; import models
    explicitly rather than relying on some other import to have done it
    first.
    """
    import models  # noqa: F401  registers every table on Base.metadata
    from database import Base

    fd, path = tempfile.mkstemp(suffix=".db")
    _os.close(fd)
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    await test_engine.dispose()
    _os.remove(path)


@pytest.fixture
def client(db_session):
    """A TestClient whose get_db dependency yields db_session — every
    request in a test using this fixture shares the same session and
    transaction state, matching how a single request's handler already
    works (route handlers call db.flush(), not db.commit(), so writes
    are visible to later queries in the same session without needing a
    commit boundary between requests in a test)."""
    from fastapi.testclient import TestClient
    from database import get_db
    from main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] **Step 2: Write a smoke test proving the fixture actually works**

Create `tests/test_db_fixtures.py`:

```python
import uuid

import pytest
from sqlalchemy import select

from models import User


@pytest.mark.asyncio
async def test_db_session_persists_and_queries(db_session):
    user = User(
        id=uuid.uuid4(),
        email="fixture-smoke@example.com",
        username="fixturesmoke",
        hashed_password="x",
        email_verified=True,
        safe_mode=False,
        uses_custom_goals=False,
    )
    db_session.add(user)
    await db_session.flush()

    result = await db_session.execute(
        select(User).where(User.email == "fixture-smoke@example.com")
    )
    found = result.scalar_one()
    assert found.username == "fixturesmoke"


def test_client_fixture_reaches_the_same_session(client, db_session):
    """A request that queries the DB should see what db_session already
    has, proving the override actually points at the same session."""
    import asyncio
    import uuid as _uuid
    from models import User

    async def _seed():
        u = User(
            id=_uuid.uuid4(),
            email="client-fixture@example.com",
            username="clientfixture",
            hashed_password="x",
            email_verified=True,
            safe_mode=False,
            uses_custom_goals=False,
        )
        db_session.add(u)
        await db_session.flush()

    asyncio.get_event_loop().run_until_complete(_seed())

    # /auth/login with a wrong password against a real seeded user
    # proves the request reached the same DB — a 401 (bad password)
    # rather than some other error confirms the user was actually found.
    res = client.post(
        "/auth/login",
        json={"email": "client-fixture@example.com", "password": "wrong"},
    )
    assert res.status_code == 401
```

- [ ] **Step 3: Run the tests to verify they pass**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_db_fixtures.py -v
```

Expected: both tests PASS. If `test_client_fixture_reaches_the_same_session`
fails with a 500 instead of 401, read the traceback — the most likely
cause is `get_db` not actually being overridden (check the import of
`get_db` in the fixture matches exactly what `main.py` imports it as).

- [ ] **Step 4: Run the full existing suite to confirm nothing broke**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest -q
```

Expected: all previously-passing tests still pass, plus the 2 new ones
(53 total, up from 51).

- [ ] **Step 5: Commit**

```bash
git add tests/conftest.py tests/test_db_fixtures.py
git commit -m "Add real SQLite-backed test fixtures (db_session, client)

No existing test touches a real database - every route test needed for
this feature (who can see a shared recipe, who can log one, does a
copy stay independent) needs real query round-trips, not mocked
SQLAlchemy calls. Verified both fixtures work: a direct db_session
write is queryable back, and a request through the client fixture
reaches that same session (proven via a real /auth/login 401 against a
seeded user, not some other error)."
```

---

### Task 2: Schema and model changes

**Files:**
- Modify: `models.py` (User, Recipe)
- Modify: `schemas.py` (RecipeCreateRequest, RecipeUpdateRequest, RecipeResponse, UserResponse)
- Test: `tests/test_shared_recipe_schemas.py`

**Interfaces:**
- Consumes: `db_session`, `client` fixtures (Task 1)
- Produces: `User.is_admin: bool`; `Recipe.image_url: Optional[str]`,
  `Recipe.source_url: Optional[str]`, `Recipe.instructions: Optional[str]`,
  `Recipe.diet_tags: Optional[str]` (comma-joined string, same shape as
  `User.metabolic_conditions`), `Recipe.is_shared: bool`. On the schema
  side: `RecipeCreateRequest`/`RecipeUpdateRequest` gain
  `image_url: Optional[str]`, `source_url: Optional[str]`,
  `instructions: Optional[str]`, `diet_tags: Optional[List[str]]`,
  `is_shared: Optional[bool]`; `RecipeResponse` gains the same five as
  response fields (with `diet_tags: List[str]`, always a list, never
  `None`, in the response); `UserResponse` gains `is_admin: bool`.

- [ ] **Step 1: Add `is_admin` to `User` in `models.py`**

Find the `User` class's boolean columns (near `safe_mode`) and add
alongside them:

```python
is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- [ ] **Step 2: Add the five new columns to `Recipe` in `models.py`**

In the `Recipe` class, after the existing `updated_at` column and
before the `# ── Totals` comment block, add:

```python
image_url:    Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
source_url:   Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
instructions: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
diet_tags:    Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
is_shared:    Mapped[bool]          = mapped_column(Boolean, default=False, nullable=False)
```

(`Boolean` and `Text` are almost certainly already imported at the top
of `models.py` for other columns — check, and add them to the existing
`from sqlalchemy import ...` line only if missing.)

- [ ] **Step 3: Extend the Recipe schemas in `schemas.py`**

Find `RecipeCreateRequest` and add:

```python
    image_url:    Optional[str]       = None
    source_url:   Optional[str]       = None
    instructions: Optional[str]       = None
    diet_tags:    Optional[List[str]] = None
    is_shared:    Optional[bool]      = None

    @validator("diet_tags")
    def validate_diet_tags(cls, v):
        if v is None:
            return v
        valid = {
            "vegan", "vegetarian", "pescatarian", "flexitarian",
            "gluten_free", "dairy_free", "nut_free", "soy_free",
            "egg_free", "shellfish_free",
            "keto", "low_carb", "paleo", "whole30", "low_fodmap",
            "diabetic_friendly", "low_sodium", "low_fat", "high_protein",
            "halal", "kosher",
            "mediterranean", "dash",
        }
        invalid = set(v) - valid
        if invalid:
            raise ValueError(f"Unknown diet tag(s): {sorted(invalid)}. Must be one of {sorted(valid)}")
        return v
```

Find `RecipeUpdateRequest` and add the same five fields (all already
`Optional` in that class's style) plus the identical `diet_tags`
validator — Pydantic validators aren't inherited across sibling
classes, so this one needs to be written out again in
`RecipeUpdateRequest` too, not just `RecipeCreateRequest`.

Find `RecipeResponse` and add:

```python
    image_url:    Optional[str]
    source_url:   Optional[str]
    instructions: Optional[str]
    diet_tags:    List[str]
    is_shared:    bool
```

`RecipeResponse` reads from the ORM object (`Config.from_attributes = True`),
where `diet_tags` is stored as a comma-joined string — Task 3 handles
the string↔list conversion at the route layer (a Pydantic response
model can't run arbitrary conversion logic on a plain column value
without a computed field, and this codebase doesn't use those
elsewhere, so keep the conversion where every other list-shaped field
in this app already does it: in the route handler).

- [ ] **Step 4: Add `is_admin` to `UserResponse` in `schemas.py`**

```python
    is_admin: bool
```

Add it near `uses_custom_goals` at the end of the class.

- [ ] **Step 5: Write and run a schema-validation test**

Create `tests/test_shared_recipe_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from schemas import RecipeCreateRequest


def test_diet_tags_accepts_valid_values():
    req = RecipeCreateRequest(
        name="Test",
        servings=1,
        ingredients=[{"food_name": "rice", "amount_g": 100}],
        diet_tags=["vegan", "gluten_free"],
    )
    assert req.diet_tags == ["vegan", "gluten_free"]


def test_diet_tags_rejects_unknown_values():
    with pytest.raises(ValidationError):
        RecipeCreateRequest(
            name="Test",
            servings=1,
            ingredients=[{"food_name": "rice", "amount_g": 100}],
            diet_tags=["not_a_real_tag"],
        )
```

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_schemas.py -v
```

Expected: both PASS.

- [ ] **Step 6: Verify the new columns actually create via the Task 1 fixture**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_db_fixtures.py -v
```

Expected: still PASS — `db_session`'s `Base.metadata.create_all` now
creates the new columns too, and if there's a syntax error in the model
changes this is where it surfaces.

- [ ] **Step 7: Commit**

```bash
git add models.py schemas.py tests/test_shared_recipe_schemas.py
git commit -m "Add shared-recipe columns and schema fields

User.is_admin; Recipe.image_url/source_url/instructions/diet_tags/is_shared.
diet_tags is validated against a fixed set (unlike metabolic_conditions,
whose unknown keys are silently ignored elsewhere in this codebase) - the
whole point of a tag set is that it means something consistent."
```

---

### Task 3: Persist the new fields, enforce admin-only `is_shared`

**Files:**
- Modify: `main.py` (`create_recipe`, `update_recipe`, `list_recipes`, `get_recipe`)
- Test: `tests/test_shared_recipe_routes.py`

**Interfaces:**
- Consumes: `client`/`db_session` fixtures (Task 1); `Recipe.is_shared`
  etc. (Task 2)
- Produces: `POST /recipes` and `PATCH /recipes/{id}` persist
  `image_url`/`source_url`/`instructions`/`diet_tags`/`is_shared` (the
  last one only when `current_user.is_admin`); every recipe-returning
  route serializes `diet_tags` from the stored comma-joined string into
  a list via a `RecipeResponse` pre-validator (Step 5), not a route-level
  helper. A helper `_diet_tags_to_str(tags: Optional[List[str]]) -> Optional[str]`
  (list → stored string, the write direction) is the only one needed —
  there's no read-direction helper, because the pre-validator handles
  every route that returns a `Recipe` through `RecipeResponse`
  automatically, including `GET /recipes/shared` (Task 4) and
  `POST /recipes/{id}/copy` (Task 5).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_shared_recipe_routes.py`:

```python
import uuid

from auth import get_current_user, hash_password
from database import get_db
from main import app
from models import User


async def _make_user(db_session, *, is_admin=False, email=None):
    user = User(
        id=uuid.uuid4(),
        email=email or f"{uuid.uuid4()}@example.com",
        username=f"user{uuid.uuid4().hex[:8]}",
        hashed_password=hash_password("TestPass123!"),
        email_verified=True,
        safe_mode=False,
        uses_custom_goals=False,
        is_admin=is_admin,
    )
    db_session.add(user)
    await db_session.flush()
    return user


def _as(client, user):
    app.dependency_overrides[get_current_user] = lambda: user
    return client


def test_non_admin_cannot_set_is_shared(client, db_session):
    import asyncio
    user = asyncio.get_event_loop().run_until_complete(_make_user(db_session))
    try:
        res = _as(client, user).post(
            "/recipes",
            json={
                "name": "Not actually shared",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
                "is_shared": True,
            },
        )
        assert res.status_code == 201
        assert res.json()["is_shared"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_admin_can_set_is_shared(client, db_session):
    import asyncio
    admin = asyncio.get_event_loop().run_until_complete(
        _make_user(db_session, is_admin=True)
    )
    try:
        res = _as(client, admin).post(
            "/recipes",
            json={
                "name": "A real shared recipe",
                "servings": 2,
                "ingredients": [{"food_name": "beans", "amount_g": 200}],
                "is_shared": True,
                "image_url": "https://example.com/beans.jpg",
                "source_url": "https://example.com/beans-recipe",
                "instructions": "Soak beans.\nSimmer 1 hour.",
                "diet_tags": ["vegan", "gluten_free"],
            },
        )
        assert res.status_code == 201
        body = res.json()
        assert body["is_shared"] is True
        assert body["image_url"] == "https://example.com/beans.jpg"
        assert body["source_url"] == "https://example.com/beans-recipe"
        assert body["instructions"] == "Soak beans.\nSimmer 1 hour."
        assert sorted(body["diet_tags"]) == ["gluten_free", "vegan"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_update_recipe_cannot_flip_is_shared_without_admin(client, db_session):
    import asyncio
    user = asyncio.get_event_loop().run_until_complete(_make_user(db_session))
    try:
        c = _as(client, user)
        created = c.post(
            "/recipes",
            json={
                "name": "Mine",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
            },
        ).json()
        res = c.patch(f"/recipes/{created['id']}", json={"is_shared": True})
        assert res.status_code == 200
        assert res.json()["is_shared"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_routes.py -v
```

Expected: FAIL — the current `create_recipe`/`update_recipe` handlers
don't read `is_shared`/`image_url`/etc. from the payload at all yet
(they'll be silently ignored, and `RecipeResponse` will 500 on
serialization since it now requires `diet_tags`/`is_shared` as
non-optional response fields the ORM object doesn't have set... actually
they default via the model, so more likely: the test's assertions on
`is_shared`/`image_url` etc. fail because those fields, while present
in the response, are `None`/`False` regardless of what was sent, since
nothing wires the payload through yet).

- [ ] **Step 3: Add the diet-tags write helper and wire the new fields into `create_recipe`**

Near the top of `main.py`, close to `_compute_recipe_totals` (find it
with `grep -n "_compute_recipe_totals" main.py`), add:

```python
def _diet_tags_to_str(tags: Optional[List[str]]) -> Optional[str]:
    return ",".join(tags) if tags else None
```

(This is the write direction only — list to stored string. The read
direction, converting the stored string back to a list for API
responses, is handled once for every route in Step 5 below via a
`RecipeResponse` pre-validator, not a second helper function here.)

In `create_recipe`, change the `Recipe(...)` construction to:

```python
    recipe = Recipe(
        user_id      = current_user.id,
        name         = payload.name,
        description  = payload.description,
        servings     = payload.servings,
        image_url    = payload.image_url,
        source_url   = payload.source_url,
        instructions = payload.instructions,
        diet_tags    = _diet_tags_to_str(payload.diet_tags),
        is_shared    = bool(payload.is_shared) and current_user.is_admin,
    )
```

- [ ] **Step 4: Wire the new fields into `update_recipe`**

After the existing `if payload.name is not None: ...` block in
`update_recipe`, add:

```python
    if payload.image_url    is not None: recipe.image_url    = payload.image_url
    if payload.source_url   is not None: recipe.source_url   = payload.source_url
    if payload.instructions is not None: recipe.instructions = payload.instructions
    if payload.diet_tags    is not None: recipe.diet_tags    = _diet_tags_to_str(payload.diet_tags)
    if payload.is_shared    is not None:
        recipe.is_shared = bool(payload.is_shared) and current_user.is_admin
```

- [ ] **Step 5: Every route returning a `Recipe` needs `diet_tags` converted to a list**

`RecipeResponse` is a Pydantic model with `from_attributes = True`,
reading `diet_tags` straight off the ORM object — but the ORM object
stores a comma-joined string, and the response schema declares
`diet_tags: List[str]`. Pydantic v2 does not auto-split a string into a
list, so this needs an explicit conversion before each return.

The cleanest fix without touching every route's return statement:
`RecipeResponse` gets a validator that runs on the raw ORM attribute
before type validation. In `schemas.py`, on `RecipeResponse`, add:

```python
    @validator("diet_tags", pre=True)
    def _split_diet_tags(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            return [t for t in v.split(",") if t]
        return v
```

Every route that returns a `Recipe` (or list of them) through
`RecipeResponse` gets the split for free from this validator — no
per-route conversion code needed, including in Task 4's
`GET /recipes/shared` and Task 5's `POST /recipes/{id}/copy`, both of
which just return ORM objects the same way `create_recipe` already
does. This validator is what actually fixes `create_recipe`/`update_recipe`/
`list_recipes`/`get_recipe`'s responses without editing each one.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_routes.py -v
```

Expected: all 3 PASS.

- [ ] **Step 7: Run the full suite**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest -q
```

Expected: all pass (56 total).

- [ ] **Step 8: Commit**

```bash
git add main.py schemas.py tests/test_shared_recipe_routes.py
git commit -m "Persist new recipe fields; enforce admin-only is_shared

create_recipe/update_recipe now read image_url/source_url/instructions/
diet_tags/is_shared from the request - is_shared is always re-derived
as \`bool(payload.is_shared) and current_user.is_admin\`, so a non-admin
client claiming is_shared:true is silently overridden to False rather
than trusted. RecipeResponse gets a pre-validator that splits the
stored comma-joined diet_tags string into a list, so every existing
recipe route (list/get/create/update) returns the new field correctly
without touching each handler's return statement individually.

Verified: a non-admin's is_shared:true request creates a recipe with
is_shared=False; an admin's the same request actually sets it; a
non-admin PATCHing is_shared:true on their own recipe doesn't flip it."
```

---

### Task 4: `GET /recipes/shared`

**Files:**
- Modify: `main.py`
- Test: `tests/test_shared_recipe_routes.py` (append)

**Interfaces:**
- Consumes: `client`/`db_session` fixtures; the `RecipeResponse`
  pre-validator (Task 3, Step 5) that converts stored `diet_tags`
  strings to lists — this route needs no diet-tags handling of its own
- Produces: `GET /recipes/shared` route, `response_model=List[RecipeResponse]`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_shared_recipe_routes.py`:

```python
def test_shared_recipes_visible_to_non_owner(client, db_session):
    import asyncio

    async def _setup():
        admin = await _make_user(db_session, is_admin=True)
        viewer = await _make_user(db_session)
        return admin, viewer

    admin, viewer = asyncio.get_event_loop().run_until_complete(_setup())
    try:
        _as(client, admin).post(
            "/recipes",
            json={
                "name": "Shared one",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
                "is_shared": True,
            },
        )
        _as(client, admin).post(
            "/recipes",
            json={
                "name": "Admin's private recipe",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
            },
        )

        res = _as(client, viewer).get("/recipes/shared")
        assert res.status_code == 200
        names = [r["name"] for r in res.json()]
        assert names == ["Shared one"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run to verify it fails**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_routes.py::test_shared_recipes_visible_to_non_owner -v
```

Expected: FAIL with 404 (route doesn't exist yet).

- [ ] **Step 3: Add the route**

In `main.py`, immediately after the existing `list_recipes` handler
(find it with `grep -n "async def list_recipes" main.py`), add — this
must come **before** `@app.get("/recipes/{recipe_id}")` in the file, or
FastAPI's path matching will treat `"shared"` as a `{recipe_id}` value
and this route will never be reached:

```python
@app.get("/recipes/shared", response_model=List[RecipeResponse])
async def list_shared_recipes(
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Every admin-curated shared recipe, for any logged-in user."""
    result = await db.execute(
        select(Recipe)
        .where(Recipe.is_shared == True)  # noqa: E712  (SQLAlchemy needs == True, not `is True`)
        .order_by(Recipe.created_at.desc())
        .options(selectinload(Recipe.ingredients))
    )
    return result.scalars().all()
```

Check the exact route ordering with:
```bash
grep -n "@app.get(\"/recipes" main.py
```
`/recipes/shared` must appear before `/recipes/{recipe_id}` in that
output. If it doesn't, move the new route above the `get_recipe`
handler.

- [ ] **Step 4: Run to verify it passes**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_routes.py -v
```

Expected: all 4 tests in the file PASS.

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_shared_recipe_routes.py
git commit -m "Add GET /recipes/shared

Returns every is_shared=True recipe, not filtered by ownership - any
logged-in user can see it. Placed before /recipes/{recipe_id} in the
route table; FastAPI matches path segments in declaration order, so
/recipes/shared would otherwise be swallowed as a recipe_id lookup for
the literal string \"shared\".

Verified: a non-admin viewer sees exactly the admin's shared recipe,
not the admin's private one."
```

---

### Task 5: `POST /recipes/{id}/copy`

**Files:**
- Modify: `main.py`
- Test: `tests/test_shared_recipe_routes.py` (append)

**Interfaces:**
- Consumes: `client`/`db_session` fixtures; `_compute_recipe_totals`
  (existing helper, reused as-is)
- Produces: `POST /recipes/{recipe_id}/copy` route,
  `response_model=RecipeResponse`, `status_code=201`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_shared_recipe_routes.py`:

```python
def test_copy_shared_recipe_is_independent(client, db_session):
    import asyncio

    async def _setup():
        admin = await _make_user(db_session, is_admin=True)
        copier = await _make_user(db_session)
        return admin, copier

    admin, copier = asyncio.get_event_loop().run_until_complete(_setup())
    try:
        original = _as(client, admin).post(
            "/recipes",
            json={
                "name": "Original",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
                "is_shared": True,
            },
        ).json()

        copy_res = _as(client, copier).post(f"/recipes/{original['id']}/copy")
        assert copy_res.status_code == 201
        copy = copy_res.json()
        assert copy["id"] != original["id"]
        assert copy["name"] == "Original"
        assert copy["is_shared"] is False
        assert copy["user_id"] == str(copier.id)

        # Editing the copy must not touch the original
        _as(client, copier).patch(f"/recipes/{copy['id']}", json={"name": "My version"})
        original_after = _as(client, admin).get(f"/recipes/{original['id']}").json()
        assert original_after["name"] == "Original"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_copy_of_private_recipe_you_dont_own_404s(client, db_session):
    import asyncio

    async def _setup():
        owner = await _make_user(db_session)
        other = await _make_user(db_session)
        return owner, other

    owner, other = asyncio.get_event_loop().run_until_complete(_setup())
    try:
        private = _as(client, owner).post(
            "/recipes",
            json={
                "name": "Private",
                "servings": 1,
                "ingredients": [{"food_name": "rice", "amount_g": 100}],
            },
        ).json()

        res = _as(client, other).post(f"/recipes/{private['id']}/copy")
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run to verify they fail**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_routes.py -k copy -v
```

Expected: FAIL (404 for both — route doesn't exist).

- [ ] **Step 3: Add the route**

In `main.py`, immediately after `list_shared_recipes` (Task 4), add:

```python
@app.post("/recipes/{recipe_id}/copy", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def copy_recipe(
    recipe_id:    uuid.UUID,
    current_user: User         = Depends(get_current_user),
    db:           AsyncSession = Depends(get_db),
):
    """Save an independent personal copy of a recipe you own or that's shared."""
    result = await db.execute(
        select(Recipe)
        .where(
            Recipe.id == recipe_id,
            (Recipe.user_id == current_user.id) | (Recipe.is_shared == True),  # noqa: E712
        )
        .options(selectinload(Recipe.ingredients))
    )
    source = result.scalar_one_or_none()
    if not source:
        raise HTTPException(status_code=404, detail="Recipe not found.")

    copy = Recipe(
        user_id      = current_user.id,
        name         = source.name,
        description  = source.description,
        servings     = source.servings,
        image_url    = source.image_url,
        source_url   = source.source_url,
        instructions = source.instructions,
        diet_tags    = source.diet_tags,
        is_shared    = False,
    )
    db.add(copy)
    await db.flush()

    ingredient_objs = []
    for ing in source.ingredients:
        obj = RecipeIngredient(
            recipe_id  = copy.id,
            fdc_id     = ing.fdc_id,
            food_name  = ing.food_name,
            brand_name = ing.brand_name,
            amount_g   = ing.amount_g,
            calories   = ing.calories,
            protein_g  = ing.protein_g,
            fat_g      = ing.fat_g,
            carbs_g    = ing.carbs_g,
            fiber_g    = ing.fiber_g,
        )
        db.add(obj)
        ingredient_objs.append(obj)

    await db.flush()

    totals = _compute_recipe_totals(ingredient_objs, copy.servings)
    copy.total_calories  = totals["total_calories"]
    copy.total_protein_g = totals["total_protein_g"]
    copy.total_fat_g     = totals["total_fat_g"]
    copy.total_carbs_g   = totals["total_carbs_g"]
    copy.total_fiber_g   = totals["total_fiber_g"]

    await db.flush()

    result = await db.execute(
        select(Recipe)
        .where(Recipe.id == copy.id)
        .options(selectinload(Recipe.ingredients))
    )
    return result.scalar_one()
```

- [ ] **Step 4: Run to verify they pass**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_routes.py -v
```

Expected: all tests in the file PASS (6 total so far).

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_shared_recipe_routes.py
git commit -m "Add POST /recipes/{id}/copy

Copies a recipe you own or that's shared into a new, fully independent
row owned by you (is_shared always False on the copy - copying doesn't
propagate sharing). 404s for a recipe that's neither yours nor shared.

Verified: copying a shared recipe produces a new id owned by the
copier; editing the copy afterward leaves the original untouched;
copying someone else's private recipe 404s."
```

---

### Task 6: Relax `POST /logs`'s recipe-ownership check

**Files:**
- Modify: `main.py`
- Test: `tests/test_shared_recipe_routes.py` (append)

**Interfaces:**
- Consumes: `client`/`db_session` fixtures
- Produces: no new interface — modifies existing `POST /logs` behavior

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_shared_recipe_routes.py`:

```python
def test_can_log_a_shared_recipe_you_dont_own(client, db_session):
    import asyncio

    async def _setup():
        admin = await _make_user(db_session, is_admin=True)
        logger_ = await _make_user(db_session)
        return admin, logger_

    admin, logger_ = asyncio.get_event_loop().run_until_complete(_setup())
    try:
        shared = _as(client, admin).post(
            "/recipes",
            json={
                "name": "Shared soup",
                "servings": 2,
                "ingredients": [{"food_name": "broth", "amount_g": 500, "calories": 50}],
                "is_shared": True,
            },
        ).json()

        res = _as(client, logger_).post(
            "/logs",
            json={
                "recipe_id": shared["id"],
                "food_name": "Shared soup",
                "amount_g": 100,
                "calories": 25,
                "meal": "lunch",
            },
        )
        assert res.status_code == 201
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_cannot_log_a_private_recipe_you_dont_own(client, db_session):
    import asyncio

    async def _setup():
        owner = await _make_user(db_session)
        other = await _make_user(db_session)
        return owner, other

    owner, other = asyncio.get_event_loop().run_until_complete(_setup())
    try:
        private = _as(client, owner).post(
            "/recipes",
            json={
                "name": "Private soup",
                "servings": 1,
                "ingredients": [{"food_name": "broth", "amount_g": 500}],
            },
        ).json()

        res = _as(client, other).post(
            "/logs",
            json={
                "recipe_id": private["id"],
                "food_name": "Private soup",
                "amount_g": 100,
                "meal": "lunch",
            },
        )
        assert res.status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)
```

- [ ] **Step 2: Run to verify the first passes accidentally-wrong and the second is the real regression guard**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_routes.py -k "log_a" -v
```

Expected: `test_can_log_a_shared_recipe_you_dont_own` FAILS (404 —
current check requires ownership); `test_cannot_log_a_private_recipe_you_dont_own`
already PASSES (this is the existing, correct behavior — it's here as a
regression guard for Step 3's change, not a new requirement).

- [ ] **Step 3: Relax the check**

Find the recipe-ownership check inside the `POST /logs` handler
(`grep -n "if payload.recipe_id is not None" main.py`) and change:

```python
    if payload.recipe_id is not None:
        recipe_result = await db.execute(
            select(Recipe).where(
                Recipe.id == payload.recipe_id,
                Recipe.user_id == current_user.id,
            )
        )
```

to:

```python
    if payload.recipe_id is not None:
        recipe_result = await db.execute(
            select(Recipe).where(
                Recipe.id == payload.recipe_id,
                (Recipe.user_id == current_user.id) | (Recipe.is_shared == True),  # noqa: E712
            )
        )
```

- [ ] **Step 4: Run to verify both pass**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_shared_recipe_routes.py -v
```

Expected: all tests in the file PASS (8 total).

- [ ] **Step 5: Run the full backend suite**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest -q
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_shared_recipe_routes.py
git commit -m "Allow logging a shared recipe you don't own

POST /logs's recipe ownership check becomes an OR: you own it, or it's
shared. Verified both directions: a shared recipe logs successfully
for a non-owner; a still-private recipe you don't own still 404s (this
second case already passed before the change - included as an explicit
regression guard, not a new requirement)."
```

---

### Task 7: Extract `instructions` during recipe import

**Files:**
- Modify: `recipe_import.py` (`RawRecipe`, `extract_structured_recipe`, `extract_recipe_via_llm`, `_EXTRACT_SYSTEM_PROMPT`, `build_import_draft`)
- Modify: `schemas.py` (`RecipeImportDraft`)
- Test: `tests/test_recipe_import_structured.py`, `tests/test_recipe_import_llm.py`, `tests/test_recipe_import_draft.py` (append to existing files — matches this codebase's existing one-file-per-concern test layout for recipe-import)

**Interfaces:**
- Consumes: none new
- Produces: `RawRecipe.instructions: Optional[str]`,
  `RecipeImportDraft.instructions: Optional[str]` — both newline-joined
  step text, `None` when no instructions were found

- [ ] **Step 1: Add `instructions` to `RawRecipe`**

In `recipe_import.py`, find `class RawRecipe:` (a dataclass) and add:

```python
    instructions: Optional[str]
```

- [ ] **Step 2: Write the failing structured-extraction test**

Check the existing fixture used by `tests/test_recipe_import_structured.py`
(`grep -n "def test_" tests/test_recipe_import_structured.py` and look
at what HTML/JSON-LD fixture it loads) — this new test follows the same
loading pattern, just adding `recipeInstructions` to the JSON-LD and
asserting it's captured. Append to `tests/test_recipe_import_structured.py`:

```python
def test_extract_structured_recipe_captures_instructions():
    html = """
    <script type="application/ld+json">
    {
      "@type": "Recipe",
      "name": "Soup",
      "recipeIngredient": ["1 cup broth"],
      "recipeInstructions": [
        {"@type": "HowToStep", "text": "Heat the broth."},
        {"@type": "HowToStep", "text": "Season and serve."}
      ]
    }
    </script>
    """
    from recipe_import import extract_structured_recipe
    result = extract_structured_recipe(html)
    assert result is not None
    assert result.instructions == "Heat the broth.\nSeason and serve."


def test_extract_structured_recipe_instructions_as_plain_strings():
    html = """
    <script type="application/ld+json">
    {
      "@type": "Recipe",
      "name": "Soup",
      "recipeIngredient": ["1 cup broth"],
      "recipeInstructions": ["Heat the broth.", "Season and serve."]
    }
    </script>
    """
    from recipe_import import extract_structured_recipe
    result = extract_structured_recipe(html)
    assert result.instructions == "Heat the broth.\nSeason and serve."


def test_extract_structured_recipe_no_instructions_is_none():
    html = """
    <script type="application/ld+json">
    {
      "@type": "Recipe",
      "name": "Soup",
      "recipeIngredient": ["1 cup broth"]
    }
    </script>
    """
    from recipe_import import extract_structured_recipe
    result = extract_structured_recipe(html)
    assert result.instructions is None
```

- [ ] **Step 3: Run to verify they fail**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_recipe_import_structured.py -k instructions -v
```

Expected: FAIL (`RawRecipe.__init__()` doesn't accept `instructions` /
`extract_structured_recipe` doesn't pass it yet — an outright
`TypeError`, not an assertion failure, until Step 1 lands; if Step 1 is
already done, expect an `AttributeError` or wrong-value assertion
failure instead).

- [ ] **Step 4: Add a `_parse_instructions` helper and wire it into `extract_structured_recipe`**

Near `_parse_image` in `recipe_import.py`, add:

```python
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
```

In `extract_structured_recipe`, change the `return RawRecipe(...)` call
to add:

```python
            instructions=_parse_instructions(node.get("recipeInstructions")),
```

- [ ] **Step 5: Run to verify the structured-extraction tests pass**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_recipe_import_structured.py -v
```

Expected: all PASS, including pre-existing tests in that file (they'll
now fail if `RawRecipe(...)`'s other call site in this same function
wasn't updated — there's only the one construction site in
`extract_structured_recipe`, so this should be the only place that
needed the new keyword argument).

- [ ] **Step 6: Extend the LLM fallback prompt and extraction**

In `recipe_import.py`, change `_EXTRACT_SYSTEM_PROMPT` to:

```python
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
```

In `extract_recipe_via_llm`, change the `return RawRecipe(...)` call to:

```python
    steps = data.get("steps") or []
    return RawRecipe(
        name=str(data["name"]).strip(),
        servings=float(data.get("servings") or 1),
        image_url=None,
        instructions="\n".join(str(s).strip() for s in steps if str(s).strip()) or None,
        ingredient_lines=[str(l).strip() for l in lines if str(l).strip()],
    )
```

- [ ] **Step 7: Write the failing LLM-fallback test**

Check the mocking pattern already used in `tests/test_recipe_import_llm.py`
(`grep -n "_call_llm_json\|monkeypatch" tests/test_recipe_import_llm.py`)
and follow it exactly. Append:

```python
@pytest.mark.asyncio
async def test_extract_recipe_via_llm_captures_steps(monkeypatch):
    import recipe_import

    async def fake_call_llm_json(system_prompt, user_content):
        return {
            "name": "Soup",
            "servings": 2,
            "ingredient_lines": ["1 cup broth"],
            "steps": ["Heat the broth.", "Season and serve."],
        }

    monkeypatch.setattr(recipe_import, "_call_llm_json", fake_call_llm_json)
    result = await recipe_import.extract_recipe_via_llm("<html></html>")
    assert result.instructions == "Heat the broth.\nSeason and serve."
```

(If the existing file's tests use a different monkeypatch target or
fixture style than shown here, match theirs — this is illustrative of
the assertion, not a rigid template; read the file first.)

- [ ] **Step 8: Run to verify it passes**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_recipe_import_llm.py -v
```

Expected: all PASS.

- [ ] **Step 9: Thread `instructions` through `RecipeImportDraft` and `build_import_draft`**

In `schemas.py`, find `class RecipeImportDraft` and add:

```python
    instructions: Optional[str] = None
```

In `recipe_import.py`'s `build_import_draft`, change the final
`return RecipeImportDraft(...)` to add:

```python
        instructions=raw.instructions,
```

- [ ] **Step 10: Run the full recipe-import test suite**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest tests/test_recipe_import_structured.py tests/test_recipe_import_llm.py tests/test_recipe_import_draft.py tests/test_main_recipes_import.py -v
```

Expected: all PASS.

- [ ] **Step 11: Run the full backend suite**

```bash
DATABASE_URL="postgresql+asyncpg://test:test@localhost/test" SECRET_KEY="test-secret-key" \
  ./venv/bin/python3 -m pytest -q
```

Expected: all pass.

- [ ] **Step 12: Commit**

```bash
git add recipe_import.py schemas.py tests/test_recipe_import_structured.py tests/test_recipe_import_llm.py
git commit -m "Extract cooking instructions during recipe import

Both extraction paths (JSON-LD recipeInstructions and the LLM fallback)
now capture steps, joined with newlines into RawRecipe.instructions and
threaded through to RecipeImportDraft. JSON-LD handles the two common
shapes (a bare string list, or a list of HowToStep {text: ...} objects)
- nested HowToSection groupings aren't handled, an acceptable gap this
file already accepts for other uncommon markup variants.

This closes half of a real gap: image_url/source_url were already
extracted but discarded on save (Task 8 wires the frontend save step to
stop dropping them); instructions is genuinely new extraction, not
previously attempted at all."
```

---

### Task 8: `RecipeBuilder.tsx` form fields, detail rendering, and closing the discard gap

**Files:**
- Modify: `pakupaku-frontend/src/components/RecipeBuilder.tsx`
- Modify: `pakupaku-frontend/src/App.tsx` (pass `userProfile` to `RecipeBuilder`)
- Test: `pakupaku-frontend/src/components/RecipeBuilder.test.tsx`

**Interfaces:**
- Consumes: `userProfile.is_admin` (from `App.tsx`, via `UserResponse`,
  Task 2)
- Produces: `RecipeBuilderProps` gains `userProfile: any`

- [ ] **Step 1: Add `userProfile` to `RecipeBuilderProps` and read `is_admin`**

In `RecipeBuilder.tsx`, find `interface RecipeBuilderProps` and change:

```tsx
interface RecipeBuilderProps {
  onBack: () => void;
}
```

to:

```tsx
interface RecipeBuilderProps {
  onBack: () => void;
  userProfile: any;
}
```

Change the function signature:

```tsx
export default function RecipeBuilder({ onBack, userProfile }: RecipeBuilderProps) {
```

- [ ] **Step 2: Extend the `RecipeResponse` and `RecipeImportDraft` TS interfaces**

Find `interface RecipeResponse` in `RecipeBuilder.tsx` and add:

```tsx
  image_url?:    string | null;
  source_url?:   string | null;
  instructions?: string | null;
  diet_tags?:    string[];
  is_shared?:    boolean;
```

Find `interface RecipeImportDraft` and add:

```tsx
  instructions?: string | null;
```

- [ ] **Step 3: Add form state for the new fields**

Near the existing `const [importImageUrl, setImportImageUrl] = useState<string | null>(null);`,
add:

```tsx
  const [imageUrl, setImageUrl]     = useState("");
  const [sourceUrl, setSourceUrl]   = useState("");
  const [instructions, setInstructions] = useState("");
  const [dietTags, setDietTags]     = useState<string[]>([]);
  const [isShared, setIsShared]     = useState(false);
```

Add the fixed tag list near the top of the file, after the existing
`_UNIT_ALIASES`/similar constant blocks (or just above the component
function):

```tsx
const DIET_TAGS = [
  "vegan", "vegetarian", "pescatarian", "flexitarian",
  "gluten_free", "dairy_free", "nut_free", "soy_free", "egg_free", "shellfish_free",
  "keto", "low_carb", "paleo", "whole30", "low_fodmap", "diabetic_friendly",
  "low_sodium", "low_fat", "high_protein",
  "halal", "kosher",
  "mediterranean", "dash",
];

function toggleDietTag(tags: string[], tag: string): string[] {
  return tags.includes(tag) ? tags.filter(t => t !== tag) : [...tags, tag];
}
```

- [ ] **Step 4: Wire the new fields through `startEdit`, `cancelEdit`, `startImport`, and `handleSave`**

In `startEdit`, after the existing `setServings(String(recipe.servings));`
line, add:

```tsx
    setImageUrl(recipe.image_url ?? "");
    setSourceUrl(recipe.source_url ?? "");
    setInstructions(recipe.instructions ?? "");
    setDietTags(recipe.diet_tags ?? []);
    setIsShared(recipe.is_shared ?? false);
```

In `cancelEdit`, after `setImportImageUrl(null);`, add:

```tsx
    setImageUrl(""); setSourceUrl(""); setInstructions("");
    setDietTags([]); setIsShared(false);
```

In `startImport`, after `setImportImageUrl(draft.image_url);`, add:

```tsx
      setImageUrl(draft.image_url ?? "");
      setSourceUrl(draft.source_url ?? "");
      setInstructions(draft.instructions ?? "");
```

(This is the fix for the discard bug: `importImageUrl` was already
tracked purely for the preview `<img>` shown during import review, but
never included in the save payload — `imageUrl`/`sourceUrl`/`instructions`
are the new state that actually gets sent.)

In `handleSave`, change the `payload` object to add the new fields:

```tsx
    const payload = {
      name:         name.trim(),
      description:  description.trim() || undefined,
      servings:     parseFloat(servings) || 1,
      image_url:    imageUrl.trim() || undefined,
      source_url:   sourceUrl.trim() || undefined,
      instructions: instructions.trim() || undefined,
      diet_tags:    dietTags.length > 0 ? dietTags : undefined,
      is_shared:    isShared,
      ingredients: valid.map(r => {
```
(keep the existing `ingredients: valid.map(...)` block exactly as-is —
this only adds five new keys before it.)

At the end of `handleSave`'s success path, alongside the existing
`setImportImageUrl(null);` line, add:

```tsx
      setImageUrl(""); setSourceUrl(""); setInstructions("");
      setDietTags([]); setIsShared(false);
```

- [ ] **Step 5: Add the new form fields to the JSX**

In the return block, find the `<label className="recipe-field recipe-field-inline">`
for Servings (`grep -n "Servings" pakupaku-frontend/src/components/RecipeBuilder.tsx`)
and insert immediately after its closing `</label>`, still before the
`<div className="ingredient-section">` block:

```tsx
            <label className="recipe-field">
              <span>Image URL</span>
              <input type="url" value={imageUrl}
                onChange={e => setImageUrl(e.target.value)}
                placeholder="https://example.com/photo.jpg" />
            </label>
            <label className="recipe-field">
              <span>Source link</span>
              <input type="url" value={sourceUrl}
                onChange={e => setSourceUrl(e.target.value)}
                placeholder="https://example.com/original-recipe" />
            </label>
            <label className="recipe-field">
              <span>Instructions</span>
              <textarea value={instructions}
                onChange={e => setInstructions(e.target.value)}
                placeholder={"One step per line\ne.g.\nHeat the broth.\nSeason and serve."} />
            </label>
            <div className="recipe-field">
              <span>Diet tags</span>
              <div className="diet-tags-grid">
                {DIET_TAGS.map(tag => (
                  <label key={tag} className="diet-tag-checkbox">
                    <input
                      type="checkbox"
                      checked={dietTags.includes(tag)}
                      onChange={() => setDietTags(prev => toggleDietTag(prev, tag))}
                    />
                    {tag.replace(/_/g, " ")}
                  </label>
                ))}
              </div>
            </div>
            {userProfile?.is_admin && (
              <label className="recipe-field recipe-field-inline">
                <input
                  type="checkbox"
                  checked={isShared}
                  onChange={e => setIsShared(e.target.checked)}
                />
                <span>Share in the shared recipe library</span>
              </label>
            )}
```

- [ ] **Step 6: Show the new fields on each saved-recipe card**

Find the saved-recipe card block (`grep -n "saved-recipe-card\"" pakupaku-frontend/src/components/RecipeBuilder.tsx`)
and, right after the existing `{recipe.description && <p>{recipe.description}</p>}`
line, add:

```tsx
                  {recipe.image_url && (
                    <img src={recipe.image_url} alt="" className="saved-recipe-image" />
                  )}
                  {recipe.diet_tags && recipe.diet_tags.length > 0 && (
                    <div className="saved-recipe-tags">
                      {recipe.diet_tags.map(tag => (
                        <span key={tag} className="diet-tag-pill">{tag.replace(/_/g, " ")}</span>
                      ))}
                    </div>
                  )}
                  {recipe.instructions && (
                    <ol className="saved-recipe-instructions">
                      {recipe.instructions.split("\n").filter(Boolean).map((step, i) => (
                        <li key={i}>{step}</li>
                      ))}
                    </ol>
                  )}
                  {recipe.source_url && (
                    <a href={recipe.source_url} target="_blank" rel="noreferrer" className="saved-recipe-source-link">
                      View original
                    </a>
                  )}
```

- [ ] **Step 7: Pass `userProfile` from `App.tsx`**

In `App.tsx`, find the `<RecipeBuilder onBack={...} />` render call
(`grep -n "<RecipeBuilder" pakupaku-frontend/src/App.tsx`) and change it to:

```tsx
    return <RecipeBuilder onBack={() => setView("dashboard")} userProfile={userProfile} />;
```

- [ ] **Step 8: Update the existing frontend test's mock draft**

`RecipeBuilder.test.tsx`'s `draft` fixture object needs `instructions`
added (it already has `image_url`/`source_url`) so the test stays
representative:

```tsx
const draft = {
  name: "Test Pancakes",
  servings: 4,
  image_url: null,
  source_url: "https://example.com/pancakes",
  instructions: "Mix ingredients.\nCook on a griddle.",
  ingredients: [
```
(keep everything else in that object unchanged — this only adds one line.)

Also update the `beforeEach`'s fetch mock: it currently returns `[]`
for `"/recipes"`; since `RecipeBuilder` now takes a `userProfile` prop,
update the `render(<RecipeBuilder onBack={() => {}} />)` call in the
existing test to `render(<RecipeBuilder onBack={() => {}} userProfile={{ is_admin: false }} />)`.

- [ ] **Step 9: Write a new test for the admin-only checkbox and the discard-fix**

Append to `RecipeBuilder.test.tsx`:

```tsx
test("is_shared checkbox only appears for admins", () => {
  const { rerender } = render(<RecipeBuilder onBack={() => {}} userProfile={{ is_admin: false }} />);
  expect(screen.queryByText("Share in the shared recipe library")).not.toBeInTheDocument();

  rerender(<RecipeBuilder onBack={() => {}} userProfile={{ is_admin: true }} />);
  expect(screen.getByText("Share in the shared recipe library")).toBeInTheDocument();
});

test("importing a URL carries instructions into the form", async () => {
  render(<RecipeBuilder onBack={() => {}} userProfile={{ is_admin: false }} />);

  const urlInput = screen.getByPlaceholderText("https://example.com/some-recipe");
  fireEvent.change(urlInput, { target: { value: "https://example.com/pancakes" } });
  fireEvent.click(screen.getByText("Import"));

  await waitFor(() => {
    expect(screen.getByDisplayValue("Mix ingredients.\nCook on a griddle.")).toBeInTheDocument();
  });
});
```

- [ ] **Step 10: Run the frontend tests**

```bash
cd pakupaku-frontend
CI=true npx --no-install react-scripts test --watchAll=false src/components/RecipeBuilder.test.tsx
```

Expected: all tests in `RecipeBuilder.test.tsx` PASS. (`App.test.tsx`
failing separately is a pre-existing, unrelated issue — the default CRA
boilerplate test was never updated when the app's actual content
diverged from the starter template; don't treat that failure as caused
by this task, and don't fix it as part of this plan — out of scope.)

- [ ] **Step 11: Verify the production build compiles**

```bash
CI=true npm run build
```

Expected: "Compiled successfully." with no new warnings (this repo
treats ESLint warnings as hard build errors under `CI=true`, matching
how the hosted deployment actually builds — see the two prior fixes for
exactly this class of failure in this repo's git history if unfamiliar
with why this check matters here specifically).

- [ ] **Step 12: Commit**

```bash
cd ..
git add pakupaku-frontend/src/components/RecipeBuilder.tsx pakupaku-frontend/src/components/RecipeBuilder.test.tsx pakupaku-frontend/src/App.tsx
git commit -m "Add image/source/instructions/diet-tags fields to RecipeBuilder

New create/edit form fields for every user (image_url, source_url,
instructions, diet_tags checkboxes), plus an is_shared checkbox visible
only when userProfile.is_admin. Saved-recipe cards now render the
image, diet tags, instructions as a numbered list, and a source link.

Also closes the recipe-import discard gap: startImport already tracked
importImageUrl purely for the preview <img>, but handleSave's payload
never included image_url/source_url/instructions at all, so URL-import
silently dropped them on save. New imageUrl/sourceUrl/instructions
state is what actually gets sent now.

Verified: CI=true npm run build compiles clean; RecipeBuilder.test.tsx
passes, including two new tests (admin-only checkbox visibility,
import carrying instructions into the form)."
```

---

### Task 9: `SharedRecipes.tsx` — browse, log, and copy

**Files:**
- Create: `pakupaku-frontend/src/components/SharedRecipes.tsx`
- Create: `pakupaku-frontend/src/components/SharedRecipes.css`
- Test: `pakupaku-frontend/src/components/SharedRecipes.test.tsx`

**Interfaces:**
- Consumes: `apiFetch` (`../apiBase`, already used throughout the
  frontend); `GET /recipes/shared`, `POST /recipes/{id}/copy`,
  `POST /logs` (all backend, Tasks 3–6)
- Produces: `export default function SharedRecipes({ onBack }: { onBack: () => void })`
  — a new top-level view, structurally a sibling of `RecipeBuilder`, not
  a section inside it. `RecipeBuilder.tsx` is already 931 lines before
  this task; folding a second, functionally distinct concern (discovery
  + logging, vs. building/editing one recipe) into the same file would
  make it unwieldy to review or safely edit. A separate file matches
  this codebase's existing pattern of one file per top-level view
  (`Dashboard.tsx`, `Onboarding.tsx`, `RecipeBuilder.tsx` are all
  siblings already).

- [ ] **Step 1: Write the failing test**

Create `pakupaku-frontend/src/components/SharedRecipes.test.tsx`:

```tsx
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import SharedRecipes from "./SharedRecipes";

const sharedRecipe = {
  id: "11111111-1111-1111-1111-111111111111",
  name: "Shared Soup",
  servings: 2,
  image_url: null,
  diet_tags: ["vegan", "gluten_free"],
  total_calories: 200,
  total_protein_g: 10,
  total_fat_g: 5,
  total_carbs_g: 20,
};

beforeEach(() => {
  localStorage.setItem("token", "test-token");
  global.fetch = jest.fn((url: RequestInfo | URL, init?: RequestInit) => {
    const u = String(url);
    if (u === "/recipes/shared") {
      return Promise.resolve({ ok: true, json: async () => [sharedRecipe] } as Response);
    }
    if (u === `/recipes/${sharedRecipe.id}/copy` && init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => ({ ...sharedRecipe, id: "copy-id", is_shared: false }) } as Response);
    }
    if (u === "/logs" && init?.method === "POST") {
      return Promise.resolve({ ok: true, json: async () => ({ id: "log-id" }) } as Response);
    }
    return Promise.reject(new Error(`Unexpected fetch: ${u}`));
  }) as jest.Mock;
});

afterEach(() => {
  jest.restoreAllMocks();
  localStorage.clear();
});

test("lists shared recipes and their diet tags", async () => {
  render(<SharedRecipes onBack={() => {}} />);
  await waitFor(() => {
    expect(screen.getByText("Shared Soup")).toBeInTheDocument();
  });
  expect(screen.getByText("vegan")).toBeInTheDocument();
  expect(screen.getByText("gluten free")).toBeInTheDocument();
});

test("save a copy calls the copy endpoint", async () => {
  render(<SharedRecipes onBack={() => {}} />);
  await waitFor(() => screen.getByText("Shared Soup"));

  fireEvent.click(screen.getByText("Save a copy"));

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith(
      `/recipes/${sharedRecipe.id}/copy`,
      expect.objectContaining({ method: "POST" })
    );
  });
});

test("log now posts to /logs with the recipe id and scaled nutrients", async () => {
  render(<SharedRecipes onBack={() => {}} />);
  await waitFor(() => screen.getByText("Shared Soup"));

  fireEvent.click(screen.getByText("Log now"));
  fireEvent.click(screen.getByText("Confirm"));

  await waitFor(() => {
    expect(global.fetch).toHaveBeenCalledWith(
      "/logs",
      expect.objectContaining({ method: "POST" })
    );
  });
  const call = (global.fetch as jest.Mock).mock.calls.find(([u]) => u === "/logs");
  const body = JSON.parse(call[1].body);
  expect(body.recipe_id).toBe(sharedRecipe.id);
  expect(body.calories).toBe(200); // 1 serving, default multiplier
});
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd pakupaku-frontend
CI=true npx --no-install react-scripts test --watchAll=false src/components/SharedRecipes.test.tsx 2>&1 | tail -20
```

Expected: FAIL — `Cannot find module './SharedRecipes'`.

- [ ] **Step 3: Create `SharedRecipes.tsx`**

```tsx
import { useEffect, useState } from "react";
import "./SharedRecipes.css";
import { apiFetch } from "../apiBase";

interface SharedRecipe {
  id: string;
  name: string;
  servings: number;
  image_url?: string | null;
  diet_tags?: string[];
  total_calories?: number;
  total_protein_g?: number;
  total_fat_g?: number;
  total_carbs_g?: number;
}

type MealCategory = "breakfast" | "lunch" | "dinner" | "snacks";

interface SharedRecipesProps {
  onBack: () => void;
}

function authHeaders(extra: Record<string, string> = {}) {
  const token = localStorage.getItem("token");
  return { Authorization: token ? `Bearer ${token}` : "", ...extra };
}

export default function SharedRecipes({ onBack }: SharedRecipesProps) {
  const [recipes, setRecipes] = useState<SharedRecipe[]>([]);
  const [error, setError]     = useState("");
  const [loggingId, setLoggingId] = useState<string | null>(null);
  const [servings, setServings]   = useState("1");
  const [meal, setMeal]           = useState<MealCategory>("lunch");
  const [copyMessage, setCopyMessage] = useState("");

  useEffect(() => {
    const fetchShared = async () => {
      try {
        const res = await apiFetch("/recipes/shared", { headers: authHeaders() });
        if (!res.ok) throw new Error();
        setRecipes(await res.json());
      } catch {
        setError("Unable to load shared recipes.");
      }
    };
    fetchShared();
  }, []);

  const startLogging = (recipe: SharedRecipe) => {
    setLoggingId(recipe.id);
    setServings("1");
    setMeal("lunch");
  };

  const confirmLog = async (recipe: SharedRecipe) => {
    const n = parseFloat(servings) || 1;
    const scale = (v?: number) => (v != null ? Math.round(v * n * 10) / 10 : undefined);
    try {
      const res = await apiFetch("/logs", {
        method: "POST",
        headers: authHeaders({ "Content-Type": "application/json" }),
        body: JSON.stringify({
          recipe_id: recipe.id,
          food_name: recipe.name,
          amount_g:  n * 100, // nominal - recipe totals are per-serving, not per-gram; see plan for reasoning
          calories:  scale(recipe.total_calories),
          protein_g: scale(recipe.total_protein_g),
          fat_g:     scale(recipe.total_fat_g),
          carbs_g:   scale(recipe.total_carbs_g),
          meal,
        }),
      });
      if (!res.ok) throw new Error();
      setLoggingId(null);
    } catch {
      setError("Failed to log that recipe.");
    }
  };

  const saveCopy = async (recipe: SharedRecipe) => {
    setCopyMessage("");
    try {
      const res = await apiFetch(`/recipes/${recipe.id}/copy`, {
        method: "POST",
        headers: authHeaders(),
      });
      if (!res.ok) throw new Error();
      setCopyMessage(`Saved a copy of "${recipe.name}" to your recipes.`);
    } catch {
      setError("Failed to save a copy.");
    }
  };

  return (
    <div className="shared-recipes-root">
      <div className="shared-recipes-container">
        <header className="shared-recipes-header">
          <button type="button" className="back-button" onClick={onBack}>← Back</button>
          <h1 className="shared-recipes-title">Shared Recipes</h1>
        </header>

        {error && <p className="shared-recipes-error">{error}</p>}
        {copyMessage && <p className="shared-recipes-message">{copyMessage}</p>}

        {recipes.length === 0 ? (
          <div className="empty-state">No shared recipes yet.</div>
        ) : (
          <div className="shared-recipes-grid">
            {recipes.map(recipe => (
              <div key={recipe.id} className="shared-recipe-card">
                {recipe.image_url && (
                  <img src={recipe.image_url} alt="" className="shared-recipe-image" />
                )}
                <h3>{recipe.name}</h3>
                <span>{recipe.servings} serving{recipe.servings !== 1 ? "s" : ""}</span>
                {recipe.diet_tags && recipe.diet_tags.length > 0 && (
                  <div className="shared-recipe-tags">
                    {recipe.diet_tags.map(tag => (
                      <span key={tag} className="diet-tag-pill">{tag.replace(/_/g, " ")}</span>
                    ))}
                  </div>
                )}
                <div className="shared-recipe-actions">
                  <button type="button" onClick={() => startLogging(recipe)}>Log now</button>
                  <button type="button" onClick={() => saveCopy(recipe)}>Save a copy</button>
                </div>
                {loggingId === recipe.id && (
                  <div className="log-recipe-form">
                    <label>
                      <span>Servings</span>
                      <input type="number" min="0.25" step="0.25" value={servings}
                        onChange={e => setServings(e.target.value)} />
                    </label>
                    <label>
                      <span>Meal</span>
                      <select value={meal} onChange={e => setMeal(e.target.value as MealCategory)}>
                        <option value="breakfast">Breakfast</option>
                        <option value="lunch">Lunch</option>
                        <option value="dinner">Dinner</option>
                        <option value="snacks">Snacks</option>
                      </select>
                    </label>
                    <button type="button" onClick={() => confirmLog(recipe)}>Confirm</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create `SharedRecipes.css`**

A minimal stylesheet reusing this app's established visual language
(check `RecipeBuilder.css` for the exact color variables/class-naming
conventions already in use — `.recipe-form-card`, `.saved-recipe-card`,
etc. — and match them rather than inventing new values):

```css
.shared-recipes-root {
  min-height: 100vh;
  padding: 2rem 1rem;
}

.shared-recipes-container {
  max-width: 900px;
  margin: 0 auto;
}

.shared-recipes-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-bottom: 1.5rem;
}

.shared-recipes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 1rem;
}

.shared-recipe-card {
  border: 1px solid #eaf5f3;
  border-radius: 12px;
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.shared-recipe-image {
  width: 100%;
  height: 140px;
  object-fit: cover;
  border-radius: 8px;
}

.shared-recipe-tags,
.saved-recipe-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}

.diet-tag-pill {
  background: #eaf5f3;
  color: #3a2a2a;
  border-radius: 999px;
  padding: 0.15rem 0.6rem;
  font-size: 0.75rem;
}

.shared-recipe-actions {
  display: flex;
  gap: 0.5rem;
}

.log-recipe-form {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-top: 1px solid #eaf5f3;
  padding-top: 0.5rem;
}

.shared-recipes-error {
  color: #c0392b;
}

.shared-recipes-message {
  color: #2e7d32;
}
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
CI=true npx --no-install react-scripts test --watchAll=false src/components/SharedRecipes.test.tsx
```

Expected: all 3 PASS. If `"log now posts to /logs..."` fails on the
`amount_g`/`calories` assertion, double check `confirmLog`'s `scale()`
math against the test's expected `200` (1 serving × `total_calories`
of `200` = `200` exactly, since the test's default `servings` state is
`"1"`).

- [ ] **Step 6: Verify the production build compiles**

```bash
CI=true npm run build
```

Expected: "Compiled successfully."

- [ ] **Step 7: Commit**

```bash
cd ..
git add pakupaku-frontend/src/components/SharedRecipes.tsx pakupaku-frontend/src/components/SharedRecipes.css pakupaku-frontend/src/components/SharedRecipes.test.tsx
git commit -m "Add SharedRecipes.tsx: browse, log, and copy shared recipes

New top-level view, a sibling of RecipeBuilder rather than a section
inside it - RecipeBuilder.tsx was already 931 lines before this
feature, and browsing/logging/copying is a distinct concern from
building one recipe.

amount_g on the /logs payload is set to servings * 100 rather than a
literal gram amount - recipe totals are per-serving, not per-gram, and
this field is never rendered anywhere in the Dashboard's meal list
(confirmed via grep), so a nominal value scaled by servings is honest
enough and matches the \"100\" placeholder this app's other log-creation
call sites already default to for non-gram-denominated entries.

Verified: CI=true npm run build compiles clean; all 3 new tests pass
(list rendering with diet tags, save-a-copy calls the copy endpoint,
log-now posts to /logs with the recipe id and servings-scaled
nutrients)."
```

---

### Task 10: Wire `SharedRecipes` into `App.tsx`

**Files:**
- Modify: `pakupaku-frontend/src/App.tsx`
- Modify: `pakupaku-frontend/src/components/Dashboard.tsx` (new nav button)

**Interfaces:**
- Consumes: `SharedRecipes` (Task 9)
- Produces: `AppView` gains `"sharedRecipes"`; `DashboardProps` gains
  `onOpenSharedRecipes: () => void`

- [ ] **Step 1: Add the new view to `AppView` and import `SharedRecipes`**

In `App.tsx`, find:
```tsx
import Settings from "./components/Settings";
```
and add immediately after:
```tsx
import SharedRecipes from "./components/SharedRecipes";
```

Find the `type AppView = ...` line and add `"sharedRecipes"` to the
union:
```tsx
type AppView = "login" | "verifyEmail" | "onboarding" | "dashboard" | "recipeBuilder" | "settings" | "resetPassword" | "sharedRecipes";
```

- [ ] **Step 2: Add the render branch**

Find the `if (view === "settings") { ... }` block and add a new branch
right after it:

```tsx
  if (view === "sharedRecipes") {
    return <SharedRecipes onBack={() => setView("dashboard")} />;
  }
```

- [ ] **Step 3: Add `onOpenSharedRecipes` to the `Dashboard` render call**

Find the `<Dashboard ... />` render call in `App.tsx` and add a new prop:

```tsx
      onOpenSharedRecipes={() => setView("sharedRecipes")}
```

- [ ] **Step 4: Add the prop and a header button in `Dashboard.tsx`**

In `Dashboard.tsx`, find `interface DashboardProps` and add:

```tsx
  onOpenSharedRecipes: () => void;
```

Find where `onOpenSharedRecipes` needs to be destructured out of props
(same place `onOpenSettings` already is — `grep -n "onOpenSettings" pakupaku-frontend/src/components/Dashboard.tsx`)
and add it there too.

Find the header's action buttons (`.dashboard-header-actions`, added
earlier this session alongside the Settings button —
`grep -n "dashboard-header-actions" pakupaku-frontend/src/components/Dashboard.tsx`)
and add a new button before the Settings button:

```tsx
        <button type="button" className="secondary-button" onClick={onOpenSharedRecipes}>Shared recipes</button>
```

- [ ] **Step 5: Update `App.test.tsx` if it renders `Dashboard` directly**

Check `grep -n "Dashboard\|onOpenSettings" pakupaku-frontend/src/App.test.tsx` —
this file's one existing test was already failing before this plan (the
default CRA "learn react" boilerplate test, unrelated to any real
component). If it does directly render `<Dashboard>` with a hand-built
props object, add `onOpenSharedRecipes: () => {}` to keep TypeScript
happy; if it only renders `<App />` (likely, given the pre-existing
failure is about App's actual rendered content, not a prop-shape
error), no change needed here.

- [ ] **Step 6: Verify the production build compiles**

```bash
cd pakupaku-frontend
CI=true npm run build
```

Expected: "Compiled successfully." A missing `onOpenSharedRecipes` prop
anywhere it's required would show up here as a TypeScript error, not
silently.

- [ ] **Step 7: Run the full frontend test suite**

```bash
CI=true npx --no-install react-scripts test --watchAll=false 2>&1 | tail -20
```

Expected: `RecipeBuilder.test.tsx` and `SharedRecipes.test.tsx` all
PASS; `App.test.tsx`'s one pre-existing failure is unchanged (not
introduced or fixed by this task — confirm the failure message is still
the same "learn react" text-not-found error, not a new error, which
would indicate this task broke something).

- [ ] **Step 8: Commit**

```bash
cd ..
git add pakupaku-frontend/src/App.tsx pakupaku-frontend/src/components/Dashboard.tsx
git commit -m "Wire SharedRecipes into App.tsx via a new Dashboard header button

Adds \"sharedRecipes\" to AppView and a \"Shared recipes\" button next to
the existing Create recipe / Settings buttons. Verified CI=true npm run
build compiles clean and the full frontend suite runs with no newly
introduced failures (App.test.tsx's one pre-existing, unrelated
failure is unchanged)."
```

---

## Admin promotion (manual, not a plan task)

Per the spec's explicit non-goal, there is no self-service admin
promotion route or UI. To make your own account an admin after this
plan is deployed, run this against the database directly (Neon for the
hosted deployment, or the desktop build's local SQLite file) — the same
way earlier bugs this session were hand-patched:

```sql
UPDATE users SET is_admin = true WHERE email = 'your-email@example.com';
```

Replace the email with your actual account's email. This works
identically against Postgres (`psql`) or SQLite (`sqlite3`) — both
accept this exact syntax.

## Plan Self-Review

**Spec coverage:**
- Data model (`is_admin`, `image_url`/`source_url`/`instructions`/`diet_tags`/`is_shared`) → Task 2 ✓
- `POST /recipes` / `PATCH /recipes/{id}` extended, admin-enforced `is_shared` → Task 3 ✓
- `GET /recipes/shared` → Task 4 ✓
- `POST /recipes/{id}/copy` → Task 5 ✓
- `POST /logs` relaxed check → Task 6 ✓
- `recipe_import.py` instructions extraction (JSON-LD + LLM) → Task 7 ✓
- `RecipeBuilder.tsx` new fields, admin-only checkbox, closing the discard gap → Task 8 ✓
- "Browse Shared Recipes" section (Log now / Save a copy) → Task 9 ✓ (built as a separate file — see Task 9's Interfaces section for the file-structure reasoning, consistent with the spec's intent, not a deviation from it)
- Admin promotion documented, not built → the section above, deliberately outside any task ✓
- Testing section's specific scenarios (non-admin can't set is_shared, copy independence, copy-of-inaccessible-recipe 404s, cross-user shared logging works, private cross-user logging still 404s, imported instructions persist) → each has a corresponding test in Tasks 2, 3, 5, 6, 7 ✓

**Gap found during planning, not in the original spec:** the spec's
frontend section said "Log now (reuses the existing quantity/meal-category
picker already used for logging a personal saved recipe)" — checking
the actual codebase, no such picker exists anywhere; `RecipeBuilder.tsx`
has never had recipe-based logging UI, only recipe creation/editing.
Task 9 builds this UI from scratch rather than reusing something that
doesn't exist. Also surfaced and resolved during planning: `amount_g`
on a recipe-based log entry has no natural meaning (recipe totals are
per-serving, not per-gram) — resolved as `servings * 100`, documented
inline in Task 9's commit message, since the field is never rendered
to a user anywhere in the app (confirmed via grep) and this matches
the "100" nominal default two other log-creation call sites in
`Dashboard.tsx` already use.

**Placeholder scan:** no TBD/TODO/"add appropriate handling"/
"similar to Task N" found on re-read.

**Type consistency:** `RecipeResponse` (Python, Task 2) and
`RecipeResponse`/`SharedRecipe` (TypeScript, Tasks 8–9) field names
match exactly (`image_url`, `source_url`, `instructions`, `diet_tags`,
`is_shared`). `_diet_tags_to_str` (Task 3) and the `RecipeResponse`
pre-validator it pairs with are each used exactly where the plan says —
confirmed no task defines a helper it never calls. `SharedRecipe.id` (TS) and the
backend's `uuid.UUID` response field are both consumed as plain strings
in the frontend, consistent with how `RecipeResponse.id` is already
handled elsewhere in `RecipeBuilder.tsx`.
