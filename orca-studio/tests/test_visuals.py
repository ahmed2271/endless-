"""Phase 4: orbital/density/MEP cubes, surface extrema, scripts, spectra data, snapshots."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import DATA, FAKE_BIN, wait_for


def _setup(store, config, mep=True):
    s = config.load_settings()
    if mep:
        s["script_paths"]["mep"] = str(FAKE_BIN / "mep.py")
    config.save_settings(s)
    p = store.get_item("calc_profiles", "optfreq_tddft")
    p["steps"][1]["workflow"] = {"cubes": {"orbitals": ["HOMO-1 to LUMO"], "densities": True, "mep": True, "grid": 24}}
    p["steps"][1]["values"]["nroots"] = 6
    return store.save_calc_profile(p)


def test_cubes_mep_and_spectra(studio):
    from orca_studio import batches, config, db, store, visuals
    from orca_studio.main import app
    from orca_studio.runner import Runner
    _setup(store, config)
    b = batches.create("vis", "optfreq_tddft", None, "tddft")
    batches.add_molecules(b["id"], [(n, (DATA / "structures" / n).read_bytes()) for n in ("water.xyz", "methanol.xyz")])
    r = Runner()
    r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 90)
    finally:
        r.stop()
    log = " ".join(x["text"] for x in db.q("SELECT text FROM logs WHERE batch_id=?", (b["id"],)))
    assert "cubes generated (3 orbitals, densities, MEP)" in log, log
    m = batches.molecules(b["id"])[0]
    names = {c["name"] for c in visuals.list_cubes(m, 1)}
    assert {"HOMO-1_a_g24.cube", "HOMO_a_g24.cube", "LUMO_a_g24.cube", "density_g24.cube", "mep_esp_g24.cube"} <= names
    c = TestClient(app)
    info = c.get(f"/api/molecules/{m['id']}/orbitals?step=1").json()
    a = info["spins"]["alpha"]
    assert a["homo"] == 4 and any(o["label"] == "LUMO+2" for o in a["orbitals"])
    mep = c.post(f"/api/molecules/{m['id']}/mep", json={"step": 1, "grid": 24}).json()
    ext = mep["extrema"]
    assert ext["vmin_au"] < 0 < ext["vmax_au"]
    assert ext["vmin_atom"]["element"] == "O" and ext["vmax_atom"]["element"] == "H"
    rng = c.get(f"/api/batches/{b['id']}/mep_range").json()
    assert rng["range"] >= max(abs(ext["vmin_au"]), abs(ext["vmax_au"]))
    # on-demand cubes: beta operator / TDDFT difference density / cached
    made = c.post(f"/api/molecules/{m['id']}/cubes", json={"step": 1, "grid": 20, "items": [
        {"kind": "mo", "label": "LUMO+1"}, {"kind": "tddft_difference", "state": 2}]}).json()
    assert not made["errors"], made
    assert {x["name"] for x in made["cubes"]} == {"LUMO+1_a_g20.cube", "diffdens_s2_g20.cube"}
    again = c.post(f"/api/molecules/{m['id']}/cubes", json={"step": 1, "grid": 20, "items": [{"kind": "mo", "label": "LUMO+1"}]}).json()
    assert again["cubes"][0].get("cached")
    # batch-wide generation
    c.post(f"/api/batches/{b['id']}/cubes", json={"items": [{"kind": "mo", "label": "HOMO"}], "grid": 20})
    assert wait_for(lambda: not c.get(f"/api/batches/{b['id']}/cubes/status").json()["running"], 30)
    ov = c.get(f"/api/batches/{b['id']}/cube_overview?name=HOMO_a_g20.cube").json()
    assert all(x["path"] for x in ov)
    # spectra data
    sp = c.get(f"/api/batches/{b['id']}/spectra_data").json()
    assert len(sp[0]["states"]) == 6 and sp[0]["ir"] and sp[0]["G"] is not None
    # snapshot saved in results/snapshots
    png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    p = c.post(f"/api/batches/{b['id']}/snapshot", json={"name": "water HOMO", "png": png}).json()["path"]
    assert Path(p).exists() and Path(p).parent.name == "snapshots"
    # script registry: run mep.py by hand
    rr = c.post("/api/scripts/mep/run", json={"molecule_id": m["id"], "step": 1, "npoints": 16}).json()
    assert rr["ok"] and rr["outputs"] and rr["outputs"][0]["path"].endswith("_mep.cube")


def test_orbital_labels():
    from orca_studio.visuals import expand_range, label_for, resolve_label
    assert expand_range("HOMO-2 to LUMO+1") == ["HOMO-2", "HOMO-1", "HOMO", "LUMO", "LUMO+1"]
    assert resolve_label("HOMO-2", 10) == 8 and resolve_label("LUMO+1", 10) == 12 and resolve_label("LUMO", 10) == 11
    assert label_for(11, 10) == "LUMO" and label_for(7, 10) == "HOMO-3"
    with pytest.raises(ValueError):
        resolve_label("SOMO", 3)
