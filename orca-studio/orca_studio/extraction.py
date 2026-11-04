"""Extraction profiles (section 9): built-in fields, custom patterns, formulas, units and flags."""
from __future__ import annotations

import ast
import math
import time
from functools import lru_cache
from pathlib import Path

from . import batches, config, db, store
from .elements import hill_formula
from .parsers.aux_files import parse_property_file, property_value
from .parsers.orca_out import OrcaOut

# --------------------------------------------------------------------------- units
UNITS = {
    "energy": {"Eh": 1.0, "kcal/mol": 627.5095, "kJ/mol": 2625.4996, "eV": 27.211386, "cm-1": 219474.63},
    "orbital": {"eV": 1.0, "Eh": 1 / 27.211386},
    "excitation": {"eV": 1.0, "nm": "nm", "cm-1": 8065.544},
    "frequency": {"cm-1": 1.0},
    "dipole": {"Debye": 1.0, "au": 1 / 2.541746473},
    "length": {"Å": 1.0},
    "angle": {"deg": 1.0},
    "time": {"s": 1.0, "min": 1 / 60, "h": 1 / 3600},
    "charge": {"e": 1.0},
    "none": {"": 1.0},
}
DEFAULT_UNIT = {"energy": "Eh", "orbital": "eV", "excitation": "eV", "frequency": "cm-1", "dipole": "Debye",
                "length": "Å", "angle": "deg", "time": "s", "charge": "e", "none": ""}


def convert(v, kind: str, unit: str | None):
    if v is None or not isinstance(v, (int, float)) or isinstance(v, bool):
        return v
    table = UNITS.get(kind or "none", {})
    f = table.get(unit or DEFAULT_UNIT.get(kind, ""), 1.0)
    if f == "nm":
        return 1239.84193 / v if v else None
    return v * f


# --------------------------------------------------------------------------- built-in fields
def _hl(o, key, spin="alpha"):
    r = o.homo_lumo(spin)
    if not r:
        return None
    if key == "gap":
        return r["gap_ev"]
    x = r.get(key)
    return x["e_ev"] if x else None


def _orbital(o, p):
    spin = p.get("spin", "alpha")
    idx = o.orbital_index(p.get("which", "homo"), int(p.get("n", 0) or 0), spin)
    orbs = (o.orbitals or {}).get(spin) or (o.orbitals or {}).get("alpha") or []
    for x in orbs:
        if x["index"] == idx:
            return x["e_ev"]
    return None


def _geom(o):
    return o.final_geometry or []


def _dist(g, a, b):
    return math.dist(g[a][1:], g[b][1:])


def _angle(g, a, b, c):
    import numpy as np
    v1 = np.array(g[a][1:]) - np.array(g[b][1:])
    v2 = np.array(g[c][1:]) - np.array(g[b][1:])
    return float(np.degrees(np.arccos(np.clip(v1 @ v2 / np.linalg.norm(v1) / np.linalg.norm(v2), -1, 1))))


def _dihedral(g, a, b, c, d):
    import numpy as np
    p = [np.array(g[i][1:]) for i in (a, b, c, d)]
    b0, b1, b2 = p[0] - p[1], p[2] - p[1], p[3] - p[2]
    b1 /= np.linalg.norm(b1)
    v = b0 - (b0 @ b1) * b1
    w = b2 - (b2 @ b1) * b1
    x = v @ w
    y = np.cross(b1, v) @ w
    return float(np.degrees(np.arctan2(y, x)))


def _atoms_param(p, ctx, natoms):
    """atoms: 'all' | '0 3 5' | element 'O' | fragment name (batch fragments)."""
    sel = str(p.get("atoms", "all") or "all").strip()
    if sel == "all":
        return list(range(natoms))
    frags = ctx.get("fragments") or {}
    if sel in frags:
        return [int(i) for i in frags[sel]]
    parts = sel.replace(",", " ").split()
    if all(x.lstrip("-").isdigit() for x in parts):
        return [int(x) for x in parts]
    return [i for i, a in enumerate(ctx.get("elements") or []) if a in parts]


def charges_of(o, scheme):
    """Charges by scheme; CHELPG falls back to a post-hoc orca_chelpg run next to the .out."""
    tab = o.charges(scheme)
    if tab is None and scheme == "chelpg" and o.path:
        ph = Path(o.path).with_suffix(".chelpg_posthoc.out")
        if ph.exists():
            tab = OrcaOut.from_file(ph).chelpg
    return tab


def _scheme_spread(o, p):
    schemes = str(p.get("schemes") or "mulliken loewdin hirshfeld mbis chelpg").split()
    thr = float(p.get("threshold") or 0.3)
    tabs = {s: charges_of(o, s) for s in schemes}
    tabs = {s: {r["atom"]: r for r in t} for s, t in tabs.items() if t}
    if len(tabs) < 2:
        return None
    atoms = sorted(set.intersection(*[set(t) for t in tabs.values()]))
    rows = []
    for a in atoms:
        vals = {s: t[a]["charge"] for s, t in tabs.items()}
        spread = max(vals.values()) - min(vals.values())
        rows.append(dict({"atom": a, "element": next(iter(tabs.values()))[a]["element"]}, **vals,
                         spread=spread, disagree=spread > thr))
    return rows


