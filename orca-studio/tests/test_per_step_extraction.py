"""Each step of a batch has its own extraction profile (default from the step type, changeable per
batch); an optional whole-batch profile adds fields across steps."""
import pytest
from fastapi.testclient import TestClient

from conftest import DATA, wait_for


def _run(profile):
    from orca_studio import batches
    from orca_studio.runner import Runner
    b = batches.create("ost", profile, None, None)
    batches.add_molecules(b["id"], [(n, (DATA / "structures" / n).read_bytes()) for n in ("water.xyz", "methanol.xyz")])
    r = Runner(); r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 90)
    finally:
        r.stop()
    return b


def test_step_profiles(studio):
    from orca_studio import batches, extraction, store
    from orca_studio.main import app
    c = TestClient(app)
    b = _run("opt_sp_tddft")
    setup = c.get(f"/api/batches/{b['id']}/extraction_setup").json()
    assert [s["profile"] for s in setup["steps"]] == ["step_opt", "step_sp", "step_tddft"] and setup["extra"] == ""
    res = extraction.results(b["id"])
    src = {f["id"]: f["source"] for f in res["fields"]}
    names = {f["id"]: f["name"] for f in res["fields"]}
    assert src["E_s1"] == "Step 1: Opt" and src["HOMO_s2"] == "Step 2: SP" and src["S1_s3"] == "Step 3: TDDFT"
    assert names["E_s2"] == "Energy (SP)" and names["S1_nm_s3"] == "S1 wavelength (TDDFT)"
    v = res["rows"][0]["values"]
    m = batches.molecules(b["id"])[0]
    sp_out = extraction.load_out(extraction.out_path_for(batches.get(b["id"]), m, 1))
    assert v["E_s2"]["v"] == pytest.approx(sp_out.final_energy) and v["optconv_s1"]["v"] is True
    assert v["S1_s3"]["v"] == pytest.approx(4.5)
    assert len([t for t in res["tables"]["q_hirshfeld_s2"] if t["molecule"] == "water"]) == 3
    assert len([t for t in res["tables"]["states_s3"] if t["molecule"] == "water"]) == 10
    # per batch: no extraction for step 1, and the SP step also reads its excited states? -> use TDDFT set on step 2
    r = c.post(f"/api/batches/{b['id']}/extract", json={"step_extraction": {"0": "", "1": "step_sp"},
                                                         "extraction_profile_id": "standard"}).json()
    ids = [f["id"] for f in r["fields"]]
    assert not any(i.endswith("_s1") for i in ids) and "E_s2" in ids and "S1_s3" in ids
    assert "relG" in ids                                                   # whole-batch extra fields appended
    assert [s["profile"] for s in c.get(f"/api/batches/{b['id']}/extraction_setup").json()["steps"]] == ["", "step_sp", "step_tddft"]


def test_step_profile_in_calc_profile_and_formulas(studio):
    from orca_studio import extraction, store
    p = store.get_item("calc_profiles", "preopt_r2scan_optfreq_b3lyp")
    p["steps"][0]["extraction_profile"] = "step_sp"            # chosen in the calculation profile
    store.save_calc_profile(p)
    b = _run("preopt_r2scan_optfreq_b3lyp")
    res = extraction.results(b["id"])
    ids = {f["id"] for f in res["fields"]}
    assert "HOMO_s1" in ids and "G_s2" in ids and "relG_s2" in ids
    rel = {r["name"]: r["values"]["relG_s2"] for r in res["rows"]}
    assert rel["water"]["v"] == pytest.approx(0.0)              # formula inside the step profile works
    assert {f["source"] for f in res["fields"] if f["id"] == "relG_s2"} == {"Step 2: Opt + Freq"}
