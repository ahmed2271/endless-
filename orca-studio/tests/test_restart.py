"""Phase 1 acceptance: stopping and restarting the service mid-run recovers correctly."""
import os
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from conftest import DATA, FAKE_BIN, ROOT, wait_for


def _port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _start(home, port, sleep):
    env = dict(os.environ, ORCA_STUDIO_HOME=str(home), FAKE_ORCA_SLEEP=str(sleep), PYTHONPATH=str(ROOT))
    p = subprocess.Popen([sys.executable, "-m", "orca_studio", "--port", str(port)], cwd=ROOT, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    assert wait_for(lambda: _up(port), 20)
    return p


def _up(port):
    try:
        return httpx.get(f"http://127.0.0.1:{port}/api/status", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


def test_restart_recovers(studio, tmp_path):
    from orca_studio import db
    db.reset_connection()
    port = _port()
    srv = _start(studio, port, 5)
    api = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30)
    try:
        b = api.post("/api/batches", json={"name": "restart", "calc_profile_id": "preopt_optfreq_b3lyp"}).json()
        files = [("files", (n, (DATA / "structures" / n).read_bytes())) for n in ("water.xyz", "methanol.xyz", "formaldehyde.inp")]
        assert all(r["ok"] for r in api.post(f"/api/batches/{b['id']}/upload", files=files).json())
        r = api.post(f"/api/batches/{b['id']}/run", json={"force": True})
        assert r.status_code == 200, r.text
        assert wait_for(lambda: len([t for t in api.get("/api/queue").json()["running"] if t["pid"]]) == 2, 20)
        running = api.get("/api/queue").json()["running"]
        pids = [t["pid"] for t in running]
        # stop the service (ORCA jobs keep running, like systemd KillMode=process)
        os.killpg(srv.pid, signal.SIGTERM)
        srv.wait(15)
        assert all(Path(f"/proc/{p}").exists() for p in pids), "ORCA jobs must survive a service stop"
        time.sleep(1)
        srv = _start(studio, port, 1)
        log = api.get(f"/api/batches/{b['id']}/log").json()
        assert any("re-attached" in x["text"] for x in log), [x["text"] for x in log]
        assert wait_for(lambda: api.get(f"/api/batches/{b['id']}").json()["status"] == "done", 120)
        bv = api.get(f"/api/batches/{b['id']}").json()
        st = [t["status"] for m in bv["molecules"] for t in m["tasks"]]
        assert st == ["done"] * 6, st
        runs = api.get(f"/api/batches/{b['id']}/runs").json()
        assert len(runs) == 6, "no job may be started twice"

        # second scenario: a job dies while the service is down -> requeued and rerun
        b2 = api.post("/api/batches", json={"name": "lost", "calc_profile_id": "preopt_optfreq_b3lyp"}).json()
        files = [("files", ("water.xyz", (DATA / "structures" / "water.xyz").read_bytes()))]
        api.post(f"/api/batches/{b2['id']}/upload", files=files)
        os.killpg(srv.pid, signal.SIGTERM)
        srv.wait(15)
        srv = _start(studio, port, 6)
        api.post(f"/api/batches/{b2['id']}/run", json={"force": True})
        assert wait_for(lambda: [t for t in api.get("/api/queue").json()["running"] if t["pid"]], 20)
        pid = api.get("/api/queue").json()["running"][0]["pid"]
        os.killpg(srv.pid, signal.SIGTERM)
        srv.wait(15)
        os.killpg(pid, signal.SIGKILL)
        time.sleep(0.5)
        srv = _start(studio, port, 0.3)
        log = api.get(f"/api/batches/{b2['id']}/log").json()
        assert any("requeued" in x["text"] for x in log)
        assert wait_for(lambda: api.get(f"/api/batches/{b2['id']}").json()["status"] == "done", 60)
        bv = api.get(f"/api/batches/{b2['id']}").json()
        assert [t["status"] for t in bv["molecules"][0]["tasks"]] == ["done", "done"]
    finally:
        try:
            os.killpg(srv.pid, signal.SIGTERM)
            srv.wait(10)
        except Exception:
            pass