def _charge_sel(o, p, ctx):
    tab = charges_of(o, p.get("scheme", "mulliken"))
    if not tab:
        return None
    key = p.get("value", "charge")
    idx = _atoms_param(p, {**ctx, "elements": [r["element"] for r in tab]}, len(tab))
    vals = [r.get(key) for r in tab if r["atom"] in idx]
    vals = [v for v in vals if v is not None]
    if not vals:
        return None
    return vals[0] if len(idx) == 1 else sum(vals)


def _s1(o, mult=1):
    st = [s for s in (o.excited_states or []) if s.get("mult") in (mult, None)]
    return st[0] if st else None


def _brightest(o, p):
    lo, hi = float(p.get("nm_min", 0) or 0), float(p.get("nm_max", 1e9) or 1e9)
    st = [s for s in (o.excited_states or []) if s.get("nm") and lo <= s["nm"] <= hi and s.get("fosc") is not None]
    return max(st, key=lambda s: s["fosc"]) if st else None


def _thermo(o, k):
    t = o.thermo
    return t.get(k) if t else None


def _thermal_corr(o):
    t = o.thermo
    if not t or t.get("total_thermal_energy") is None or t.get("electronic_energy") is None:
        return None
    return t["total_thermal_energy"] - t["electronic_energy"]


def _final_energy(o, ctx):
    if ctx.get("prefer_property") and o.path:
        pf = Path(o.path).with_suffix(".property.txt")
        if pf.exists():
            v = property_value(parse_property_file(pf), "FINALENERGY", "SCF_ENERGY")
            if v is not None:
                return v
    return o.final_energy


def _rmsd(o):
    from .molecules import rmsd
    g0, g1 = o.initial_geometry, o.final_geometry
    return rmsd(g0, g1) if g0 and g1 else None


B = {}


def builtin(fid, label, group, kind="energy", shape="scalar", params=None, requires=None, step_kinds=None):
    def deco(fn):
        B[fid] = {"id": fid, "label": label, "group": group, "unit_kind": kind, "shape": shape,
                  "params": params or [], "requires": requires or [], "step_kinds": step_kinds, "fn": fn}
        return fn
    return deco


