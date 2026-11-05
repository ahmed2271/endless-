"""Deleting batches (with or without their folder), files, and profiles."""
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import DATA, wait_for


def test_delete_batches_files_profiles(studio, tmp_path):
    from orca_studio import batches, config
    from orca_studio.main import app
    from orca_studio.runner import Runner
    c = TestClient(app)
    b = batches.create("del", "preopt_r2scan_optfreq_b3lyp", None, None)
    batches.add_molecules(b["id"], [("water.xyz", (DATA / "structures" / "water.xyz").read_bytes())])
    r = Runner(); r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 60)
    finally:
        r.stop()
    folder = Path(b["folder"])
    sd = folder / "water" / "01_r2scan_preopt"
    # delete one file, then a step folder, from the Files tab
    assert c.delete("/api/file", params={"path": str(sd / "water.gbw")}).status_code == 200
    assert not (sd / "water.gbw").exists()
    assert c.delete("/api/file", params={"path": str(folder)}).status_code == 400          # whole batch: use batch delete
    assert c.delete("/api/file", params={"path": str(tmp_path)}).status_code == 403        # outside batch folders
    assert c.delete("/api/file", params={"path": str(sd)}).status_code == 200 and not sd.exists()
    # remove from the list only: files stay
    b2 = batches.create("keep", "preopt_r2scan_optfreq_b3lyp", None, None)
    (Path(b2["folder"]) / "note.txt").write_text("x")
    assert c.delete(f"/api/batches/{b2['id']}").status_code == 200
    assert Path(b2["folder"], "note.txt").exists() and batches.get(b2["id"]) is None
    # delete together with the folder
    assert c.delete(f"/api/batches/{b['id']}", params={"delete_files": 1}).status_code == 200
    assert not folder.exists() and batches.get(b["id"]) is None
    assert Path(config.load_settings()["folders"]["calculations_root"]).exists()          # root itself is never deleted
    # an analysed folder of the user's own .out files is never deleted
    own = tmp_path / "my_outs"; own.mkdir()
    (own / "w.out").write_text((DATA / "synthetic" / "water_optfreq.out").read_text())
    a = c.post("/api/analyze", json={"folder": str(own)}).json()
    assert c.delete(f"/api/batches/{a['id']}", params={"delete_files": 1}).status_code == 400
    assert (own / "w.out").exists()
    # profiles: user profiles are deleted, starter profiles hidden (so they do not come back)
    p = c.post("/api/calc_profiles", json={"name": "mine"}).json()
    assert p["steps"] == []                                                                # new profiles start empty
    assert c.delete(f"/api/calc_profiles/{p['id']}").json() == {"ok": True}
    assert c.get(f"/api/calc_profiles/{p['id']}").status_code == 404
    # starter profiles can be deleted too, and do not come back at the next start
    from orca_studio import store
    assert c.delete("/api/calc_profiles/optfreq_tddft").json() == {"ok": True}
    store.seed()
    assert c.get("/api/calc_profiles/optfreq_tddft").status_code == 404
    assert "optfreq_tddft" not in [x["id"] for x in c.get("/api/calc_profiles").json()]
