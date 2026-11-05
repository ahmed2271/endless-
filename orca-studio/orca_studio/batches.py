"""Batches and molecules (section 7)."""
from __future__ import annotations

import io
import json
import shutil
import time
import zipfile
from pathlib import Path

from . import config, db, store
from .molecules import StructureError, parse_inp_text, parse_xyz_text, safe_name, write_xyz

TERMINAL = ("done", "failed", "skipped", "cancelled")

WORKFLOW_DEFAULTS = {
    "between": "wait_all",          # wait_all | pause | per_molecule
    "run_condition": "always",      # always | prev_success | check_fired
    "scf_retry": [],                # retry strategy ids, tried in order
    "opt_restarts": 0,              # restart unconverged optimizations from the last geometry
    "imag_fix": 0,                  # displace along imaginary modes and re-run, up to N times
    "after_failure": "skip",        # skip | stop
    "time_limit_h": None,
    "order": "list",                # list | smallest | largest
    "keep": "all",                  # all | results | minimal
    "checks": {
        "opt_converged": "fail",    # fail | warn | off
        "scf_converged": "fail",
        "imaginary": "fail",
        "imag_threshold": -30.0,
        "s2": "warn",
        "s2_max_dev": 0.1,
    },
    "scripts": [],
    "cubes": {},
}


def workflow(step: dict) -> dict:
    w = json.loads(json.dumps(WORKFLOW_DEFAULTS))
    for k, v in (step.get("workflow") or {}).items():
        if k == "checks" and isinstance(v, dict):
            w["checks"].update(v)
        elif v is not None:
            w[k] = v
    return w


def get(batch_id: int) -> dict | None:
    b = db.q1("SELECT * FROM batches WHERE id=?", (batch_id,))
    if not b:
        return None
    b["profile"] = db.uj(b.pop("profile_json"), {}) or {}
    b["released_steps"] = db.uj(b["released_steps"], [])
    b["fragments"] = db.uj(b["fragments"], {})
    b["options"] = db.uj(b["options"], {})
    return b


def molecules(batch_id: int, include_removed=False) -> list[dict]:
    rows = db.q("SELECT * FROM molecules WHERE batch_id=? %s ORDER BY order_idx, id"
                % ("" if include_removed else "AND removed=0"), (batch_id,))
    for r in rows:
        r["warnings"] = db.uj(r["warnings"], [])
    return rows


def molecule_record(mrow: dict) -> dict:
    """Molecule row -> dict used by assembly/validation (atoms from start.xyz)."""
    d = dict(mrow)
    d["atoms"] = start_atoms(mrow)
    return d


def batch_folder(b: dict) -> Path:
    return Path(b["folder"])


def mol_folder(b: dict, m: dict) -> Path:
    return batch_folder(b) / m["dirname"]


def start_xyz_path(b: dict, m: dict) -> Path:
    return mol_folder(b, m) / "start.xyz"


def start_atoms(m: dict):
    b = get(m["batch_id"])
    p = start_xyz_path(b, m)
    if p.exists():
        try:
            return parse_xyz_text(p.read_text(), m["name"])["atoms"]
        except StructureError:
            return []
    return []


def step_slug(step: dict, k: int) -> str:
    return store.slugify(step.get("slug") or step.get("name") or step.get("type") or f"step{k + 1}")


def step_dir(b: dict, m: dict, k: int) -> Path:
    steps = b["profile"].get("steps") or []
    layout = b["options"].get("layout") or config.load_settings()["folders"]["layout"]
    rel = layout.format(batch=Path(b["folder"]).name, molecule=m["dirname"], step_no=k + 1,
                        step_slug=step_slug(steps[k], k) if k < len(steps) else f"step{k + 1}")
    return Path(b["folder"]).parent / rel