def _reg():
    R = builtin
    # run info
    R("termination", "Termination status", "Run info", "none")(lambda o, p, c: "normal" if o.terminated_normally else "error")
    R("run_time", "Run time", "Run info", "time")(lambda o, p, c: o.run_time_seconds)
    R("orca_version", "ORCA version", "Run info", "none")(lambda o, p, c: o.version)
    R("formula", "Formula", "Run info", "none")(lambda o, p, c: hill_formula([a[0] for a in _geom(o)]) if _geom(o) else None)
    R("n_atoms", "Number of atoms", "Run info", "none")(lambda o, p, c: len(_geom(o)) or None)
    R("charge", "Charge", "Run info", "none")(lambda o, p, c: o.charge)
    R("mult", "Multiplicity", "Run info", "none")(lambda o, p, c: o.mult)
    R("method_basis", "Method and basis (keywords)", "Run info", "none")(lambda o, p, c: " ".join(o.keywords))
    R("n_basis", "Number of basis functions", "Run info", "none")(lambda o, p, c: o.n_basis_functions)
    R("scf_iterations", "SCF iterations (last SCF)", "Run info", "none")(lambda o, p, c: o.scf_iterations)
    # energies
    R("final_energy", "Final single-point energy", "Energies")(lambda o, p, c: _final_energy(o, c))
    for k, lab in (("nuclear_repulsion", "Nuclear repulsion"), ("electronic_energy", "Electronic energy"),
                   ("e_xc", "Exchange-correlation energy"), ("dispersion", "Dispersion correction"),
                   ("gcp", "gCP correction"), ("solvation", "Solvation (CPCM dielectric) energy"),
                   ("correlation", "Correlation energy")):
        R(k, lab, "Energies")(lambda o, p, c, k=k: o.energy_components.get(k))
    R("t1_diagnostic", "T1 diagnostic", "Energies", "none")(lambda o, p, c: o.energy_components.get("t1_diagnostic"))
    # geometry
    R("opt_converged", "Optimization converged", "Geometry", "none", step_kinds=["opt", "opt_freq", "xtb"])(
        lambda o, p, c: o.opt_converged(store.text("output_patterns", "opt_converged", "THE OPTIMIZATION HAS CONVERGED")))
    R("opt_cycles", "Optimization cycles", "Geometry", "none")(lambda o, p, c: o.opt_cycles)
    R("final_geometry", "Final geometry", "Geometry", "length", "table")(
        lambda o, p, c: [{"atom": i, "element": a[0], "x": a[1], "y": a[2], "z": a[3]} for i, a in enumerate(_geom(o))] or None)
    R("bond_length", "Bond length", "Geometry", "length", params=["a", "b"])(lambda o, p, c: _dist(_geom(o), int(p["a"]), int(p["b"])))
    R("angle", "Angle", "Geometry", "angle", params=["a", "b", "c"])(lambda o, p, c: _angle(_geom(o), int(p["a"]), int(p["b"]), int(p["c"])))
    R("dihedral", "Dihedral", "Geometry", "angle", params=["a", "b", "c", "d"])(
        lambda o, p, c: _dihedral(_geom(o), int(p["a"]), int(p["b"]), int(p["c"]), int(p["d"])))
    R("rmsd_start", "RMSD from start geometry (Å)", "Geometry", "length")(lambda o, p, c: _rmsd(o))
    R("rot_constants", "Rotational constants (cm⁻¹)", "Geometry", "none")(
        lambda o, p, c: " ".join(f"{x:.5f}" for x in o.rotational_constants_cm) if o.rotational_constants_cm else None)
    # thermochemistry
    F = ["freq", "opt_freq"]
    for k, lab, fn in (("zpe", "Zero-point energy", lambda o: _thermo(o, "zpe")),
                       ("thermal_correction", "Thermal energy correction (U − E)", _thermal_corr),
                       ("enthalpy_correction", "Enthalpy correction (H − E)", lambda o: _thermo(o, "enthalpy_correction")),
                       ("gibbs_correction", "Gibbs correction (G − E)", lambda o: _thermo(o, "gibbs_correction")),
                       ("total_enthalpy", "Total enthalpy H", lambda o: _thermo(o, "total_enthalpy")),
                       ("total_gibbs", "Total Gibbs free energy G", lambda o: _thermo(o, "total_gibbs")),
                       ("entropy_ts", "Entropy term T·S (total)", lambda o: _thermo(o, "ts_total")),
                       ("entropy_el", "T·S electronic", lambda o: _thermo(o, "s_el")),
                       ("entropy_vib", "T·S vibrational", lambda o: _thermo(o, "s_vib")),
                       ("entropy_rot", "T·S rotational", lambda o: _thermo(o, "s_rot")),
                       ("entropy_trans", "T·S translational", lambda o: _thermo(o, "s_trans"))):
        R(k, lab, "Thermochemistry", requires=[{"kind": "freq"}], step_kinds=F)(lambda o, p, c, fn=fn: fn(o))
    R("temperature", "Temperature (K)", "Thermochemistry", "none", step_kinds=F)(lambda o, p, c: _thermo(o, "temperature"))
    R("pressure", "Pressure (atm)", "Thermochemistry", "none", step_kinds=F)(lambda o, p, c: _thermo(o, "pressure"))
    R("imag_count", "Imaginary frequencies", "Thermochemistry", "none", params=["threshold"], step_kinds=F)(
        lambda o, p, c: o.imaginary_count(float(p.get("threshold", 0) or 0)))
    R("lowest_freq", "Lowest frequency", "Thermochemistry", "frequency", step_kinds=F)(lambda o, p, c: o.lowest_frequency)
    R("ir_spectrum", "Frequencies with IR intensities", "Thermochemistry", "frequency", "table", step_kinds=F)(lambda o, p, c: o.ir_spectrum)
    R("raman_spectrum", "Raman activities", "Thermochemistry", "frequency", "table", step_kinds=F)(lambda o, p, c: o.raman_spectrum)
    # orbitals & spin
    R("homo", "HOMO energy", "Orbitals and spin", "orbital", params=["spin"])(lambda o, p, c: _hl(o, "homo", p.get("spin", "alpha")))
    R("lumo", "LUMO energy", "Orbitals and spin", "orbital", params=["spin"])(lambda o, p, c: _hl(o, "lumo", p.get("spin", "alpha")))
    R("gap", "HOMO–LUMO gap", "Orbitals and spin", "orbital", params=["spin"])(lambda o, p, c: _hl(o, "gap", p.get("spin", "alpha")))
    R("orbital", "Orbital energy (HOMO−n / LUMO+n)", "Orbitals and spin", "orbital", params=["which", "n", "spin"])(lambda o, p, c: _orbital(o, p))
    R("orbitals", "Orbital energies and occupations", "Orbitals and spin", "orbital", "table")(
        lambda o, p, c: ([dict(x, spin="alpha") for x in o.orbitals["alpha"]] + [dict(x, spin="beta") for x in o.orbitals["beta"]]) if o.orbitals else None)
    R("s2", "⟨S²⟩", "Orbitals and spin", "none")(lambda o, p, c: (o.s2 or {}).get("s2"))
    R("s2_dev", "⟨S²⟩ deviation", "Orbitals and spin", "none")(lambda o, p, c: (o.s2 or {}).get("deviation"))
    R("spin_populations", "Spin populations (Mulliken)", "Orbitals and spin", "charge", "table", params=["scheme"])(
        lambda o, p, c: [{"atom": r["atom"], "element": r["element"], "spin": r.get("spin")} for r in (o.charges(p.get("scheme", "mulliken")) or [])] or None)
    R("spin_on", "Spin on atoms", "Orbitals and spin", "charge", params=["scheme", "atoms"])(
        lambda o, p, c: _charge_sel(o, {**p, "value": "spin"}, c))
    # electric properties
    R("dipole", "Dipole moment (total)", "Electric properties", "dipole")(lambda o, p, c: (o.dipole or {}).get("total"))
    for ax in "xyz":
        R(f"dipole_{ax}", f"Dipole {ax}", "Electric properties", "dipole")(lambda o, p, c, ax=ax: (o.dipole or {}).get(ax))
    R("quadrupole_iso", "Quadrupole (isotropic)", "Electric properties", "none")(lambda o, p, c: o.quadrupole_isotropic)
    R("polarizability", "Polarizability (isotropic, au)", "Electric properties", "none")(lambda o, p, c: o.polarizability_isotropic)
    R("charges", "Atomic charges", "Electric properties", "charge", "table", params=["scheme"])(
        lambda o, p, c: charges_of(o, p.get("scheme", "mulliken")))
    R("scheme_spread", "Charge scheme spread (flags atoms where schemes disagree)", "Electric properties", "charge", "table",
      params=["schemes", "threshold"])(lambda o, p, c: _scheme_spread(o, p))
    R("charge_on", "Charge on atoms / element / fragment", "Electric properties", "charge", params=["scheme", "atoms", "value"])(
        lambda o, p, c: _charge_sel(o, p, c))
    R("bond_orders", "Bond orders", "Electric properties", "none", "table", params=["scheme"])(
        lambda o, p, c: o.loewdin_bond_orders if p.get("scheme") == "loewdin" else o.mayer_bond_orders)
    R("bond_order", "Bond order for a bond", "Electric properties", "none", params=["scheme", "a", "b"])(lambda o, p, c: _bond_order(o, p))
    R("mayer_valence", "Mayer valence / free valence", "Electric properties", "none", "table")(lambda o, p, c: o.mayer_atoms)
    # excited states
    T = ["tddft", "opt", "sp", "custom", "opt_freq", "freq"]
    R("excited_states", "Excited states", "Excited states", "excitation", "table", requires=[{"kind": "tddft"}], step_kinds=T)(
        lambda o, p, c: [{k: v for k, v in s.items() if k != "transitions"} for s in (o.excited_states or [])] or None)
    R("s1_energy", "S1 energy", "Excited states", "excitation", requires=[{"kind": "tddft"}], step_kinds=T)(lambda o, p, c: (_s1(o, 1) or {}).get("energy_ev"))
    R("s1_fosc", "S1 oscillator strength", "Excited states", "none", requires=[{"kind": "tddft"}], step_kinds=T)(lambda o, p, c: (_s1(o, 1) or {}).get("fosc"))
    R("t1_energy", "T1 energy", "Excited states", "excitation", requires=[{"kind": "tddft", "column": "triplets"}], step_kinds=T)(lambda o, p, c: (_s1(o, 3) or {}).get("energy_ev"))
    R("brightest", "Brightest state energy (in nm range)", "Excited states", "excitation", params=["nm_min", "nm_max"], requires=[{"kind": "tddft"}], step_kinds=T)(
        lambda o, p, c: (_brightest(o, p) or {}).get("energy_ev"))
    R("brightest_fosc", "Brightest state oscillator strength", "Excited states", "none", params=["nm_min", "nm_max"], requires=[{"kind": "tddft"}], step_kinds=T)(
        lambda o, p, c: (_brightest(o, p) or {}).get("fosc"))


