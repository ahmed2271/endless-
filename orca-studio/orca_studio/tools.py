"""Program paths: job environment, tests, auto-detection, test job (section 4)."""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from . import config


def build_env(settings: dict | None = None) -> dict:
    """Explicit job environment: never relies on .bashrc."""
    s = settings or config.load_settings()
    p = s["programs"]
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
    path_parts, ld_parts = [], []
    if p.get("openmpi_bin"):
        path_parts.append(str(Path(p["openmpi_bin"]).expanduser()))
    lib = config.mpi_lib(s)
    if lib:
        ld_parts.append(str(Path(lib).expanduser()))
    od = str(config.orca_dir(s))
    path_parts.append(od)
    ld_parts.append(od)
    if p.get("xtb"):
        xtb = Path(p["xtb"]).expanduser()
        path_parts.append(str(xtb.parent))
        env["XTBEXE"] = str(xtb)       # [VERIFY] how ORCA 6.0.1 finds xtb (Appendix D check 1)
    if p.get("nbo"):
        env["NBOEXE"] = str(Path(p["nbo"]).expanduser())
    env["PATH"] = ":".join(path_parts + [env.get("PATH", "/usr/bin:/bin")])
    env["LD_LIBRARY_PATH"] = ":".join(ld_parts + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
    return env


def is_exec(path: str) -> bool:
    p = os.path.expanduser(path or "")
    return bool(path) and os.path.isfile(p) and os.access(p, os.X_OK)


def test_program(key: str, settings: dict | None = None) -> dict:
    """File exists and is executable; for ORCA, report the version."""
    s = settings or config.load_settings()
    if key in ("orca_2mkl", "orca_plot", "orca_vpot", "orca_chelpg", "orca_pltvib"):
        path = config.utility_path(key, s)
    elif key == "openmpi_bin":
        d = Path(s["programs"].get("openmpi_bin") or "").expanduser()
        mp = d / "mpirun"
        if not s["programs"].get("openmpi_bin"):
            return {"ok": False, "message": "not set"}
        if not is_exec(str(mp)):
            return {"ok": False, "message": f"no executable mpirun in {d}"}
        try:
            out = subprocess.run([str(mp), "--version"], capture_output=True, text=True, timeout=20,
                                 env=build_env(s)).stdout
            ver = re.search(r"(\d+\.\d+\.\d+)", out or "")
            msg = f"mpirun {ver.group(1) if ver else '?'}"
            if ver and not ver.group(1).startswith("4.1"):
                msg += " (ORCA 6.0.1 is built for OpenMPI 4.1.x)"
            return {"ok": True, "message": msg}
        except (OSError, subprocess.SubprocessError) as e:
            return {"ok": False, "message": str(e)}
    elif key.startswith("script:"):
        path = s.get("script_paths", {}).get(key.split(":", 1)[1], "")
        ok = bool(path) and os.path.isfile(os.path.expanduser(path))
        return {"ok": ok, "message": "found" if ok else "not found"}
    else:
        path = s["programs"].get(key) or ""
    if not path:
        return {"ok": False, "message": "not set"}
    if not is_exec(path):
        return {"ok": False, "message": f"{path} does not exist or is not executable"}
    if key == "orca":
        v = orca_version(path)
        return {"ok": True, "message": f"ORCA {v}" if v else "found (version not reported)", "version": v}
    return {"ok": True, "message": "found"}


def orca_version(path: str) -> str | None:
    """Run ORCA on a missing input: it prints its banner (with version) and stops."""
    try:
        with tempfile.TemporaryDirectory() as td:
            r = subprocess.run([os.path.expanduser(path), "--version"], capture_output=True, text=True,
                               timeout=30, cwd=td, env=build_env())
            text = (r.stdout or "") + (r.stderr or "")
            m = re.search(r"Program Version\s+(\S+)", text) or re.search(r"Version\s+(\d+\.\d+\.\d+)", text)
            return m.group(1) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def autodetect() -> dict:
    """Search $HOME, /opt, /usr/local and PATH for ORCA, OpenMPI, xtb, Multiwfn, NBO, mep.py."""
    found: dict[str, list[str]] = {k: [] for k in ("orca", "openmpi_bin", "xtb", "multiwfn", "nbo", "mep")}
    roots = [Path.home(), Path("/opt"), Path("/usr/local")]
    targets = {"orca": "orca", "xtb": "xtb", "multiwfn": "Multiwfn", "mep": "mep.py", "mpirun": "mpirun",
               "nbo": "nbo7.i8.exe"}
    for name, exe in targets.items():
        w = shutil.which(exe)
        if w:
            _add(found, name, w)
    deadline = time.time() + 25
    for r in roots:
        if not r.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(r):
            if time.time() > deadline:
                break
            depth = len(Path(dirpath).relative_to(r).parts)
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in (
                "node_modules", "dft_projects", "snap", "proc", "__pycache__") and depth < 5]
            fs = set(filenames)
            if "orca" in fs and ("orca_plot" in fs or "orca_scf" in fs):
                _add(found, "orca", os.path.join(dirpath, "orca"))
            if "mpirun" in fs:
                _add(found, "mpirun", os.path.join(dirpath, "mpirun"))
            if "xtb" in fs:
                _add(found, "xtb", os.path.join(dirpath, "xtb"))
            for f in fs:
                if f.startswith("Multiwfn") and not f.endswith((".pdf", ".ini", ".txt")):
                    _add(found, "multiwfn", os.path.join(dirpath, f))
                if re.match(r"nbo\d.*\.exe$", f):
                    _add(found, "nbo", os.path.join(dirpath, f))
            if "mep.py" in fs:
                _add(found, "mep", os.path.join(dirpath, "mep.py"))
    found["openmpi_bin"] = [str(Path(p).parent) for p in found.pop("mpirun", [])]
    return {k: [p for p in v if is_exec(p) or k in ("mep", "openmpi_bin")] for k, v in found.items()}


