"""
Tests for the desktop SQLite `fdc_id` -> `food_id` migration.

Each test builds its own throwaway sqlite engine because it needs an
OLD-shape table (int `fdc_id`, no `food_id`) that the `db_session`
fixture — which builds the full current schema — cannot produce.
"""

import os
import tempfile

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from migrations import _migrate_fdc_to_food_id


async def test_desktop_migration_copies_int_fdc_id_to_text_food_id():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_async_engine("sqlite+aiosqlite:///%s" % path)
    try:
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE food_logs (id TEXT, fdc_id INTEGER)"))
            await conn.execute(text("INSERT INTO food_logs VALUES ('a', 173944), ('b', NULL)"))
            await conn.execute(text("CREATE TABLE recipe_ingredients (id TEXT, fdc_id INTEGER)"))
            await _migrate_fdc_to_food_id(conn)
            rows = (await conn.execute(text("SELECT id, food_id FROM food_logs ORDER BY id"))).fetchall()
        assert [tuple(r) for r in rows] == [("a", "173944"), ("b", None)]
    finally:
        await eng.dispose()
        os.remove(path)


async def test_desktop_migration_is_idempotent():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_async_engine("sqlite+aiosqlite:///%s" % path)
    try:
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE food_logs (id TEXT, fdc_id INTEGER)"))
            await conn.execute(text("INSERT INTO food_logs VALUES ('a', 173944), ('b', NULL)"))
            await conn.execute(text("CREATE TABLE recipe_ingredients (id TEXT, fdc_id INTEGER)"))
            await _migrate_fdc_to_food_id(conn)
            # Second run on the already-migrated DB must not raise or change anything.
            await _migrate_fdc_to_food_id(conn)
            rows = (await conn.execute(text("SELECT id, food_id FROM food_logs ORDER BY id"))).fetchall()
        assert [tuple(r) for r in rows] == [("a", "173944"), ("b", None)]
    finally:
        await eng.dispose()
        os.remove(path)


async def test_desktop_migration_noop_on_fresh_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_async_engine("sqlite+aiosqlite:///%s" % path)
    try:
        async with eng.begin() as conn:
            # Fresh-DB shape: food_id already present, no legacy fdc_id column.
            await conn.execute(text("CREATE TABLE food_logs (id TEXT, food_id TEXT)"))
            await conn.execute(text("INSERT INTO food_logs VALUES ('a', '173944')"))
            await conn.execute(text("CREATE TABLE recipe_ingredients (id TEXT, food_id TEXT)"))
            await _migrate_fdc_to_food_id(conn)
            cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(food_logs)"))).fetchall()]
            rows = (await conn.execute(text("SELECT id, food_id FROM food_logs"))).fetchall()
        assert "fdc_id" not in cols
        assert [tuple(r) for r in rows] == [("a", "173944")]
    finally:
        await eng.dispose()
        os.remove(path)