def create(name: str, calc_profile_id: str | None, version: int | None, extraction_profile_id: str | None,
           root: str | None = None, kind: str = "calc", folder: str | None = None) -> dict:
    s = config.load_settings()
    if folder is None:
        base = Path(root or s["folders"]["calculations_root"]).expanduser()
        folder_p = base / safe_name(name)
        i = 2
        while folder_p.exists() and any(folder_p.iterdir()):
            folder_p = base / f"{safe_name(name)}_{i}"
            i += 1
        folder_p.mkdir(parents=True, exist_ok=True)
    else:
        folder_p = Path(folder).expanduser()
    profile = {}
    if calc_profile_id:
        profile = store.calc_profile_version(calc_profile_id, version) or {}
        if not profile:
            raise ValueError(f"calculation profile '{calc_profile_id}' v{version} not found")
        version = profile.get("version", 1)
        if not extraction_profile_id:
            extraction_profile_id = profile.get("extraction_profile")
    opts = {"layout": s["folders"]["layout"]}
    now = time.time()
    bid = db.ex(
        "INSERT INTO batches(name, kind, folder, calc_profile_id, calc_profile_version, profile_json, "
        "extraction_profile_id, status, options, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (name, kind, str(folder_p), calc_profile_id, version, db.j(profile), extraction_profile_id, "draft",
         db.j(opts), now, now))
    db.log(bid, f"Batch '{name}' created in {folder_p} with profile {calc_profile_id} v{version}")
    return get(bid)


def set_profile(batch_id: int, calc_profile_id: str, version: int | None = None):
    profile = store.calc_profile_version(calc_profile_id, version)
    if not profile:
        raise ValueError("profile not found")
    db.ex("UPDATE batches SET calc_profile_id=?, calc_profile_version=?, profile_json=?, updated=? WHERE id=?",
          (calc_profile_id, profile.get("version", 1), db.j(profile), time.time(), batch_id))


def _unique_dirname(batch_id: int, name: str) -> str:
    existing = {r["dirname"] for r in db.q("SELECT dirname FROM molecules WHERE batch_id=?", (batch_id,))}
    base = safe_name(name)
    cand, i = base, 2
    while cand in existing or cand in ("inputs", "results"):
        cand = f"{base}_{i}"
        i += 1
    return cand


def expand_uploads(files: list[tuple[str, bytes]]) -> list[tuple[str, bytes]]:
    out = []
    for fname, data in files:
        if fname.lower().endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for n in z.namelist():
                    if n.lower().endswith((".xyz", ".inp")) and not n.startswith("__MACOSX"):
                        out.append((Path(n).name, z.read(n)))
        else:
            out.append((Path(fname).name, data))
    return out


def add_molecules(batch_id: int, files: list[tuple[str, bytes]]) -> list[dict]:
    """Copy uploaded files into {batch}/inputs and register one molecule per structure file."""
    b = get(batch_id)
    s = config.load_settings()
    dc, dm = s["defaults"]["charge"], s["defaults"]["mult"]
    files = expand_uploads(files)
    inputs = batch_folder(b) / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    texts = {fn: data.decode("utf-8", errors="replace") for fn, data in files}
    referenced = set()
    for fn, t in texts.items():
        if fn.lower().endswith(".inp"):
            for ln in t.splitlines():
                parts = ln.split()
                if len(parts) >= 5 and parts[0] == "*" and parts[1].lower() == "xyzfile":
                    referenced.add(Path(parts[4].strip('"')).name)
    results = []
    order0 = (db.q1("SELECT MAX(order_idx) AS m FROM molecules WHERE batch_id=?", (batch_id,)) or {}).get("m") or 0
    for fn, t in texts.items():
        stem, ext = Path(fn).stem, Path(fn).suffix.lower()
        if ext not in (".xyz", ".inp"):
            results.append({"file": fn, "ok": False, "error": "only .xyz, .inp or .zip files"})
            continue
        if ext == ".xyz" and fn in referenced:
            dst = inputs / fn
            if not dst.exists():
                dst.write_text(t)
            continue
        try:
            if ext == ".xyz":
                rec = parse_xyz_text(t, stem, dc, dm)
                if t.count("\n") > rec["natoms"] + 3 and len(parse_xyz_text(t, stem, dc, dm, multi=True)) > 1:
                    rec["warnings"].append("File has several structures; only the first is used")
            else:
                rec = parse_inp_text(t, stem, {k: v for k, v in texts.items() if k.lower().endswith(".xyz")}, dc, dm)
        except StructureError as e:
            results.append({"file": fn, "ok": False, "error": str(e)})
            continue
        dst = inputs / fn
        n = 2
        while dst.exists() and dst.read_text(errors="replace") != t:
            dst = inputs / f"{stem}_{n}{ext}"
            n += 1
        if not dst.exists():
            dst.write_text(t)
        dirname = _unique_dirname(batch_id, stem)
        order0 += 1
        mid = db.ex(
            "INSERT INTO molecules(batch_id, name, dirname, formula, charge, mult, natoms, nelectrons, coord_type, "
            "raw_block, source_file, warnings, order_idx) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (batch_id, dirname if dirname != safe_name(stem) else stem, dirname, rec["formula"], rec["charge"],
             rec["mult"], rec["natoms"], rec["nelectrons"] + 0, rec["coord_type"], rec["raw_block"], str(dst),
             db.j(rec["warnings"]), order0))
        md = batch_folder(b) / dirname
        md.mkdir(parents=True, exist_ok=True)
        (md / "start.xyz").write_text(write_xyz(rec["atoms"], f"{rec['name']} charge={rec['charge']} mult={rec['mult']}"))
        results.append({"file": fn, "ok": True, "molecule_id": mid, "name": dirname, "warnings": rec["warnings"]})
        db.log(batch_id, f"Added {dirname} ({rec['formula']}, charge {rec['charge']}, mult {rec['mult']}) from {fn}")
    if b["status"] not in ("draft",):
        ensure_tasks(batch_id)
    return results


