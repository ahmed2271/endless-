"""Cubes: a looping orca_plot is stopped quickly and the %plots route takes over; batches finish
while cubes are made in the background."""
from pathlib import Path

from conftest import DATA, wait_for


def test_orca_plot_loop_falls_back_to_plots(studio, monkeypatch):
    from orca_studio import batches, db, store, visuals
    from orca_studio.runner import Runner
    monkeypatch.setenv("FAKE_ORCA_PLOT_LOOP", "1")
    p = store.get_item("calc_profiles", "preopt_r2scan_optfreq_b3lyp")
    p["steps"][1]["workflow"] = {"cubes": {"orbitals": ["HOMO", "LUMO"], "densities": True, "grid": 20}}
    store.save_calc_profile(p)
    b = batches.create("cubes", "preopt_r2scan_optfreq_b3lyp", None, None)
    batches.add_molecules(b["id"], [("water.xyz", (DATA / "structures" / "water.xyz").read_bytes())])
    r = Runner(); r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 60)
        logs = lambda: " ".join(x["text"] for x in db.q("SELECT text FROM logs WHERE batch_id=?", (b["id"],)))
        assert wait_for(lambda: "cube(s) made" in logs(), 60), logs()
    finally:
        r.stop()
    assert "3 cube(s) made" in logs() and "problems" not in logs(), logs()
    m = batches.molecules(b["id"])[0]
    cubes = {c["name"]: c for c in visuals.list_cubes(m, 1)}
    assert {"HOMO_a_g20.cube", "LUMO_a_g20.cube", "density_g20.cube"} <= set(cubes)
    assert all(c["route"] == "plots" for c in cubes.values())
    assert db.kv_get("cube_route") == "plots"                     # remembered for next time
    sd, _ = visuals.step_paths(m, 1)
    log = (sd / "cubes" / "orca_plot_mo.log").read_text()
    assert len(log) < 70000                                        # the endless menu was cut off
    inp = (sd / "cubes" / "_plot_run" / "plot.inp").read_text()
    assert "MORead NoIter" in inp and "%plots" in inp and 'MO("HOMO_a_g20.cube", 4, 0);' in inp
    bang = " ".join(l for l in inp.splitlines() if l.startswith("!")).split()
    assert "Opt" not in bang and "Freq" not in bang and "B3LYP" in bang and "* xyzfile 0 1 geom.xyz" in inp
    assert "Hirshfeld" not in bang and "MBIS" not in bang
    # next request goes straight to the %plots route (no orca_plot attempt)
    (sd / "cubes" / "orca_plot_mo.log").unlink()
    done, errors = visuals.make_cubes(m, 1, [{"kind": "mo", "label": "HOMO-1"}], 20)
    assert not errors and done[0]["route"] == "plots" and not (sd / "cubes" / "orca_plot_mo.log").exists()
