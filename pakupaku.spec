# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the PakuPaku desktop backend + bundled React frontend.
#
# Build with:
#   pyinstaller pakupaku.spec --distpath dist-backend --workpath build
# (or `npm run build:backend`, which passes those flags for you)
#
# Requires pakupaku-frontend/build to already exist — run
# `npm run build:frontend` (or `cd pakupaku-frontend && npm run build`)
# first.

import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

# ── Paths ──────────────────────────────────────────────────────────────────────
HERE = os.path.dirname(os.path.abspath(SPEC))
FRONTEND = os.path.join(HERE, "pakupaku-frontend", "build")

if not os.path.isdir(FRONTEND):
    raise SystemExit(
        f"Frontend build not found at {FRONTEND!r} — run "
        "`npm run build:frontend` first."
    )

# ── Analysis ───────────────────────────────────────────────────────────────────
a = Analysis(
    [os.path.join(HERE, "backend_entry.py")],
    pathex=[HERE],
    binaries=[],
    datas=[
        # Bundle the compiled React app
        (FRONTEND, "frontend_build"),
    ],
    hiddenimports=[
        # uvicorn internals
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        # fastapi / starlette
        "fastapi",
        "starlette",
        "starlette.middleware.cors",
        "starlette.staticfiles",
        "starlette.responses",
        # sqlalchemy async + sqlite (the desktop build's database)
        "sqlalchemy.ext.asyncio",
        "sqlalchemy.dialects.sqlite",
        "aiosqlite",
        # auth / crypto
        "passlib.handlers.bcrypt",
        "passlib.handlers.pbkdf2",
        "jose",
        "jose.jwt",
        # email
        "aiosmtplib",
        # httpx for USDA calls
        "httpx",
        # misc
        "dotenv",
        "email_validator",
        "anyio",
        "anyio._backends._asyncio",
        "sniffio",
    ],
    excludes=[
        "alembic",
        "asyncpg",
        "psycopg2",
        "psycopg2-binary",
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "PIL",
        "test",
        "unittest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="pakupaku-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # must stay True — Electron reads PAKUPAKU_PORT off stdout
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="pakupaku-backend",
)
