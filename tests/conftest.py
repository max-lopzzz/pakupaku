"""
conftest.py
-----------
Runs before any test module is imported. Sets safe, fake environment
values so importing `main` (and therefore `database.py`, which builds a
SQLAlchemy engine from DATABASE_URL at import time) never requires a
real .env file or a reachable database. SQLAlchemy engines are lazy —
they don't connect until a query actually runs — so a syntactically
valid but unreachable URL is enough for tests that don't touch the DB.
"""

import os

os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")

import tempfile
import os as _os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


@pytest_asyncio.fixture
async def db_session():
    """A real, isolated SQLite-backed session for one test.

    Creates a fresh temp-file database (not :memory: — an in-memory
    SQLite database is scoped to a single connection, and SQLAlchemy's
    async engine uses a connection pool by default, so a second
    connection would see an empty database; a temp file sidesteps that
    entirely), builds every table via Base.metadata.create_all, yields
    a session, then disposes the engine and deletes the file.

    `import models` is required before create_all() — Base.metadata is
    only populated by the side effect of every model class being
    defined, and importing only `database` (which defines Base but not
    the models) leaves it empty. This exact mistake was made once
    already this session in a very similar script; import models
    explicitly rather than relying on some other import to have done it
    first.
    """
    import models  # noqa: F401  registers every table on Base.metadata
    from database import Base

    fd, path = tempfile.mkstemp(suffix=".db")
    _os.close(fd)
    test_engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as session:
        yield session

    await test_engine.dispose()
    _os.remove(path)


@pytest.fixture
def client(db_session):
    """A TestClient whose get_db dependency yields db_session — every
    request in a test using this fixture shares the same session and
    transaction state, matching how a single request's handler already
    works (route handlers call db.flush(), not db.commit(), so writes
    are visible to later queries in the same session without needing a
    commit boundary between requests in a test)."""
    from fastapi.testclient import TestClient
    from database import get_db
    from main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)