def _bond_order(o, p):
    a, b = sorted((int(p["a"]), int(p["b"])))
    tab = o.loewdin_bond_orders if p.get("scheme") == "loewdin" else o.mayer_bond_orders
    for r in tab or []:
        if sorted((r["atom1"], r["atom2"])) == [a, b]:
            return r["order"]
    return 0.0 if tab else None


_reg()

# requirements: which library entry a scheme needs on the source step
SCHEME_REQ = {"hirshfeld": ("populations", "hirshfeld"), "mbis": ("populations", "mbis"),
              "chelpg": ("populations", "chelpg"), "resp": ("populations", "resp"),
              "npa": ("populations", "npa"), "nbo": ("populations", "nbo")}


def field_requirements(f: dict) -> list[dict]:
    if f.get("kind", "builtin") != "builtin":
        return []
    b = B.get(f.get("builtin"))
    if not b:
        return []
    req = list(b["requires"])
    sch = (f.get("params") or {}).get("scheme")
    if sch in SCHEME_REQ and b["id"] in ("charges", "charge_on", "spin_populations", "spin_on"):
        col, val = SCHEME_REQ[sch]
        req.append({"column": col, "value": val})
    if f.get("builtin") == "polarizability":
        req.append({"column": "polar", "value": True})
    if f.get("builtin") == "quadrupole_iso":
        req.append({"column": "quadrupole", "value": True})
    return req


# --------------------------------------------------------------------------- sources
def resolve_step(profile: dict, source: dict | None) -> int | None:
    steps = profile.get("steps") or []
    if not steps:
        return None
    src = source or {"mode": "last"}
    mode = src.get("mode", "last")
    cat = None
    if mode == "step_index":
        i = int(src.get("value", 0))
        return i if 0 <= i < len(steps) else None
    if mode == "step_name":
        for i, s in enumerate(steps):
            if (s.get("name") or "").strip().lower() == str(src.get("value", "")).strip().lower():
                return i
        return None
    if mode == "last_of_type":
        from .assemble import Catalog
        cat = Catalog()
        want = src.get("value")
        for i in range(len(steps) - 1, -1, -1):
            st = cat.step_type(steps[i].get("type"))
            if steps[i].get("type") == want or st.get("kind") == want:
                return i
        return None
    return len(steps) - 1


