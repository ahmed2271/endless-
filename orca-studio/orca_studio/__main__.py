"""python -m orca_studio : start the web app (host/port from Settings → Access)."""
import argparse
import os

import uvicorn

from . import config, store


def main():
    ap = argparse.ArgumentParser(description="ORCA Studio web app")
    ap.add_argument("--host", help="override the bind address")
    ap.add_argument("--port", type=int, help="override the port")
    a = ap.parse_args()
    store.seed()
    s = config.load_settings()
    host = a.host or ("0.0.0.0" if s["access"].get("mode") == "lan" else "127.0.0.1")
    port = a.port or int(s["access"].get("port") or 8080)
    if s["access"].get("mode") == "lan" and not s["access"].get("password_hash") and not a.host:
        print("LAN mode is on but no password is set: staying on 127.0.0.1. Set a password in Settings → Access.")
        host = "127.0.0.1"
    print(f"ORCA Studio: open http://{'localhost' if host in ('127.0.0.1', '0.0.0.0') else host}:{port} in your browser")
    uvicorn.run("orca_studio.main:app", host=host, port=port, log_level=os.environ.get("ORCA_STUDIO_LOGLEVEL", "warning"),
                workers=1)


if __name__ == "__main__":
    main()
