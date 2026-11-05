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


def orca_plot_raw(sd: Path, gbw: str, answers: str, timeout: float = 900, max_log: int = 2_000_000,
                  silent: float = 180) -> tuple[list[Path], str, str]:
    """Run 'orca_plot gbw -i' with menu answers on stdin, with a watchdog.

    orca_plot repeats its menu forever when an answer does not fit; the watchdog stops it as soon as
    its output grows beyond max_log bytes. Returns (new cube files, log text, problem or '').
    """
    s = config.load_settings()
    exe = config.utility_path("orca_plot", s)
    if not tools.is_exec(exe):
        return [], "", f"orca_plot not found at {exe}"
    before = {p.name: p.stat().st_mtime for p in sd.glob("*.cube")}
    log_path = sd / ".orca_plot_run.log"
    problem = ""
    with open(log_path, "w") as log:
        proc = subprocess.Popen([exe, gbw, "-i"], cwd=sd, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                                env=tools.build_env(s), text=True, start_new_session=True)
        try:
            proc.stdin.write(answers)
            proc.stdin.close()
        except (BrokenPipeError, OSError):
            pass
        t0 = time.time()
        last_size, last_change = 0, time.time()
        while proc.poll() is None:
            time.sleep(0.2)
            size = log_path.stat().st_size
            if size != last_size or any(p.name not in before for p in sd.glob("*.cube")):
                last_size, last_change = size, time.time()
            if time.time() - last_change > silent:
                problem = f"orca_plot printed nothing for {int(silent)} s and wrote no cube (probably waiting for an answer it did not get)"
                break
            if size > max_log:
                problem = "orca_plot kept repeating its menu: the menu answers in Libraries → orca_plot do not fit this orca_plot version"
                break
            if time.time() - t0 > timeout:
                problem = f"orca_plot did not finish within {int(timeout)} s"
                break
        if proc.poll() is None:
            from .runner import kill_tree
            kill_tree(proc.pid, grace=2)
    text = log_path.read_text(errors="replace")
    if len(text) > 60000:
        text = text[:30000] + "\n[...]\n" + text[-20000:]
    new = [p for p in sd.glob("*.cube") if p.name not in before or p.stat().st_mtime > before[p.name]]
    if not new and not problem:
        problem = "orca_plot wrote no cube"
    return new, text, problem


def run_orca_plot(sd: Path, base: str, entry_id: str, fill: dict) -> Path:
    """Feed the library's menu answers to orca_plot; return the new cube file."""
    e = store.get_entry("orca_plot", entry_id)
    if not e:
        raise RuntimeError(f"no orca_plot recipe '{entry_id}' in the library")
    if e.get("hidden"):
        raise RuntimeError(f"orca_plot '{e['label']}' is disabled (ORCA checks found it does not work here)")
    answers = e["orca_text"]
    for k_, v in fill.items():
        answers = answers.replace("{" + k_ + "}", str(v))
    new, text, problem = orca_plot_raw(sd, f"{base}.gbw", answers, timeout=600 + int(fill.get("grid", 80)) ** 3 / 2000)
    (sd / "cubes").mkdir(exist_ok=True)
    (sd / "cubes" / f"orca_plot_{entry_id}.log").write_text(text)
    if not new:
        raise RuntimeError(f"{problem} (log: cubes/orca_plot_{entry_id}.log)")
    return max(new, key=lambda p: p.stat().st_mtime)


PLOTS_KINDS = ("mo", "density", "spin_density")