def requirement_issues(profile: dict, ep: dict, cat=None) -> list[dict]:
    from .assemble import Catalog, assemble
    cat = cat or Catalog()
    issues = []
    for f in ep.get("fields") or []:
        reqs = field_requirements(f)
        if not reqs:
            continue
        k = resolve_step(profile, f.get("source"))
        if k is None:
            issues.append({"level": "warning", "message": f"Extraction field '{f.get('name')}': its source step is not in this profile"})
            continue
        step = profile["steps"][k]
        st = cat.step_type(step.get("type"))
        try:
            r = assemble(profile, k, None, catalog=cat)
        except Exception:
            continue
        kws = {x.lower() for x in r["keywords"]}
        for req in reqs:
            if req.get("kind") == "freq" and st.get("kind") not in ("freq", "opt_freq") and "freq" not in kws and "numfreq" not in kws:
                issues.append({"level": "warning", "step": k, "message": f"Extraction field '{f.get('name')}' needs frequencies, but step {k + 1} ({step.get('name')}) has no Freq"})
            elif req.get("kind") == "tddft" and not req.get("column") and "tddft" not in (r["blocks"] or {}) and st.get("kind") != "tddft":
                issues.append({"level": "warning", "step": k, "message": f"Extraction field '{f.get('name')}' needs TDDFT states, but step {k + 1} has no %tddft"})
            elif req.get("column"):
                col = cat.columns.get(req["column"])
                if not col:
                    continue
                if col.get("type") == "dropdown":
                    e = cat.entry(col.get("library"), req["value"])
                    if e and e["orca_text"].lower() not in kws:
                        issues.append({"level": "warning", "step": k,
                                       "message": f"Extraction field '{f.get('name')}' needs {e['label']} on step {k + 1} ({step.get('name')})",
                                       "fix": {"action": "add_value", "step": k, "column": req["column"], "value": req["value"],
                                               "label": f"Add {e['label']} to step {k + 1}"}})
                else:
                    if r["chosen"].get(req["column"]) in (None, "", False):
                        issues.append({"level": "warning", "step": k,
                                       "message": f"Extraction field '{f.get('name')}' needs '{col['label']}' on step {k + 1}",
                                       "fix": {"action": "add_value", "step": k, "column": req["column"], "value": req["value"],
                                               "label": f"Turn on {col['label']} in step {k + 1}"}})
    return issues


# --------------------------------------------------------------------------- evaluation
@lru_cache(maxsize=256)
def _parse_cached(path: str, mtime: float, size: int) -> OrcaOut:
    return OrcaOut.from_file(path)


def load_out(path) -> OrcaOut | None:
    p = Path(path)
    if not p.exists():
        return None
    st = p.stat()
    return _parse_cached(str(p), st.st_mtime, st.st_size)


def out_path_for(b: dict, m: dict, k: int, subjob: str | None = None) -> Path | None:
    if b["kind"] == "external":
        return Path(m["source_file"])
    t = db.q1("SELECT * FROM tasks WHERE molecule_id=? AND step_index=?", (m["id"], k))
    if not t or not t["step_dir"]:
        return None
    from .runner import base_name
    d = Path(t["step_dir"])
    if subjob:
        d = d / subjob
    p = d / f"{base_name(m)}.out"
    return p if p.exists() else None


def eval_pattern(o: OrcaOut, pat: dict):
    v, _ = o.custom_pattern(pat.get("text", ""), bool(pat.get("regex")), pat.get("occurrence", "last"),
                            int(pat.get("number_index", 1) or 1), bool(pat.get("next_line")), bool(pat.get("ignore_case")))
    return v


def field_unit_kind(f: dict) -> str:
    if f.get("unit_kind"):
        return f["unit_kind"]
    if f.get("kind", "builtin") == "builtin" and f.get("builtin") in B:
        return B[f["builtin"]]["unit_kind"]
    return "none"


def field_shape(f: dict) -> str:
    if f.get("kind", "builtin") == "builtin" and f.get("builtin") in B:
        return B[f["builtin"]]["shape"]
    if f.get("kind") == "pattern" and (f.get("pattern") or {}).get("occurrence") == "all":
        return "table"
    if f.get("kind") == "multiwfn":
        return (f.get("multiwfn") or {}).get("shape", "scalar")
    if f.get("kind") == "fukui":
        return "table"
    return "scalar"


def extract_one(b: dict, m: dict, f: dict, ctx: dict):
    """Value of one non-formula field for one molecule: (value, error or None)."""
    kind = f.get("kind", "builtin")
    if kind == "fukui":
        return fukui(b, m, f, ctx)
    if kind == "dscf":
        return dscf_value(b, m, f, ctx)
    k = resolve_step(b["profile"], f.get("source")) if b["kind"] != "external" else 0
    if k is None:
        return None, "source step not in profile"
    path = out_path_for(b, m, k)
    if not path:
        return None, "no output yet"
    o = load_out(path)
    if o is None:
        return None, "no output"
    try:
        if kind == "builtin":
            bi = B.get(f.get("builtin"))
            if not bi:
                return None, f"unknown built-in '{f.get('builtin')}'"
            return bi["fn"](o, f.get("params") or {}, ctx), None
        if kind == "pattern":
            return eval_pattern(o, f.get("pattern") or {}), None
        if kind == "multiwfn":
            from .multiwfn import field_value
            return field_value(b, m, k, f, path)
    except (KeyError, IndexError, ValueError, TypeError, ZeroDivisionError) as e:
        return None, f"{type(e).__name__}: {e}"
    return None, f"unknown field kind '{kind}'"


