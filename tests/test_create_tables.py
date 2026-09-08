"""
Tests for the hosted-deploy schema+seed entrypoint.

`create_tables()` must do everything a fresh Neon deploy needs in one
idempotent step: create missing tables, rename the legacy `fdc_id`
column to `food_id` on an *existing* DB, and seed the `foods` table from
the committed artifact. `create_all()` alone does none of the last two,
which is why a real deploy 500'd every `/logs` read with
"column food_logs.food_id does not exist" and served an empty food index.

Uses a throwaway sqlite engine because it needs an OLD-shape table (int
`fdc_id`, no `food_id`) the `db_session` fixture cannot produce.
"""

import os
import tempfile

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import create_tables as create_tables_mod
from tests.fixtures.make_foods_mini import build as build_mini


async def _run(tmp_path, *, seed=True):
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_async_engine("sqlite+aiosqlite:///%s" % db_path)
    Session = async_sessionmaker(eng, expire_on_commit=False)

    art = tmp_path / "foods.sqlite"
    if seed:
        build_mini(str(art))

    try:
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE food_logs (id TEXT, fdc_id INTEGER)"))
            await conn.execute(text("INSERT INTO food_logs VALUES ('a', 173944), ('b', NULL)"))
            await conn.execute(text("CREATE TABLE recipe_ingredients (id TEXT, fdc_id INTEGER)"))

        n = await create_tables_mod.create_tables(
            db_engine=eng, session_factory=Session, artifact_path=str(art)
        )

        async with eng.begin() as conn:
            fl_cols = [r[1] for r in (await conn.execute(text("PRAGMA table_info(food_logs)"))).fetchall()]
            fl_rows = (await conn.execute(
                text("SELECT id, food_id FROM food_logs ORDER BY id"))).fetchall()
            foods_n = (await conn.execute(text("SELECT count(*) FROM foods"))).scalar()
        return n, fl_cols, [tuple(r) for r in fl_rows], foods_n
    finally:
        await eng.dispose()
        os.remove(db_path)


async def test_create_tables_migrates_fdc_id_and_seeds_foods(tmp_path):
    n, fl_cols, fl_rows, foods_n = await _run(tmp_path)

    assert "food_id" in fl_cols
    assert fl_rows == [("a", "173944"), ("b", None)]
    assert foods_n == 6          # the mini artifact's row count
    assert n == 6


async def test_create_tables_is_idempotent(tmp_path):
    # Second run over the same tmp artifact: no error, foods replaced not doubled.
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    eng = create_async_engine("sqlite+aiosqlite:///%s" % db_path)
    Session = async_sessionmaker(eng, expire_on_commit=False)
    art = tmp_path / "foods.sqlite"
    build_mini(str(art))
    try:
        async with eng.begin() as conn:
            await conn.execute(text("CREATE TABLE food_logs (id TEXT, fdc_id INTEGER)"))
            await conn.execute(text("CREATE TABLE recipe_ingredients (id TEXT, fdc_id INTEGER)"))
        await create_tables_mod.create_tables(db_engine=eng, session_factory=Session, artifact_path=str(art))
        n2 = await create_tables_mod.create_tables(db_engine=eng, session_factory=Session, artifact_path=str(art))
        async with eng.begin() as conn:
            foods_n = (await conn.execute(text("SELECT count(*) FROM foods"))).scalar()
        assert n2 == 6
        assert foods_n == 6
    finally:
        await eng.dispose()
        os.remove(db_path)


async def test_create_tables_seed_is_a_noop_when_artifact_absent(tmp_path):
    n, _, _, foods_n = await _run(tmp_path, seed=False)
    assert n == 0
    assert foods_n == 0         # table created by create_all, just empty
