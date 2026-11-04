"""Phase 1 acceptance (with the stand-in ORCA): stage-by-stage execution, folder layout, controls."""
from pathlib import Path

from conftest import DATA, wait_for


def _files(*names):
    return [(n, (DATA / "structures" / n).read_bytes()) for n in names]


def _make_batch(name="acc", profile="preopt_optfreq_b3lyp", files=("water.xyz", "methanol.xyz", "formaldehyde.inp")):
    from orca_studio import batches
    b = batches.create(name, profile, None, None)
    res = batches.add_molecules(b["id"], _files(*files))
    assert all(r["ok"] for r in res), res
    return b


def test_acceptance_stage_by_stage(studio):
    from orca_studio import batches, db
    from orca_studio.runner import Runner

    b = _make_batch()
    r = Runner()
    r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 90)
    finally:
        r.stop()
    tasks = batches.tasks(b["id"])
    assert len(tasks) == 6 and all(t["status"] == "done" for t in tasks), [(t["status"], t["message"]) for t in tasks]
    # folder layout {batch}/{molecule}/{NN}_{step}/ with {molecule}.inp/.out and input.xyz
    folder = Path(b["folder"])
    for mol in ("water", "methanol", "formaldehyde"):
        for d in ("01_xtb_preopt", "02_opt_freq"):
            sd = folder / mol / d
            assert (sd / f"{mol}.inp").exists() and (sd / f"{mol}.out").exists() and (sd / "input.xyz").exists()
        # step 2 starts from step 1's optimized geometry
        src = (folder / mol / "02_opt_freq" / ".studio_geometry_source").read_text().strip()
        assert src.endswith(f"01_xtb_preopt/{mol}.xyz")
    inp = (folder / "water" / "02_opt_freq" / "water.inp").read_text()
    assert "! Opt Freq B3LYP D3BJ def2-SVP" in inp and "%pal nprocs 2 end" in inp
    assert "* xyzfile 0 1 input.xyz" in inp
    # original files were copied, not moved
    assert (folder / "inputs" / "formaldehyde.inp").exists()
    # stage-by-stage: every step-2 run started after every step-1 run ended
    runs = db.q("SELECT r.*, t.step_index FROM runs r JOIN tasks t ON t.id=r.task_id WHERE r.batch_id=?", (b["id"],))
    last_end_1 = max(x["end"] for x in runs if x["step_index"] == 0)
    first_start_2 = min(x["start"] for x in runs if x["step_index"] == 1)
    assert first_start_2 >= last_end_1
    # never more than 4 cores (2 jobs x 2 cores) at once
    events = sorted([(x["start"], 2) for x in runs] + [(x["end"], -2) for x in runs])
    cur = peak = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    assert peak <= 4
    assert (folder / "batch_log.txt").exists()


def test_pause_cancel_retry(studio, monkeypatch):
    monkeypatch.setenv("FAKE_ORCA_SLEEP", "3")
    from orca_studio import batches, db
    from orca_studio.runner import Runner, session_pids

    b = _make_batch("ctl")
    r = Runner()
    r.start()
    try:
        r.run_batch(b["id"])
        assert wait_for(lambda: len(r.jobs) == 2, 20)
        r.pause(b["id"])
        assert wait_for(lambda: len(r.jobs) == 0, 30)
        time.sleep(3)
        assert len(r.jobs) == 0
        assert batches.summary(b["id"]).get("done") == 2
        r.resume(b["id"])
        assert wait_for(lambda: len(r.jobs) == 1, 20)
        pids = [j.pid for j in r.jobs.values()]
        r.cancel(b["id"])
        assert batches.get(b["id"])["status"] == "cancelled"
        assert all(not session_pids(p) for p in pids if p)
        assert wait_for(lambda: len(r.jobs) == 0, 10)
        n = r.retry_failed(b["id"])
        assert n >= 1
        monkeypatch.setenv("FAKE_ORCA_SLEEP", "0.2")
        assert wait_for(lambda: batches.get(b["id"])["status"] == "done", 90)
        assert all(t["status"] == "done" for t in batches.tasks(b["id"]))
    finally:
        r.stop()


import time  # noqa: E402
