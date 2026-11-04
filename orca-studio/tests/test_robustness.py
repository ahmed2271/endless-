"""Phase 3: retries, optimization restarts, imaginary-frequency displacement, review pauses,
run conditions, per-molecule mode, stop-on-failure, time limits, versioning, templates."""
import copy

from conftest import DATA, wait_for

WATER = (DATA / "structures" / "water.xyz").read_text()


def _profile(store, pid, steps, **extra):
    p = {"name": pid, "columns": [{"column": "method"}, {"column": "basis"}], "defaults": {"method": "b3lyp", "basis": "def2svp"},
         "resources": {"nprocs": 1, "maxcore": 500}, "extraction_profile": "standard", "steps": steps}
    p.update(extra)
    p["id"] = pid
    return store.save_calc_profile(p)


def _batch(pid, names, sleep_env=None):
    from orca_studio import batches
    b = batches.create(pid + "_batch", pid, None, None)
    batches.add_molecules(b["id"], [(f"{n}.xyz", WATER.encode()) for n in names])
    return b


def _run(b, timeout=120, until=("done",)):
    from orca_studio import batches
    from orca_studio.runner import Runner
    r = Runner()
    r.start()
    r.run_batch(b["id"])
    ok = wait_for(lambda: batches.get(b["id"])["status"] in until, timeout)
    return r, ok


def test_retries_restarts_displacement(studio):
    from orca_studio import batches, db, store
    wf = {"scf_retry": ["slowconv_maxiter", "kdiis_soscf"], "opt_restarts": 2, "imag_fix": 2}
    _profile(store, "robust", [{"name": "Opt + Freq", "type": "opt_freq", "values": {}, "workflow": wf}])
    b = _batch("robust", ["scffail_w", "optfail_w", "imag_w", "plain_w"])
    r, ok = _run(b)
    r.stop()
    assert ok
    t = {m["name"]: m for m in batches.molecules(b["id"])}
    tasks = {x["molecule_id"]: x for x in batches.tasks(b["id"])}
    for n in ("scffail_w", "optfail_w", "imag_w", "plain_w"):
        assert tasks[t[n]["id"]]["status"] == "done", (n, tasks[t[n]["id"]]["message"])
    runs = db.q("SELECT r.*, t.molecule_id FROM runs r JOIN tasks t ON t.id=r.task_id WHERE r.batch_id=?", (b["id"],))
    n_runs = {n: sum(1 for x in runs if x["molecule_id"] == t[n]["id"]) for n in t}
    assert n_runs == {"scffail_w": 2, "optfail_w": 2, "imag_w": 2, "plain_w": 1}
    from pathlib import Path
    sd = Path(tasks[t["scffail_w"]["id"]]["step_dir"])
    assert (sd / "scffail_w.attempt1.out").exists()
    inp = (sd / "scffail_w.inp").read_text()
    assert "SlowConv" in inp and "MaxIter 500" in inp
    sd = Path(tasks[t["imag_w"]["id"]]["step_dir"])
    assert "displaced along mode" in (sd / "input.xyz").read_text()
    sd = Path(tasks[t["optfail_w"]["id"]]["step_dir"])
    assert "last geometry" in (sd / "input.xyz").read_text()


def test_failure_rules(studio):
    from orca_studio import batches, db, store
    # no retries: SCF failure -> later steps skipped; crash with 'stop' -> batch stopped
    _profile(store, "skip", [{"name": "Opt", "type": "opt", "values": {}}, {"name": "SP", "type": "sp", "values": {}}])
    b = _batch("skip", ["scffail_a", "ok_a"])
    r, ok = _run(b)
    r.stop()
    assert ok
    st = {(x["molecule_id"], x["step_index"]): x["status"] for x in batches.tasks(b["id"])}
    ms = {m["name"]: m["id"] for m in batches.molecules(b["id"])}
    assert st[(ms["scffail_a"], 0)] == "failed" and st[(ms["scffail_a"], 1)] == "skipped"
    assert st[(ms["ok_a"], 1)] == "done"
    assert db.q("SELECT * FROM notifications WHERE text LIKE '%failed at step 1%'")

    _profile(store, "stop", [{"name": "Opt", "type": "opt", "values": {}, "workflow": {"after_failure": "stop", "order": "list"}},
                             {"name": "SP", "type": "sp", "values": {}}])
    b = _batch("stop", ["crash_b", "ok_b"])
    r, ok = _run(b, until=("stopped",))
    try:
        assert ok
        assert wait_for(lambda: not r.jobs, 20)
        st = {x["step_index"]: x["status"] for x in batches.tasks(b["id"]) if x["status"] != "done"}
        assert batches.get(b["id"])["status"] == "stopped"
        assert all(v in ("failed", "pending", "queued") for v in st.values())
    finally:
        r.stop()


