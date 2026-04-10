"""
database.py
-----------
Async SQLAlchemy engine, session factory, and Base for PakuPaku.
All models inherit from Base. All routes use get_db() as a dependency.
"""

import uuid as _uuid
from sqlalchemy import String, CHAR
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import TypeDecorator
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from config import DATABASE_URL, DESKTOP_MODE


# ─────────────────────────────────────────────
#  UUID COMPATIBILITY
# ─────────────────────────────────────────────

class UUIDType(TypeDecorator):
    """
    Cross-database UUID column type.
    - PostgreSQL: native UUID (fast, compact)
    - SQLite / others: CHAR(36) string
    """
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_UUID(as_uuid=True))
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return str(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if isinstance(value, _uuid.UUID):
            return value
        return _uuid.UUID(value)


# ─────────────────────────────────────────────
#  ENGINE
# ─────────────────────────────────────────────

_engine_kwargs: dict = {"echo": False}

if DESKTOP_MODE:
    # SQLite requires check_same_thread=False for async use
    _engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    # PostgreSQL can use a connection pool
    _engine_kwargs["pool_size"]    = 10
    _engine_kwargs["max_overflow"] = 20

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)


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
#  INIT (desktop mode)
# ─────────────────────────────────────────────

async def init_db():
    """
    Create all tables if they don't exist.
    Used instead of Alembic in desktop/standalone mode so we don't
    need a writable migrations directory inside the PyInstaller bundle.
    """
    import models  # noqa: F401 — registers all ORM models with Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


# ─────────────────────────────────────────────
#  DEPENDENCY
# ─────────────────────────────────────────────

async def get_db():
    """
    FastAPI dependency. Yields an async database session
    and ensures it is closed after each request.
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
