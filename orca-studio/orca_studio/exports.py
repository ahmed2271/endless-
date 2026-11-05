"""Exports (section 13): CSV, Excel, final geometries, Supporting Information, charge files."""
from __future__ import annotations

import csv
import io
import time
import zipfile
from pathlib import Path

from . import batches, config, db, store
from .extraction import load_out, out_path_for, results
from .molecules import write_xyz


def export_dir(b: dict) -> Path:
    s = config.load_settings()["folders"]
    if s.get("exports_mode") == "central" and s.get("exports_central"):
        d = Path(s["exports_central"]).expanduser()
    else:
        d = Path(b["folder"]) / "results"
    d.mkdir(parents=True, exist_ok=True)
    return d


def file_name(b: dict, ext: str, profile_name: str | None = None) -> str:
    pat = config.load_settings()["folders"].get("export_pattern") or "{batch}_{profile}_{date}.csv"
    stem = pat.rsplit(".", 1)[0] if "." in pat else pat
    name = stem.format(batch=store.slugify(b["name"]), profile=store.slugify(profile_name or b.get("extraction_profile_id") or "results"),
                       date=time.strftime("%Y%m%d"))
    return f"{name}.{ext}"


def _fmt(v, dec):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float):
        return f"{v:.{dec}f}"
    return "" if v is None else str(v)


def header(f) -> str:
    return f"{f['name']} ({f['unit']})" if f.get("unit") else f["name"]


def csv_text(batch_id: int) -> str:
    r = results(batch_id)
    s = config.load_settings()["folders"]
    sep = s.get("csv_separator", ",")
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=sep)
    scal = [f for f in r["fields"] if f["shape"] != "table"]
    w.writerow(["Molecule", "Formula", "Charge", "Mult"] + [header(f) for f in scal])
    for row in r["rows"]:
        w.writerow([row["name"], row["formula"], row["charge"], row["mult"]] +
                   [_fmt(row["values"][f["id"]].get("v"), f["decimals"]) for f in scal])
    text = buf.getvalue()
    if sep == ";":
        # semicolon CSVs are for locales that use a decimal comma
        pass
    return text


def xlsx_bytes(batch_id: int) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    r = results(batch_id)
    fills = {"red": "FDE2DF", "orange": "FEEFD6", "yellow": "FEF9C3", "blue": "DBEAFE", "grey": "EEEEEE"}
    wb = Workbook()
    ws = wb.active
    ws.title = "Results"
    scal = [f for f in r["fields"] if f["shape"] != "table"]
    ws.append(["Molecule", "Formula", "Charge", "Mult"] + [header(f) for f in scal])
    for c in ws[1]:
        c.font = Font(bold=True)
    for i, row in enumerate(r["rows"], start=2):
        ws.append([row["name"], row["formula"], row["charge"], row["mult"]] +
                  [_xl(row["values"][f["id"]].get("v")) for f in scal])
        for j, f in enumerate(scal, start=5):
            fl = row["values"][f["id"]].get("flags") or []
            cell = ws.cell(row=i, column=j)
            if fl:
                cell.fill = PatternFill("solid", fgColor=fills.get(fl[-1], "FEF9C3"))
            if isinstance(cell.value, float):
                cell.number_format = "0." + "0" * int(f["decimals"]) if int(f["decimals"]) > 0 else "0"
    for j in range(1, len(scal) + 5):
        ws.column_dimensions[get_column_letter(j)].width = 16
    used = {"Results"}
    for f in r["fields"]:
        if f["shape"] != "table":
            continue
        rows = r["tables"].get(f["id"]) or []
        name = _sheet_name(f["name"], used)
        sh = wb.create_sheet(name)
        cols = []
        for x in rows:
            for k in x:
                if k not in cols and not isinstance(x[k], (list, dict)):
                    cols.append(k)
        sh.append(cols or ["(no data)"])
        for c in sh[1]:
            c.font = Font(bold=True)
        for x in rows:
            sh.append([_xl(x.get(k)) for k in cols])
    meta = wb.create_sheet("About")
    b = batches.get(batch_id)
    for k, v in (("Batch", b["name"]), ("Folder", b["folder"]), ("Calculation profile", f"{b.get('calc_profile_id')} v{b.get('calc_profile_version')}"),
                 ("Extraction profile", r["profile"].get("name")), ("Exported", time.strftime("%Y-%m-%d %H:%M"))):
        meta.append([k, v])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _xl(v):
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float, str)) or v is None:
        return v
    return str(v)


def _sheet_name(name: str, used: set) -> str:
    base = "".join(ch for ch in name if ch not in '[]:*?/\\')[:28] or "Table"
    n, cand = 2, base
    while cand in used:
        cand = f"{base[:25]}_{n}"
        n += 1
    used.add(cand)
    return cand


def final_geometry(b, m):
    """Final geometry of the last finished step: ORCA's .xyz, else the last block in the .out."""
    from .runner import base_name
    if b["kind"] == "external":
        o = load_out(m["source_file"])
        return o.final_geometry if o else None
    from .molecules import parse_xyz_text
    for k in range(len(b["profile"].get("steps") or []) - 1, -1, -1):
        t = db.q1("SELECT * FROM tasks WHERE molecule_id=? AND step_index=?", (m["id"], k))
        if t and t["status"] == "done" and t["step_dir"]:
            p = Path(t["step_dir"]) / f"{base_name(m)}.xyz"
            if p.exists():
                try:
                    return parse_xyz_text(p.read_text(), m["name"])["atoms"]
                except Exception:
                    pass
            o = load_out(Path(t["step_dir"]) / f"{base_name(m)}.out")
            if o and o.final_geometry:
                return o.final_geometry
    return None


