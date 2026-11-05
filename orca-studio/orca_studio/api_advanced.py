"""API: Multiwfn recipes and record mode (phase 5)."""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import signal
import struct
import subprocess
import termios
from pathlib import Path

from fastapi import APIRouter, Body, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from . import auth, config, db, multiwfn, store, tools

router = APIRouter()


def err(msg, code=400):
    raise HTTPException(status_code=code, detail=msg)


@router.post("/api/multiwfn/record/start")
def record_start(data: dict = Body(...)):
    try:
        return multiwfn.start_record(data.get("molecule_id"), data.get("step"))
    except (ValueError, RuntimeError) as e:
        err(str(e))


@router.post("/api/multiwfn/record/upload")
async def record_upload(file: UploadFile = File(...)):
    return multiwfn.start_record(upload=(file.filename, await file.read()))


@router.get("/api/multiwfn/record/{sid}")
def record_get(sid: str):
    try:
        return multiwfn.recorded(sid)
    except ValueError as e:
        err(str(e), 404)


@router.websocket("/ws/multiwfn/record/{sid}")
async def record_ws(ws: WebSocket, sid: str):
    """A terminal in the browser: Multiwfn runs in a pseudo-terminal; every answer line is recorded."""
    s = config.load_settings()
    host = ws.client.host if ws.client else ""
    if s["access"].get("mode") == "lan" and host not in auth.LOCAL and not auth.token_ok(ws.cookies.get(auth.COOKIE)):
        await ws.close(code=4401)
        return
    sess = multiwfn.SESSIONS.get(sid)
    await ws.accept()
    if not sess:
        await ws.send_text(json.dumps({"type": "out", "data": "record session not found\r\n"}))
        await ws.close()
        return
    exe = multiwfn.exe(s)
    if not tools.is_exec(exe):
        await ws.send_text(json.dumps({"type": "out", "data": "Multiwfn is not set in Settings.\r\n"}))
        await ws.close()
        return
    multiwfn.prepare_settings_ini(Path(sess["dir"]), s)
    master, slave = os.openpty()
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", 32, 110, 0, 0))
    proc = subprocess.Popen([exe, sess["sample"]], cwd=sess["dir"], stdin=slave, stdout=slave, stderr=slave,
                            env=multiwfn.env_for(s), start_new_session=True, close_fds=True)
    os.close(slave)
    sess["pid"] = proc.pid
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def readable():
        try:
            data = os.read(master, 65536)
        except OSError:
            data = b""
        if not data:
            loop.remove_reader(master)
        queue.put_nowait(data)

    loop.add_reader(master, readable)

    async def pump():
        while True:
            data = await queue.get()
            if not data:
                break
            text = data.decode("utf-8", errors="replace")
            sess["output"] += text
            try:
                await ws.send_text(json.dumps({"type": "out", "data": text}))
            except Exception:
                break
        sess["done"] = True
        try:
            await ws.send_text(json.dumps({"type": "exit", "code": proc.poll()}))
        except Exception:
            pass

    task = asyncio.create_task(pump())
    try:
        while True:
            msg = json.loads(await ws.receive_text())
            if msg.get("type") == "in":
                multiwfn.record_input(sess, msg["data"])
                os.write(master, msg["data"].encode())
            elif msg.get("type") == "resize":
                fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", int(msg["rows"]), int(msg["cols"]), 0, 0))
            elif msg.get("type") == "stop":
                break
    except WebSocketDisconnect:
        pass
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(task, 3)
        except asyncio.TimeoutError:
            task.cancel()
        try:
            loop.remove_reader(master)
        except Exception:
            pass
        os.close(master)
        sess["done"] = True


@router.post("/api/multiwfn/recipes")
def recipe_save(data: dict = Body(...)):
    return multiwfn.save_recipe(data.get("session"), data["recipe"])


@router.post("/api/multiwfn/recipes/{rid}/retest")
def recipe_retest(rid: str):
    try:
        return multiwfn.retest(rid)
    except RuntimeError as e:
        err(str(e))


@router.post("/api/multiwfn/retest_all")
def recipe_retest_all():
    out = []
    for r in store.list_items("multiwfn_recipes"):
        try:
            out.append(multiwfn.retest(r["id"]))
        except RuntimeError as e:
            out.append({"id": r["id"], "ok": False, "message": str(e)})
    return out


@router.post("/api/multiwfn/test_rule")
def test_rule(data: dict = Body(...)):
    text = data.get("text")
    if text is None and data.get("session"):
        text = multiwfn.recorded(data["session"])["output"]
    if text is None and data.get("recipe"):
        r = store.get_item("multiwfn_recipes", data["recipe"])
        p = Path((r or {}).get("sample", {}).get("output", ""))
        text = p.read_text(errors="replace") if p.exists() else ""
    try:
        return {"value": multiwfn.parse_rule(data["rule"], text or "")}
    except Exception as e:
        return {"value": None, "error": f"{type(e).__name__}: {e}"}


@router.post("/api/multiwfn/recipes/{rid}/run")
def recipe_run(rid: str, data: dict = Body(...)):
    from .scripts_reg import ensure_molden
    from .visuals import last_step_with_gbw, step_paths
    r = store.get_item("multiwfn_recipes", rid)
    m = db.q1("SELECT * FROM molecules WHERE id=?", (int(data["molecule_id"]),))
    if not r or not m:
        err("not found", 404)
    k = data.get("step")
    k = last_step_with_gbw(m) if k in (None, "") else int(k)
    if k is None:
        err("no finished step with a .gbw")
    sd, base = step_paths(m, k)
    try:
        out = multiwfn.run_recipe(r, sd, ensure_molden(sd, base))
    except RuntimeError as e:
        err(str(e))
    text = out.read_text(errors="replace")
    return {"output": text[-20000:], "path": str(out),
            "rules": [{"label": x.get("label") or x.get("id"), "value": multiwfn.parse_rule(x, text)} for x in r.get("rules") or []]}