# --------------------------------------------------------------------------- ΔSCF and Fukui
def dscf_value(b, m, f, ctx):
    k = resolve_step(b["profile"], f.get("source") or {"mode": "last_of_type", "value": "dscf"})
    if k is None:
        return None, "no ΔSCF step"
    gs, es, t = (load_out(out_path_for(b, m, k, s)) if out_path_for(b, m, k, s) else None for s in ("gs", "es", "t"))
    what = (f.get("params") or {}).get("value", "de")
    if not gs or not es or gs.final_energy is None or es.final_energy is None:
        return None, "ΔSCF outputs missing"
    de = (es.final_energy - gs.final_energy) * 27.211386
    if what == "de":
        return de, None
    if what == "s2":
        return (es.s2 or {}).get("s2"), None
    if what == "collapse":
        return de < 0.05, None
    if what == "pure":
        if not t or t.final_energy is None:
            return None, "no triplet sub-job"
        e_s = 2 * es.final_energy - t.final_energy
        return (e_s - gs.final_energy) * 27.211386, None
    return None, f"unknown ΔSCF value '{what}'"


def fukui(b, m, f, ctx):
    """Condensed Fukui functions from charges at N, N+1, N-1 (steps chosen in params)."""
    p = f.get("params") or {}
    scheme = p.get("scheme", "hirshfeld")
    outs = {}
    for key in ("step_n", "step_plus", "step_minus"):
        src = {"mode": "step_name", "value": p.get(key)} if not str(p.get(key, "")).isdigit() else {"mode": "step_index", "value": int(p[key])}
        k = resolve_step(b["profile"], src)
        path = out_path_for(b, m, k) if k is not None else None
        o = load_out(path) if path else None
        tab = o.charges(scheme) if o else None
        if not tab:
            return None, f"no {scheme} charges for {key} ({p.get(key)})"
        outs[key] = {r["atom"]: r["charge"] for r in tab}
        outs[key + "_el"] = {r["atom"]: r["element"] for r in tab}
    rows = []
    for a in sorted(outs["step_n"]):
        qn, qp, qm = outs["step_n"][a], outs["step_plus"].get(a), outs["step_minus"].get(a)
        if qp is None or qm is None:
            continue
        fp, fm = qn - qp, qm - qn
        rows.append({"atom": a, "element": outs["step_n_el"][a], "f_plus": fp, "f_minus": fm, "f_zero": (qm - qp) / 2,
                     "dual": fp - fm})
    return rows, None


# --------------------------------------------------------------------------- formulas
SAFE_FUNCS = {"abs": abs, "min": min, "max": max, "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
              "log10": math.log10, "round": round}
KB_EH = 3.166811563e-6  # Eh/K


class FormulaError(Exception):
    pass