def _add(found, k, p):
    found.setdefault(k, [])
    if p not in found[k]:
        found[k].append(p)


TEST_JOB_XYZ = "2\ncharge=0 mult=1\nH 0.0 0.0 0.0\nH 0.0 0.0 0.74\n"


def run_test_job(settings: dict | None = None, timeout: int = 300) -> dict:
    """H2, HF/def2-SVP single point with 2 cores: confirms ORCA and MPI work together."""
    from . import store

    s = settings or config.load_settings()
    work = config.studio_dir() / "test_job"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    (work / "input.xyz").write_text(TEST_JOB_XYZ)
    pal = store.text("assembly", "pal", "%pal nprocs {nprocs} end").replace("{nprocs}", "2")
    geo = store.text("assembly", "geometry_xyzfile", "* xyzfile {charge} {mult} {xyzfile}")
    geo = geo.replace("{charge}", "0").replace("{mult}", "1").replace("{xyzfile}", "input.xyz")
    method = store.text("functionals", "hf", "HF")
    basis = store.text("basis_sets", "def2svp", "def2-SVP")
    (work / "h2.inp").write_text(f"! {method} {basis}\n{pal}\n\n{geo}\n")
    t0 = time.time()
    try:
        with open(work / "h2.out", "w") as out:
            r = subprocess.run([os.path.expanduser(s["programs"]["orca"]), "h2.inp"], cwd=work, stdout=out,
                               stderr=subprocess.STDOUT, env=build_env(s), timeout=timeout)
        text = (work / "h2.out").read_text(errors="replace")
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"test job did not finish within {timeout} s", "folder": str(work)}
    except OSError as e:
        return {"ok": False, "message": f"could not start ORCA: {e}", "folder": str(work)}
    ok = r.returncode == 0 and "ORCA TERMINATED NORMALLY" in text
    m = re.search(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", text)
    tail = "\n".join(text.splitlines()[-25:])
    msg = (f"OK: E(HF/def2-SVP, H2) = {m.group(1)} Eh in {time.time() - t0:.1f} s with 2 MPI processes"
           if ok else f"failed (exit code {r.returncode}). Last lines of h2.out:\n{tail}")
    return {"ok": ok, "message": msg, "folder": str(work), "energy": float(m.group(1)) if m else None}
