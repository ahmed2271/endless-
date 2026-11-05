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
    assert cp["version"] == 2 and cp["steps"][1]["values"]["populations"] == ["hirshfeld", "mbis"]
    assert store.calc_profile_version("preopt_optfreq_b3lyp", 1)["steps"][1]["values"].get("populations") is None
    assert {"q_hirshfeld", "q_mbis"} <= {f["id"] for f in store.get_item("extraction_profiles", "standard")["fields"]}
    assert store.get_item("extraction_profiles", "tddft")["name"] == "My TDDFT"            # edited copy kept
    assert (store.root() / ".trash" / "upgraded" / "extraction_profiles" / "standard.yaml").exists()
