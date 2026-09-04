"""
migrations.py
-------------
One-off schema fixups that run on the desktop SQLite database at launch
(there is no migration tooling in a packaged end-user app). Kept in its
own module so tests can import a single function without pulling in
`backend_entry`, which runs `asyncio.run(_create_tables())` and
`from main import app` at import time.
"""

from sqlalchemy import text


async def _migrate_fdc_to_food_id(conn) -> None:
    """SQLite desktop path: if a table still has the old int `fdc_id`
    column and no `food_id`, add `food_id TEXT` and copy the ids
    across (stringified). Idempotent; a no-op on fresh DBs."""
    for table in ("food_logs", "recipe_ingredients"):
        cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(%s)" % table))).fetchall()]
        if not cols or "food_id" in cols or "fdc_id" not in cols:
            continue
        await conn.execute(text("ALTER TABLE %s ADD COLUMN food_id TEXT" % table))
        await conn.execute(text(
            "UPDATE %s SET food_id = CAST(fdc_id AS TEXT) WHERE fdc_id IS NOT NULL" % table
        ))
