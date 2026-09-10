"""
migrations.py
-------------
One-off schema fixups applied at deploy/launch time. There is no
migration tooling in this project (packaged desktop app + a Render build
step, not an Alembic pipeline), so these run from `backend_entry.py`
(desktop SQLite) and `create_tables.py` (hosted Postgres/Neon).

Kept in its own module so tests can import a single function without
pulling in `backend_entry`, which runs `asyncio.run(_create_tables())`
and `from main import app` at import time.
"""

from sqlalchemy import text

# Only these two tables ever carried the legacy int `fdc_id`. Literal,
# fixed list — safe to interpolate into DDL below.
_FDC_TABLES = ("food_logs", "recipe_ingredients")

# `migrate_fdc_to_food_id.sql` is the same rename as a standalone psql
# script (DO-blocks, which psql runs natively). The Python paths below
# avoid DO-blocks / dollar-quoting so they're safe under asyncpg's
# prepared-statement handling.


async def _migrate_fdc_to_food_id_sqlite(conn) -> None:
    """SQLite path: if a table still has the old int `fdc_id` column and no
    `food_id`, add `food_id TEXT` and copy the ids across (stringified)."""
    for table in _FDC_TABLES:
        cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(%s)" % table))).fetchall()]
        if not cols or "food_id" in cols or "fdc_id" not in cols:
            continue
        await conn.execute(text("ALTER TABLE %s ADD COLUMN food_id TEXT" % table))
        await conn.execute(text(
            "UPDATE %s SET food_id = CAST(fdc_id AS TEXT) WHERE fdc_id IS NOT NULL" % table
        ))


async def _pg_has_column(conn, table: str, column: str) -> bool:
    row = (await conn.execute(
        text("SELECT 1 FROM information_schema.columns "
             "WHERE table_name = :t AND column_name = :c"),
        {"t": table, "c": column},
    )).first()
    return row is not None


async def _migrate_fdc_to_food_id_pg(conn) -> None:
    """PostgreSQL path: rename `fdc_id` -> `food_id` (retyped to text) on
    the two tables that carry it, in-place. A no-op once the column has
    already been renamed, so it is safe to run on every deploy. Plain
    single statements only — no DO-block — so asyncpg is happy."""
    for table in _FDC_TABLES:
        if not await _pg_has_column(conn, table, "fdc_id"):
            continue
        if await _pg_has_column(conn, table, "food_id"):
            continue
        await conn.execute(text(
            "ALTER TABLE %s ALTER COLUMN fdc_id TYPE text USING fdc_id::text" % table))
        await conn.execute(text(
            "ALTER TABLE %s RENAME COLUMN fdc_id TO food_id" % table))


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


async def _migrate_fdc_to_food_id(conn) -> None:
    """Rename the legacy int `fdc_id` column to text `food_id` on
    `food_logs` / `recipe_ingredients`. Idempotent; a no-op on a fresh DB
    that already has `food_id`. Dispatches on the connection's dialect so
    the same call works for the desktop (SQLite) and hosted (Postgres)
    deploys — `create_all()` can only *create* missing tables, it can
    never rename a column on one that already exists."""
    if conn.dialect.name == "postgresql":
        await _migrate_fdc_to_food_id_pg(conn)
    else:
        await _migrate_fdc_to_food_id_sqlite(conn)