def test_review_conditions_and_per_molecule(studio):
    from orca_studio import batches, db, store
    _profile(store, "review", [
        {"name": "Opt + Freq", "type": "opt_freq", "values": {}, "workflow": {"between": "pause", "checks": {"imaginary": "warn"}}},
        {"name": "Re-opt if imaginary", "type": "opt_freq", "values": {}, "workflow": {"run_condition": "check_fired"}},
        {"name": "SP", "type": "sp", "values": {}, "workflow": {"run_condition": "prev_success"}},
    ])
    b = _batch("review", ["imag_r", "plain_r"])
    r, ok = _run(b, until=("review",))
    try:
        assert ok, batches.get(b["id"])["status"]
        assert all(t["status"] in ("pending",) for t in batches.tasks(b["id"]) if t["step_index"] > 0)
        assert wait_for(lambda: db.q("SELECT * FROM notifications WHERE text LIKE '%Review the results%'"), 5)
        r.continue_review(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 60)
    finally:
        r.stop()
    ms = {m["id"]: m["name"] for m in batches.molecules(b["id"])}
    st = {(ms[x["molecule_id"]], x["step_index"]): x for x in batches.tasks(b["id"])}
    assert st[("imag_r", 0)]["status"] == "done" and "imaginary" in st[("imag_r", 0)]["fired"]
    assert st[("imag_r", 1)]["status"] in ("done", "failed")        # ran because the check fired
    assert st[("plain_r", 1)]["status"] == "skipped"                  # no check fired
    assert st[("plain_r", 2)]["status"] == "done"                     # runs from step 1 geometry
    assert st[("plain_r", 2)]["message"] == "all checks passed"


def test_per_molecule_and_time_limit(studio, monkeypatch):
    from orca_studio import batches, db, store
    monkeypatch.setenv("FAKE_ORCA_SLEEP", "3")
    _profile(store, "permol", [{"name": "Opt", "type": "opt", "values": {}, "workflow": {"between": "per_molecule"}},
                               {"name": "SP", "type": "sp", "values": {}, "workflow": {"time_limit_h": 0.0003}}],
             resources={"nprocs": 1, "maxcore": 500})
    s = __import__("orca_studio.config", fromlist=["x"]).load_settings()
    s["resources"]["total_cores"] = 2
    __import__("orca_studio.config", fromlist=["x"]).save_settings(s)
    b = _batch("permol", ["m1", "m2", "m3"])
    r, ok = _run(b, 90)
    r.stop()
    assert ok
    runs = db.q("SELECT r.*, t.step_index, t.molecule_id FROM runs r JOIN tasks t ON t.id=r.task_id WHERE r.batch_id=? ORDER BY r.start", (b["id"],))
    ms = [m["id"] for m in batches.molecules(b["id"])]
    run = {(x["molecule_id"], x["step_index"]): x for x in runs}
    # m1 moves on to step 2 while m3 is still in step 1 (with 'wait for all' it would have to wait)
    assert run[(ms[0], 1)]["start"] < run[(ms[2], 0)]["end"]
    sp = [t for t in batches.tasks(b["id"]) if t["step_index"] == 1]
    assert all(t["status"] == "failed" and "time limit" in t["message"] for t in sp)


def test_versioning_and_templates(studio):
    from fastapi.testclient import TestClient
    from orca_studio import batches, store
    from orca_studio.main import app
    c = TestClient(app)
    p = c.get("/api/calc_profiles/preopt_optfreq_b3lyp").json()
    b = batches.create("v", "preopt_optfreq_b3lyp", None, None)
    p2 = copy.deepcopy(p)
    p2["steps"][1]["values"]["basis"] = "def2tzvp"
    r = c.put("/api/calc_profiles/preopt_optfreq_b3lyp", json=p2).json()
    assert r["version"] == 2
    assert c.put("/api/calc_profiles/preopt_optfreq_b3lyp", json=r).json()["version"] == 2   # unchanged -> no new version
    assert batches.get(b["id"])["profile"]["steps"][1]["values"]["basis"] == "def2svp"       # batch keeps v1
    assert c.get("/api/calc_profiles/preopt_optfreq_b3lyp?version=1").json()["steps"][1]["values"]["basis"] == "def2svp"
    assert c.get("/api/calc_profiles/preopt_optfreq_b3lyp").json()["versions"] == [1, 2]
    # step templates are stored by copy
    t = c.post("/api/items/step_templates", json={"name": "My TDDFT", "step": {"name": "TDDFT", "type": "tddft", "values": {"nroots": 8}}}).json()
    assert store.get_item("step_templates", t["id"])["step"]["values"]["nroots"] == 8