def eval_formula(expr: str, mol: dict, all_rows: list[dict], fields: dict):
    """Evaluate a formula for one molecule. mol/all_rows: {'id','name','formula','values':{fid: v}}."""
    tree = ast.parse(expr, mode="eval")

    def col(name):
        if name not in fields:
            raise FormulaError(f"unknown field '{name}'")
        return [(r, r["values"].get(name)) for r in all_rows]

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.Name):
            if n.id in SAFE_FUNCS:
                return SAFE_FUNCS[n.id]
            if n.id == "pi":
                return math.pi
            if n.id not in fields:
                raise FormulaError(f"unknown field '{n.id}'")
            v = mol["values"].get(n.id)
            if v is None:
                raise FormulaError(f"'{n.id}' has no value")
            return v
        if isinstance(n, ast.BinOp):
            a, c = ev(n.left), ev(n.right)
            ops = {ast.Add: lambda x, y: x + y, ast.Sub: lambda x, y: x - y, ast.Mult: lambda x, y: x * y,
                   ast.Div: lambda x, y: x / y, ast.Pow: lambda x, y: x ** y, ast.Mod: lambda x, y: x % y}
            if type(n.op) not in ops:
                raise FormulaError("operator not allowed")
            return ops[type(n.op)](a, c)
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            if isinstance(n.op, ast.USub):
                return -v
            if isinstance(n.op, ast.UAdd):
                return v
            raise FormulaError("operator not allowed")
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name):
            fn = n.func.id
            args = n.args
            if fn in ("rel", "boltzmann", "ref", "fragsum", "atomval", "lowest"):
                if not args or not isinstance(args[0], ast.Name):
                    raise FormulaError(f"{fn}() needs a field name as first argument")
                fname = args[0].id
                if fn == "rel" or fn == "lowest":
                    vals = [v for r, v in col(fname) if isinstance(v, (int, float))]
                    comp = [v for r, v in col(fname) if isinstance(v, (int, float)) and r["formula"] == mol["formula"]]
                    if len(comp) != len(vals):
                        raise FormulaError("relative energies need the same atomic composition for all molecules "
                                           "(use relsame() to compare within each composition)")
                    if not vals:
                        raise FormulaError("no values")
                    return (ev(ast.Name(id=fname)) - min(vals)) if fn == "rel" else min(vals)
                if fn == "boltzmann":
                    T = ev(args[1]) if len(args) > 1 else 298.15
                    vals = [(r, v) for r, v in col(fname) if isinstance(v, (int, float))]
                    if any(r["formula"] != mol["formula"] for r, v in vals):
                        raise FormulaError("Boltzmann populations need the same atomic composition")
                    e0 = min(v for _, v in vals)
                    ws = [math.exp(-(v - e0) / (KB_EH * T)) for _, v in vals]
                    me = mol["values"].get(fname)
                    if me is None:
                        raise FormulaError(f"'{fname}' has no value")
                    return math.exp(-(me - e0) / (KB_EH * T)) / sum(ws)
                if fn == "ref":
                    refname = ev(args[1])
                    rr = [r for r in all_rows if r["name"] == refname]
                    if not rr:
                        raise FormulaError(f"reference molecule '{refname}' not found")
                    if rr[0]["formula"] != mol["formula"]:
                        raise FormulaError(f"{mol['name']} and {refname} have different compositions")
                    rv = rr[0]["values"].get(fname)
                    if rv is None:
                        raise FormulaError(f"reference has no '{fname}'")
                    return ev(ast.Name(id=fname)) - rv
                if fn == "fragsum":
                    frag = ev(args[1])
                    key = ev(args[2]) if len(args) > 2 else "charge"
                    tab = mol["values"].get(fname)
                    atoms = (mol.get("fragments") or {}).get(frag)
                    if atoms is None:
                        raise FormulaError(f"fragment '{frag}' is not defined for this batch")
                    if not isinstance(tab, list):
                        raise FormulaError(f"'{fname}' is not a per-atom table")
                    return sum(r.get(key) or 0 for r in tab if r.get("atom") in atoms)
                if fn == "atomval":
                    idx = int(ev(args[1]))
                    key = ev(args[2]) if len(args) > 2 else "charge"
                    tab = mol["values"].get(fname) or []
                    for r in tab:
                        if r.get("atom") == idx:
                            return r.get(key)
                    raise FormulaError(f"atom {idx} not in '{fname}'")
            if fn == "relsame":
                fname = args[0].id
                comp = [v for r, v in col(fname) if isinstance(v, (int, float)) and r["formula"] == mol["formula"]]
                return ev(ast.Name(id=fname)) - min(comp)
            if fn in SAFE_FUNCS:
                return SAFE_FUNCS[fn](*[ev(a) for a in args])
            raise FormulaError(f"function '{fn}' not allowed")
        if isinstance(n, ast.Compare) and len(n.ops) == 1:
            a, c = ev(n.left), ev(n.comparators[0])
            return {ast.Gt: a > c, ast.Lt: a < c, ast.GtE: a >= c, ast.LtE: a <= c, ast.Eq: a == c,
                    ast.NotEq: a != c}.get(type(n.ops[0]))
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        raise FormulaError(f"'{type(n).__name__}' not allowed in formulas")

    return ev(tree)


# --------------------------------------------------------------------------- flags
AUTO_FLAGS = {
    "imag_count": lambda v: "red" if isinstance(v, (int, float)) and v > 0 else None,
    "opt_converged": lambda v: "red" if v is False else None,
    "termination": lambda v: "red" if v == "error" else None,
    "s2_dev": lambda v: "orange" if isinstance(v, (int, float)) and abs(v) > 0.1 else None,
}


def flag_for(f: dict, v, err) -> list[str]:
    out = []
    if err and err not in ("no output yet",):
        out.append("red" if "composition" in err else "grey")
    b = f.get("builtin")
    if f.get("kind", "builtin") == "builtin" and b in AUTO_FLAGS and not f.get("no_auto_flag"):
        c = AUTO_FLAGS[b](v)
        if c:
            out.append(c)
    rule = f.get("flag") or {}
    if rule.get("op") and isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            x = float(rule.get("value"))
            vv = convert(v, field_unit_kind(f), f.get("unit"))
            hit = {">": vv > x, "<": vv < x, ">=": vv >= x, "<=": vv <= x, "==": vv == x, "!=": vv != x,
                   "abs>": abs(vv) > x}.get(rule["op"], False)
            if hit:
                out.append(rule.get("color", "yellow"))
        except (TypeError, ValueError):
            pass
    return out


# --------------------------------------------------------------------------- batch level
def profile_for(b: dict) -> dict:
    eid = b.get("extraction_profile_id") or "standard"
    ep = store.get_item("extraction_profiles", eid) or store.get_item("extraction_profiles", "standard") or {"fields": []}
    for i, f in enumerate(ep.get("fields") or []):
        f.setdefault("id", f"f{i + 1}")
        f.setdefault("kind", "builtin")
    return ep


def extract_batch(batch_id: int, molecule_ids: list[int] | None = None) -> dict:
    b = batches.get(batch_id)
    ep = profile_for(b)
    fields = ep.get("fields") or []
    mols = batches.molecules(batch_id)
    ctx = {"fragments": b.get("fragments") or {}, "prefer_property": bool(db.kv_get("property_file_trusted", False))}
    now = time.time()
    with db.tx() as con:
        for m in mols:
            if molecule_ids and m["id"] not in molecule_ids:
                continue
            for f in fields:
                if f["kind"] == "formula":
                    continue
                v, err = extract_one(b, m, f, ctx)
                con.execute("INSERT INTO results(batch_id, molecule_id, field_id, value, flags, updated) VALUES (?,?,?,?,?,?) "
                            "ON CONFLICT(batch_id, molecule_id, field_id) DO UPDATE SET value=excluded.value, "
                            "flags=excluded.flags, updated=excluded.updated",
                            (batch_id, m["id"], f["id"], db.j({"v": v, "err": err}), db.j(flag_for(f, v, err)), now))
    _formulas(b, ep, mols)
    if (b.get("options") or {}).get("auto_export"):
        try:
            from . import exports
            exports.write_all(batch_id)
        except Exception as e:
            db.log(batch_id, f"automatic export failed: {e}", "warning")
    return results(batch_id)


