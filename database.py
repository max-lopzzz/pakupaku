"""
database.py
-----------
Async SQLAlchemy engine, session factory, and Base for PakuPaku.
All models inherit from Base. All routes use get_db() as a dependency.
"""

import uuid

from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import CHAR, TypeDecorator
from config import DATABASE_URL


# ─────────────────────────────────────────────
#  PORTABLE UUID TYPE
# ─────────────────────────────────────────────

class GUID(TypeDecorator):
    """Platform-independent UUID column.

    Uses Postgres's native UUID type when running against Postgres
    (the hosted deployment); stores as a 32-char hex string everywhere
    else (SQLite, used by the desktop build — see backend_entry.py).
    """

    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(32))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        if dialect.name == "postgresql":
            return str(value)
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return "%.32x" % value.int

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        if not isinstance(value, uuid.UUID):
            value = uuid.UUID(value)
        return value


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