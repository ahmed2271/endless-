"""Newer starter profiles replace unedited copies in an existing studio folder; edited ones are kept."""
from orca_studio import store


def test_starter_upgrade(studio):
    from orca_studio.main import app
    from fastapi.testclient import TestClient
    # simulate an install from before Hirshfeld/MBIS became the default
    old_cp = store.get_item("calc_profiles", "preopt_optfreq_b3lyp")
    old_cp["version"] = 1
    old_cp["steps"][1]["values"].pop("populations")
    store.write_yaml(store.kind_dir("calc_profiles") / "preopt_optfreq_b3lyp.yaml", {k: v for k, v in old_cp.items() if k != "id"})
    ep = store.get_item("extraction_profiles", "standard")
    ep.pop("version")
    ep["fields"] = [f for f in ep["fields"] if f["id"] not in ("q_hirshfeld", "q_mbis")]
    store.save_item("extraction_profiles", ep)
    edited = store.get_item("extraction_profiles", "tddft")
    edited.pop("version")
    edited["name"] = "My TDDFT"
    TestClient(app).put("/api/items/extraction_profiles/tddft", json=edited)      # an edit made in the app
    store.seed()
    cp = store.get_item("calc_profiles", "preopt_optfreq_b3lyp")
    assert cp["version"] == 3 and cp["steps"][1]["values"]["populations"] == ["hirshfeld", "mbis"]
    assert cp["extraction_profile"] == ""                         # per-step extraction from now on
    assert store.calc_profile_version("preopt_optfreq_b3lyp", 1)["steps"][1]["values"].get("populations") is None
    assert {"q_hirshfeld", "q_mbis"} <= {f["id"] for f in store.get_item("extraction_profiles", "standard")["fields"]}
    assert store.get_item("extraction_profiles", "tddft")["name"] == "My TDDFT"            # edited copy kept
    assert (store.root() / ".trash" / "upgraded" / "extraction_profiles" / "standard.yaml").exists()


def test_migrate_whole_run_extraction(studio):
    from orca_studio import batches, db, store
    from orca_studio.main import migrate_step_extraction
    b = batches.create("old", "preopt_optfreq_b3lyp", None, "standard")
    mine = store.get_item("calc_profiles", "preopt_optfreq_b3lyp")
    mine.update(id="mine", name="mine", extraction_profile="standard")
    store.save_item("calc_profiles", mine)
    keep = batches.create("keep", "preopt_optfreq_b3lyp", None, "step_sp")       # a deliberate choice stays
    db.kv_set("migrated_step_extraction", False)
    migrate_step_extraction()
    assert batches.get(b["id"])["extraction_profile_id"] is None
    assert batches.get(keep["id"])["extraction_profile_id"] == "step_sp"
    assert store.get_item("calc_profiles", "mine")["extraction_profile"] == ""
