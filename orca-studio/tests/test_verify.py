"""ORCA checks run end to end (against the stand-in ORCA) without crashing and update libraries."""


def test_verify_runs(studio):
    from orca_studio import store, verify
    res = verify.run_all(["opt_message", "numbering", "property_file", "xtb", "freq_keywords"])
    by = {r["id"]: r for r in res}
    assert by["opt_message"]["status"] == "pass"
    assert by["numbering"]["status"] == "pass"
    assert by["property_file"]["status"] == "pass"
    assert by["xtb"]["status"] == "pass"
    # confirmed entries lose the 'unverified' tag
    assert "unverified" not in store.get_entry("output_patterns", "opt_converged")["tags"]
    assert "unverified" not in store.get_entry("semiempirical", "xtb2")["tags"]
    assert (studio / "verify_report.md").exists()


def test_verify_orca_plot_falls_back(studio, monkeypatch):
    from orca_studio import db, verify
    monkeypatch.setenv("FAKE_ORCA_PLOT_LOOP", "1")
    r = verify.run_all(["orca_plot"])[0]
    assert r["status"] == "pass" and db.kv_get("cube_route") == "plots"
    assert any("repeating its menu" in d for d in r["details"])
