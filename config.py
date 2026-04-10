"""
config.py
---------
Loads environment variables for PakuPaku.
All sensitive values live in .env and are never committed to git.
"""

from dotenv import load_dotenv
import os

load_dotenv()

# ── Desktop mode flag ─────────────────────────
# Set PAKUPAKU_DESKTOP=1 to run in fully offline / SQLite mode.
# This is used by the Electron desktop build.
DESKTOP_MODE: bool = os.getenv("PAKUPAKU_DESKTOP", "0") == "1"

# ── USDA ──────────────────────────────────────
USDA_API_KEY = os.getenv("USDA_API_KEY")

# ── Database ──────────────────────────────────
if DESKTOP_MODE:
    # PAKUPAKU_DB_PATH is set by the Electron main process to the
    # OS userData directory so data survives app updates.
    _db_path = os.getenv("PAKUPAKU_DB_PATH", "pakupaku.db")
    DATABASE_URL = f"sqlite+aiosqlite:///{_db_path}"
else:
    DATABASE_URL = os.getenv("DATABASE_URL")

# ── Auth ──────────────────────────────────────
# Generate a strong secret with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY                  = os.getenv("SECRET_KEY", "changeme")
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))
# Default: 7 days. Adjust as needed.

# ── Email (SMTP) ───────────────────────────────
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", SMTP_USER)
FRONTEND_URL  = os.getenv("FRONTEND_URL", "http://localhost:3000")
