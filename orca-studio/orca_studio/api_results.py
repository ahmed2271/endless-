"""API: extraction, results, exports and analysing folders of .out files (phase 2)."""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse, Response

from . import batches, db, exports, extraction, store
from .parsers.orca_out import OrcaOut

router = APIRouter()


def err(msg, code=400):
    raise HTTPException(status_code=code, detail=msg)


@router.get("/api/extraction/builtins")
def builtins():
    return extraction.builtin_catalog()


@router.get("/api/extraction/units")
def units():
    return {k: list(v) for k, v in extraction.UNITS.items()}


@router.get("/api/batches/{bid}/extraction_setup")
def extraction_setup(bid: int):
    """Which extraction profile each step uses, and the optional whole-batch profile."""
    b = batches.get(bid)
    if not b:
        err("batch not found", 404)
    if b["kind"] == "external":
        return {"external": True, "extra": b.get("extraction_profile_id")}
    ov = (b.get("options") or {}).get("step_extraction") or {}
    ids = extraction.step_extraction_ids(b["profile"], ov)
    steps = b["profile"].get("steps") or []
    return {"external": False, "extra": b.get("extraction_profile_id") or "",
            "steps": [{"index": k, "name": st.get("name"), "type": st.get("type"), "profile": ids[k],
                       "chosen_here": str(k) in ov} for k, st in enumerate(steps)]}


@router.get("/api/batches/{bid}/results")
def batch_results(bid: int):
    if not batches.get(bid):
        err("batch not found", 404)
    return extraction.results(bid)


@router.post("/api/batches/{bid}/extract")
def batch_extract(bid: int, data: dict = Body(default={})):
    b = batches.get(bid)
    if not b:
        err("batch not found", 404)
    if "extraction_profile_id" in data:
        db.ex("UPDATE batches SET extraction_profile_id=? WHERE id=?", (data["extraction_profile_id"] or None, bid))
    if "step_extraction" in data:
        opts = b.get("options") or {}
        opts["step_extraction"] = {str(k): v for k, v in (data["step_extraction"] or {}).items()}
        db.ex("UPDATE batches SET options=? WHERE id=?", (db.j(opts), bid))
    db.ex("DELETE FROM results WHERE batch_id=?", (bid,))
    extraction._parse_cached.cache_clear()
    return extraction.extract_batch(bid)


