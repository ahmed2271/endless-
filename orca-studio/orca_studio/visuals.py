"""Visual outputs (section 11): orbital / density / ESP cubes, MEP surfaces and their extrema."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from . import batches, config, db, store, tools
from .extraction import load_out
from .parsers.aux_files import read_cube, surface_extrema

LABEL_RX = re.compile(r"^(HOMO|LUMO)(?:([+-])(\d+))?$", re.I)


def step_paths(m: dict, k: int) -> tuple[Path, str]:
    from .runner import base_name
    t = db.q1("SELECT * FROM tasks WHERE molecule_id=? AND step_index=?", (m["id"], k))
    if not t or not t["step_dir"]:
        raise ValueError("this step has not run")
    return Path(t["step_dir"]), base_name(m)


def last_step_with_gbw(m: dict) -> int | None:
    from .runner import base_name
    for t in db.q("SELECT * FROM tasks WHERE molecule_id=? AND status='done' ORDER BY step_index DESC", (m["id"],)):
        if t["step_dir"] and (Path(t["step_dir"]) / f"{base_name(m)}.gbw").exists():
            return t["step_index"]
    return None


def orbital_info(m: dict, k: int) -> dict:
    sd, base = step_paths(m, k)
    o = load_out(sd / f"{base}.out")
    if not o or not o.orbitals:
        raise ValueError("no orbital energies in this step's output")
    info = {"restricted": o.orbitals["restricted"], "spins": {}}
    for spin in (["alpha"] if o.orbitals["restricted"] else ["alpha", "beta"]):
        hl = o.homo_lumo(spin)
        orbs = o.orbitals[spin]
        h_idx = hl["homo"]["index"] if hl["homo"] else None
        near = [x for x in orbs if h_idx is not None and h_idx - 8 <= x["index"] <= h_idx + 9]
        info["spins"][spin] = {"homo": h_idx, "lumo": hl["lumo"]["index"] if hl["lumo"] else None,
                               "orbitals": [dict(x, label=label_for(x["index"], h_idx)) for x in near]}
    info["gbw"] = (sd / f"{base}.gbw").exists()
    info["states"] = [{"state": s["state"], "mult": s["mult"], "energy_ev": s["energy_ev"], "fosc": s["fosc"]}
                      for s in (o.excited_states or [])]
    return info


def label_for(idx: int, homo: int | None) -> str:
    if homo is None:
        return str(idx)
    if idx <= homo:
        return "HOMO" if idx == homo else f"HOMO-{homo - idx}"
    return "LUMO" if idx == homo + 1 else f"LUMO+{idx - homo - 1}"


def resolve_label(label: str, homo: int) -> int:
    """'HOMO-2' -> index; orbital numbers in ORCA start at 0 [VERIFY, Appendix D check 7]."""
    if str(label).isdigit():
        return int(label)
    m = LABEL_RX.match(label.strip())
    if not m:
        raise ValueError(f"cannot read orbital label '{label}'")
    base = homo if m.group(1).upper() == "HOMO" else homo + 1
    n = int(m.group(3) or 0)
    return base - n if m.group(2) == "-" else base + n


def expand_range(spec: str) -> list[str]:
    """'HOMO-3 to LUMO+3' -> ['HOMO-3', ..., 'LUMO+3']."""
    if " to " not in spec:
        return [spec]
    a, b = [x.strip() for x in spec.split(" to ", 1)]

    def rank(lbl):
        m = LABEL_RX.match(lbl)
        n = int(m.group(3) or 0)
        return -n if m.group(1).upper() == "HOMO" else 1 + n

    out = []
    for r in range(rank(a), rank(b) + 1):
        out.append("HOMO" if r == 0 else f"HOMO-{-r}" if r < 0 else "LUMO" if r == 1 else f"LUMO+{r - 1}")
    return out


def _index(sd: Path) -> dict:
    p = sd / "cubes" / "index.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _save_index(sd: Path, idx: dict):
    (sd / "cubes").mkdir(exist_ok=True)
    (sd / "cubes" / "index.json").write_text(json.dumps(idx, indent=1))


def list_cubes(m: dict, k: int) -> list[dict]:
    sd, _ = step_paths(m, k)
    idx = _index(sd)
    return [dict(v, name=n, path=str(sd / "cubes" / n)) for n, v in idx.items() if (sd / "cubes" / n).exists()]


def run_orca_plot(sd: Path, base: str, entry_id: str, fill: dict) -> Path:
    """Feed the library's menu answers to orca_plot; return the new cube file."""
    s = config.load_settings()
    exe = config.utility_path("orca_plot", s)
    if not tools.is_exec(exe):
        raise RuntimeError(f"orca_plot not found at {exe}")
    e = store.get_entry("orca_plot", entry_id)
    if not e:
        raise RuntimeError(f"no orca_plot recipe '{entry_id}' in the library")
    if e.get("hidden"):
        raise RuntimeError(f"orca_plot '{e['label']}' is disabled (ORCA checks found it does not work here)")
    answers = e["orca_text"]
    for k_, v in fill.items():
        answers = answers.replace("{" + k_ + "}", str(v))
    before = {p.name: p.stat().st_mtime for p in sd.glob("*.cube")}
    r = subprocess.run([exe, f"{base}.gbw", "-i"], cwd=sd, input=answers, capture_output=True, text=True,
                       timeout=1800, env=tools.build_env(s))
    new = [p for p in sd.glob("*.cube") if p.name not in before or p.stat().st_mtime > before[p.name]]
    if not new:
        (sd / "cubes").mkdir(exist_ok=True)
        (sd / "cubes" / f"orca_plot_{entry_id}.log").write_text(r.stdout + r.stderr)
        raise RuntimeError(f"orca_plot wrote no cube (see cubes/orca_plot_{entry_id}.log)")
    return max(new, key=lambda p: p.stat().st_mtime)


