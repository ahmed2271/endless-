"""Script registry (section 12.1): user scripts run in a step folder after the step succeeds."""
from __future__ import annotations

import glob
import os
import re
import shlex
import subprocess
import time
from pathlib import Path

from . import config, db, store, tools


def script_path(sc: dict, s: dict | None = None) -> str:
    s = s or config.load_settings()
    key = sc.get("path_setting") or sc["id"]
    return s.get("script_paths", {}).get(key) or sc.get("path", "")


def ensure_molden(sd: Path, base: str) -> str:
    """{basename}.molden from the .gbw via orca_2mkl (section 12.2)."""
    target = sd / f"{base}.molden"
    if target.exists():
        return target.name
    s = config.load_settings()
    exe = config.utility_path("orca_2mkl", s)
    subprocess.run([exe, base, "-molden"], cwd=sd, capture_output=True, text=True, timeout=600, env=tools.build_env(s))
    produced = sd / f"{base}.molden.input"
    if produced.exists():
        produced.rename(target)
    if not target.exists():
        raise RuntimeError("orca_2mkl did not write a .molden.input file (is the .gbw kept?)")
    return target.name


def run_script(sc: dict, sd: Path, base: str, extra: dict | None = None, nprocs: int | None = None) -> dict:
    """Run one registered script in a step folder. Returns {'ok', 'outputs', 'log'}."""
    s = config.load_settings()
    path = script_path(sc, s)
    if not path or not os.path.isfile(os.path.expanduser(path)):
        raise RuntimeError(f"script '{sc.get('name', sc['id'])}' has no valid path in Settings")
    vals = {"python": s["programs"].get("python") or "python3", "script": os.path.expanduser(path),
            "basename": base, "step_dir": str(sd), "nprocs": nprocs or int(sc.get("cores") or 1),
            "npoints": (extra or {}).get("npoints", sc.get("npoints", 80)), "gbw": f"{base}.gbw",
            "out": f"{base}.out", "molden": ""}
    vals.update(extra or {})
    tmpl = sc.get("command") or "{python} {script} {basename}"
    if "{molden}" in tmpl:
        vals["molden"] = ensure_molden(sd, base)
    args = [re.sub(r"\{(\w+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), a) for a in shlex.split(tmpl)]
    before = {p.name: p.stat().st_mtime for p in sd.iterdir() if p.is_file()}
    log = sd / f"{store.slugify(sc.get('name') or sc['id'])}_{base}.log"
    t0 = time.time()
    with open(log, "w") as fh:
        try:
            r = subprocess.run(args, cwd=sd, stdout=fh, stderr=subprocess.STDOUT, env=tools.build_env(s),
                               timeout=float(sc.get("timeout") or 3600))
            rc = r.returncode
        except subprocess.TimeoutExpired:
            rc = -1
            fh.write("\n[ORCA Studio] script timed out\n")
    outputs = []
    for o in sc.get("outputs") or []:
        pat = re.sub(r"\{(\w+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), o.get("glob", ""))
        for p in sorted(glob.glob(str(sd / pat))):
            pp = Path(p)
            if pp.name not in before or pp.stat().st_mtime > before[pp.name]:
                outputs.append({"path": p, "type": o.get("type", "file"), "role": o.get("role", "")})
    return {"ok": rc == 0, "exit_code": rc, "outputs": outputs, "log": str(log), "seconds": time.time() - t0}


def run_step_scripts(b, m, k, step, sd, base):
    from .batches import workflow
    for sid in workflow(step).get("scripts") or []:
        sc = store.get_item("scripts", sid)
        if not sc:
            db.log(b["id"], f"script '{sid}' is not registered", "warning")
            continue
        r = run_script(sc, Path(sd), base)
        db.log(b["id"], f"{m['name']} step {k + 1}: script {sc.get('name', sid)} "
                        f"{'finished' if r['ok'] else 'FAILED (exit ' + str(r['exit_code']) + ')'}; "
                        f"outputs: {', '.join(Path(o['path']).name for o in r['outputs']) or 'none'}",
               "info" if r["ok"] else "warning")