@router.get("/api/batches/{bid}/export/{kind}")
def batch_export(bid: int, kind: str, save: bool = False):
    b = batches.get(bid)
    if not b:
        err("batch not found", 404)
    pname = extraction.profile_for(b).get("name")
    if kind == "csv":
        data, mt, name = exports.csv_text(bid).encode(), "text/csv", exports.file_name(b, "csv", pname)
    elif kind == "xlsx":
        data, mt, name = exports.xlsx_bytes(bid), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", exports.file_name(b, "xlsx", pname)
    elif kind == "geometries":
        data, mt, name = exports.geometries_zip(bid), "application/zip", f"{store.slugify(b['name'])}_final_geometries.zip"
    elif kind == "si":
        data, mt, name = exports.si_text(bid).encode(), "text/plain", f"{store.slugify(b['name'])}_SI.txt"
    elif kind == "citations":
        from .multiwfn import citation_report
        data, mt, name = citation_report(bid).encode(), "text/plain", f"{store.slugify(b['name'])}_citations.txt"
    else:
        err("unknown export", 404)
    if save:
        p = exports.export_dir(b) / name
        p.write_bytes(data)
        return {"ok": True, "path": str(p)}
    return Response(data, media_type=mt, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/api/batches/{bid}/charges/{mid}")
def charge_export(bid: int, mid: int, field: str, fmt: str = "pqr"):
    if fmt not in ("pqr", "mol2"):
        err("format must be pqr or mol2")
    m = db.q1("SELECT name FROM molecules WHERE id=?", (mid,))
    txt = exports.charge_file(bid, mid, field, fmt)
    return Response(txt, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{m["name"]}_{field}.{fmt}"'})


@router.post("/api/batches/{bid}/save_file")
def save_export_file(bid: int, data: dict = Body(...)):
    """Save text produced in the browser (spectrum CSV, SVG) into the batch results folder."""
    b = batches.get(bid)
    name = re.sub(r"[^A-Za-z0-9._+-]+", "_", data["name"])
    p = exports.export_dir(b) / name
    if data.get("base64"):
        import base64
        p.write_bytes(base64.b64decode(data["base64"].split(",", 1)[-1]))
    else:
        p.write_text(data.get("text", ""))
    return {"ok": True, "path": str(p)}


# --------------------------------------------------------------------------- pattern tester
@router.get("/api/extraction/sample_outs")
def sample_outs(limit: int = 200):
    out = []
    for r in db.q("SELECT out_file FROM runs WHERE status IN ('done','failed') ORDER BY id DESC LIMIT ?", (limit,)):
        if r["out_file"] and Path(r["out_file"]).exists() and r["out_file"] not in out:
            out.append(r["out_file"])
    for m in db.q("SELECT source_file FROM molecules m JOIN batches b ON b.id=m.batch_id WHERE b.kind='external' LIMIT 100"):
        if m["source_file"] not in out:
            out.append(m["source_file"])
    return out


def _load_sample(path: str | None, upload: bytes | None) -> OrcaOut:
    if upload:
        return OrcaOut(upload.decode("utf-8", errors="replace"))
    if not path:
        err("choose a sample .out file")
    from .main import _allowed
    p = Path(path)
    if not _allowed(p) or not p.exists():
        err("file not accessible", 403)
    return OrcaOut.from_file(p)


@router.post("/api/extraction/test")
async def test_field(field: str = Form(...), path: str = Form(""), file: UploadFile | None = File(None)):
    """Evaluate a pattern or built-in field on a sample .out and show where it matched."""
    import json
    f = json.loads(field)
    o = _load_sample(path, await file.read() if file else None)
    hits, value, error = [], None, None
    try:
        if f.get("kind") == "pattern":
            pat = f.get("pattern") or {}
            value, used = o.custom_pattern(pat.get("text", ""), bool(pat.get("regex")), pat.get("occurrence", "last"),
                                           int(pat.get("number_index", 1) or 1), bool(pat.get("next_line")),
                                           bool(pat.get("ignore_case")))
            hits = used
            if value is None:
                error = "no match" if not used else "matched text, but no number at that position"
        elif f.get("kind", "builtin") == "builtin":
            bi = extraction.B.get(f.get("builtin"))
            if not bi:
                err("unknown built-in")
            value = bi["fn"](o, f.get("params") or {}, {"fragments": {}})
        else:
            error = "only built-in and pattern fields can be tested on a single file"
    except re.error as e:
        error = f"bad regular expression: {e}"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    ctx = []
    for i in hits[:20]:
        lo, hi = max(0, i - 2), min(len(o.lines), i + 3)
        ctx.append({"line": i + 1, "context": [{"n": j + 1, "text": o.lines[j], "hit": j == i} for j in range(lo, hi)]})
    if isinstance(value, list) and len(value) > 200:
        value = value[:200]
    uk = extraction.field_unit_kind(f)
    return {"value": value, "converted": extraction.convert(value, uk, f.get("unit")) if not isinstance(value, list) else None,
            "error": error, "hits": ctx}


# --------------------------------------------------------------------------- analyse a folder
@router.post("/api/analyze")
def analyze(data: dict = Body(...)):
    """Run an extraction profile on any folder of .out files, even ones the app did not create."""
    folder = Path(data["folder"]).expanduser()
    if not folder.is_dir():
        err("folder not found")
    outs = sorted(p for p in folder.rglob("*.out") if not re.search(r"\.attempt\d+\.out$", p.name)
                  and re.search(r"O\s+R\s+C\s+A|ORCA", p.read_text(errors="replace")[:20000]))
    if not outs:
        err("no ORCA .out files found in that folder")
    name = data.get("name") or folder.name
    b = batches.create(name, None, None, data.get("extraction_profile_id") or "standard", kind="external", folder=str(folder))
    with db.tx() as con:
        for i, p in enumerate(outs):
            o = OrcaOut.from_file(p)
            g = o.final_geometry or []
            from .elements import Z, hill_formula
            formula = hill_formula([a[0] for a in g]) if g else ""
            rel = p.relative_to(folder)
            mname = str(rel.with_suffix("")).replace("/", "__") if len(rel.parts) > 1 else p.stem
            ch = o.charge or 0
            con.execute("INSERT INTO molecules(batch_id, name, dirname, formula, charge, mult, natoms, nelectrons, source_file, "
                        "warnings, order_idx) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (b["id"], mname, store.slugify(mname), formula, ch, o.mult or 1, len(g),
                         sum(Z.get(a[0], 0) for a in g) - ch, str(p), "[]", i))
    batches.set_status(b["id"], "done")
    extraction.extract_batch(b["id"])
    return {"id": b["id"], "files": len(outs)}