def make_cube(m: dict, k: int, kind: str, grid: int = 80, label: str | None = None, operator: int = 0,
              state: int | None = None, force: bool = False) -> dict:
    """kind: mo | density | spin_density | esp | tddft_difference | tddft_transition."""
    sd, base = step_paths(m, k)
    if not (sd / f"{base}.gbw").exists():
        raise ValueError("the .gbw file of this step was not kept")
    spin = "b" if operator else "a"
    fill = {"grid": grid, "operator": operator}
    if kind == "mo":
        o = load_out(sd / f"{base}.out")
        hl = o.homo_lumo("beta" if operator else "alpha")
        idx = resolve_label(label or "HOMO", hl["homo"]["index"])
        fill["index"] = idx
        name = f"{label_for(idx, hl['homo']['index'])}_{spin}_g{grid}.cube"
    elif kind in ("tddft_difference", "tddft_transition"):
        fill["state"] = int(state or 1)
        name = f"{'diffdens' if kind == 'tddft_difference' else 'transdens'}_s{fill['state']}_g{grid}.cube"
    else:
        name = f"{kind}_g{grid}.cube"
    idx = _index(sd)
    target = sd / "cubes" / name
    if target.exists() and not force:
        return dict(idx.get(name, {}), name=name, path=str(target), cached=True)
    produced = run_orca_plot(sd, base, kind, fill)
    target.parent.mkdir(exist_ok=True)
    shutil.move(str(produced), target)
    idx[name] = {"kind": kind, "grid": grid, "label": label, "operator": operator, "state": state,
                 "index": fill.get("index"), "created": time.time()}
    _save_index(sd, idx)
    return dict(idx[name], name=name, path=str(target))


def make_mep(m: dict, k: int, grid: int = 80, iso: float = 0.001, force: bool = False) -> dict:
    """Density + ESP cubes on the same grid, then V_min/V_max on the isosurface."""
    sd, base = step_paths(m, k)
    s = config.load_settings()
    esp_entry = store.get_entry("orca_plot", "esp") or {}
    idx = _index(sd)
    dens = make_cube(m, k, "density", grid, force=force)
    esp_name = f"mep_esp_g{grid}.cube"
    esp_path = sd / "cubes" / esp_name
    route = None
    if not esp_path.exists() or force:
        errors = []
        mep_path = s.get("script_paths", {}).get("mep")
        if mep_path:
            sc = store.get_item("scripts", "mep") or {"id": "mep", "name": "mep.py", "command": "{python} {script} {basename} {npoints} {nprocs}",
                                                       "outputs": [{"glob": "{basename}_mep.cube", "type": "cube", "role": "esp"}]}
            from .scripts_reg import run_script
            try:
                r = run_script(sc, sd, base, {"npoints": grid}, nprocs=int(sc.get("cores") or 2))
                cubes = [o for o in r["outputs"] if o["type"] == "cube" and o.get("role", "esp") == "esp"]
                if r["ok"] and cubes:
                    shutil.copy2(cubes[0]["path"], esp_path)
                    route = "mep.py"
                else:
                    errors.append(f"mep.py failed (see {Path(r['log']).name})")
            except RuntimeError as e:
                errors.append(str(e))
        if route is None and not esp_entry.get("hidden"):
            try:
                p = run_orca_plot(sd, base, "esp", {"grid": grid})
                shutil.move(str(p), esp_path)
                route = "orca_plot"
            except RuntimeError as e:
                errors.append(str(e))
        if route is None:
            raise RuntimeError("could not make an ESP cube: " + "; ".join(errors or ["set mep.py in Settings"]))
        idx[esp_name] = {"kind": "mep_esp", "grid": grid, "route": route, "created": time.time()}
    d = read_cube(dens["path"])
    e = read_cube(esp_path)
    if d["shape"] != e["shape"]:
        raise RuntimeError(f"density grid {d['shape']} and ESP grid {e['shape']} differ: use the same number of points")
    ext = surface_extrema(dens["path"], esp_path, iso)
    idx[esp_name] = dict(idx.get(esp_name, {}), extrema=ext, iso=iso)
    _save_index(sd, idx)
    db.kv_set(f"mep:{m['id']}:{k}", ext)
    return {"density": dens["path"], "esp": str(esp_path), "extrema": ext, "route": route or idx[esp_name].get("route")}


