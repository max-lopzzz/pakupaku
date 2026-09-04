"""
backend_entry.py
-----------------
Entry point for the PyInstaller-bundled desktop backend. Not used by the
hosted deployment — that runs `uvicorn main:app` directly.

Responsibilities:
  1. Set up a per-user SQLite database and a persisted SECRET_KEY under
     the OS's app-data directory (passed in by Electron as
     PAKUPAKU_USER_DATA).
  2. Set required env vars *before* importing anything from the app, so
     config.py/database.py pick them up on first import.
  3. Find a free local port, print it as PAKUPAKU_PORT=<port> (Electron's
     main process reads this off stdout to know where to connect).
  4. Run uvicorn.

Build with: pyinstaller pakupaku.spec
"""

import os
import secrets
import socket

# ─── Locate the per-user data directory ───────────────────────────────────────
# Electron passes this in (app.getPath("userData")); fall back to the
# executable's own directory for a manual/dev run.
user_data = os.environ.get("PAKUPAKU_USER_DATA", os.path.dirname(os.path.abspath(__file__)))
os.makedirs(user_data, exist_ok=True)

db_path = os.path.join(user_data, "pakupaku.db")

# ─── Persist a per-install secret key ──────────────────────────────────────────
# Generated once on first launch and reused after that, so existing JWTs
# and sessions survive app restarts.
secret_file = os.path.join(user_data, "secret.key")
if os.path.exists(secret_file):
    with open(secret_file) as f:
        secret_key = f.read().strip()
else:
    secret_key = secrets.token_hex(32)
    with open(secret_file, "w") as f:
        f.write(secret_key)

# ─── Set env vars BEFORE importing anything from the app ──────────────────────
# config.py reads these via os.getenv() at import time.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
os.environ["SECRET_KEY"] = secret_key
# USDA's own published demo key — works out of the box for light use, low
# rate limit. Users who hit the limit can set a real USDA_API_KEY
# themselves (free, instant, at https://api.data.gov/signup) before
# launching; this only fills in when they haven't.
os.environ.setdefault("USDA_API_KEY", "DEMO_KEY")

# ─── Now safe to import the app ────────────────────────────────────────────────
from main import app  # noqa: E402  (must come after the env vars above)

# ─── Create tables / migrate schema on every launch ────────────────────────────
# There's no migration tooling available to an end user running a packaged
# app, and no one to run one for them — so the desktop build creates its own
# SQLite schema directly. create_all() only creates tables that don't already
# exist, though, so an install from before some model gained a new column
# would keep failing on that column forever. _add_missing_columns() below
# closes that gap by diffing each table's live columns against the model's
# declared columns and ALTERing in whatever's missing.
import asyncio  # noqa: E402
from database import Base, engine  # noqa: E402
from sqlalchemy import text  # noqa: E402
from migrations import _migrate_fdc_to_food_id  # noqa: E402


async def _add_missing_columns(conn):
    """Additive-only schema safety net: adds columns that exist on the
    model but not in the live table. Covers nullable-column additions,
    and NOT NULL additions that carry a usable scalar default (emitted as
    `ALTER TABLE ... ADD COLUMN ... NOT NULL DEFAULT <literal>`, which
    SQLite supports) — these are the shapes of schema drift this app has
    hit in practice. A NOT NULL column with no usable default (or a
    non-scalar/computed default) still needs a real migration; if one of
    those ever ships, handle it explicitly here rather than relying on
    this loop."""
    for table in Base.metadata.sorted_tables:
        rows = (await conn.execute(text(f"PRAGMA table_info({table.name})"))).fetchall()
        existing_columns = {row[1] for row in rows}
        if not existing_columns:
            continue  # table doesn't exist yet — create_all() just made it, so it's already complete
        for column in table.columns:
            if column.name in existing_columns:
                continue
            coltype = column.type.compile(dialect=conn.dialect)
            ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {coltype}"
            if not column.nullable and column.default is not None and getattr(column.default, "is_scalar", False):
                default_arg = column.default.arg
                if default_arg is True:
                    default_sql = "1"
                elif default_arg is False:
                    default_sql = "0"
                else:
                    default_sql = repr(default_arg)
                ddl += f" NOT NULL DEFAULT {default_sql}"
            await conn.execute(text(ddl))
            if column.unique:
                index_name = f"ix_{table.name}_{column.name}"
                await conn.execute(text(
                    f"CREATE UNIQUE INDEX IF NOT EXISTS {index_name} ON {table.name} ({column.name})"
                ))


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_fdc_to_food_id(conn)      # NEW — must precede _add_missing_columns
        await _add_missing_columns(conn)


asyncio.run(_create_tables())


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


port = find_free_port()
print(f"PAKUPAKU_PORT={port}", flush=True)

import uvicorn  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