def plot_input(sd: Path, base: str, items: list[dict], grid: int) -> str:
    """Input for the %plots route: the step's own input with MORead NoIter, the job keywords
    (Opt, Freq, ...) and heavy blocks (TDDFT, ...) removed, and a %plots block added."""
    src = (sd / f"{base}.inp").read_text(errors="replace").splitlines()
    strip = set()
    for lid in ("step_types", "opt_target", "opt_convergence", "hessian", "populations"):
        for e in (store.get_library(lid) or {}).get("entries", []):
            strip |= {t.lower() for t in e["orca_text"].split()}
    strip |= {"moread", "keepdens"}
    drop = set(store.text("orca_plot", "plots_drop_blocks", "tddft geom freq").lower().split()) | {"moinp", "pal", "plots"}
    out, skipping = [], False
    for line in src:
        st = line.strip()
        if skipping:
            if line.rstrip().lower() == "end" or (st.lower() == "end" and not line.startswith(" ")):
                skipping = False
            continue
        if st.startswith("%"):
            name = st[1:].split()[0].lower() if st[1:].split() else ""
            if name in drop:
                single = name == "moinp" or st.lower().endswith(" end") or (len(st.split()) > 1 and name == "maxcore")
                skipping = not single
                continue
        if st.startswith("!"):
            toks = [t for t in st[1:].split() if t.lower() not in strip]
            if not toks:
                continue
            line = "! " + " ".join(toks)
        if st.lower().startswith("* xyzfile"):
            parts = st.split()
            line = " ".join(parts[:4] + ["geom.xyz"])
        out.append(line)
    kw = store.text("orca_plot", "plots_keywords", "MORead NoIter")
    hdr = store.text("orca_plot", "plots_header", "dim1 {grid}\ndim2 {grid}\ndim3 {grid}\nFormat Gaussian_Cube").replace("{grid}", str(grid))
    lines = []
    for it in items:
        tpl = store.text("orca_plot", f"plots_{it['kind']}", "")
        lines.append(tpl.replace("{file}", it["file"]).replace("{index}", str(it.get("index", 0)))
                     .replace("{operator}", str(it.get("operator", 0))))
    moinp = store.text("assembly", "moinp", '%moinp "{gbw}"').replace("{gbw}", "orbitals.gbw")
    pal = store.text("assembly", "pal", "%pal nprocs {nprocs} end").replace("{nprocs}", "1")
    # insert our lines right after the last "!" line
    last_bang = max([i for i, ln in enumerate(out) if ln.strip().startswith("!")] or [-1])
    extra = [f"! {kw}", pal, moinp, "%plots"] + ["  " + x for x in hdr.splitlines() + lines] + ["end"]
    return "\n".join(out[:last_bang + 1] + extra + out[last_bang + 1:]) + "\n"


def run_plots_route(sd: Path, base: str, items: list[dict], grid: int) -> dict[str, Path]:
    """Make several cubes in one short ORCA run (reads the .gbw, no SCF iterations)."""
    s = config.load_settings()
    wd = sd / "cubes" / "_plot_run"
    if wd.exists():
        shutil.rmtree(wd)
    wd.mkdir(parents=True)
    shutil.copy2(sd / f"{base}.gbw", wd / "orbitals.gbw")
    geo = sd / f"{base}.xyz" if (sd / f"{base}.xyz").exists() else sd / "input.xyz"
    shutil.copy2(geo, wd / "geom.xyz")
    (wd / "plot.inp").write_text(plot_input(sd, base, items, grid))
    with open(wd / "plot.out", "w") as fh:
        try:
            subprocess.run([str(Path(s["programs"]["orca"]).expanduser()), "plot.inp"], cwd=wd, stdout=fh,
                           stderr=subprocess.STDOUT, env=tools.build_env(s), timeout=3600)
        except subprocess.TimeoutExpired:
            fh.write("\n[ORCA Studio] plot run timed out\n")
    got = {it["file"]: wd / it["file"] for it in items if (wd / it["file"]).exists()}
    if not got:
        tail = "\n".join((wd / "plot.out").read_text(errors="replace").splitlines()[-15:])
        raise RuntimeError(f"the %plots run wrote no cube (see cubes/_plot_run/plot.out). Last lines:\n{tail}")
    return got


def _spec(m, k, kind, grid, label=None, operator=0, state=None):
    """Name and orca_plot fill values for one requested cube."""
    sd, base = step_paths(m, k)
    spin = "b" if operator else "a"
    fill = {"grid": grid, "operator": operator}
    if kind == "mo":
        o = load_out(sd / f"{base}.out")
        if not o or not o.orbitals:
            raise ValueError("no orbital energies in this step's output")
        hl = o.homo_lumo("beta" if operator else "alpha")
        idx = resolve_label(label or "HOMO", hl["homo"]["index"])
        fill["index"] = idx
        name = f"{label_for(idx, hl['homo']['index'])}_{spin}_g{grid}.cube"
    elif kind in ("tddft_difference", "tddft_transition"):
        fill["state"] = int(state or 1)
        name = f"{'diffdens' if kind == 'tddft_difference' else 'transdens'}_s{fill['state']}_g{grid}.cube"
    else:
        name = f"{kind}_g{grid}.cube"
    return {"kind": kind, "name": name, "fill": fill, "label": label, "operator": operator, "state": state}


