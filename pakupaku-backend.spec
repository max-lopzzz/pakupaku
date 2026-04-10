# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['backend_entry.py'],
    pathex=['.'],
    binaries=[],
    datas=[
    ('pakupaku-frontend/build', 'frontend'),
    ],
    hiddenimports=[
        # passlib
        'passlib.handlers.bcrypt',
        'passlib.handlers.sha2_crypt',
        'passlib.handlers.pbkdf2',
        'passlib.handlers.scrypt',
        'passlib.handlers.des_crypt',
        'passlib.handlers.md5_crypt',
        'passlib.handlers.misc',
        # bcrypt
        'bcrypt',
        # uvicorn
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        # sqlalchemy + async
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.ext.asyncio',
        # aiosqlite
        'aiosqlite',
        'aiosqlite.connection',
        'aiosqlite.context',
        'aiosqlite.cursor',
        'aiosqlite.pool',
        # anyio
        'anyio',
        'anyio._backends._asyncio',
        'anyio._backends._trio',
        # email
        'email_validator',
        # multipart (FastAPI file uploads)
        'multipart',
        'python_multipart',
        # jose (JWT tokens)
        'jose',
        'jose.jwt',
        'jose.exceptions',
        'jose.constants',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='pakupaku-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='pakupaku-backend',
)
