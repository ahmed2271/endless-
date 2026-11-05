"""Phase 2: extraction profiles, formulas, flags, exports, analysing a folder, pattern tester."""
import io
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import DATA, wait_for


def _run_batch(profile="preopt_optfreq_b3lyp", files=("water.xyz", "methanol.xyz", "formaldehyde.inp"), ep=None):
    from orca_studio import batches
    from orca_studio.runner import Runner
    b = batches.create("ext", profile, None, ep)
    batches.add_molecules(b["id"], [(n, (DATA / "structures" / n).read_bytes()) for n in files])
    r = Runner()
    r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 90)
    finally:
        r.stop()
    return b


def test_standard_profile_and_exports(studio):
    from orca_studio import exports, extraction
    b = _run_batch()
    res = extraction.results(b["id"])
    ids = [f["id"] for f in res["fields"]]
    assert {"E", "G", "nimag", "HOMO", "q_hirshfeld", "q_mbis"} <= set(ids)
    rows = {r["name"]: r for r in res["rows"]}
    w = rows["water"]["values"]
    assert w["E"]["v"] < -40 and w["nimag"]["v"] == 0 and w["optconv"]["v"] is True
    assert w["ZPE"]["v"] > 0                         # shown in kcal/mol
    assert w["relG"]["v"] == pytest.approx(0.0)      # only molecule with its composition
    hw = [t for t in res["tables"]["q_hirshfeld"] if t["molecule"] == "water"]
    mw = [t for t in res["tables"]["q_mbis"] if t["molecule"] == "water"]
    assert len(hw) == 3 and len(mw) == 3
    assert sum(t["charge"] for t in hw) == pytest.approx(0, abs=1e-4) and mw[0]["population"] > 8
    # CSV + Excel
    csv = exports.csv_text(b["id"])
    assert csv.splitlines()[0].startswith("Molecule,Formula,Charge,Mult,Final energy (Eh)")
    assert len(csv.strip().splitlines()) == 4
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(exports.xlsx_bytes(b["id"])))
    assert {"Results", "Hirshfeld charges", "MBIS charges"} <= set(wb.sheetnames)
    assert "Molecule" in exports.si_text(b["id"]) or "Cartesian" in exports.si_text(b["id"])
    import zipfile
    z = zipfile.ZipFile(io.BytesIO(exports.geometries_zip(b["id"])))
    assert {"water.xyz", "methanol.xyz", "formaldehyde.xyz"} <= set(z.namelist())
    assert exports.charge_file(b["id"], rows["water"]["molecule_id"], "q_hirshfeld", "pqr").count("ATOM") == 3


def test_formulas_flags_and_units(studio):
    from orca_studio import db, extraction, store
    ep = {"name": "F", "fields": [
        {"id": "E", "name": "E", "kind": "builtin", "builtin": "final_energy", "unit": "kcal/mol"},
        {"id": "Ekj", "name": "E kJ", "kind": "builtin", "builtin": "final_energy", "unit": "kJ/mol"},
        {"id": "rel", "name": "rel", "kind": "formula", "expr": "rel(E)", "unit_kind": "energy", "unit": "kcal/mol"},
        {"id": "rs", "name": "relsame", "kind": "formula", "expr": "relsame(E)", "unit_kind": "energy", "unit": "kcal/mol"},
        {"id": "pop", "name": "pop", "kind": "formula", "expr": "boltzmann(E, 298.15)"},
        {"id": "big", "name": "flagged", "kind": "builtin", "builtin": "dipole", "flag": {"op": ">", "value": 0.1, "color": "blue"}},
        {"id": "zpe", "name": "ZPE", "kind": "pattern", "pattern": {"text": "Zero point energy", "occurrence": "last", "number_index": 1},
         "source": {"mode": "last_of_type", "value": "opt_freq"}, "unit_kind": "energy", "unit": "kcal/mol"},
    ]}
    store.save_item("extraction_profiles", dict(ep, id="ftest"))
    b = _run_batch(ep="ftest")
    res = extraction.results(b["id"])
    rows = {r["name"]: r["values"] for r in res["rows"]}
    w = rows["water"]
    assert w["Ekj"]["raw"] == w["E"]["raw"]
    assert w["Ekj"]["v"] == pytest.approx(w["E"]["raw"] * 2625.4996)
    assert w["E"]["v"] == pytest.approx(w["E"]["raw"] * 627.5095)
    # different compositions: rel() refuses, relsame() works
    assert w["rel"]["v"] is None and "composition" in w["rel"]["err"]
    assert w["rs"]["v"] == pytest.approx(0)
    assert "composition" in w["pop"]["err"]
    assert "blue" in w["big"]["flags"]
    assert w["zpe"]["v"] > 1


