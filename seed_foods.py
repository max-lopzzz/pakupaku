"""
seed_foods.py
-------------
Load the offline ``data/foods.sqlite`` artifact (built by
``scripts/build_food_db``) into the runtime DB ``foods`` table.

``seed_foods`` takes a live ``AsyncSession`` and does NOT commit — the
caller owns the transaction boundary. ``main()`` is the standalone /
deploy-build entrypoint and commits for you.
"""

import asyncio
import logging
import os
import sqlite3

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from models import Food

logger = logging.getLogger(__name__)

# TODO(plan1-task9): bundle data/foods.sqlite + resolve ARTIFACT_PATH via
# sys._MEIPASS — this CWD-relative path yields an empty index in the
# packaged desktop (PyInstaller) app.
ARTIFACT_PATH = "data/foods.sqlite"
_COLS = [c.name for c in Food.__table__.columns]


async def seed_foods(session: AsyncSession, artifact_path: str = ARTIFACT_PATH) -> int:
    """Replace every row of the ``foods`` table with the artifact's rows.

    Returns the number of rows loaded. If ``artifact_path`` does not
    exist, logs a warning and returns 0 without touching the table (so
    CI / a deploy that runs before the build pipeline still works).
    The caller is responsible for committing.
    """
    if not os.path.exists(artifact_path):
        logger.warning(
            "seed_foods: %s not found - foods table left untouched", artifact_path
        )
        return 0

    src = sqlite3.connect(artifact_path)
    src.row_factory = sqlite3.Row
    try:
        rows = [
            dict(r)
            for r in src.execute("SELECT %s FROM foods" % ",".join(_COLS))
        ]
    finally:
        src.close()

    await session.execute(delete(Food))
    if rows:
        await session.execute(insert(Food), rows)

    logger.info("seed_foods: loaded %d rows from %s", len(rows), artifact_path)
    return len(rows)


def main() -> None:
    async def _run() -> int:
        from database import AsyncSessionLocal

        async with AsyncSessionLocal() as s:
            n = await seed_foods(s)
            await s.commit()
        return n

    n = asyncio.run(_run())
    print("seeded %d foods" % n)


if __name__ == "__main__":
    main()
