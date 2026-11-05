"""FastAPI application: REST API + static single-page frontend."""
from __future__ import annotations

import copy
import io
import mimetypes
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, assemble, auth, batches, config, db, store, tools, validate
from .runner import RUNNER


@asynccontextmanager
async def lifespan(app):
    store.seed()
    db.init()
    try:
        mpi = tools.autofill_openmpi()
        if mpi:
            db.log(None, f"OpenMPI folder was not set: found and saved {mpi}")
            db.notify(f"OpenMPI found automatically: {mpi} (check it in Settings)")
    except Exception as e:  # never block start-up
        db.log(None, f"OpenMPI auto-detection failed: {e}", "warning")
    if os.environ.get("ORCA_STUDIO_NO_RUNNER") != "1":
        RUNNER.start()
    yield
    RUNNER.stop()


app = FastAPI(title="ORCA Studio", version=__version__, lifespan=lifespan)
app.middleware("http")(auth.middleware)


def err(msg: str, code: int = 400):
    raise HTTPException(status_code=code, detail=msg)


# =========================================================================== status
@app.get("/api/status")
def api_status():
    st = RUNNER.status()
    st["notifications"] = db.q1("SELECT COUNT(*) AS n FROM notifications WHERE seen=0")["n"]
    st["version"] = __version__
    st["time"] = time.time()
    return st


