"""Phase 5: Multiwfn record mode and recipes, Fukui functions, ΔSCF, LAN login, citations."""
import json

import pytest
from fastapi.testclient import TestClient

from conftest import DATA, FAKE_BIN, wait_for

WATER = (DATA / "structures" / "water.xyz").read_bytes()


def _settings(**programs):
    from orca_studio import config
    s = config.load_settings()
    s["programs"].update(programs)
    config.save_settings(s)


def _run(b):
    from orca_studio import batches
    from orca_studio.runner import Runner
    r = Runner()
    r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 90)
    finally:
        r.stop()


def test_multiwfn_record_recipe_and_field(studio):
    from orca_studio import batches, extraction, store, validate
    from orca_studio.main import app
    _settings(multiwfn=str(FAKE_BIN / "Multiwfn"), multiwfn_threads=3)
    with TestClient(app) as c:
        sess = c.post("/api/multiwfn/record/upload", files={"file": ("sample water.molden", b"[Molden Format]\n")}).json()
        with c.websocket_connect(f"/ws/multiwfn/record/{sess['id']}") as ws:
            out = ""
            for keys in ("12\r", "0\r", "-1\r", "7\r", "11\r", "n\r", "0\r", "q\r"):
                ws.send_text(json.dumps({"type": "in", "data": keys}))
            while True:
                msg = json.loads(ws.receive_text())
                if msg["type"] == "exit":
                    break
                out += msg["data"]
        rec = c.get(f"/api/multiwfn/record/{sess['id']}").json()
        assert rec["answers"] == ["12", "0", "-1", "7", "11", "n", "0", "q"]
        assert "Global surface minimum" in rec["output"] and rec["version"] == "3.8(dev)"
        assert "The number of threads: 3" in rec["output"]            # settings.ini nthreads applied
        rules = [{"id": "vmin", "label": "Surface minimum (a.u.)", "anchor": "Global surface minimum:", "column": 1},
                 {"id": "vmax_kcal", "label": "Surface maximum (kcal/mol)", "anchor": "Global surface maximum:", "column": 2},
                 {"id": "adch", "label": "ADCH charges", "anchor": "Summary of ADCH charges", "table": True,
                  "columns": ["atom", "charge", "before"], "label_regex": r"Atom:\s+\d+(\w+)"}]
        assert c.post("/api/multiwfn/test_rule", json={"session": sess["id"], "rule": rules[0]}).json()["value"] == pytest.approx(-0.045021)
        adch = c.post("/api/multiwfn/test_rule", json={"session": sess["id"], "rule": rules[2]}).json()["value"]
        assert len(adch) == 3 and adch[0]["charge"] == pytest.approx(-0.663148) and adch[0]["label"] == "O"
        rid = c.post("/api/multiwfn/recipes", json={"session": sess["id"], "recipe": {
            "name": "ESP and ADCH", "answers": rec["answers"], "rules": rules}}).json()["id"]
        saved = store.get_item("multiwfn_recipes", rid)
        assert saved["multiwfn_version"] == "3.8(dev)" and "10.1002/jcc.22885" in saved["citations"][0]
        rt = c.post(f"/api/multiwfn/recipes/{rid}/retest").json()
        assert rt["ok"], rt
        # recipe results as extraction fields on a real batch
        ep = {"id": "mw", "name": "MW", "fields": [
            {"id": "vmin", "name": "Vmin", "kind": "multiwfn", "multiwfn": {"recipe": rid, "rule": "vmin"}},
            {"id": "adch", "name": "ADCH", "kind": "multiwfn", "multiwfn": {"recipe": rid, "rule": "adch", "shape": "table"}}]}
        store.save_item("extraction_profiles", ep)
        b = batches.create("mwb", "preopt_r2scan_optfreq_b3lyp", None, "mw")
        batches.add_molecules(b["id"], [("water.xyz", WATER)])
        assert not [i for i in validate.validate(b["profile"], None, ep) if "Multiwfn" in i["message"]]
        _run(b)
        res = extraction.results(b["id"])
        assert res["rows"][0]["values"]["vmin"]["v"] == pytest.approx(-0.045021)
        assert len(res["tables"]["adch"]) == 3
        assert "jcc.22885" in c.get(f"/api/batches/{b['id']}/export/citations").text


def test_fukui_functions(studio):
    from orca_studio import batches, extraction, store
    p = {"id": "fukui", "name": "Fukui", "columns": [{"column": "method"}, {"column": "basis"}, {"column": "charge_offset"}],
         "defaults": {"method": "b3lyp", "basis": "def2svp", "populations": ["hirshfeld"]}, "resources": {"nprocs": 1, "maxcore": 500},
         "steps": [{"name": "N", "type": "sp", "values": {}},
                   {"name": "N+1", "type": "sp", "values": {"charge_offset": -1}},
                   {"name": "N-1", "type": "sp", "values": {"charge_offset": 1}}]}
    store.save_calc_profile(p)
    store.save_item("extraction_profiles", {"id": "fk", "name": "fk", "fields": [
        {"id": "fk", "name": "Fukui", "kind": "fukui", "params": {"scheme": "hirshfeld", "step_n": "N", "step_plus": "N+1", "step_minus": "N-1"}}]})
    b = batches.create("fk", "fukui", None, "fk")
    batches.add_molecules(b["id"], [("water.xyz", WATER)])
    inp = batches.step_dir(batches.get(b["id"]), batches.molecules(b["id"])[0], 1)
    _run(b)
    assert "* xyzfile -1 2 input.xyz" in (inp / "water.inp").read_text()
    rows = extraction.results(b["id"])["tables"]["fk"]
    assert len(rows) == 3
    assert sum(r["f_plus"] for r in rows) == pytest.approx(0.5, abs=1e-3)      # stand-in Hirshfeld = half the charge change
    assert sum(r["f_minus"] for r in rows) == pytest.approx(0.5, abs=1e-3)
    assert all("dual" in r for r in rows)