def test_formula_engine_directly():
    from orca_studio.extraction import FormulaError, eval_formula
    rows = [{"id": 1, "name": "a", "formula": "C2H6O", "values": {"G": -100.0, "q": [{"atom": 0, "charge": -0.5}, {"atom": 1, "charge": 0.2}]}, "fragments": {"A": [0, 1]}},
            {"id": 2, "name": "b", "formula": "C2H6O", "values": {"G": -100.001}, "fragments": {"A": [0, 1]}}]
    f = {"G": {}, "q": {}}
    assert eval_formula("rel(G)", rows[0], rows, f) == pytest.approx(0.001)
    p = eval_formula("boltzmann(G, 298.15)", rows[1], rows, f)
    assert 0.5 < p < 1
    assert eval_formula("ref(G, 'b')", rows[0], rows, f) == pytest.approx(0.001)
    assert eval_formula("fragsum(q, 'A')", rows[0], rows, f) == pytest.approx(-0.3)
    with pytest.raises(FormulaError):
        eval_formula("__import__('os')", rows[0], rows, f)
    with pytest.raises(FormulaError):
        eval_formula("G.real", rows[0], rows, f)


def test_requirements_offer_fix(studio):
    from orca_studio import store, validate
    p = store.get_item("calc_profiles", "preopt_optfreq_b3lyp")
    ep = {"fields": [{"id": "m", "name": "MBIS", "kind": "builtin", "builtin": "charges", "params": {"scheme": "mbis"}, "source": {"mode": "last"}}]}
    assert not [i for i in validate.validate(p, None, ep) if i.get("fix")]          # starter profile already has MBIS
    ep = {"fields": [{"id": "c", "name": "CHELPG", "kind": "builtin", "builtin": "charges", "params": {"scheme": "chelpg"}, "source": {"mode": "last"}}]}
    issues = validate.validate(p, None, ep)
    fix = [i for i in issues if i.get("fix")]
    assert fix and fix[0]["fix"]["value"] == "chelpg" and fix[0]["fix"]["step"] == 1
    from orca_studio.main import app
    c = TestClient(app)
    r = c.post("/api/calc_profiles/preopt_optfreq_b3lyp/fix", json={"fix": fix[0]["fix"]}).json()
    assert r["version"] == p["version"] + 1 and r["steps"][1]["values"]["populations"] == ["hirshfeld", "mbis", "chelpg"]
    assert not [i for i in validate.validate(r, None, ep) if i.get("fix")]


def test_analyze_folder_and_pattern_tester(studio, tmp_path):
    from orca_studio.main import app
    folder = tmp_path / "old_outs"
    (folder / "sub").mkdir(parents=True)
    shutil.copy(DATA / "synthetic" / "water_optfreq.out", folder / "water.out")
    shutil.copy(DATA / "synthetic" / "methanol_tddft.out", folder / "sub" / "methanol.out")
    c = TestClient(app)
    r = c.post("/api/analyze", json={"folder": str(folder), "extraction_profile_id": "tddft"})
    assert r.status_code == 200, r.text
    res = c.get(f"/api/batches/{r.json()['id']}/results").json()
    rows = {x["name"]: x["values"] for x in res["rows"]}
    assert set(rows) == {"water", "sub__methanol"}
    assert rows["sub__methanol"]["S1_f"]["v"] == pytest.approx(0.05)
    assert rows["sub__methanol"]["S1_nm"]["v"] == pytest.approx(1239.84193 / 4.5, rel=1e-3)
    assert len(res["tables"]["states"]) == 12
    # pattern tester highlights the matched line
    t = c.post("/api/extraction/test", data={"field": json.dumps({"kind": "pattern", "pattern": {"text": "Total Enthalpy", "number_index": 1}}),
                                              "path": str(folder / "water.out")}).json()
    assert t["value"] < -40 and t["hits"] and any(x["hit"] for x in t["hits"][0]["context"])
    t = c.post("/api/extraction/test", data={"field": json.dumps({"kind": "pattern", "pattern": {"text": "(unclosed", "regex": True}}),
                                              "path": str(folder / "water.out")}).json()
    assert "regular expression" in t["error"]
    csv = c.get(f"/api/batches/{r.json()['id']}/export/csv").text
    assert "S1 wavelength (nm)" in csv
