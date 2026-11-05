"""Opt → SP → TDDFT: each field reads its own step, and results are grouped by step."""
import pytest

from conftest import DATA, wait_for


def test_opt_sp_tddft(studio):
    from orca_studio import batches, extraction, validate
    from orca_studio.runner import Runner
    b = batches.create("ost", "opt_sp_tddft", None, None)
    assert b["extraction_profile_id"] == "opt_sp_tddft"
    batches.add_molecules(b["id"], [("water.xyz", (DATA / "structures" / "water.xyz").read_bytes())])
    from orca_studio import store
    issues = validate.validate(b["profile"], None, store.get_item("extraction_profiles", "opt_sp_tddft"))
    assert not [i for i in issues if "Extraction" in i["message"]], issues
    r = Runner(); r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 90)
    finally:
        r.stop()
    res = extraction.results(b["id"])
    src = {f["id"]: f["source"] for f in res["fields"]}
    assert src["E_Opt"] == "Step 1: Opt" and src["HOMO_SP"] == "Step 2: SP" and src["S1_TDDFT"] == "Step 3: TDDFT"
    v = res["rows"][0]["values"]
    # the SP energy comes from the SP output, not from the last (TDDFT) step
    m = batches.molecules(b["id"])[0]
    sp_out = extraction.load_out(extraction.out_path_for(batches.get(b["id"]), m, 1))
    assert v["E_SP"]["v"] == pytest.approx(sp_out.final_energy) and v["optconv_Opt"]["v"] is True
    assert v["S1_TDDFT"]["v"] == pytest.approx(4.5) and len(res["tables"]["states_TDDFT"]) == 10
    assert len(res["tables"]["q_hirshfeld_SP"]) == 3 and len(res["tables"]["q_mbis_SP"]) == 3
