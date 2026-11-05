"""ORCA checks (Appendix D): confirm [VERIFY] syntax with tiny real runs on this workstation.

Each check runs small jobs (H2 / H2O, 2 cores) in {studio}/verify/<check>/, decides what works,
updates the library entry accordingly (removing the 'unverified' tag, switching to a working
candidate, or hiding an entry that cannot work) and records every change in a report.
Run from the app (Settings → ORCA checks) or:  python -m orca_studio.verify
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time
import traceback
from pathlib import Path

from . import config, db, store, tools
from .parsers.aux_files import parse_property_file, property_value
from .parsers.orca_out import OrcaOut

WATER = "3\nwater charge=0 mult=1\nO 0.000000 0.000000 0.117300\nH 0.000000 0.757200 -0.469200\nH 0.000000 -0.757200 -0.469200\n"
H2 = "2\nH2 charge=0 mult=1\nH 0 0 0\nH 0 0 0.74\n"

STATE = {"running": False, "current": "", "results": [], "started": None, "finished": None}
_lock = threading.Lock()

CHECKS = [
    ("xtb", "1. How ORCA finds xtb; XTB2 / XTB1 / GFN-FF and ALPB(solvent) keywords"),
    ("opt_message", "2. Exact 'optimization converged' message"),
    ("freq_keywords", "3. %freq Pressure, QRRHO and CutOffFreq"),
    ("tddft_keywords", "4. FollowIRoot and OrbWin syntax in %tddft"),
    ("dscf", "5. ΔSCF keywords"),
    ("orca_plot", "6. orca_plot: non-interactive use and electrostatic potential plot type"),
    ("numbering", "7. Orbital numbering starts at 0"),
    ("multiwfn", "8. Where Multiwfn reads settings.ini and how to set its thread count"),
    ("property_file", "9. Property file contains the values the parsers rely on"),
]


# --------------------------------------------------------------------------- helpers
def _dir(name: str) -> Path:
    d = config.studio_dir() / "verify" / name
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    return d


def _pal_maxcore() -> str:
    pal = store.text("assembly", "pal", "%pal nprocs {nprocs} end").replace("{nprocs}", "2")
    mc = store.text("assembly", "maxcore", "%maxcore {maxcore}").replace("{maxcore}", "500")
    return f"{mc}\n{pal}"


def _geo(charge=0, mult=1, xyz="input.xyz") -> str:
    g = store.text("assembly", "geometry_xyzfile", "* xyzfile {charge} {mult} {xyzfile}")
    return g.replace("{charge}", str(charge)).replace("{mult}", str(mult)).replace("{xyzfile}", xyz)


def run_orca(d: Path, base: str, keywords: str, blocks: str = "", xyz: str = WATER, charge=0, mult=1,
             timeout=600) -> OrcaOut:
    s = config.load_settings()
    (d / "input.xyz").write_text(xyz)
    (d / f"{base}.inp").write_text(f"! {keywords}\n{_pal_maxcore()}\n{blocks}\n\n{_geo(charge, mult)}\n")
    with open(d / f"{base}.out", "w") as fh:
        try:
            subprocess.run([os.path.expanduser(s["programs"]["orca"]), f"{base}.inp"], cwd=d, stdout=fh,
                           stderr=subprocess.STDOUT, env=tools.build_env(s), timeout=timeout)
        except subprocess.TimeoutExpired:
            fh.write("\n[ORCA Studio] timed out\n")
    return OrcaOut.from_file(d / f"{base}.out")


def _ok(out: OrcaOut) -> bool:
    return out.terminated_normally


def _err_lines(out: OrcaOut, n=6) -> str:
    keys = re.compile(r"error|unrecognized|unknown|aborting|cannot|not found|invalid", re.I)
    lines = [ln.strip() for ln in out.lines if keys.search(ln)]
    return " | ".join(lines[:n]) or "\n".join(out.lines[-6:])


def _set_entry(list_id: str, entry_id: str, **changes) -> list[str]:
    lib = store.get_library(list_id)
    msgs = []
    for e in lib["entries"]:
        if e["id"] == entry_id:
            for k, v in changes.items():
                if k == "verified":
                    tags = [t for t in e.get("tags") or [] if t != "unverified"]
                    if v:
                        if tags != e.get("tags"):
                            e["tags"] = tags
                            msgs.append(f"{list_id}/{entry_id}: confirmed (removed 'unverified')")
                    continue
                if e.get(k) != v:
                    msgs.append(f"{list_id}/{entry_id}: {k} '{e.get(k)}' → '{v}'")
                    e[k] = v
    store.save_library(lib)
    return msgs


def _set_column(cid: str, **changes) -> list[str]:
    c = store.get_item("columns", cid)
    if not c:
        return []
    msgs = []
    for k, v in changes.items():
        if k == "verified":
            tags = [t for t in c.get("tags") or [] if t != "unverified"]
            if tags != (c.get("tags") or []):
                c["tags"] = tags
                msgs.append(f"column {cid}: confirmed")
            continue
        if c.get(k) != v:
            msgs.append(f"column {cid}: {k} '{c.get(k)}' → '{v}'")
            c[k] = v
    store.save_item("columns", c)
    return msgs


def _result(cid, status, details, changes=None):
    return {"id": cid, "title": dict(CHECKS)[cid], "status": status, "details": details, "changes": changes or []}


# --------------------------------------------------------------------------- checks
def check_xtb():
    s = config.load_settings()
    otool = config.orca_dir(s) / "otool_xtb"
    found = []
    if s["programs"].get("xtb"):
        found.append(f"xtb set in Settings: {s['programs']['xtb']} (passed to ORCA as XTBEXE and on PATH)")
    found.append(f"otool_xtb in the ORCA folder: {'yes' if otool.exists() else 'no'} ({otool})")
    changes, details = [], list(found)
    any_ok = False
    lib = store.get_library("semiempirical")
    for e in lib["entries"]:
        cands = e.get("verify_candidates") or [e["orca_text"]]
        chosen = None
        for c in cands:
            d = _dir(f"xtb_{e['id']}_{re.sub(r'[^A-Za-z0-9]+', '_', c)}")
            out = run_orca(d, "w", f"{c} Opt", timeout=300)
            if _ok(out):
                chosen = c
                break
            details.append(f"{e['label']}: '{c}' failed: {_err_lines(out)}")
        if chosen:
            any_ok = True
            details.append(f"{e['label']}: '{chosen}' works")
            changes += _set_entry("semiempirical", e["id"], orca_text=chosen, verified=True)
        else:
            changes += _set_entry("semiempirical", e["id"], notes=f"Did not run on this workstation ({time.strftime('%Y-%m-%d')})")
    xtb2 = store.get_entry("semiempirical", "xtb2")
    if any_ok and xtb2:
        d = _dir("xtb_alpb")
        out = run_orca(d, "w", f"{xtb2['orca_text']} ALPB(water)", timeout=300)
        if _ok(out):
            details.append("ALPB(water) works with xTB")
            changes += _set_entry("solvent_models", "alpb", verified=True)
        else:
            details.append(f"ALPB(water) failed: {_err_lines(out)}")
            changes += _set_entry("solvent_models", "alpb", hidden=True, notes="ALPB failed on ORCA 6.0.1 here")
    status = "pass" if any_ok else "fail"
    if not any_ok:
        details.append("xTB does not run: set the xtb program in Settings, or use the r2SCAN-3c pre-opt profile.")
    return _result("xtb", status, details, changes)


def check_opt_message():
    d = _dir("opt_message")
    out = run_orca(d, "h2", f"{store.text('functionals', 'hf', 'HF')} {store.text('basis_sets', 'def2svp', 'def2-SVP')} Opt", xyz=H2)
    if not _ok(out):
        return _result("opt_message", "fail", [f"test optimization failed: {_err_lines(out)}"])
    e = store.get_entry("output_patterns", "opt_converged")
    lines = [ln.strip() for ln in out.lines if re.search(r"OPTIMIZATION|CONVERGED", ln) and "*" in ln or "HAS CONVERGED" in ln]
    for c in e.get("verify_candidates") or [e["orca_text"]]:
        if re.search(c, out.text, re.I):
            ch = _set_entry("output_patterns", "opt_converged", orca_text=c, verified=True)
            return _result("opt_message", "pass", [f"found: '{c}'", "matching lines: " + " / ".join(lines[:3])], ch)
    return _result("opt_message", "fail", ["none of the known messages were found; lines with OPTIMIZATION/CONVERGED: "
                                           + " / ".join(lines[:5])])


def _try_column_templates(cid, base_kw, block_name, value, cands, extra=""):
    """Try candidate templates for a %block column; returns (working template or None, details)."""
    details = []
    for tpl in cands:
        line = tpl.replace("{value}", str(value))
        d = _dir(f"{cid}_{re.sub(r'[^A-Za-z0-9]+', '_', tpl)[:30]}")
        out = run_orca(d, "w", base_kw, f"%{block_name}\n  {line}\n{extra}end")
        if _ok(out):
            return tpl, details + [f"'{line}' accepted"], out
        details.append(f"'{line}' failed: {_err_lines(out)}")
    return None, details, None


def check_freq_keywords():
    kw = f"{store.text('functionals', 'hf', 'HF')} {store.text('basis_sets', 'def2svp', 'def2-SVP')} Freq"
    details, changes, ok_all = [], [], True
    for cid, value, cands in (("pressure", 2.0, ["Pressure {value}"]),
                              ("qrrho", None, ["QRRHO true", "QuasiRRHO true"]),
                              ("cutoff_freq", 100, ["CutOffFreq {value}", "Cutoff {value}"])):
        col = store.get_item("columns", cid) or {}
        cands = [col.get("template")] + [c for c in cands if c != col.get("template")] if col.get("template") else cands
        tpl, det, out = _try_column_templates(cid, kw, "freq", value if value is not None else "", cands)
        details += [f"{cid}: {x}" for x in det]
        if tpl:
            changes += _set_column(cid, template=tpl, verified=True)
            if cid == "pressure" and out is not None and out.thermo and out.thermo.get("pressure") is not None:
                details.append(f"pressure read back from output: {out.thermo['pressure']} atm")
        else:
            ok_all = False
            changes += _set_column(cid, notes="Not accepted by ORCA 6.0.1 here; hidden from new profiles", hidden=True)
    return _result("freq_keywords", "pass" if ok_all else "fail", details, changes)


def check_tddft_keywords():
    kw = f"{store.text('functionals', 'b3lyp', 'B3LYP')} {store.text('basis_sets', 'def2svp', 'def2-SVP')}"
    details, changes, ok_all = [], [], True
    tpl, det, _ = _try_column_templates("followiroot", kw, "tddft", "", ["FollowIRoot true"], "  NRoots 3\n  IRoot 1\n")
    details += [f"FollowIRoot: {x}" for x in det]
    if tpl:
        changes += _set_column("followiroot", verified=True)
    else:
        ok_all = False
        changes += _set_column("followiroot", hidden=True, notes="Not accepted by ORCA 6.0.1 here")
    tpl, det, _ = _try_column_templates("orbwin", kw, "tddft", "1,-1,-1,-1",
                                        ["OrbWin[0] = {value}", "OrbWin[0] {value}"], "  NRoots 3\n")
    details += [f"OrbWin: {x}" for x in det]
    if tpl:
        changes += _set_column("orbwin", template=tpl, verified=True)
    else:
        ok_all = False
        changes += _set_column("orbwin", notes="Syntax not confirmed on ORCA 6.0.1; enter the block in Extra blocks")
    return _result("tddft_keywords", "pass" if ok_all else "fail", details, changes)


def check_dscf():
    func = store.text("functionals", "b3lyp", "B3LYP")
    basis = store.text("basis_sets", "def2svp", "def2-SVP")
    d = _dir("dscf")
    gs = run_orca(d, "gs", f"{func} {basis}")
    if not _ok(gs):
        return _result("dscf", "fail", [f"ground state failed: {_err_lines(gs)}"])
    shutil.copy2(d / "gs.gbw", d / "previous.gbw")
    kw_col = store.get_item("columns", "dscf_keyword") or {}
    kws = (kw_col.get("default") or "UKS DeltaSCF")
    moinp = store.text("assembly", "moinp", '%moinp "{gbw}"').replace("{gbw}", "previous.gbw")
    details, changes = [], []
    variants = [("IMOM", "  ALPHACONF 0,1\n  DOMOM true\n  PMOM true\n"), ("MOM", "  ALPHACONF 0,1\n  DOMOM true\n")]
    any_ok = False
    for label, block in variants:
        out = run_orca(d, f"es_{label.lower()}", f"{func} {basis} {kws} MORead", f"{moinp}\n%scf\n{block}end")
        if _ok(out) and out.final_energy and gs.final_energy:
            de = (out.final_energy - gs.final_energy) * 27.211386
            details.append(f"{label}: ran, ΔE = {de:.3f} eV" + (" (collapsed!)" if de < 0.05 else ""))
            if de >= 0.05:
                any_ok = True
                changes += _set_entry("dscf_mom", label.lower(), verified=True)
        else:
            details.append(f"{label}: failed: {_err_lines(out)}")
    if any_ok:
        changes += _set_column("dscf_keyword", verified=True) + _set_column("dscf_alphaconf", verified=True)
    return _result("dscf", "pass" if any_ok else "fail", details, changes)


def check_orca_plot():
    from . import visuals
    d = _dir("orca_plot")
    out = run_orca(d, "w", f"{store.text('functionals', 'b3lyp', 'B3LYP')} {store.text('basis_sets', 'def2svp', 'def2-SVP')} "
                           f"{store.text('assembly', 'keepdens_keyword', 'KeepDens')}")
    if not _ok(out):
        return _result("orca_plot", "fail", [f"SP job failed: {_err_lines(out)}"])
    details, changes = [], []
    homo = out.orbital_index("homo", 0)
    results = {}
    for eid, fill in (("mo", {"index": homo, "operator": 0, "grid": 40}), ("density", {"grid": 40}), ("esp", {"grid": 40})):
        e = store.get_entry("orca_plot", eid)
        if not e:
            continue
        answers = e["orca_text"]
        for k, v in fill.items():
            answers = answers.replace("{" + k + "}", str(v))
        new, text, problem = visuals.orca_plot_raw(d, "w.gbw", answers, timeout=300)
        (d / f"orca_plot_{eid}.log").write_text(text)
        results[eid] = new
        if new:
            details.append(f"orca_plot {e['label']}: cube written ({', '.join(p.name for p in new)})")
            changes += _set_entry("orca_plot", eid, verified=True)
        else:
            menu = [ln.strip() for ln in text.splitlines() if re.match(r"^\s*\d+\s*-\s", ln)]
            seen = list(dict.fromkeys(menu))[:40]
            details.append(f"orca_plot {e['label']}: {problem}. Menu lines printed by orca_plot: " + " | ".join(seen)
                           + f" (full log: verify/orca_plot/orca_plot_{eid}.log)")
            if eid == "esp":
                changes += _set_entry("orca_plot", "esp", hidden=True, notes="No ESP plot type in this orca_plot; use mep.py")
    # second route: %plots in a short ORCA run that reads the .gbw
    try:
        got = visuals.run_plots_route(d, "w", [{"kind": "mo", "file": "homo_plots.cube", "index": homo, "operator": 0},
                                              {"kind": "density", "file": "dens_plots.cube"}], 40)
        details.append(f"%plots route: cubes written ({', '.join(sorted(got))})")
        plots_ok = True
    except RuntimeError as e:
        details.append(f"%plots route failed: {e}")
        plots_ok = False
    if results.get("mo"):
        db.kv_set("cube_route", "orca_plot")
        details.append("Cubes will be made with orca_plot.")
    elif plots_ok:
        db.kv_set("cube_route", "plots")
        details.append("Cubes will be made with the %plots route (orca_plot's menu answers did not fit). "
                       "Send the orca_plot log to fix the menu answers if you also want TDDFT difference densities.")
    if not results.get("esp"):
        details.append("ESP route: use the registered mep.py script (Scripts page).")
    status = "pass" if (results.get("mo") or plots_ok) else "fail"
    return _result("orca_plot", status, details, changes)


def check_numbering():
    d = _dir("numbering")
    out = run_orca(d, "w", f"{store.text('functionals', 'hf', 'HF')} {store.text('basis_sets', 'def2svp', 'def2-SVP')}")
    orbs = out.orbitals
    if not orbs or not orbs["alpha"]:
        return _result("numbering", "fail", [f"no orbital energies found: {_err_lines(out)}"])
    first = orbs["alpha"][0]["index"]
    homo = out.orbital_index("homo", 0)
    ok = first == 0 and homo == 4
    return _result("numbering", "pass" if ok else "fail",
                   [f"first orbital number printed: {first}; water HOMO number: {homo} (expected 4 with numbering from 0)"])


def check_multiwfn():
    s = config.load_settings()
    mw = s["programs"].get("multiwfn")
    if not mw:
        return _result("multiwfn", "skipped", ["Multiwfn is not set in Settings."])
    exe = Path(mw).expanduser()
    details = []
    cands = [exe.parent / "settings.ini"]
    if os.environ.get("Multiwfnpath"):
        cands.append(Path(os.environ["Multiwfnpath"]) / "settings.ini")
    for c in cands:
        details.append(f"{c}: {'exists' if c.exists() else 'missing'}")
        if c.exists():
            m = re.search(r"^\s*nthreads\s*=\s*(\d+)", c.read_text(errors="replace"), re.M)
            details.append(f"  nthreads in it: {m.group(1) if m else 'not found'}")
    details.append("ORCA Studio copies settings.ini into the working folder with nthreads set from Settings "
                   "(Multiwfn reads ./settings.ini first) and also sets Multiwfnpath to the Multiwfn folder.")
    from .multiwfn import probe_threads
    probe = probe_threads(s)
    details.append(probe["message"])
    return _result("multiwfn", "pass" if probe["ok"] else "fail", details)


def check_property_file():
    d = _dir("property_file")
    out = run_orca(d, "w", f"{store.text('functionals', 'b3lyp', 'B3LYP')} {store.text('basis_sets', 'def2svp', 'def2-SVP')}")
    pf = d / "w.property.txt"
    if not pf.exists():
        return _result("property_file", "fail", ["w.property.txt was not written; the parsers use the .out file only."])
    props = parse_property_file(pf)
    e = property_value(props, "FINALENERGY", "SCF_ENERGY", "TOTALENERGY")
    details = [f"sections: {', '.join(list(props)[:15])}"]
    ok = e is not None and out.final_energy is not None and abs(e - out.final_energy) < 1e-6
    details.append(f"final energy in property file: {e}; in .out: {out.final_energy}")
    db.kv_set("property_file_trusted", bool(ok))
    if ok:
        details.append("The final energy is taken from the property file when present.")
    else:
        details.append("Energies are taken from the .out file.")
    return _result("property_file", "pass" if ok else "fail", details)


FUNCS = {"xtb": check_xtb, "opt_message": check_opt_message, "freq_keywords": check_freq_keywords,
         "tddft_keywords": check_tddft_keywords, "dscf": check_dscf, "orca_plot": check_orca_plot,
         "numbering": check_numbering, "multiwfn": check_multiwfn, "property_file": check_property_file}


def run_all(only: list[str] | None = None) -> list[dict]:
    with _lock:
        if STATE["running"]:
            return STATE["results"]
        STATE.update(running=True, results=[], started=time.time(), finished=None)
    try:
        if not tools.is_exec(config.load_settings()["programs"]["orca"]):
            STATE["results"].append({"id": "orca", "title": "ORCA", "status": "fail",
                                     "details": ["ORCA not found: set it in Settings first"], "changes": []})
            return STATE["results"]
        for cid, title in CHECKS:
            if only and cid not in only:
                continue
            STATE["current"] = title
            try:
                r = FUNCS[cid]()
            except Exception as e:
                r = _result(cid, "fail", [f"check crashed: {e}", traceback.format_exc()[-800:]])
            STATE["results"].append(r)
            db.kv_set("verify_results", STATE["results"])
        write_report(STATE["results"])
        return STATE["results"]
    finally:
        STATE.update(running=False, current="", finished=time.time())


def write_report(results):
    v = tools.orca_version(config.load_settings()["programs"]["orca"]) or "?"
    lines = [f"# ORCA checks report ({time.strftime('%Y-%m-%d %H:%M')}, ORCA {v})", ""]
    for r in results:
        lines += [f"## {r['title']}: {r['status'].upper()}", ""] + [f"- {d}" for d in r["details"]]
        if r["changes"]:
            lines += ["", "Library changes:"] + [f"- {c}" for c in r["changes"]]
        lines.append("")
    (config.studio_dir() / "verify_report.md").write_text("\n".join(lines))


def start_background(only=None):
    t = threading.Thread(target=run_all, args=(only,), daemon=True)
    t.start()


if __name__ == "__main__":
    store.seed()
    db.init()
    for r in run_all():
        print(f"[{r['status'].upper():7s}] {r['title']}")
        for d in r["details"]:
            print("          ", d)
        for c in r["changes"]:
            print("   change:", c)
    print(f"Report: {config.studio_dir() / 'verify_report.md'}")
