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

# The PostgreSQL half of the fdc_id -> food_id rename, also kept as a
# standalone script (`migrate_fdc_to_food_id.sql`) for anyone who wants to
# run it by hand with psql. Keep the two in sync. Each block is a no-op
# when fdc_id has already been renamed, so re-running is safe.
_PG_FDC_TO_FOOD_ID = [
    """
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'food_logs' AND column_name = 'fdc_id') THEN
        ALTER TABLE food_logs ALTER COLUMN fdc_id TYPE text USING fdc_id::text;
        ALTER TABLE food_logs RENAME COLUMN fdc_id TO food_id;
      END IF;
    END $$;
    """,
    """
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'recipe_ingredients' AND column_name = 'fdc_id') THEN
        ALTER TABLE recipe_ingredients ALTER COLUMN fdc_id TYPE text USING fdc_id::text;
        ALTER TABLE recipe_ingredients RENAME COLUMN fdc_id TO food_id;
      END IF;
    END $$;
    """,
]


async def _migrate_fdc_to_food_id_sqlite(conn) -> None:
    """SQLite path: if a table still has the old int `fdc_id` column and no
    `food_id`, add `food_id TEXT` and copy the ids across (stringified)."""
    for table in ("food_logs", "recipe_ingredients"):
        cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(%s)" % table))).fetchall()]
        if not cols or "food_id" in cols or "fdc_id" not in cols:
            continue
        await conn.execute(text("ALTER TABLE %s ADD COLUMN food_id TEXT" % table))
        await conn.execute(text(
            "UPDATE %s SET food_id = CAST(fdc_id AS TEXT) WHERE fdc_id IS NOT NULL" % table
        ))


async def _migrate_fdc_to_food_id_pg(conn) -> None:
    """PostgreSQL path: rename fdc_id -> food_id (retyped to text) on the
    two tables that carry it, in-place, guarded so it is a no-op once the
    column has already been renamed."""
    for stmt in _PG_FDC_TO_FOOD_ID:
        await conn.execute(text(stmt))


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
