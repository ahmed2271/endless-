"""Optional LAN access with a password (section 4, phase 5).

Requests from this computer (127.0.0.1 / ::1) never need a password. In LAN mode every other
client must log in; the session is a signed cookie valid for 7 days.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi.responses import JSONResponse, RedirectResponse

from . import config

COOKIE = "orca_studio_session"
OPEN_PATHS = ("/login", "/api/login", "/static/style.css", "/static/login.js", "/favicon.ico")
LOCAL = ("127.0.0.1", "::1", "localhost", "testclient")


def _secret() -> bytes:
    p = config.studio_dir() / ".secret"
    if not p.exists():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(secrets.token_bytes(32))
        os.chmod(p, 0o600)
    return p.read_bytes()


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 200_000)
    return f"pbkdf2${200_000}${base64.b64encode(salt).decode()}${base64.b64encode(h).decode()}"


def check_password(pw: str, stored: str) -> bool:
    try:
        _, it, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), base64.b64decode(salt), int(it))
        return hmac.compare_digest(calc, base64.b64decode(h))
    except (ValueError, TypeError):
        return False


def make_token(days: int = 7) -> str:
    exp = str(int(time.time()) + days * 86400)
    sig = hmac.new(_secret(), exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def token_ok(tok: str | None) -> bool:
    if not tok or "." not in tok:
        return False
    exp, sig = tok.split(".", 1)
    good = hmac.new(_secret(), exp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, good) and exp.isdigit() and int(exp) > time.time()


def needs_login(request) -> bool:
    s = config.load_settings()
    if s["access"].get("mode") != "lan":
        return False
    host = request.client.host if request.client else ""
    if host in LOCAL:
        return False
    return not token_ok(request.cookies.get(COOKIE))


async def middleware(request, call_next):
    path = request.url.path
    if not path.startswith(OPEN_PATHS) and needs_login(request):
        if path.startswith("/api/") or path.startswith("/ws/"):
            return JSONResponse({"detail": "login required"}, status_code=401)
        return RedirectResponse("/login")
    return await call_next(request)


def login(password: str):
    stored = config.load_settings()["access"].get("password_hash", "")
    if not stored or not check_password(password, stored):
        time.sleep(1.0)
        return JSONResponse({"ok": False, "detail": "wrong password"}, status_code=401)
    r = JSONResponse({"ok": True})
    r.set_cookie(COOKIE, make_token(), httponly=True, samesite="lax", max_age=7 * 86400)
    return r


def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE)
    return r
