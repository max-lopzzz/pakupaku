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

# ─── Create tables on first launch ─────────────────────────────────────────────
# There's no migration tooling available to an end user running a packaged
# app, and no one to run one for them — so the desktop build creates its own
# SQLite schema directly. create_all() only creates tables that don't
# already exist, so this is a safe no-op on every launch after the first.
import asyncio  # noqa: E402
from database import Base, engine  # noqa: E402


async def _create_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


asyncio.run(_create_tables())


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


port = find_free_port()
print(f"PAKUPAKU_PORT={port}", flush=True)

import uvicorn  # noqa: E402

uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
