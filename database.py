"""
database.py
-----------
Async SQLAlchemy engine, session factory, and Base for PakuPaku.
All models inherit from Base. All routes use get_db() as a dependency.
"""

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL


# ─────────────────────────────────────────────
#  ENGINE
# ─────────────────────────────────────────────

engine = create_async_engine(
    DATABASE_URL,
    echo=False,       # set True to log all SQL queries during development
    pool_size=10,
    max_overflow=20,
)


# ─────────────────────────────────────────────
#  SESSION FACTORY
# ─────────────────────────────────────────────

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,   # keeps objects usable after commit
)


# ─────────────────────────────────────────────
#  BASE CLASS
# ─────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────
#  DEPENDENCY
# ─────────────────────────────────────────────

async def get_db():
    """
    FastAPI dependency. Yields an async database session
    and ensures it is closed after each request.

    Usage in a route:
        from database import get_db
        from sqlalchemy.ext.asyncio import AsyncSession
        from fastapi import Depends

        @app.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()