def update_molecule(mid: int, name=None, charge=None, mult=None):
    m = db.q1("SELECT * FROM molecules WHERE id=?", (mid,))
    if not m:
        raise ValueError("molecule not found")
    started = db.q1("SELECT 1 FROM tasks WHERE molecule_id=? AND status NOT IN ('pending','queued')", (mid,))
    if started and (charge is not None or mult is not None):
        raise ValueError("charge/multiplicity cannot change after the molecule has started")
    if charge is not None:
        ch = int(charge)
        nel = m["nelectrons"] + m["charge"] - ch
        db.ex("UPDATE molecules SET charge=?, nelectrons=? WHERE id=?", (ch, nel, mid))
    if mult is not None:
        db.ex("UPDATE molecules SET mult=? WHERE id=?", (int(mult), mid))
    if name:
        db.ex("UPDATE molecules SET name=? WHERE id=?", (name.strip(), mid))


def ensure_tasks(batch_id: int) -> None:
    b = get(batch_id)
    n = len(b["profile"].get("steps") or [])
    with db.tx() as con:
        for m in molecules(batch_id):
            for k in range(n):
                con.execute("INSERT OR IGNORE INTO tasks(batch_id, molecule_id, step_index, status, updated) "
                            "VALUES (?,?,?,?,?)", (batch_id, m["id"], k, "pending", time.time()))


def tasks(batch_id: int) -> list[dict]:
    rows = db.q("SELECT * FROM tasks WHERE batch_id=? ORDER BY molecule_id, step_index", (batch_id,))
    for r in rows:
        r["checks"] = db.uj(r["checks"], {})
        r["fired"] = db.uj(r["fired"], [])
    return rows


def set_status(batch_id: int, status: str):
    db.ex("UPDATE batches SET status=?, updated=? WHERE id=?", (status, time.time(), batch_id))


def summary(batch_id: int) -> dict:
    rows = db.q("SELECT status, COUNT(*) AS n FROM tasks WHERE batch_id=? GROUP BY status", (batch_id,))
    return {r["status"]: r["n"] for r in rows}


def remove_molecule(mid: int):
    db.ex("UPDATE molecules SET removed=1 WHERE id=?", (mid,))
    db.ex("UPDATE tasks SET status='cancelled', message='molecule removed' WHERE molecule_id=? AND status IN "
          "('pending','queued')", (mid,))


def delete_batch_record(batch_id: int):
    """Remove the batch from the database only; files on disk are left alone."""
    with db.tx() as con:
        for t in ("molecules", "tasks", "runs", "logs", "results"):
            con.execute(f"DELETE FROM {t} WHERE batch_id=?", (batch_id,))
        con.execute("DELETE FROM batches WHERE id=?", (batch_id,))


def copy_original(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