def _formulas(b, ep, mols):
    fields = {f["id"]: f for f in ep.get("fields") or []}
    rows = _rows(b["id"], mols)
    formulas = [f for f in ep.get("fields") or [] if f["kind"] == "formula"]
    now = time.time()
    for _ in range(2):          # formulas may depend on formulas: two passes
        for f in formulas:
            for r in rows:
                try:
                    v, err = eval_formula(f.get("expr", ""), r, rows, fields), None
                except FormulaError as e:
                    v, err = None, str(e)
                except (ZeroDivisionError, ValueError, TypeError, OverflowError, SyntaxError) as e:
                    v, err = None, f"{type(e).__name__}: {e}"
                r["values"][f["id"]] = v
                db.ex("INSERT INTO results(batch_id, molecule_id, field_id, value, flags, updated) VALUES (?,?,?,?,?,?) "
                      "ON CONFLICT(batch_id, molecule_id, field_id) DO UPDATE SET value=excluded.value, "
                      "flags=excluded.flags, updated=excluded.updated",
                      (b["id"], r["id"], f["id"], db.j({"v": v, "err": err}), db.j(flag_for(f, v, err)), now))


def _rows(batch_id, mols):
    b = batches.get(batch_id)
    vals = db.q("SELECT molecule_id, field_id, value FROM results WHERE batch_id=?", (batch_id,))
    by = {}
    for x in vals:
        by.setdefault(x["molecule_id"], {})[x["field_id"]] = (db.uj(x["value"], {}) or {}).get("v")
    return [{"id": m["id"], "name": m["name"], "formula": m["formula"], "values": by.get(m["id"], {}),
             "fragments": b.get("fragments") or {}} for m in mols]


def on_task_finished(batch_id: int, molecule_id: int, step_index: int):
    extract_batch(batch_id, [molecule_id])


def results(batch_id: int) -> dict:
    """Results for the UI/exports: field list, one row per molecule, sub-tables."""
    b = batches.get(batch_id)
    ep = profile_for(b)
    fields = ep.get("fields") or []
    mols = batches.molecules(batch_id)
    raw = db.q("SELECT * FROM results WHERE batch_id=?", (batch_id,))
    by = {(r["molecule_id"], r["field_id"]): r for r in raw}
    s = config.load_settings()
    dec = int(s["folders"].get("decimals", 6))
    fl = []
    for f in fields:
        uk = field_unit_kind(f)
        unit = f.get("unit") or DEFAULT_UNIT.get(uk, "")
        fl.append({"id": f["id"], "name": f.get("name") or f["id"], "unit": unit, "unit_kind": uk,
                   "shape": field_shape(f), "kind": f["kind"], "decimals": f.get("decimals", dec)})
    rows, tables = [], {x["id"]: [] for x in fl if x["shape"] == "table"}
    tasks = db.q("SELECT molecule_id, step_index, status FROM tasks WHERE batch_id=?", (batch_id,))
    tstat = {}
    for t in tasks:
        tstat.setdefault(t["molecule_id"], []).append(t["status"])
    for m in mols:
        row = {"molecule_id": m["id"], "name": m["name"], "formula": m["formula"], "charge": m["charge"], "mult": m["mult"],
               "values": {}, "status": "failed" if "failed" in tstat.get(m["id"], []) else ""}
        for f, meta in zip(fields, fl):
            r = by.get((m["id"], f["id"]))
            val = (db.uj(r["value"], {}) or {}) if r else {}
            v, err = val.get("v"), val.get("err")
            flags = db.uj(r["flags"], []) if r else []
            if meta["shape"] == "table":
                if isinstance(v, list):
                    for item in v:
                        tables[f["id"]].append(dict({"molecule": m["name"]}, **_conv_row(item, meta)))
                    row["values"][f["id"]] = {"v": f"{len(v)} rows", "err": err, "flags": flags}
                else:
                    row["values"][f["id"]] = {"v": None, "err": err, "flags": flags}
                continue
            row["values"][f["id"]] = {"v": convert(v, meta["unit_kind"], meta["unit"]), "raw": v, "err": err, "flags": flags}
        rows.append(row)
    return {"fields": fl, "rows": rows, "tables": tables, "profile": {"id": ep.get("id"), "name": ep.get("name")}}


ENERGY_KEYS = {"energy_ev": "excitation"}


def _conv_row(item: dict, meta: dict) -> dict:
    """Convert unit-bearing columns of table rows (energies of orbitals/states stay in their natural units)."""
    out = dict(item)
    if meta["unit_kind"] == "excitation" and "energy_ev" in out and meta["unit"] not in ("eV", ""):
        out[f"energy_{meta['unit']}"] = convert(out["energy_ev"], "excitation", meta["unit"])
    return out


def builtin_catalog() -> list[dict]:
    return [{k: v for k, v in b.items() if k != "fn"} for b in B.values()]
