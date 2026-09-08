"""
create_tables.py
-----------------
Brings the deployment's database schema + seed data fully up to date
against DATABASE_URL, in one idempotent step. Run from the hosted
deployment's Render Build Command (see docs/deployment.md) — Render has
no lifespan hook for this, and its Pre-Deploy Command field is
paid-instance-only.

It does three things, in order:

1. `create_all()` — create any brand-new tables (`foods`, ...).
2. `migrations._migrate_fdc_to_food_id()` — rename the legacy `fdc_id`
   column to `food_id` on `food_logs` / `recipe_ingredients` if the DB
   still has the old shape. `create_all()` cannot do this itself (it only
   ever *creates* missing tables), so without this step a deploy that
   ships `food_id` 500s every `/logs` read with
   "column food_logs.food_id does not exist".
3. `seed_foods()` — replace the `foods` table contents from the committed
   `data/foods.sqlite` artifact so the in-memory food index has something
   to load at app startup.

All three are safe to re-run on every deploy.

Run directly:

    python create_tables.py
"""

import asyncio
import logging

from sqlalchemy.exc import DBAPIError

from database import AsyncSessionLocal, Base, engine
import models  # noqa: F401  (import side effect: registers every table on Base.metadata)
from migrations import _migrate_fdc_to_food_id
from seed_foods import seed_foods

logger = logging.getLogger(__name__)

_SEED_ATTEMPTS = 4


def _is_disconnect(exc: BaseException) -> bool:
    return isinstance(exc, DBAPIError) and bool(getattr(exc, "connection_invalidated", False))


async def create_tables(db_engine=None, session_factory=None, artifact_path=None) -> int:
    db_engine = db_engine if db_engine is not None else engine
    session_factory = session_factory if session_factory is not None else AsyncSessionLocal

    async with db_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_fdc_to_food_id(conn)

    kwargs = {} if artifact_path is None else {"artifact_path": artifact_path}
    # Neon (serverless Postgres) drops connections mid-operation under load,
    # so the seed — delete + chunked re-insert, one transaction — is retried
    # whole on a disconnect. Each attempt starts a fresh session, so the
    # pool hands out a new connection after the previous one is invalidated.
    for attempt in range(1, _SEED_ATTEMPTS + 1):
        try:
            async with session_factory() as s:
                seeded = await seed_foods(s, **kwargs)
                await s.commit()
            return seeded
        except DBAPIError as exc:
            if attempt == _SEED_ATTEMPTS or not _is_disconnect(exc):
                raise
            logger.warning(
                "create_tables: seed attempt %d hit a dropped connection, retrying", attempt
            )
            await asyncio.sleep(2 ** attempt)


if __name__ == "__main__":
    n = asyncio.run(create_tables())
    print("✓ Tables created (or already existed); migrated; seeded %d foods" % n)