@app.get("/api/notifications")
def api_notifications(limit: int = 50):
    return db.q("SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,))


@app.post("/api/notifications/seen")
def api_notifications_seen():
    db.ex("UPDATE notifications SET seen=1 WHERE seen=0")
    return {"ok": True}


# =========================================================================== settings
@app.get("/api/settings")
def api_settings():
    s = config.load_settings()
    s["access"] = {k: v for k, v in s["access"].items() if k != "password_hash"} | {
        "password_set": bool(config.load_settings()["access"].get("password_hash"))}
    return {"settings": s, "studio_dir": str(config.studio_dir()), "detected_cores": config.detect_cores(),
            "detected_memory_mb": config.detect_memory_mb(),
            "derived": {k: config.utility_path(k) for k in ("orca_2mkl", "orca_plot", "orca_vpot", "orca_chelpg",
                                                            "orca_pltvib")} | {"openmpi_lib": config.mpi_lib()}}


@app.put("/api/settings")
def api_settings_save(data: dict = Body(...)):
    cur = config.load_settings()
    new = data.get("settings", data)
    acc = new.get("access", {})
    pw = acc.pop("new_password", None)
    acc.pop("password_set", None)
    acc["password_hash"] = cur["access"].get("password_hash", "")
    if pw:
        acc["password_hash"] = auth.hash_password(pw)
    new["access"] = acc
    saved = config.save_settings(new)
    RUNNER.poke()
    return {"ok": True, "restart_needed": saved["access"]["mode"] != cur["access"]["mode"] or
            saved["access"]["port"] != cur["access"]["port"]}


@app.post("/api/settings/test")
def api_settings_test(data: dict = Body(...)):
    return tools.test_program(data["key"])


@app.post("/api/settings/autodetect")
def api_autodetect():
    return tools.autodetect()


@app.post("/api/settings/testjob")
def api_testjob():
    return tools.run_test_job()


@app.get("/api/settings/backup")
def api_backup():
    data = store.export_zip()
    name = f"orca_studio_backup_{time.strftime('%Y%m%d')}.zip"
    return Response(data, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.post("/api/settings/restore")
async def api_restore(file: UploadFile = File(...)):
    written = store.import_zip(await file.read())
    return {"ok": True, "files": written}


@app.post("/api/settings/studio_dir")
def api_studio_dir(data: dict = Body(...)):
    config.set_studio_dir(data["path"])
    store.seed()
    db.reset_connection()
    db.init()
    return {"ok": True, "studio_dir": str(config.studio_dir()), "note": "Restart the service to use the new folder."}


@app.get("/api/verify")
def api_verify_state():
    from . import verify
    st = dict(verify.STATE)
    if not st["results"]:
        st["results"] = db.kv_get("verify_results", [])
    st["checks"] = [{"id": c, "title": t} for c, t in verify.CHECKS]
    return st


@app.post("/api/verify/run")
def api_verify_run(data: dict = Body(default={})):
    from . import verify
    if verify.STATE["running"]:
        err("checks are already running")
    verify.start_background(data.get("only") or None)
    return {"ok": True}


# =========================================================================== libraries & columns
@app.get("/api/libraries")
def api_libraries(full: bool = False):
    libs = store.all_libraries()
    if full:
        return libs
    return [{"id": k, "label": v["label"], "count": len(v["entries"])} for k, v in libs.items()]


@app.get("/api/libraries/{list_id}")
def api_library(list_id: str):
    lib = store.get_library(list_id)
    if not lib:
        err("library not found", 404)
    return lib


@app.put("/api/libraries/{list_id}")
def api_library_save(list_id: str, lib: dict = Body(...)):
    lib["id"] = list_id
    try:
        return store.save_library(lib)
    except ValueError as e:
        err(str(e))


@app.post("/api/libraries")
def api_library_new(data: dict = Body(...)):
    lid = store.safe_id(data.get("id") or data.get("label"))
    if store.get_library(lid):
        err("a list with this id exists")
    return store.save_library({"id": lid, "label": data.get("label") or lid, "entries": []})


@app.post("/api/libraries/{list_id}/entries")
def api_library_add(list_id: str, entry: dict = Body(...)):
    return store.add_entry(list_id, entry)


@app.get("/api/columns")
def api_columns():
    return store.columns()


@app.put("/api/columns/{cid}")
def api_column_save(cid: str, col: dict = Body(...)):
    col["id"] = cid
    old = store.get_item("columns", cid)
    if old and old.get("builtin"):
        col["builtin"] = True
    return store.save_item("columns", col)


@app.post("/api/columns")
def api_column_new(col: dict = Body(...)):
    col["id"] = store.unique_id("columns", col.get("id") or col.get("label") or "column")
    col.setdefault("type", "text")
    col.setdefault("applies_to", ["all"])
    col.setdefault("default", "")
    col.setdefault("slot", "extras")
    return store.save_item("columns", col)


@app.delete("/api/columns/{cid}")
def api_column_delete(cid: str):
    try:
        store.delete_item("columns", cid)
    except ValueError as e:
        err(str(e))
    return {"ok": True}


# =========================================================================== calc profiles
def new_profile(name: str) -> dict:
    default_layout = db.kv_get("default_layout") or [{"column": "method"}, {"column": "basis"}]
    s = config.load_settings()
    return {"name": name, "description": "", "columns": default_layout, "defaults": {},
            "resources": {"nprocs": s["resources"]["default_nprocs"], "maxcore": s["resources"]["default_maxcore"]},
            "extraction_profile": "standard",
            "steps": []}


@app.get("/api/calc_profiles")
def api_profiles():
    out = []
    for p in store.list_items("calc_profiles"):
        out.append({"id": p["id"], "name": p.get("name", p["id"]), "version": p.get("version", 1),
                    "description": p.get("description", ""), "steps": [s.get("name") for s in p.get("steps") or []],
                    "builtin": p.get("builtin", False), "saved_at": p.get("saved_at"), "hidden": p.get("hidden", False)})
    return out


@app.get("/api/calc_profiles/{pid}")
def api_profile(pid: str, version: int | None = None):
    p = store.calc_profile_version(pid, version)
    if not p:
        err("profile not found", 404)
    p = copy.deepcopy(p)
    p["id"] = pid
    p["versions"] = store.calc_profile_versions(pid)
    return p


@app.post("/api/calc_profiles")
def api_profile_new(data: dict = Body(...)):
    name = data.get("name") or "New profile"
    p = data.get("profile") or new_profile(name)
    p["name"] = name
    p["id"] = store.unique_id("calc_profiles", name)
    p.pop("version", None)
    p.pop("builtin", None)
    return store.save_calc_profile(p)


@app.put("/api/calc_profiles/{pid}")
def api_profile_save(pid: str, p: dict = Body(...), mode: str = "overwrite"):
    """mode=overwrite (default): change this profile in place; mode=new_version: keep the old version."""
    p["id"] = pid
    p.pop("versions", None)
    if mode not in ("overwrite", "new_version"):
        err("mode must be overwrite or new_version")
    return store.save_calc_profile(p, mode)


@app.get("/api/calc_profiles/{pid}/batches")
def api_profile_batches(pid: str):
    """Batches that ran with this profile (they keep their own copy of it)."""
    return db.q("SELECT id, name, calc_profile_version AS version, status FROM batches WHERE calc_profile_id=? ORDER BY id", (pid,))


@app.delete("/api/calc_profiles/{pid}")
def api_profile_delete(pid: str):
    """Delete a profile (moved to .trash). Batches that used it keep their own copy."""
    if not store.get_item("calc_profiles", pid):
        err("profile not found", 404)
    store.delete_item("calc_profiles", pid, allow_builtin=True)
    return {"ok": True}


@app.post("/api/calc_profiles/default_layout")
def api_default_layout(data: dict = Body(...)):
    db.kv_set("default_layout", data.get("columns") or [])
    return {"ok": True}


@app.post("/api/preview")
def api_preview(data: dict = Body(...)):
    """Live input preview for an (unsaved) profile. Byte-identical to the file that will be written."""
    p = data["profile"]
    i = int(data.get("step_index", 0))
    mol = data.get("molecule")
    if data.get("molecule_id"):
        m = db.q1("SELECT * FROM molecules WHERE id=?", (data["molecule_id"],))
        mol = {"charge": m["charge"], "mult": m["mult"], "name": m["name"]} if m else None
    if not p.get("steps"):
        return {"text": "", "warnings": ["no steps"]}
    try:
        step = p["steps"][i]
        sub = None
        cat = assemble.Catalog()
        st = cat.step_type(step.get("type"))
        if st.get("kind") == "dscf":
            sub = data.get("subjob") or "es"
        r = assemble.assemble(p, i, mol, catalog=cat, subjob=sub,
                              gbw="previous.gbw" if sub == "es" else None)
        return {"text": r["text"], "warnings": r["warnings"], "manual": r["manual"], "nprocs": r["nprocs"],
                "maxcore": r["maxcore"], "subjob": sub}
    except Exception as e:
        return {"text": "", "warnings": [f"cannot assemble: {e}"]}


@app.post("/api/manual_template")
def api_manual_template(data: dict = Body(...)):
    return {"text": assemble.manual_template(data["profile"], int(data.get("step_index", 0)))}


@app.post("/api/validate")
def api_validate(data: dict = Body(...)):
    p = data["profile"]
    mols = None
    if data.get("batch_id"):
        mols = [batches.molecule_record(m) for m in batches.molecules(int(data["batch_id"]))]
    ep = store.get_item("extraction_profiles", data.get("extraction_profile") or p.get("extraction_profile") or "")
    return validate.validate(p, mols, ep)


@app.post("/api/calc_profiles/{pid}/fix")
def api_profile_fix(pid: str, data: dict = Body(...)):
    """Apply a validation 'fix' (e.g. add MBIS to a step) and save as a new version."""
    p = store.get_item("calc_profiles", pid)
    if not p:
        err("profile not found", 404)
    fix = data["fix"]
    if fix.get("action") == "add_value":
        step = p["steps"][int(fix["step"])]
        vals = step.setdefault("values", {})
        col = store.columns().get(fix["column"], {})
        if col.get("multi"):
            cur = vals.get(fix["column"]) or []
            if not isinstance(cur, list):
                cur = [cur] if cur else []
            if fix["value"] not in cur:
                cur.append(fix["value"])
            vals[fix["column"]] = cur
        else:
            vals[fix["column"]] = fix["value"]
        if not any(c.get("column") == fix["column"] for c in p.get("columns") or []):
            p.setdefault("columns", []).append({"column": fix["column"]})
    elif fix.get("action") == "add_keyword":
        step = p["steps"][int(fix["step"])]
        step["extra_keywords"] = ((step.get("extra_keywords") or "") + " " + fix["keyword"]).strip()
    return store.save_calc_profile(p)


# =========================================================================== generic items
@app.get("/api/items/{kind}")
def api_items(kind: str):
    if kind not in store.KINDS:
        err("unknown kind", 404)
    return store.list_items(kind)


@app.get("/api/items/{kind}/{item_id}")
def api_item(kind: str, item_id: str):
    d = store.get_item(kind, item_id)
    if not d:
        err("not found", 404)
    return d


@app.put("/api/items/{kind}/{item_id}")
def api_item_save(kind: str, item_id: str, data: dict = Body(...)):
    data["id"] = item_id
    old = store.get_item(kind, item_id)
    if old and old.get("builtin"):
        data["builtin"] = True
        data["edited"] = True          # never replaced by a newer starter version
    return store.save_item(kind, data)


@app.post("/api/items/{kind}")
def api_item_new(kind: str, data: dict = Body(...)):
    data["id"] = store.unique_id(kind, data.get("id") or data.get("name") or kind)
    data.pop("builtin", None)
    return store.save_item(kind, data)


@app.delete("/api/items/{kind}/{item_id}")
def api_item_delete(kind: str, item_id: str):
    try:
        store.delete_item(kind, item_id)
    except ValueError as e:
        err(str(e))
    return {"ok": True}


# =========================================================================== batches
def batch_view(bid: int) -> dict:
    b = batches.get(bid)
    if not b:
        err("batch not found", 404)
    mols = batches.molecules(bid)
    tasks = batches.tasks(bid)
    by = {(t["molecule_id"], t["step_index"]): t for t in tasks}
    for m in mols:
        m["tasks"] = [by.get((m["id"], k)) for k in range(len(b["profile"].get("steps") or []))]
    b["molecules"] = mols
    b["summary"] = batches.summary(bid)
    b["steps"] = [{"name": s.get("name"), "type": s.get("type"), "workflow": batches.workflow(s)}
                  for s in b["profile"].get("steps") or []]
    return b


@app.get("/api/batches")
def api_batches():
    out = []
    for b in db.q("SELECT id, name, kind, folder, calc_profile_id, calc_profile_version, extraction_profile_id, "
                  "status, created, updated FROM batches ORDER BY id DESC"):
        b["summary"] = batches.summary(b["id"])
        b["molecules"] = db.q1("SELECT COUNT(*) AS n FROM molecules WHERE batch_id=? AND removed=0", (b["id"],))["n"]
        out.append(b)
    return out


@app.post("/api/batches")
def api_batch_new(data: dict = Body(...)):
    try:
        b = batches.create(data.get("name") or "batch", data.get("calc_profile_id"), data.get("version"),
                           data.get("extraction_profile_id"), data.get("root") or None)
    except ValueError as e:
        err(str(e))
    return batch_view(b["id"])


@app.get("/api/batches/{bid}")
def api_batch(bid: int):
    return batch_view(bid)


@app.patch("/api/batches/{bid}")
def api_batch_patch(bid: int, data: dict = Body(...)):
    b = batches.get(bid)
    if not b:
        err("batch not found", 404)
    if "name" in data:
        db.ex("UPDATE batches SET name=? WHERE id=?", (data["name"], bid))
    if "extraction_profile_id" in data:
        db.ex("UPDATE batches SET extraction_profile_id=? WHERE id=?", (data["extraction_profile_id"], bid))
    if "fragments" in data:
        db.ex("UPDATE batches SET fragments=? WHERE id=?", (db.j(data["fragments"]), bid))
    if "options" in data:
        o = b["options"]
        o.update(data["options"])
        db.ex("UPDATE batches SET options=? WHERE id=?", (db.j(o), bid))
    if "calc_profile_id" in data:
        if b["status"] != "draft":
            err("the profile can only change before the batch runs")
        try:
            batches.set_profile(bid, data["calc_profile_id"], data.get("version"))
        except ValueError as e:
            err(str(e))
    return batch_view(bid)


def _protected(path: Path) -> str | None:
    """Folders the app must never delete, whatever is asked."""
    path = path.resolve()
    s = config.load_settings()
    never = [Path("/"), Path.home(), Path(s["folders"]["calculations_root"]).expanduser(), config.studio_dir(),
             config.PACKAGE_DIR.parent]
    for n in never:
        n = n.resolve()
        if path == n or path in n.parents:
            return f"{path} is (or contains) {n}"
    if len(path.parts) < 3:
        return f"{path} is too close to the top of the disk"
    return None


@app.delete("/api/batches/{bid}")
def api_batch_delete(bid: int, delete_files: bool = False):
    """Remove a batch from the app; with delete_files=1 also delete its folder on disk."""
    import shutil
    b = batches.get(bid)
    if not b:
        err("batch not found", 404)
    if any(j.batch_id == bid for j in RUNNER.jobs.values()):
        err("this batch still has running jobs: cancel it first")
    folder = Path(b["folder"])
    if delete_files:
        if b["kind"] == "external":
            err("this batch is an analysed folder of your own .out files; ORCA Studio never deletes those")
        why = _protected(folder)
        if why:
            err(f"refusing to delete: {why}")
    batches.delete_batch_record(bid)
    if delete_files and folder.exists():
        shutil.rmtree(folder)
        db.log(None, f"Batch '{b['name']}' deleted together with its folder {folder}", "warning")
        return {"ok": True, "note": f"Batch and folder {folder} deleted."}
    return {"ok": True, "note": f"Removed from the list. Files in {folder} were kept."}


@app.delete("/api/file")
def api_file_delete(path: str):
    """Delete a file or folder inside a batch folder (from the Files tab)."""
    import shutil
    p = Path(path).expanduser().resolve()
    owners = [b for b in db.q("SELECT id, kind, folder FROM batches")
              if p == Path(b["folder"]).resolve() or Path(b["folder"]).resolve() in p.parents]
    if not owners or not p.exists():
        err("only files inside a batch folder can be deleted here", 403)
    if any(b["kind"] == "external" for b in owners):
        err("this is an analysed folder of your own .out files; ORCA Studio never deletes those", 403)
    if any(p == Path(b["folder"]).resolve() for b in owners):
        err("to delete the whole batch folder, delete the batch (Batches list)")
    for j in RUNNER.jobs.values():
        t = db.q1("SELECT step_dir FROM tasks WHERE id=?", (j.task["id"],))
        sd = Path(t["step_dir"]).resolve() if t and t["step_dir"] else None
        if sd and (sd == p or p in sd.parents or sd in p.parents):
            err("a running job uses this folder")
    why = _protected(p)
    if why:
        err(f"refusing to delete: {why}")
    if p.is_dir():
        shutil.rmtree(p)
    else:
        p.unlink()
    return {"ok": True}


@app.post("/api/batches/{bid}/upload")
async def api_upload(bid: int, files: list[UploadFile] = File(...)):
    if not batches.get(bid):
        err("batch not found", 404)
    data = [(f.filename, await f.read()) for f in files]
    return batches.add_molecules(bid, data)


@app.patch("/api/molecules/{mid}")
def api_molecule_patch(mid: int, data: dict = Body(...)):
    try:
        batches.update_molecule(mid, data.get("name"), data.get("charge"), data.get("mult"))
    except ValueError as e:
        err(str(e))
    return db.q1("SELECT * FROM molecules WHERE id=?", (mid,))


@app.delete("/api/molecules/{mid}")
def api_molecule_delete(mid: int):
    batches.remove_molecule(mid)
    return {"ok": True}


@app.get("/api/molecules/{mid}/xyz")
def api_molecule_xyz(mid: int, step: int | None = None):
    """Latest geometry of a molecule (or the geometry of one step)."""
    from .runner import base_name
    m = db.q1("SELECT * FROM molecules WHERE id=?", (mid,))
    if not m:
        err("not found", 404)
    b = batches.get(m["batch_id"])
    if b["kind"] == "external":
        from .molecules import write_xyz
        from .parsers.orca_out import OrcaOut
        g = OrcaOut.from_file(m["source_file"]).final_geometry
        return PlainTextResponse(write_xyz(g or [], m["name"]))
    n = len(b["profile"].get("steps") or [])
    order = range(n - 1, -1, -1) if step is None else [step]
    for k in order:
        t = db.q1("SELECT * FROM tasks WHERE molecule_id=? AND step_index=?", (mid, k))
        if t and t["step_dir"]:
            for c in (Path(t["step_dir"]) / f"{base_name(m)}.xyz", Path(t["step_dir"]) / "input.xyz"):
                if c.exists() and c.stat().st_size:
                    return PlainTextResponse(c.read_text())
    p = batches.start_xyz_path(b, m)
    return PlainTextResponse(p.read_text() if p.exists() else "0\n\n")


@app.post("/api/batches/{bid}/validate")
def api_batch_validate(bid: int):
    b = batches.get(bid)
    mols = [batches.molecule_record(m) for m in batches.molecules(bid)]
    ep = store.get_item("extraction_profiles", b["extraction_profile_id"] or "") if b["extraction_profile_id"] else None
    return validate.validate(b["profile"], mols, ep)


@app.post("/api/batches/{bid}/run")
def api_batch_run(bid: int, data: dict = Body(default={})):
    b = batches.get(bid)
    if not b:
        err("batch not found", 404)
    if not batches.molecules(bid):
        err("add molecules first")
    if not b["profile"].get("steps"):
        err("choose a calculation profile first")
    if not data.get("force"):
        issues = api_batch_validate(bid)
        errors = [i for i in issues if i["level"] == "error"]
        if errors:
            return JSONResponse({"ok": False, "issues": issues}, status_code=409)
    RUNNER.run_batch(bid)
    return {"ok": True}


def _batch_action(bid: int, action: str):
    if not batches.get(bid):
        err("batch not found", 404)
    if action == "retry":
        return {"ok": True, "retried": RUNNER.retry_failed(bid)}
    {"pause": RUNNER.pause, "resume": RUNNER.resume, "cancel": RUNNER.cancel,
     "continue": RUNNER.continue_review}[action](bid)
    return {"ok": True}


def _make_action(action: str):
    def endpoint(bid: int):
        return _batch_action(bid, action)
    return endpoint


for _action in ("pause", "resume", "cancel", "retry", "continue"):
    app.add_api_route(f"/api/batches/{{bid}}/{_action}", _make_action(_action), methods=["POST"], name=f"batch_{_action}")


@app.get("/api/batches/{bid}/log")
def api_batch_log(bid: int, after: int = 0):
    return db.q("SELECT * FROM logs WHERE batch_id=? AND id>? ORDER BY id DESC LIMIT 500", (bid, after))


@app.get("/api/batches/{bid}/runs")
def api_batch_runs(bid: int, molecule_id: int | None = None):
    sql = ("SELECT r.*, t.step_index, t.molecule_id FROM runs r JOIN tasks t ON t.id=r.task_id WHERE r.batch_id=?")
    args = [bid]
    if molecule_id:
        sql += " AND t.molecule_id=?"
        args.append(molecule_id)
    return db.q(sql + " ORDER BY r.id", args)


# =========================================================================== files
def _allowed(path: Path) -> bool:
    path = path.resolve()
    roots = [Path(b["folder"]).resolve() for b in db.q("SELECT folder FROM batches")]
    roots += [Path(b["folder"]).resolve().parent for b in db.q("SELECT folder FROM batches")]
    roots.append(config.studio_dir().resolve())
    roots.append(Path(config.load_settings()["folders"]["calculations_root"]).expanduser().resolve())
    return any(path == r or r in path.parents for r in roots)


@app.get("/api/files")
def api_files(path: str):
    p = Path(path).expanduser()
    if not _allowed(p) or not p.is_dir():
        err("folder not accessible", 403)
    out = []
    for c in sorted(p.iterdir()):
        st = c.stat()
        out.append({"name": c.name, "path": str(c), "dir": c.is_dir(), "size": st.st_size, "mtime": st.st_mtime})
    return out


@app.get("/api/file")
def api_file(path: str, download: bool = False, tail: int = 0):
    p = Path(path).expanduser()
    if not _allowed(p) or not p.is_file():
        err("file not accessible", 403)
    if tail:
        with open(p, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - tail))
            return PlainTextResponse(fh.read().decode("utf-8", errors="replace"))
    if download:
        return FileResponse(p, filename=p.name)
    mt = mimetypes.guess_type(p.name)[0] or "text/plain"
    if p.suffix in (".out", ".inp", ".xyz", ".txt", ".log", ".cube", ".hess", ".molden", ".csv"):
        mt = "text/plain"
    return FileResponse(p, media_type=mt)


# =========================================================================== queue
@app.get("/api/queue")
def api_queue():
    running = []
    for tid, j in list(RUNNER.jobs.items()):
        t = db.q1("SELECT t.*, m.name AS molecule, b.name AS batch FROM tasks t JOIN molecules m ON m.id=t.molecule_id "
                  "JOIN batches b ON b.id=t.batch_id WHERE t.id=?", (tid,))
        r = db.q1("SELECT * FROM runs WHERE task_id=? ORDER BY id DESC LIMIT 1", (tid,))
        if t:
            b = batches.get(t["batch_id"])
            t["step_name"] = b["profile"]["steps"][t["step_index"]].get("name")
            t["cores"] = j.nprocs
            t["pid"] = j.pid
            t["started"] = r["start"] if r else None
            t["out_file"] = r["out_file"] if r else None
            running.append(t)
    queued = db.q("SELECT t.*, m.name AS molecule, b.name AS batch FROM tasks t JOIN molecules m ON m.id=t.molecule_id "
                  "JOIN batches b ON b.id=t.batch_id WHERE t.status='queued' AND b.status='running' "
                  "ORDER BY t.step_index, t.id LIMIT 500")
    return {"running": running, "queued": queued, "status": RUNNER.status()}


# =========================================================================== optional modules
def _include_optional():
    import importlib

    for name in ("api_results", "api_visuals", "api_advanced"):
        try:
            mod = importlib.import_module(f".{name}", __package__)
            app.include_router(mod.router)
        except ModuleNotFoundError as e:
            if e.name and e.name.endswith(name):
                continue
            raise


_include_optional()


# =========================================================================== auth + static
@app.post("/api/login")
def api_login(data: dict = Body(...)):
    return auth.login(data.get("password", ""))


@app.post("/api/logout")
def api_logout():
    return auth.logout()


app.mount("/static", StaticFiles(directory=str(config.STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(config.STATIC_DIR / "index.html")


@app.get("/login")
def login_page():
    return FileResponse(config.STATIC_DIR / "login.html")