def geometries_zip(batch_id: int) -> bytes:
    b = batches.get(batch_id)
    buf = io.BytesIO()
    multi = []
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for m in batches.molecules(batch_id):
            g = final_geometry(b, m)
            if not g:
                continue
            txt = write_xyz(g, f"{m['name']} charge={m['charge']} mult={m['mult']}")
            z.writestr(f"{m['name']}.xyz", txt)
            multi.append(txt)
        z.writestr(f"{store.slugify(b['name'])}_all.xyz", "".join(multi))
    return buf.getvalue()


def si_text(batch_id: int) -> str:
    """Supporting Information: coordinates, energies and imaginary-frequency count per molecule."""
    b = batches.get(batch_id)
    lines = [f"Supporting Information: {b['name']}", f"Generated by ORCA Studio on {time.strftime('%Y-%m-%d')}", ""]
    for m in batches.molecules(batch_id):
        steps = b["profile"].get("steps") or [{}]
        info = {}
        for k in range(len(steps) - 1, -1, -1):
            p = out_path_for(b, m, k)
            o = load_out(p) if p else None
            if not o:
                continue
            if "E" not in info and o.final_energy is not None:
                info["E"] = (o.final_energy, steps[k].get("name", f"step {k + 1}") if b["kind"] != "external" else "", " ".join(o.keywords))
            if "thermo" not in info and o.thermo:
                info["thermo"] = o.thermo
                info["nimag"] = o.imaginary_count(0)
            if b["kind"] == "external":
                break
        g = final_geometry(b, m) or []
        lines.append("=" * 72)
        lines.append(f"{m['name']}   {m['formula']}   charge {m['charge']}   multiplicity {m['mult']}")
        if "E" in info:
            e, sname, kw = info["E"]
            lines.append(f"Method: {kw}")
            lines.append(f"E(electronic)        = {e:.8f} Eh   ({sname})")
        t = info.get("thermo")
        if t:
            for key, lab in (("zpe", "ZPE"), ("total_enthalpy", "H"), ("total_gibbs", "G"), ("gibbs_correction", "G - E(el)")):
                if t.get(key) is not None:
                    lines.append(f"{lab:<20s} = {t[key]:.8f} Eh")
            lines.append(f"Imaginary frequencies = {info.get('nimag')}")
        lines.append(f"Cartesian coordinates (Å), {len(g)} atoms:")
        for s, x, y, z in g:
            lines.append(f"  {s:<3s}{x:14.6f}{y:14.6f}{z:14.6f}")
        lines.append("")
    return "\n".join(lines)


def charge_file(batch_id: int, molecule_id: int, field_id: str, fmt: str) -> str:
    """.pqr or .mol2 of a molecule with charges from a per-atom charge field."""
    b = batches.get(batch_id)
    m = db.q1("SELECT * FROM molecules WHERE id=?", (molecule_id,))
    g = final_geometry(b, m) or []
    r = db.q1("SELECT value FROM results WHERE batch_id=? AND molecule_id=? AND field_id=?", (batch_id, molecule_id, field_id))
    tab = (db.uj(r["value"], {}) or {}).get("v") if r else None
    q = {x["atom"]: x.get("charge", 0.0) for x in tab} if isinstance(tab, list) else {}
    radii = {"H": 1.10, "C": 1.70, "N": 1.55, "O": 1.52, "F": 1.47, "P": 1.80, "S": 1.80, "Cl": 1.75, "Br": 1.85, "I": 1.98}
    if fmt == "pqr":
        out = [f"REMARK  {m['name']} charges from field {field_id}"]
        for i, (s, x, y, z) in enumerate(g):
            out.append(f"ATOM  {i + 1:5d} {s:>2s}{i + 1:<2d} MOL     1    {x:8.3f}{y:8.3f}{z:8.3f} {q.get(i, 0.0):7.4f} {radii.get(s, 1.8):6.3f}")
        out.append("END")
        return "\n".join(out) + "\n"
    # mol2
    out = ["@<TRIPOS>MOLECULE", m["name"], f"{len(g)} 0 0 0 0", "SMALL", "USER_CHARGES", "", "@<TRIPOS>ATOM"]
    for i, (s, x, y, z) in enumerate(g):
        out.append(f"{i + 1:7d} {s}{i + 1:<6d} {x:10.4f} {y:10.4f} {z:10.4f} {s:<5s} 1 MOL {q.get(i, 0.0):10.4f}")
    return "\n".join(out) + "\n"


def write_all(batch_id: int) -> list[str]:
    """Write CSV and Excel into the export folder (used by the automatic re-export option)."""
    b = batches.get(batch_id)
    r = results(batch_id)
    d = export_dir(b)
    pname = r["profile"].get("name")
    p1 = d / file_name(b, "csv", pname)
    p1.write_text(csv_text(batch_id))
    p2 = d / file_name(b, "xlsx", pname)
    p2.write_bytes(xlsx_bytes(batch_id))
    return [str(p1), str(p2)]
