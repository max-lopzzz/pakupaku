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