def batch_mep_range(batch_id: int) -> dict:
    """Fixed colour range across a batch: the largest |V| on any molecule's surface."""
    vals = []
    for m in batches.molecules(batch_id):
        for r in db.q("SELECT k, v FROM kv WHERE k LIKE ?", (f"mep:{m['id']}:%",)):
            ext = db.uj(r["v"], {})
            if ext:
                vals += [ext["vmin_au"], ext["vmax_au"]]
    if not vals:
        return {"range": None}
    return {"range": max(abs(min(vals)), abs(max(vals))), "vmin": min(vals), "vmax": max(vals)}


def auto_cubes(b, m, k, step, sd, base, cfg):
    """After a successful step: orbitals / densities / MEP requested in the step's workflow."""
    grid = int(cfg.get("grid") or 80)
    labels = []
    for spec in cfg.get("orbitals") or []:
        labels += expand_range(spec)
    for lbl in labels:
        make_cube(m, k, "mo", grid, lbl, 0)
        o = load_out(Path(sd) / f"{base}.out")
        if o and o.orbitals and not o.orbitals["restricted"]:
            make_cube(m, k, "mo", grid, lbl, 1)
    if cfg.get("densities"):
        make_cube(m, k, "density", grid)
        o = load_out(Path(sd) / f"{base}.out")
        if o and o.mult and o.mult > 1:
            make_cube(m, k, "spin_density", grid)
    if cfg.get("mep"):
        make_mep(m, k, grid)
    db.log(b["id"], f"{m['name']} step {k + 1}: cubes generated ({len(labels)} orbitals"
                    f"{', densities' if cfg.get('densities') else ''}{', MEP' if cfg.get('mep') else ''})")


# --------------------------------------------------------------------------- batch-wide jobs
JOBS: dict[int, dict] = {}


def batch_cubes(batch_id: int, items: list[dict], grid: int, step: int | None):
    state = JOBS[batch_id] = {"running": True, "done": 0, "total": 0, "errors": [], "started": time.time()}

    def work():
        mols = batches.molecules(batch_id)
        state["total"] = len(mols) * max(1, len(items))
        for m in mols:
            k = step if step is not None else last_step_with_gbw(m)
            for it in items:
                try:
                    if k is None:
                        raise ValueError("no step with a .gbw")
                    if it["kind"] == "mep":
                        make_mep(m, k, grid)
                    elif it["kind"] == "mo":
                        for lbl in expand_range(it.get("label", "HOMO")):
                            make_cube(m, k, "mo", grid, lbl, int(it.get("operator", 0)))
                    else:
                        make_cube(m, k, it["kind"], grid, state=it.get("state"))
                except Exception as e:
                    state["errors"].append(f"{m['name']}: {e}")
                state["done"] += 1
        state["running"] = False

    threading.Thread(target=work, daemon=True).start()
    return state


def save_snapshot(batch_id: int, name: str, data_url: str) -> str:
    import base64

    from .exports import export_dir
    b = batches.get(batch_id)
    d = export_dir(b) / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    fn = re.sub(r"[^A-Za-z0-9._+-]+", "_", name)
    if not fn.endswith(".png"):
        fn += ".png"
    (d / fn).write_bytes(base64.b64decode(data_url.split(",", 1)[-1]))
    return str(d / fn)
