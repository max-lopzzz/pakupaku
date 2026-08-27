"""
create_tables.py
-----------------
Creates any tables that don't already exist against DATABASE_URL.

Used by the hosted deployment's Render Build Command (see
docs/deployment.md) — Render has no lifespan hook to run this at app
startup, and its Pre-Deploy Command field (the more natural place for a
once-per-deploy step like this) is a paid-instance-only feature. Folding
this into the Build Command instead means it runs on every build, which
is fine: create_all() only creates tables that don't already exist, so
it's a no-op after the first deploy.

Mirrors the same create_all() pattern backend_entry.py already uses for
the desktop build.

Run directly:

    python create_tables.py
"""

import asyncio

from database import Base, engine
import models  # noqa: F401  (import side effect: registers every table on Base.metadata)


async def create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


if __name__ == "__main__":
    asyncio.run(create_tables())
    print("✓ Tables created (or already existed)")