def test_dscf(studio):
    from orca_studio import batches, extraction, store
    p = {"id": "dscf", "name": "dscf", "columns": [{"column": "method"}, {"column": "basis"}],
         "defaults": {"method": "b3lyp", "basis": "def2svp"}, "resources": {"nprocs": 1, "maxcore": 500},
         "steps": [{"name": "ΔSCF", "type": "dscf", "values": {"dscf_triplet": True}}]}
    store.save_calc_profile(p)
    store.save_item("extraction_profiles", {"id": "ds", "name": "ds", "fields": [
        {"id": "de", "name": "ΔE", "kind": "dscf", "params": {"value": "de"}, "unit_kind": "excitation", "unit": "eV"},
        {"id": "nm", "name": "λ", "kind": "dscf", "params": {"value": "de"}, "unit_kind": "excitation", "unit": "nm"},
        {"id": "pure", "name": "pure", "kind": "dscf", "params": {"value": "pure"}, "unit_kind": "excitation", "unit": "eV"},
        {"id": "col", "name": "collapse", "kind": "dscf", "params": {"value": "collapse"}}]})
    b = batches.create("ds", "dscf", None, "ds")
    batches.add_molecules(b["id"], [("water.xyz", WATER)])
    _run(b)
    t = batches.tasks(b["id"])[0]
    assert t["status"] == "done", t["message"]
    from pathlib import Path
    es = (Path(t["step_dir"]) / "es" / "water.inp").read_text()
    assert "DeltaSCF" in es and "MORead" in es and "ALPHACONF 0,1" in es and '%moinp "previous.gbw"' in es
    assert "DeltaSCF" not in (Path(t["step_dir"]) / "gs" / "water.inp").read_text()
    assert "* xyzfile 0 3 input.xyz" in (Path(t["step_dir"]) / "t" / "water.inp").read_text()
    v = extraction.results(b["id"])["rows"][0]["values"]
    assert v["de"]["v"] == pytest.approx(0.15 * 27.211386, rel=1e-4)
    assert v["nm"]["v"] == pytest.approx(1239.84193 / (0.15 * 27.211386), rel=1e-4)
    assert v["pure"]["v"] == pytest.approx(0.20 * 27.211386, rel=1e-4)
    assert v["col"]["v"] is False


def test_lan_login(studio):
    from orca_studio import auth, config
    from orca_studio.main import app
    s = config.load_settings()
    s["access"]["mode"] = "lan"
    s["access"]["password_hash"] = auth.hash_password("s3cret")
    config.save_settings(s)
    with TestClient(app) as local:
        assert local.get("/api/status").status_code == 200                       # this computer: no login
    with TestClient(app, client=("192.168.1.20", 50000)) as remote:
        assert remote.get("/api/status").status_code == 401
        assert remote.get("/", follow_redirects=False).status_code in (302, 307)
        assert remote.get("/login").status_code == 200
        assert remote.post("/api/login", json={"password": "nope"}).status_code == 401
        assert remote.post("/api/login", json={"password": "s3cret"}).status_code == 200
        assert remote.get("/api/status").status_code == 200
    # settings API never returns the hash
    with TestClient(app) as local:
        assert "password_hash" not in local.get("/api/settings").json()["settings"]["access"]


def test_posthoc_chelpg_and_scheme_spread(studio):
    from orca_studio import batches, extraction, store
    from orca_studio.main import app
    store.save_item("extraction_profiles", {"id": "sp", "name": "sp", "fields": [
        {"id": "chelpg", "name": "CHELPG", "kind": "builtin", "builtin": "charges", "params": {"scheme": "chelpg"}},
        {"id": "spread", "name": "spread", "kind": "builtin", "builtin": "scheme_spread",
         "params": {"schemes": "mulliken loewdin chelpg", "threshold": 0.2}}]})
    b = batches.create("ch", "preopt_r2scan_optfreq_b3lyp", None, "sp")
    batches.add_molecules(b["id"], [("water.xyz", WATER)])
    _run(b)
    res = extraction.results(b["id"])
    assert res["rows"][0]["values"]["chelpg"]["v"] is None           # no CHELPG keyword in the run
    m = batches.molecules(b["id"])[0]
    with TestClient(app) as c:
        r = c.post(f"/api/molecules/{m['id']}/chelpg", json={})
        assert r.status_code == 200, r.text
    res = extraction.results(b["id"])
    assert len([x for x in res["tables"]["chelpg"]]) == 3
    sp = res["tables"]["spread"]
    assert len(sp) == 3 and {"mulliken", "loewdin", "chelpg", "spread", "disagree"} <= set(sp[0])
    assert any(x["disagree"] for x in sp)
