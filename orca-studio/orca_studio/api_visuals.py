"""API: orbitals, cubes, MEP, snapshots, spectra data, scripts (phase 4)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Body, HTTPException

from . import batches, db, store, visuals
from .extraction import load_out, out_path_for

router = APIRouter()


def err(msg, code=400):
    raise HTTPException(status_code=code, detail=msg)


def _mol(mid):
    m = db.q1("SELECT * FROM molecules WHERE id=?", (mid,))
    if not m:
        err("molecule not found", 404)
    return m


def _step(m, step):
    if step is None or step == "":
        k = visuals.last_step_with_gbw(m)
        if k is None:
            err("no finished step with a kept .gbw file")
        return k
    return int(step)


@router.get("/api/molecules/{mid}/steps")
def mol_steps(mid: int):
    m = _mol(mid)
    from .runner import base_name
    out = []
    for t in db.q("SELECT * FROM tasks WHERE molecule_id=? ORDER BY step_index", (mid,)):
        b = batches.get(t["batch_id"])
        sd = Path(t["step_dir"]) if t["step_dir"] else None
        out.append({"step": t["step_index"], "name": b["profile"]["steps"][t["step_index"]].get("name"), "status": t["status"],
                    "gbw": bool(sd and (sd / f"{base_name(m)}.gbw").exists())})
    return out


@router.get("/api/molecules/{mid}/orbitals")
def mol_orbitals(mid: int, step: int | None = None):
    m = _mol(mid)
    try:
        return visuals.orbital_info(m, _step(m, step))
    except ValueError as e:
        err(str(e))


@router.get("/api/molecules/{mid}/cubes")
def mol_cubes(mid: int, step: int | None = None):
    m = _mol(mid)
    try:
        return visuals.list_cubes(m, _step(m, step))
    except ValueError:
        return []


@router.post("/api/molecules/{mid}/cubes")
def mol_make_cubes(mid: int, data: dict = Body(...)):
    m = _mol(mid)
    k = _step(m, data.get("step"))
    grid = int(data.get("grid") or 80)
    reqs = []
    for it in data.get("items") or []:
        if it["kind"] == "mo":
            reqs += [{"kind": "mo", "label": lbl, "operator": int(it.get("operator", 0))} for lbl in visuals.expand_range(it.get("label", "HOMO"))]
        else:
            reqs.append({"kind": it["kind"], "state": it.get("state")})
    try:
        made, errors = visuals.make_cubes(m, k, reqs, grid, force=bool(data.get("force")))
    except (ValueError, RuntimeError) as e:
        made, errors = [], [str(e)]
    return {"cubes": made, "errors": errors}


@router.post("/api/molecules/{mid}/cube_diagnose")
def mol_cube_diagnose(mid: int, data: dict = Body(default={})):
    m = _mol(mid)
    return visuals.diagnose(m, _step(m, data.get("step")))


@router.post("/api/molecules/{mid}/mep")
def mol_mep(mid: int, data: dict = Body(default={})):
    m = _mol(mid)
    try:
        return visuals.make_mep(m, _step(m, data.get("step")), int(data.get("grid") or 80), float(data.get("iso") or 0.001),
                                force=bool(data.get("force")))
    except (ValueError, RuntimeError) as e:
        err(str(e))


@router.post("/api/molecules/{mid}/chelpg")
def mol_chelpg(mid: int, data: dict = Body(default={})):
    """Post hoc CHELPG charges: orca_chelpg {basename}.gbw, without rerunning the job."""
    import subprocess
    from . import config, tools
    from .parsers.orca_out import OrcaOut
    m = _mol(mid)
    k = _step(m, data.get("step"))
    sd, base = visuals.step_paths(m, k)
    s = config.load_settings()
    exe = config.utility_path("orca_chelpg", s)
    if not tools.is_exec(exe):
        err(f"orca_chelpg not found at {exe}")
    out = sd / f"{base}.chelpg_posthoc.out"
    with open(out, "w") as fh:
        subprocess.run([exe, f"{base}.gbw"], cwd=sd, stdout=fh, stderr=subprocess.STDOUT, timeout=3600, env=tools.build_env(s))
    ch = OrcaOut.from_file(out).chelpg
    if not ch:
        err(f"orca_chelpg ran but no CHELPG table was found in {out.name}")
    from . import extraction
    extraction.extract_batch(m["batch_id"], [m["id"]])
    return {"charges": ch, "file": str(out)}


@router.get("/api/batches/{bid}/mep_range")
def mep_range(bid: int):
    return visuals.batch_mep_range(bid)


@router.post("/api/batches/{bid}/cubes")
def batch_cubes(bid: int, data: dict = Body(...)):
    st = visuals.JOBS.get(bid)
    if st and st["running"]:
        err("cube generation is already running for this batch")
    return visuals.batch_cubes(bid, data.get("items") or [], int(data.get("grid") or 80), data.get("step"))


@router.get("/api/batches/{bid}/cubes/status")
def batch_cubes_status(bid: int):
    return visuals.JOBS.get(bid) or {"running": False}


@router.get("/api/batches/{bid}/cube_overview")
def cube_overview(bid: int, name: str):
    """Path of a named cube (e.g. HOMO_a_g80.cube or mep) for every molecule, for figure grids."""
    out = []
    for m in batches.molecules(bid):
        k = visuals.last_step_with_gbw(m)
        row = {"molecule_id": m["id"], "name": m["name"], "step": k, "path": None}
        if k is not None:
            for c in visuals.list_cubes(m, k):
                if c["name"] == name:
                    row["path"] = c["path"]
            if name == "mep":
                sd, _ = visuals.step_paths(m, k)
                dens = [c for c in visuals.list_cubes(m, k) if c["kind"] == "density"]
                esp = [c for c in visuals.list_cubes(m, k) if c["kind"] == "mep_esp"]
                if dens and esp:
                    row["path"], row["esp"] = dens[0]["path"], esp[0]["path"]
        out.append(row)
    return out


@router.post("/api/batches/{bid}/snapshot")
def snapshot(bid: int, data: dict = Body(...)):
    return {"path": visuals.save_snapshot(bid, data["name"], data["png"])}


@router.get("/api/batches/{bid}/spectra_data")
def spectra_data(bid: int, step: int | None = None):
    """Excited states, IR/Raman lines and energies per molecule for the Spectra tab."""
    b = batches.get(bid)
    if not b:
        err("batch not found", 404)
    nsteps = len(b["profile"].get("steps") or []) if b["kind"] != "external" else 1
    out = []
    for m in batches.molecules(bid):
        row = {"molecule_id": m["id"], "name": m["name"], "formula": m["formula"], "states": None, "ir": None,
               "raman": None, "G": None, "E": None, "state_step": None, "ir_step": None}
        order = [step] if step is not None else list(range(nsteps - 1, -1, -1))
        for k in order:
            p = out_path_for(b, m, k)
            o = load_out(p) if p else None
            if not o:
                continue
            if row["states"] is None and o.excited_states:
                row["states"] = [{x: s[x] for x in ("state", "mult", "energy_ev", "nm", "fosc", "rotatory_strength")}
                                 for s in o.excited_states]
                row["state_step"] = k
            if row["ir"] is None and o.ir_spectrum:
                row["ir"], row["ir_step"] = o.ir_spectrum, k
            if row["raman"] is None and o.raman_spectrum:
                row["raman"] = o.raman_spectrum
            if row["G"] is None and o.thermo and o.thermo.get("total_gibbs") is not None:
                row["G"] = o.thermo["total_gibbs"]
            if row["E"] is None and o.final_energy is not None:
                row["E"] = o.final_energy
        out.append(row)
    return out


@router.post("/api/scripts/{sid}/run")
def run_script_now(sid: int | str, data: dict = Body(...)):
    from .scripts_reg import run_script
    sc = store.get_item("scripts", str(sid))
    if not sc:
        err("script not found", 404)
    m = _mol(int(data["molecule_id"]))
    k = _step(m, data.get("step"))
    sd, base = visuals.step_paths(m, k)
    try:
        r = run_script(sc, sd, base, {"npoints": data.get("npoints", sc.get("npoints", 80))})
    except RuntimeError as e:
        err(str(e))
    r["log_text"] = Path(r["log"]).read_text(errors="replace")[-5000:]
    return r
