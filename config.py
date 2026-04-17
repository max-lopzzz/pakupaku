"""
config.py
---------
Loads environment variables for PakuPaku.
All sensitive values live in .env and are never committed to git.
"""

import os
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _split_csv_env(name: str, default: str = "") -> List[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# ── App URLs / CORS ───────────────────────────
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")
BACKEND_PUBLIC_URL = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000").rstrip("/")
CORS_ALLOWED_ORIGINS = _split_csv_env(
    "CORS_ALLOWED_ORIGINS",
    f"{FRONTEND_URL},http://localhost:3000,http://127.0.0.1:3000",
)

# ── Spoonacular ───────────────────────────────
SPOONACULAR_API_KEY = os.getenv("SPOONACULAR_API_KEY")

# ── Database ──────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL")

# ── Auth ──────────────────────────────────────
# Generate a strong secret with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = os.getenv("SECRET_KEY", "changeme")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60 * 24 * 7))
# Default: 7 days. Adjust as needed.

# ── Email (SMTP) ──────────────────────────────
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER)