def make_cubes(m: dict, k: int, requests: list[dict], grid: int = 80, force: bool = False) -> tuple[list[dict], list[str]]:
    """Make several cubes. Tries the route that worked last time first (orca_plot or %plots)."""
    sd, base = step_paths(m, k)
    if not (sd / f"{base}.gbw").exists():
        raise ValueError("the .gbw file of this step was not kept")
    idx = _index(sd)
    done, todo, errors = [], [], []
    for rq in requests:
        try:
            sp = _spec(m, k, rq["kind"], grid, rq.get("label"), int(rq.get("operator", 0)), rq.get("state"))
        except ValueError as e:
            errors.append(f"{rq.get('label') or rq['kind']}: {e}")
            continue
        target = sd / "cubes" / sp["name"]
        if target.exists() and not force:
            done.append(dict(idx.get(sp["name"], {}), name=sp["name"], path=str(target), cached=True))
        elif sp["name"] not in [t["name"] for t in todo]:
            todo.append(sp)
    if not todo:
        return done, errors
    (sd / "cubes").mkdir(exist_ok=True)
    pref = db.kv_get("cube_route", "plots")
    order = [pref] + [r for r in ("orca_plot", "plots") if r != pref]

    def record(sp, path, route):
        target = sd / "cubes" / sp["name"]
        shutil.move(str(path), target)
        idx[sp["name"]] = {"kind": sp["kind"], "grid": grid, "label": sp["label"], "operator": sp["operator"],
                           "state": sp["state"], "index": sp["fill"].get("index"), "created": time.time(), "route": route}
        done.append(dict(idx[sp["name"]], name=sp["name"], path=str(target)))

    remaining = list(todo)
    problems = {}
    for route in order:
        if not remaining:
            break
        if route == "orca_plot":
            for sp in remaining:
                try:
                    record(sp, run_orca_plot(sd, base, sp["kind"], sp["fill"]), "orca_plot")
                    db.kv_set("cube_route", "orca_plot")
                except RuntimeError as e:
                    problems.setdefault(sp["name"], []).append(f"orca_plot: {e}")
                    if any(w in str(e) for w in ("repeating its menu", "not found", "printed nothing", "did not finish")):
                        break          # the menu answers do not fit at all: do not try the other cubes
            remaining = [sp for sp in remaining if not (sd / "cubes" / sp["name"]).exists()]
        else:
            can = [sp for sp in remaining if sp["kind"] in PLOTS_KINDS]
            if not can:
                continue
            items = [{"kind": sp["kind"], "file": sp["name"], "index": sp["fill"].get("index", 0),
                      "operator": sp["operator"]} for sp in can]
            try:
                got = run_plots_route(sd, base, items, grid)
                for sp in can:
                    if sp["name"] in got:
                        record(sp, got[sp["name"]], "plots")
                    else:
                        problems.setdefault(sp["name"], []).append("%plots: cube not written")
                if got:
                    db.kv_set("cube_route", "plots")
            except RuntimeError as e:
                for sp in can:
                    problems.setdefault(sp["name"], []).append(f"%plots: {e}")
            remaining = [sp for sp in remaining if not (sd / "cubes" / sp["name"]).exists()]
    _save_index(sd, idx)
    for sp in remaining:
        errors.append(f"{sp['name'].replace('.cube', '')}: " + " | ".join(problems.get(sp["name"], ["failed"])))
    with open(sd / "cubes" / "cubes_report.txt", "a") as fh:
        fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  made: {', '.join(d['name'] for d in done if not d.get('cached')) or '-'}\n")
        for e in errors:
            fh.write(f"    PROBLEM {e}\n")
    return done, errors


