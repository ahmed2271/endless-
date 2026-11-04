"""Validation before a batch runs (section 6.7)."""
from __future__ import annotations

import os
from pathlib import Path

from . import config
from .assemble import Catalog, assemble, cell_value, column_applies, is_blank
from .elements import parse_ranges
from .molecules import parity_ok


def _issue(level, message, step=None, molecule=None, fix=None):
    d = {"level": level, "message": message}
    if step is not None:
        d["step"] = step
    if molecule is not None:
        d["molecule"] = molecule
    if fix:
        d["fix"] = fix
    return d


def program_ok(path: str) -> bool:
    return bool(path) and os.path.isfile(os.path.expanduser(path)) and os.access(os.path.expanduser(path), os.X_OK)


def xtb_available(settings: dict) -> bool:
    if program_ok(settings["programs"].get("xtb", "")):
        return True
    # ORCA ships xtb as 'otool_xtb' next to the orca binary  [VERIFY how ORCA 6.0.1 finds xtb]
    return program_ok(str(config.orca_dir(settings) / "otool_xtb"))


def validate(profile: dict, molecules: list[dict] | None = None, extraction_profile: dict | None = None,
             settings: dict | None = None, catalog: Catalog | None = None) -> list[dict]:
    s = settings or config.load_settings()
    cat = catalog or Catalog()
    issues: list[dict] = []
    steps = profile.get("steps") or []
    if not steps:
        issues.append(_issue("error", "The profile has no steps"))
        return issues

    basis_lists = ["basis_sets", "relativistic_basis"]
    basis_texts = {}
    for lid in basis_lists:
        for e in (cat.libs.get(lid) or {}).get("entries", []):
            if e["orca_text"]:
                basis_texts[e["orca_text"].lower()] = e
    excl = {}
    for lid, lib in cat.libs.items():
        for e in lib.get("entries", []):
            for t in e.get("tags") or []:
                if str(t).startswith("exclusive:") and e["orca_text"]:
                    for tok in e["orca_text"].split():
                        excl[tok.lower()] = (t.split(":", 1)[1], e["label"])

    if not program_ok(s["programs"].get("orca", "")):
        issues.append(_issue("error", f"ORCA not found at {s['programs'].get('orca')}: fix it in Settings"))
    if not s["programs"].get("openmpi_bin"):
        if any(assemble(profile, i, None, catalog=cat, settings=s)["nprocs"] > 1 for i in range(len(steps))):
            issues.append(_issue("warning", "OpenMPI bin folder is not set: parallel (PAL > 1) jobs will fail"))

    for i, step in enumerate(steps):
        label = f"Step {i + 1} ({step.get('name') or step.get('type')})"
        stype = cat.step_type(step.get("type"))
        if step.get("type") not in cat.step_types:
            issues.append(_issue("error", f"{label}: unknown step type '{step.get('type')}'", i))
            continue
        r = assemble(profile, i, None, catalog=cat, settings=s)
        for w in r["warnings"]:
            issues.append(_issue("warning", f"{label}: {w}", i))
        if r["manual"]:
            issues.append(_issue("warning", f"{label}: uses a manually edited input (checks are limited)", i))
            continue
        kw = [k.lower() for k in r["keywords"]]
        bases = [k for k in kw if k in basis_texts]
        if len(bases) > 1:
            issues.append(_issue("error", f"{label}: two basis sets on the keyword line ({', '.join(bases)})", i))
        # method-based conflicts
        chosen = r["chosen"]
        method_ids = chosen.get("method")
        method = cat.entry(cat.columns.get("method", {}).get("library"), method_ids) if method_ids else None
        if method is None and stype.get("kind") not in ("custom",) and not any(
                k in kw for k in ("hf", "dlpno-ccsd(t)")):
            issues.append(_issue("warning", f"{label}: no method chosen (ORCA's default is HF)", i))
        if method:
            tags = method.get("tags") or []
            if "includes_dispersion" in tags:
                disp = chosen.get("dispersion")
                de = cat.entry(cat.columns.get("dispersion", {}).get("library"), disp) if disp else None
                if de and de.get("orca_text"):
                    issues.append(_issue("error", f"{label}: {method['label']} already includes dispersion; "
                                                  f"remove {de['label']}", i))
            if "includes_basis" in tags and bases:
                issues.append(_issue("error", f"{label}: {method['label']} brings its own basis; remove the basis set", i))
            if "includes_basis" not in tags and not bases and stype.get("kind") not in ("xtb", "custom") \
                    and not any(k.endswith("-3c") for k in kw):
                issues.append(_issue("warning", f"{label}: no basis set chosen", i))
        groups: dict[str, list[str]] = {}
        for k in kw:
            if k in excl:
                groups.setdefault(excl[k][0], []).append(excl[k][1])
        for g, labs in groups.items():
            if len(set(labs)) > 1:
                issues.append(_issue("error", f"{label}: mutually exclusive keywords: {', '.join(sorted(set(labs)))}", i))
        # required programs from tags of chosen entries + step type
        req = set(t.split(":", 1)[1] for t in stype.get("tags") or [] if str(t).startswith("requires:"))
        for cid, v in chosen.items():
            col = cat.columns.get(cid, {})
            if col.get("type") != "dropdown":
                continue
            for eid in (v if isinstance(v, list) else [v]):
                e = cat.entry(col.get("library"), eid)
                if e:
                    req |= set(t.split(":", 1)[1] for t in e.get("tags") or [] if str(t).startswith("requires:"))
        if "xtb" in req and not xtb_available(s):
            issues.append(_issue("warning", f"{label}: needs xtb, but no xtb binary is set and otool_xtb was not "
                                            f"found in the ORCA folder", i))
        if "nbo" in req and not program_ok(s["programs"].get("nbo", "")):
            issues.append(_issue("error", f"{label}: NPA/NBO needs the NBO program (Settings → NBO)", i))
        for sc in step.get("scripts") or []:
            from . import store
            sd = store.get_item("scripts", sc)
            if not sd:
                issues.append(_issue("error", f"{label}: script '{sc}' is not registered", i))
            else:
                path = s.get("script_paths", {}).get(sd.get("path_setting") or sd["id"]) or sd.get("path", "")
                if not path or not os.path.isfile(os.path.expanduser(path)):
                    issues.append(_issue("error", f"{label}: script '{sd.get('name', sc)}' path is not set in Settings", i))

        # per molecule checks
        basis_entry = None
        bid = chosen.get("basis")
        if bid:
            basis_entry = cat.entry(cat.columns.get("basis", {}).get("library"), bid)
        for m in molecules or []:
            rr = assemble(profile, i, m, catalog=cat, settings=s)
            nel = m["nelectrons"] - (rr["charge"] - m["charge"])
            if not parity_ok(nel, rr["mult"]):
                issues.append(_issue("error", f"{label}: {m['name']} has {nel} electrons; multiplicity "
                                              f"{rr['mult']} is impossible", i, m["name"]))
            if basis_entry and basis_entry.get("elements"):
                cover = parse_ranges(basis_entry["elements"])
                syms = {a[0] for a in m.get("atoms") or []}
                missing = sorted(syms - cover)
                if missing:
                    issues.append(_issue("error", f"{label}: {basis_entry['label']} does not cover "
                                                  f"{', '.join(missing)} in {m['name']}", i, m["name"]))

        cubes = (step.get("workflow") or {}).get("cubes") or {}
        if cubes.get("orbitals") or cubes.get("densities"):
            if not program_ok(config.utility_path("orca_plot", s)):
                issues.append(_issue("warning", f"{label}: cubes requested but orca_plot was not found", i))
        if cubes.get("mep"):
            mep = s.get("script_paths", {}).get("mep", "")
            from . import store as _st
            esp = _st.get_entry("orca_plot", "esp") or {}
            if not (mep and os.path.isfile(os.path.expanduser(mep))) and (esp.get("hidden") or "unverified" in (esp.get("tags") or [])):
                issues.append(_issue("warning", f"{label}: MEP requested, but mep.py is not set in Settings and the "
                                                f"orca_plot ESP route is not confirmed (run ORCA checks)", i))

    if extraction_profile and any(f.get("kind") == "multiwfn" for f in extraction_profile.get("fields") or []):
        if not program_ok(s["programs"].get("multiwfn", "")):
            issues.append(_issue("error", "The extraction profile uses Multiwfn results, but Multiwfn is not set in Settings"))
        if not program_ok(config.utility_path("orca_2mkl", s)):
            issues.append(_issue("error", "Multiwfn recipes need orca_2mkl (ORCA folder) to make .molden files"))
    if extraction_profile:
        from .extraction import requirement_issues
        issues.extend(requirement_issues(profile, extraction_profile, cat))
    return issues
