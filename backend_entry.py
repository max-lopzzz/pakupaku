import os
import sys
import socket
import secrets

# ─── Locate userData directory ────────────────────────────────────────────────
user_data = os.environ.get("PAKUPAKU_USER_DATA", os.path.dirname(sys.executable))
db_path   = os.path.join(user_data, "pakupaku.db")

# ─── Persist secret key ───────────────────────────────────────────────────────
secret_file = os.path.join(user_data, "secret.key")
if os.path.exists(secret_file):
    with open(secret_file) as f:
        secret_key = f.read().strip()
else:
    secret_key = secrets.token_hex(32)
    os.makedirs(user_data, exist_ok=True)
    with open(secret_file, "w") as f:
        f.write(secret_key)

# ─── Set env vars BEFORE importing anything from your app ────────────────────
os.environ["PAKUPAKU_DESKTOP"] = "1"
os.environ["PAKUPAKU_DB_PATH"] = db_path
os.environ["SECRET_KEY"]       = secret_key
os.environ["USDA_API_KEY"]     = "uGwmyMG3VG7zPU2JPptsZUoCX0kbWZcqWGrzN2JP"

# ─── NOW safe to import app ───────────────────────────────────────────────────
from main import app  # ← moved here, after env vars are set

# ─── Find a free port ─────────────────────────────────────────────────────────
def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

port = find_free_port()
print(f"PAKUPAKU_PORT={port}", flush=True)

# ─── Start server ─────────────────────────────────────────────────────────────
import uvicorn
uvicorn.run(
    app,
    host="127.0.0.1",
    port=port,
    log_level="warning",
)