def diagnose(m: dict, k: int, grid: int = 40) -> dict:
    """Try both cube routes for the HOMO in a scratch folder and return everything they printed."""
    sd, base = step_paths(m, k)
    if not (sd / f"{base}.gbw").exists():
        return {"ok": False, "summary": "the .gbw file of this step was not kept (Files to keep = minimal?)"}
    o = load_out(sd / f"{base}.out")
    homo = o.orbital_index("homo", 0) if o and o.orbitals else 0
    rep = {"homo_index": homo, "step_dir": str(sd)}
    d = sd / "cubes" / "_diagnose"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for f in (f"{base}.gbw", f"{base}.inp", f"{base}.out", f"{base}.xyz", "input.xyz", f"{base}.densities", f"{base}.densitiesinfo"):
        if (sd / f).exists():
            shutil.copy2(sd / f, d / f)
    e = store.get_entry("orca_plot", "mo") or {"orca_text": ""}
    answers = e["orca_text"].replace("{index}", str(homo)).replace("{operator}", "0").replace("{grid}", str(grid))
    new, text, problem = orca_plot_raw(d, f"{base}.gbw", answers, timeout=300, silent=60)
    rep["orca_plot"] = {"ok": bool(new), "problem": problem, "answers": answers, "log": text[-15000:]}
    try:
        got = run_plots_route(d, base, [{"kind": "mo", "file": "diag_homo.cube", "index": homo, "operator": 0},
                                         {"kind": "density", "file": "diag_density.cube"}], grid)
        rep["plots"] = {"ok": True, "made": sorted(got)}
    except RuntimeError as ex:
        rep["plots"] = {"ok": False, "problem": str(ex)}
    pr = d / "cubes" / "_plot_run"
    rep["plots"]["input"] = (pr / "plot.inp").read_text() if (pr / "plot.inp").exists() else ""
    rep["plots"]["output_tail"] = "\n".join((pr / "plot.out").read_text(errors="replace").splitlines()[-60:]) if (pr / "plot.out").exists() else ""
    s = config.load_settings()
    mep = s.get("script_paths", {}).get("mep", "")
    rep["mep_script"] = mep or "(not set in Settings)"
    rep["ok"] = rep["orca_plot"]["ok"] or rep["plots"]["ok"]
    rep["summary"] = ("orca_plot: " + ("works" if rep["orca_plot"]["ok"] else f"FAILED ({problem})") + "; %plots route: "
                      + ("works" if rep["plots"]["ok"] else "FAILED") + f"; mep.py: {rep['mep_script']}")
    rep_txt = d / "diagnose_report.txt"
    import json
    rep_txt.write_text(json.dumps(rep, indent=1))
    rep["report_file"] = str(rep_txt)
    return rep


def make_cube(m: dict, k: int, kind: str, grid: int = 80, label: str | None = None, operator: int = 0,
              state: int | None = None, force: bool = False) -> dict:
    """kind: mo | density | spin_density | esp | tddft_difference | tddft_transition."""
    done, errors = make_cubes(m, k, [{"kind": kind, "label": label, "operator": operator, "state": state}], grid, force)
    if errors or not done:
        raise RuntimeError("; ".join(errors) or "cube not made")
    return done[0]


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
    o = load_out(Path(sd) / f"{base}.out")
    open_shell = bool(o and o.orbitals and not o.orbitals["restricted"])
    reqs = []
    for spec in cfg.get("orbitals") or []:
        for lbl in expand_range(spec):
            reqs.append({"kind": "mo", "label": lbl, "operator": 0})
            if open_shell:
                reqs.append({"kind": "mo", "label": lbl, "operator": 1})
    if cfg.get("densities"):
        reqs.append({"kind": "density"})
        if o and o.mult and o.mult > 1:
            reqs.append({"kind": "spin_density"})
    made, errors = make_cubes(m, k, reqs, grid) if reqs else ([], [])
    if cfg.get("mep"):
        try:
            make_mep(m, k, grid)
        except (RuntimeError, ValueError) as e:
            errors.append(f"MEP: {e}")
    db.log(b["id"], f"{m['name']} step {k + 1}: {len(made)} cube(s) made"
                    + (f"; problems: {' / '.join(errors)}" if errors else ""), "warning" if errors else "info")


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
                    else:
                        labels = expand_range(it.get("label", "HOMO")) if it["kind"] == "mo" else [None]
                        _, errs = make_cubes(m, k, [dict(it, label=l) for l in labels], grid)
                        state["errors"] += [f"{m['name']}: {e}" for e in errs]
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
