"""
config.py
---------
Loads environment variables for PakuPaku.
All sensitive values live in .env and are never committed to git.
"""

from dotenv import load_dotenv
import os

load_dotenv()

# ── USDA ──────────────────────────────────────
USDA_API_KEY = os.getenv("USDA_API_KEY")

# ── Database ──────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

# ── Auth ──────────────────────────────────────
# Generate a strong secret with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY                  = os.getenv("SECRET_KEY", "changeme")
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))
# Default: 7 days. Adjust as needed.