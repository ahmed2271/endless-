"""Job runner: scheduler, job execution, retries and restart recovery (sections 8.1-8.7).

One scheduler thread owns the queue. Each running ORCA job is watched by its own Job thread.
All state lives in SQLite, so the browser can close and the service can restart: on start,
`reconcile()` re-attaches to ORCA processes that are still alive and judges finished ones
from their output.
"""
from __future__ import annotations

import fnmatch
import os
import shutil
import signal
import subprocess
import threading
import time
import traceback
from pathlib import Path

from . import batches, checks, config, db, store, tools
from .assemble import Catalog, assemble, cell_value, is_blank
from .molecules import last_frame_of_trj, parse_xyz_text, write_xyz
from .parsers.aux_files import displace_along_mode, parse_hess

EXIT_FILE = ".studio_exit"
COND_SKIP = "skipped (condition):"
KEEP = {
    "results": ["*.inp", "*.out", "*.xyz", "*.hess", "*.gbw", "*.densities", "*.densitiesinfo", "*.scfp",
                "*.property.txt", "*.cube", "*.molden", "*.txt", "*.json", "*.png", "*.cis", "*.engrad", ".studio_*"],
    "minimal": ["*.inp", "*.out", "*.xyz", "*.property.txt", "*.txt", ".studio_*"],
}


def base_name(m: dict) -> str:
    d = m["dirname"]
    return d + "_m" if d.lower() in ("input", "previous", "start") else d


# --------------------------------------------------------------------------- process helpers
def proc_start_time(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/stat") as fh:
            data = fh.read()
        return data.rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def proc_alive(pid: int | None, start: str | None) -> bool:
    if not pid:
        return False
    st = proc_start_time(pid)
    if st is None:
        return False
    try:
        with open(f"/proc/{pid}/stat") as fh:
            state = fh.read().rsplit(")", 1)[1].split()[0]
        if state == "Z":
            return False
    except OSError:
        return False
    return start is None or st == start


def session_pids(sid: int) -> list[int]:
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            with open(f"/proc/{d}/stat") as fh:
                f = fh.read().rsplit(")", 1)[1].split()
            if int(f[3]) == sid:       # field 6 = session id
                out.append(int(d))
        except (OSError, IndexError, ValueError):
            continue
    return out


def kill_tree(pid: int, grace: float = 10.0) -> None:
    """Kill the whole process group/session of a job (ORCA spawns MPI children)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError):
            pass
        for p in session_pids(pid):
            try:
                os.kill(p, sig)
            except (ProcessLookupError, PermissionError):
                pass
        deadline = time.time() + (grace if sig == signal.SIGTERM else 2)
        while time.time() < deadline:
            if not session_pids(pid) and not proc_alive(pid, None):
                return
            time.sleep(0.2)


# --------------------------------------------------------------------------- job
class Job(threading.Thread):
    def __init__(self, runner: "Runner", task: dict, nprocs: int, mem: int, reattach: dict | None = None):
        super().__init__(daemon=True, name=f"job-{task['id']}")
        self.runner = runner
        self.task = task
        self.nprocs = nprocs
        self.mem = mem
        self.reattach = reattach
        self.cancel_event = threading.Event()
        self.pid: int | None = None
        self.batch_id = task["batch_id"]

    # ---------------------------------------------------------------- helpers
    def log(self, text, level="info"):
        db.log(self.batch_id, text, level)

    def set_task(self, **kw):
        kw["updated"] = time.time()
        cols = ", ".join(f"{k}=?" for k in kw)
        db.ex(f"UPDATE tasks SET {cols} WHERE id=?", (*[db.j(v) if isinstance(v, (dict, list)) else v
                                                         for v in kw.values()], self.task["id"]))

    def kill(self):
        self.cancel_event.set()
        if self.pid:
            kill_tree(self.pid)

    # ---------------------------------------------------------------- main
    def run(self):
        try:
            self._run()
        except Exception as e:  # never let a job thread die silently
            self.log(f"Internal error in job {self.task['id']}: {e}\n{traceback.format_exc()}", "error")
            self.set_task(status="failed", message=f"internal error: {e}")
            self.runner.after_failure(self.task, "internal error")
        finally:
            self.runner.release(self)

    def _ctx(self):
        b = batches.get(self.batch_id)
        m = db.q1("SELECT * FROM molecules WHERE id=?", (self.task["molecule_id"],))
        k = self.task["step_index"]
        step = b["profile"]["steps"][k]
        return b, m, k, step

    def _run(self):
        b, m, k, step = self._ctx()
        cat = Catalog()
        stype = cat.step_type(step.get("type"))
        wf = batches.workflow(step)
        sd = batches.step_dir(b, m, k)
        sd.mkdir(parents=True, exist_ok=True)
        self.set_task(step_dir=str(sd))
        if stype.get("kind") == "dscf":
            return self._run_dscf(b, m, k, step, stype, wf, sd, cat)
        base = base_name(m)
        state = (db.uj(db.q1("SELECT checks FROM tasks WHERE id=?", (self.task["id"],))["checks"], {}) or {}).get(
            "_retry", {"scf": 0, "opt": 0, "imag": 0, "additions": [], "extra_opt": False})
        if self.reattach:
            run = self.reattach
            self.reattach = None
            res = self._wait_and_check(run, sd, base, stype, wf, step, cat, state)
        else:
            self._prepare_geometry(b, m, k, sd)
            res = None
        while True:
            if res is None:
                if self.cancel_event.is_set():
                    return
                self._write_input(b, m, k, step, sd, base, cat, state)
                run = self._launch(sd, base, b, m, k, step)
                if run is None:
                    return
                res = self._wait_and_check(run, sd, base, stype, wf, step, cat, state)
            if res.get("cancelled"):
                return
            if res["ok"]:
                break
            nxt = self._retry_plan(res, wf, sd, base, state, stype, cat)
            if not nxt:
                break
            self.log(f"{m['name']} step {k + 1}: {nxt}", "warning")
            self._archive_attempt(sd, base, res["failure"])
            self.set_task(checks={"_retry": state, **res["checks"]}, message=f"retrying: {nxt}")
            res = None
        self._finish(b, m, k, step, wf, sd, base, res)

    # ---------------------------------------------------------------- preparation
    def _prepare_geometry(self, b, m, k, sd):
        src = None
        for j in range(k - 1, -1, -1):
            t = db.q1("SELECT * FROM tasks WHERE molecule_id=? AND step_index=?", (m["id"], j))
            if t and t["status"] == "done" and t["step_dir"]:
                pdir = Path(t["step_dir"])
                cand = pdir / f"{base_name(m)}.xyz"
                if cand.exists() and cand.stat().st_size:
                    src = cand
                    break
                if (pdir / "input.xyz").exists():
                    src = pdir / "input.xyz"
                    break
        if src is None:
            src = batches.start_xyz_path(b, m)
        target = sd / "input.xyz"
        text = src.read_text()
        try:
            rec = parse_xyz_text(text, m["name"])
            text = write_xyz(rec["atoms"], f"{m['name']} from {src.parent.name}/{src.name}")
        except Exception:
            pass
        target.write_text(text)
        (sd / ".studio_geometry_source").write_text(str(src) + "\n")

    def _prev_gbw(self, m, k, sd):
        for j in range(k - 1, -1, -1):
            t = db.q1("SELECT * FROM tasks WHERE molecule_id=? AND step_index=?", (m["id"], j))
            if t and t["status"] == "done" and t["step_dir"]:
                g = Path(t["step_dir"]) / f"{base_name(m)}.gbw"
                if g.exists():
                    shutil.copy2(g, sd / "previous.gbw")
                    return "previous.gbw"
                return None
        return None

    def _write_input(self, b, m, k, step, sd, base, cat, state, subjob=None, gbw=None, mult_force=None):
        mol = {"charge": m["charge"], "mult": m["mult"], "name": m["name"]}
        additions = list(state.get("additions") or [])
        if state.get("extra_opt"):
            additions.append({"destination": "keyword_line", "orca_text": store.text("step_types", "opt", "Opt"),
                              "slot": "job"})
        wf = batches.workflow(step)
        if wf.get("cubes", {}).get("densities") or wf.get("cubes", {}).get("mep"):
            additions.append({"destination": "keyword_line", "orca_text": store.text("assembly", "keepdens_keyword",
                                                                                      "KeepDens"), "slot": "properties"})
        use_inline = (k == 0 and m.get("coord_type") not in (None, "", "xyz") and m.get("raw_block")
                      and not state.get("geometry_replaced"))
        if gbw is None and not subjob:
            moread_wanted = cell_value(b["profile"], step, "moread", cat) in (True, "true", "on", 1, "1", "yes")
            gbw = self._prev_gbw(m, k, sd) if moread_wanted else None
            allow = gbw is not None
        else:
            allow = True
        r = assemble(b["profile"], k, mol, subjob=subjob, catalog=cat, additions=additions, gbw=gbw,
                     inline_block=m["raw_block"] if use_inline else None,
                     coord_type=m.get("coord_type") or "xyz", molecule_name=m["name"], allow_moread=allow)
        text = r["text"]
        (sd / f"{base}.inp").write_text(text)
        return r

    # ---------------------------------------------------------------- run one ORCA process
    def _launch(self, sd, base, b, m, k, step, subjob=""):
        s = config.load_settings()
        orca = os.path.expanduser(s["programs"]["orca"])
        attempt = (db.q1("SELECT attempts FROM tasks WHERE id=?", (self.task["id"],))["attempts"] or 0) + 1
        self.set_task(attempts=attempt, status="running", message=f"running (attempt {attempt})" +
                      (f" {subjob}" if subjob else ""))
        workdir = sd
        scratch = s["folders"].get("scratch")
        if scratch:
            workdir = Path(scratch).expanduser() / "orca_studio" / f"b{b['id']}_m{m['id']}_s{k + 1}{('_' + subjob) if subjob else ''}"
            if workdir.exists():
                shutil.rmtree(workdir)
            shutil.copytree(sd, workdir)
        (workdir / EXIT_FILE).unlink(missing_ok=True)
        out_path = workdir / f"{base}.out"
        cmd = ["/bin/sh", "-c", '"$0" "$1"; echo $? > ' + EXIT_FILE, orca, f"{base}.inp"]
        nice = int(s["resources"].get("nice", 10) or 0)
        if nice and shutil.which("nice"):
            cmd = [shutil.which("nice"), "-n", str(nice)] + cmd
        try:
            fh = open(out_path, "w")
            proc = subprocess.Popen(cmd, cwd=workdir, stdout=fh, stderr=subprocess.STDOUT,
                                    env=tools.build_env(s),
                                    start_new_session=True)
            fh.close()
        except OSError as e:
            self.log(f"Could not start ORCA for {m['name']} step {k + 1}: {e}", "error")
            self.set_task(status="failed", message=f"could not start ORCA: {e}")
            self.runner.after_failure(self.task, "could not start ORCA")
            return None
        self.pid = proc.pid
        self._proc = proc
        rid = db.ex("INSERT INTO runs(task_id, batch_id, attempt, subjob, status, pid, pid_start, nprocs, mem_mb, start, "
                    "out_file) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (self.task["id"], self.batch_id, attempt, subjob, "running", proc.pid, proc_start_time(proc.pid),
                     self.nprocs, self.mem, time.time(), str(out_path)))
        self.log(f"Started {m['name']} step {k + 1} ({step.get('name')}){(' ' + subjob) if subjob else ''}, "
                 f"attempt {attempt}, PID {proc.pid}, {self.nprocs} cores")
        return db.q1("SELECT * FROM runs WHERE id=?", (rid,))

    def _wait(self, run, step) -> dict:
        """Wait for a run to end. Returns {'exit_code', 'cancelled', 'timeout'}."""
        wf = batches.workflow(step)
        limit = wf.get("time_limit_h")
        limit_s = float(limit) * 3600 if limit not in (None, "", 0, "0") else None
        self.pid = run["pid"]
        proc = getattr(self, "_proc", None)
        timed_out = False
        while True:
            if proc is not None and proc.pid == run["pid"]:
                if proc.poll() is not None:
                    break
            elif not proc_alive(run["pid"], run["pid_start"]):
                break
            if self.cancel_event.is_set():
                kill_tree(run["pid"])
                break
            if limit_s and time.time() - run["start"] > limit_s:
                self.log(f"Run {run['id']} hit the time limit ({limit} h): stopping it", "warning")
                kill_tree(run["pid"])
                timed_out = True
                break
            time.sleep(1.0)
        if proc is not None:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        workdir = Path(run["out_file"]).parent
        ec = None
        ef = workdir / EXIT_FILE
        for _ in range(10):
            if ef.exists():
                try:
                    ec = int(ef.read_text().strip() or "0")
                except ValueError:
                    ec = None
                break
            if self.cancel_event.is_set() or timed_out:
                break
            time.sleep(0.2)
        if ec is None and proc is not None and proc.returncode is not None and not self.cancel_event.is_set():
            ec = proc.returncode
        scratch = config.load_settings()["folders"].get("scratch")
        if scratch and str(workdir).startswith(str(Path(scratch).expanduser())):
            sd = Path(db.q1("SELECT step_dir FROM tasks WHERE id=?", (self.task["id"],))["step_dir"])
            sub = run.get("subjob") or ""
            dest = sd / sub if sub else sd
            for p in workdir.iterdir():
                if p.is_file() and not p.name.endswith(".tmp"):
                    shutil.copy2(p, dest / p.name)
            shutil.rmtree(workdir, ignore_errors=True)
            db.ex("UPDATE runs SET out_file=? WHERE id=?", (str(dest / Path(run["out_file"]).name), run["id"]))
            run["out_file"] = str(dest / Path(run["out_file"]).name)
        cancelled = self.cancel_event.is_set()
        status = "killed" if cancelled or timed_out else ("done" if ec == 0 else "failed")
        db.ex("UPDATE runs SET status=?, end=?, exit_code=? WHERE id=?", (status, time.time(), ec, run["id"]))
        self.pid = None
        return {"exit_code": ec, "cancelled": cancelled, "timeout": timed_out, "out": Path(run["out_file"])}

    def _wait_and_check(self, run, sd, base, stype, wf, step, cat, state) -> dict:
        w = self._wait(run, step)
        if w["cancelled"]:
            return {"cancelled": True, "ok": False}
        kws = (sd / f"{base}.inp").read_text() if (sd / f"{base}.inp").exists() else ""
        opt_expected = stype.get("kind") in checks.OPT_KINDS or bool(state.get("extra_opt"))
        freq_expected = stype.get("kind") in checks.FREQ_KINDS
        res = checks.evaluate(w["out"], w["exit_code"], stype.get("kind", "custom"), wf,
                              opt_expected=opt_expected, freq_expected=freq_expected)
        if w["timeout"]:
            res.update(ok=False, failure="time", summary="time limit reached; " + res["summary"])
        res["exit_code"] = w["exit_code"]
        return res

    # ---------------------------------------------------------------- retries (section 8.6)
    def _retry_plan(self, res, wf, sd, base, state, stype, cat) -> str | None:
        f = res["failure"]
        if f == "scf":
            strategies = list(wf.get("scf_retry") or [])
            i = int(state.get("scf", 0))
            if i < len(strategies):
                e = store.get_entry("retry_strategies", strategies[i])
                if e:
                    adds = [{"destination": e.get("destination", "keyword_line"), "orca_text": e["orca_text"],
                             "slot": "scf"}]
                    adds += [{"destination": a.get("destination"), "orca_text": a.get("orca_text", ""), "slot": "scf"}
                             for a in e.get("also") or []]
                    state["scf"] = i + 1
                    state["additions"] = adds
                    if stype.get("kind") in checks.OPT_KINDS:
                        self._use_last_geometry(sd, base, state)
                    for g in sd.glob(f"{base}.gbw"):
                        g.rename(sd / f"{base}.scf_fail{i + 1}.gbw")
                    return f"SCF did not converge; retry {i + 1} with {e['label']}"
            return None
        if f == "opt":
            n = int(wf.get("opt_restarts") or 0)
            i = int(state.get("opt", 0))
            if i < n and self._use_last_geometry(sd, base, state):
                state["opt"] = i + 1
                return f"optimization not converged; restart {i + 1} of {n} from the last geometry"
            return None
        if f == "imag":
            n = int(wf.get("imag_fix") or 0)
            i = int(state.get("imag", 0))
            hess = sd / f"{base}.hess"
            if i < n and hess.exists():
                try:
                    h = parse_hess(hess)
                    freqs = h.get("frequencies") or []
                    mode = min(range(len(freqs)), key=lambda q: freqs[q])
                    geom = displace_along_mode(h, mode, 0.15)
                except Exception as e:
                    self.log(f"could not read {hess.name} for displacement: {e}", "warning")
                    return None
                (sd / "input.xyz").write_text(write_xyz(geom, f"displaced along mode {mode} ({freqs[mode]:.1f} cm-1)"))
                state["imag"] = i + 1
                state["geometry_replaced"] = True
                if stype.get("kind") == "freq":
                    state["extra_opt"] = True
                return f"imaginary frequency {freqs[mode]:.1f} cm-1; displaced along it and re-optimizing ({i + 1}/{n})"
            return None
        return None

    def _use_last_geometry(self, sd, base, state) -> bool:
        trj = sd / f"{base}_trj.xyz"
        src = None
        try:
            if trj.exists() and trj.stat().st_size:
                rec = last_frame_of_trj(trj)
                src = write_xyz(rec["atoms"], "last geometry of previous attempt")
            elif (sd / f"{base}.xyz").exists():
                rec = parse_xyz_text((sd / f"{base}.xyz").read_text(), base)
                src = write_xyz(rec["atoms"], "last geometry of previous attempt")
        except Exception:
            src = None
        if src:
            (sd / "input.xyz").write_text(src)
            state["geometry_replaced"] = True
            return True
        return False

    def _archive_attempt(self, sd, base, why):
        n = 1
        while (sd / f"{base}.attempt{n}.out").exists():
            n += 1
        for ext in (".out", ".inp"):
            p = sd / f"{base}{ext}"
            if p.exists():
                p.rename(sd / f"{base}.attempt{n}{ext}")

    # ---------------------------------------------------------------- finish
    def _finish(self, b, m, k, step, wf, sd, base, res):
        status = "done" if res["ok"] else "failed"
        chk = dict(res["checks"])
        self.set_task(status=status, message=res["summary"], checks=chk, fired=res["fired"])
        self.log(f"{m['name']} step {k + 1} ({step.get('name')}): {status.upper()} - {res['summary']}",
                 "info" if res["ok"] else "error")
        if res["ok"]:
            self.runner.post_success(b, m, k, step, wf, sd, base)
        else:
            self.runner.after_failure(self.task, res["summary"])
        self.runner.post_any(b, m, k)

    # ---------------------------------------------------------------- ΔSCF (linked sub-jobs)
    def _run_dscf(self, b, m, k, step, stype, wf, sd, cat):
        base = base_name(m)
        if not self.reattach:
            self._prepare_geometry(b, m, k, sd)
        results = {}
        want_t = cell_value(b["profile"], step, "dscf_triplet", cat) in (True, "true", "on", 1, "1", "yes")
        state = {"additions": []}
        done_subjobs = set()
        if self.reattach:
            # re-attached after a restart: finish this sub-job first
            sub = self.reattach.get("subjob") or "gs"
            run = self.reattach
            self.reattach = None
            res = self._wait_and_check(run, sd / sub, base, {"kind": "sp"}, wf, step, cat, state)
            results[sub] = res
            done_subjobs.add(sub)
        for sj in stype.get("subjobs") or []:
            sid = sj["id"]
            if sid in done_subjobs:
                continue
            if sj.get("only_if_column") == "dscf_triplet" and not want_t:
                continue
            if any(not r.get("ok") for r in results.values()):
                break
            sub = sd / sid
            sub.mkdir(exist_ok=True)
            out_existing = sub / f"{base}.out"
            if out_existing.exists() and "ORCA TERMINATED NORMALLY" in out_existing.read_text(errors="replace"):
                results[sid] = checks.evaluate(out_existing, 0, "sp", wf)
                continue
            shutil.copy2(sd / "input.xyz", sub / "input.xyz")
            gbw = None
            if sj.get("moread_from"):
                src = sd / sj["moread_from"] / f"{base}.gbw"
                if src.exists():
                    shutil.copy2(src, sub / "previous.gbw")
                    gbw = "previous.gbw"
            self._write_input(b, m, k, step, sub, base, cat, state, subjob=sid, gbw=gbw)
            run = self._launch(sub, base, b, m, k, step, subjob=sid)
            if run is None:
                return
            res = self._wait_and_check(run, sub, base, {"kind": "sp"}, wf, step, cat, state)
            if res.get("cancelled"):
                return
            results[sid] = res
        ok = all(r.get("ok") for r in results.values()) and "gs" in results and "es" in results
        fired = sorted({f for r in results.values() for f in r.get("fired", [])})
        chk = {f"{sid}:{name}": v for sid, r in results.items() for name, v in (r.get("checks") or {}).items()}
        # collapse check: excited state energy must differ from the ground state
        try:
            from .parsers.orca_out import OrcaOut
            egs = OrcaOut.from_file(sd / "gs" / f"{base}.out").final_energy
            ees = OrcaOut.from_file(sd / "es" / f"{base}.out").final_energy
            if egs is not None and ees is not None:
                de = (ees - egs) * 27.211386
                collapsed = de < 0.05
                chk["collapse"] = {"status": "fail" if collapsed else "pass",
                                   "detail": f"ΔE = {de:.3f} eV" + (" (collapsed to the ground state)" if collapsed else "")}
                if collapsed:
                    ok = False
                    fired.append("collapse")
        except Exception:
            pass
        summary = "; ".join(f"{k_}: {v['detail']}" for k_, v in chk.items() if v["status"] != "pass") or "all checks passed"
        self._finish(b, m, k, step, wf, sd, base, {"ok": ok, "checks": chk, "fired": fired, "summary": summary,
                                                    "failure": None if ok else "dscf"})


# --------------------------------------------------------------------------- runner
class Runner:
    def __init__(self):
        self.lock = threading.RLock()
        self.jobs: dict[int, Job] = {}        # task_id -> Job
        self.post_threads: set[threading.Thread] = set()   # cube / script work after jobs
        self.thread: threading.Thread | None = None
        self.stop_event = threading.Event()
        self.rr = 0
        self.wakeup = threading.Event()

    # ---------------------------------------------------------------- lifecycle
    def start(self):
        db.init()
        self.reconcile()
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name="scheduler")
        self.thread.start()

    def stop(self):
        """Stop scheduling. Running ORCA processes are left alone (they keep running)."""
        self.stop_event.set()
        self.wakeup.set()
        if self.thread:
            self.thread.join(timeout=5)

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as e:
                db.log(None, f"scheduler error: {e}\n{traceback.format_exc()}", "error")
            self.wakeup.wait(2.0)
            self.wakeup.clear()

    def poke(self):
        self.wakeup.set()

    # ---------------------------------------------------------------- accounting
    def used(self) -> tuple[int, int]:
        with self.lock:
            return sum(j.nprocs for j in self.jobs.values()), sum(j.mem for j in self.jobs.values())

    def release(self, job: Job):
        with self.lock:
            self.jobs.pop(job.task["id"], None)
        self.poke()

    # ---------------------------------------------------------------- restart recovery
    def reconcile(self):
        """After a service restart: re-attach to live ORCA runs, judge finished ones, requeue lost ones."""
        for run in db.q("SELECT * FROM runs WHERE status='running'"):
            task = db.q1("SELECT * FROM tasks WHERE id=?", (run["task_id"],))
            if not task:
                db.ex("UPDATE runs SET status='lost' WHERE id=?", (run["id"],))
                continue
            b = batches.get(task["batch_id"])
            alive = proc_alive(run["pid"], run["pid_start"])
            out = Path(run["out_file"] or "")
            exit_file = out.parent / EXIT_FILE
            if alive:
                db.log(task["batch_id"], f"Service restarted: re-attached to running job PID {run['pid']} "
                                         f"({out.name}, step {task['step_index'] + 1})")
                self._start_job(task, b, reattach=run)
            elif exit_file.exists() or (out.exists() and "ORCA TERMINATED NORMALLY" in out.read_text(errors="replace")):
                db.log(task["batch_id"], f"Service restarted: job {out.name} finished while the service was down; "
                                         f"checking its output")
                self._start_job(task, b, reattach=run)
            else:
                db.ex("UPDATE runs SET status='lost', end=? WHERE id=?", (time.time(), run["id"]))
                db.ex("UPDATE tasks SET status='pending', message='requeued: process was gone after restart' "
                      "WHERE id=?", (task["id"],))
                db.log(task["batch_id"], f"Service restarted: job {out.name} was no longer running and did not "
                                         f"finish; requeued", "warning")
        with self.lock:
            running_tasks = set(self.jobs)
        for t in db.q("SELECT * FROM tasks WHERE status='running'"):
            if t["id"] not in running_tasks:
                db.ex("UPDATE tasks SET status='pending', message='requeued after restart' WHERE id=?", (t["id"],))

    # ---------------------------------------------------------------- scheduling
    def _start_job(self, task, b, reattach=None):
        s = config.load_settings()
        from .assemble import resources
        step = b["profile"]["steps"][task["step_index"]]
        nprocs, maxcore = resources(b["profile"], step, s)
        total = int(s["resources"]["total_cores"])
        need = min(nprocs, total)
        job = Job(self, task, need, nprocs * maxcore, reattach=reattach)
        with self.lock:
            self.jobs[task["id"]] = job
        db.ex("UPDATE tasks SET status='running', updated=? WHERE id=?", (time.time(), task["id"]))
        job.start()
        return job

    def eligible(self, b: dict, tasks: list[dict], mols: dict[int, dict]) -> list[dict]:
        """Tasks that may start now (section 8.1). Also applies skip rules (run conditions)."""
        steps = b["profile"].get("steps") or []
        by = {(t["molecule_id"], t["step_index"]): t for t in tasks}
        active_mids = [mid for mid in mols]
        out = []
        for t in tasks:
            if t["status"] not in ("pending", "queued") or t["molecule_id"] not in mols:
                continue
            k = t["step_index"]
            if k >= len(steps):
                continue
            if k > 0:
                prev = by.get((t["molecule_id"], k - 1))
                if not prev or prev["status"] not in batches.TERMINAL:
                    continue
                wf_prev = batches.workflow(steps[k - 1])
                if wf_prev["between"] in ("wait_all", "pause"):
                    if any(by.get((mid, k - 1), {}).get("status") not in batches.TERMINAL for mid in active_mids):
                        continue
                    if wf_prev["between"] == "pause" and (k - 1) not in b["released_steps"]:
                        continue
                if prev["status"] in ("failed", "cancelled"):
                    self._skip(t, f"skipped: step {k} {prev['status']}")
                    continue
                # run conditions look at the last step that actually ran for this molecule
                ran = prev
                j = k - 1
                while ran and ran["status"] == "skipped" and (ran.get("message") or "").startswith(COND_SKIP) and j > 0:
                    j -= 1
                    ran = by.get((t["molecule_id"], j))
                cond = batches.workflow(steps[k])["run_condition"]
                if cond == "prev_success" and ran["status"] != "done":
                    self._skip(t, f"{COND_SKIP} step {j + 1} did not succeed")
                    continue
                if cond == "check_fired" and not ran["fired"]:
                    self._skip(t, f"{COND_SKIP} no check fired in step {j + 1}")
                    continue
            out.append(t)
        order = {}
        for t in out:
            wf = batches.workflow(steps[t["step_index"]])
            m = mols[t["molecule_id"]]
            if wf["order"] == "smallest":
                key = (t["step_index"], m["natoms"] or 0, m["order_idx"])
            elif wf["order"] == "largest":
                key = (t["step_index"], -(m["natoms"] or 0), m["order_idx"])
            else:
                key = (t["step_index"], m["order_idx"], m["id"])
            order[t["id"]] = key
        return sorted(out, key=lambda t: order[t["id"]])

    def _skip(self, t, msg):
        db.ex("UPDATE tasks SET status='skipped', message=?, updated=? WHERE id=?", (msg, time.time(), t["id"]))
        t["status"] = "skipped"

    def tick(self):
        s = config.load_settings()
        total_cores = int(s["resources"]["total_cores"])
        total_mem = int(s["resources"].get("total_memory_mb") or 10 ** 9)
        blist = db.q("SELECT id FROM batches WHERE status IN ('running','paused','review','stopped') "
                     "AND kind='calc' ORDER BY id")
        candidates: dict[int, list[dict]] = {}
        for row in blist:
            b = batches.get(row["id"])
            mols = {m["id"]: m for m in batches.molecules(b["id"])}
            tasks = batches.tasks(b["id"])
            if b["status"] == "running":
                el = self.eligible(b, tasks, mols)
                el_ids = {t["id"] for t in el}
                # 'queued' = may start as soon as cores are free
                for t in tasks:
                    if t["status"] == "pending" and t["id"] in el_ids:
                        db.ex("UPDATE tasks SET status='queued' WHERE id=?", (t["id"],))
                    elif t["status"] == "queued" and t["id"] not in el_ids:
                        db.ex("UPDATE tasks SET status='pending' WHERE id=?", (t["id"],))
                with self.lock:
                    el = [t for t in el if t["id"] not in self.jobs]
                candidates[b["id"]] = [(t, b) for t in el]
            self._check_batch_state(b, tasks)
        # round-robin between batches
        bids = [bid for bid in candidates if candidates[bid]]
        if not bids:
            return
        self.rr = (self.rr + 1) % len(bids)
        bids = bids[self.rr:] + bids[:self.rr]
        progressed = True
        while progressed:
            progressed = False
            for bid in bids:
                lst = candidates[bid]
                if not lst:
                    continue
                t, b = lst[0]
                step = b["profile"]["steps"][t["step_index"]]
                from .assemble import resources
                nprocs, maxcore = resources(b["profile"], step, s)
                need = min(nprocs, total_cores)
                used_c, used_m = self.used()
                if used_c + need <= total_cores and (used_m + nprocs * maxcore <= total_mem or used_c == 0):
                    lst.pop(0)
                    cur = db.q1("SELECT status FROM batches WHERE id=?", (bid,))
                    if cur and cur["status"] == "running":
                        self._start_job(t, b)
                        progressed = True

    def _check_batch_state(self, b, tasks):
        if not tasks:
            return
        steps = b["profile"].get("steps") or []
        with self.lock:
            running = any(j.batch_id == b["id"] for j in self.jobs.values())
        all_terminal = all(t["status"] in batches.TERMINAL for t in tasks)
        if all_terminal and not running and b["status"] in ("running", "stopped", "review"):
            n_done = sum(1 for t in tasks if t["status"] == "done")
            n_fail = sum(1 for t in tasks if t["status"] == "failed")
            batches.set_status(b["id"], "done")
            msg = f"Batch '{b['name']}' finished: {n_done} jobs done, {n_fail} failed"
            db.log(b["id"], msg)
            notify(msg, "info" if not n_fail else "warning", b["id"])
            return
        if b["status"] == "running":
            for k, st in enumerate(steps[:-1]):
                if batches.workflow(st)["between"] != "pause" or k in b["released_steps"]:
                    continue
                at_k = [t for t in tasks if t["step_index"] == k]
                nxt = [t for t in tasks if t["step_index"] == k + 1 and t["status"] in ("pending", "queued")]
                if at_k and all(t["status"] in batches.TERMINAL for t in at_k) and nxt:
                    batches.set_status(b["id"], "review")
                    msg = f"Batch '{b['name']}': step {k + 1} finished. Review the results, then press Continue."
                    db.log(b["id"], msg)
                    notify(msg, "info", b["id"])
                    break

    # ---------------------------------------------------------------- after a job
    def after_failure(self, task, why):
        b = batches.get(task["batch_id"])
        steps = b["profile"].get("steps") or []
        k = task["step_index"]
        wf = batches.workflow(steps[k]) if k < len(steps) else {}
        m = db.q1("SELECT name FROM molecules WHERE id=?", (task["molecule_id"],))
        if wf.get("after_failure") == "stop":
            batches.set_status(b["id"], "stopped")
            msg = f"Batch '{b['name']}' stopped: {m['name'] if m else '?'} failed at step {k + 1} ({why})"
            db.log(b["id"], msg, "error")
            notify(msg, "error", b["id"])
        else:
            db.ex("UPDATE tasks SET status='skipped', message=? WHERE molecule_id=? AND step_index>? AND status IN "
                  "('pending','queued')", (f"skipped: step {k + 1} failed", task["molecule_id"], k))
            notify(f"{m['name'] if m else '?'} failed at step {k + 1} in batch '{b['name']}'", "warning", b["id"])
        self.poke()

    def post_success(self, b, m, k, step, wf, sd, base):
        """Scripts and cubes run in their own thread after the job, so a batch is finished as soon
        as ORCA is; a slow or failing post-processing step never holds the batch."""
        if not wf.get("scripts") and not wf.get("cubes"):
            cleanup(sd, wf.get("keep", "all"))
            return

        def work():
            for hook in ("scripts", "cubes"):
                try:
                    if hook == "scripts" and wf.get("scripts"):
                        from . import scripts_reg
                        scripts_reg.run_step_scripts(b, m, k, step, sd, base)
                    if hook == "cubes" and wf.get("cubes"):
                        from . import visuals
                        visuals.auto_cubes(b, m, k, step, sd, base, wf["cubes"])
                except Exception as e:
                    db.log(b["id"], f"{m['name']} step {k + 1}: post-processing ({hook}) failed: {e}", "warning")
            cleanup(sd, wf.get("keep", "all"))
            with self.lock:
                self.post_threads.discard(threading.current_thread())

        t = threading.Thread(target=work, daemon=True, name=f"post-{m['id']}-{k}")
        with self.lock:
            self.post_threads.add(t)
        db.log(b["id"], f"{m['name']} step {k + 1}: making cubes / running scripts in the background")
        t.start()

    def post_any(self, b, m, k):
        try:
            from . import extraction
            extraction.on_task_finished(b["id"], m["id"], k)
        except Exception as e:
            db.log(b["id"], f"extraction after {m['name']} step {k + 1} failed: {e}", "warning")

    # ---------------------------------------------------------------- user controls
    def run_batch(self, batch_id):
        batches.ensure_tasks(batch_id)
        batches.set_status(batch_id, "running")
        db.log(batch_id, "Batch started")
        self.poke()

    def pause(self, batch_id):
        batches.set_status(batch_id, "paused")
        db.ex("UPDATE tasks SET status='pending' WHERE batch_id=? AND status='queued'", (batch_id,))
        db.log(batch_id, "Paused: running jobs finish, nothing new starts")

    def resume(self, batch_id):
        batches.set_status(batch_id, "running")
        db.log(batch_id, "Resumed")
        self.poke()

    def continue_review(self, batch_id):
        b = batches.get(batch_id)
        steps = b["profile"].get("steps") or []
        rel = set(b["released_steps"])
        tasks = batches.tasks(batch_id)
        for k in range(len(steps)):
            at_k = [t for t in tasks if t["step_index"] == k]
            if at_k and all(t["status"] in batches.TERMINAL for t in at_k):
                rel.add(k)
        db.ex("UPDATE batches SET released_steps=?, status='running' WHERE id=?", (db.j(sorted(rel)), batch_id))
        db.log(batch_id, "Continue pressed after review")
        self.poke()

    def cancel(self, batch_id):
        batches.set_status(batch_id, "cancelled")
        with self.lock:
            jobs = [j for j in self.jobs.values() if j.batch_id == batch_id]
        for j in jobs:
            j.kill()
        for j in jobs:
            j.join(timeout=20)
        db.ex("UPDATE tasks SET status='cancelled', message='cancelled by user' WHERE batch_id=? AND status IN "
              "('pending','queued','running')", (batch_id,))
        db.log(batch_id, f"Cancelled; {len(jobs)} running job(s) killed", "warning")

    def retry_failed(self, batch_id):
        n = 0
        for t in db.q("SELECT * FROM tasks WHERE batch_id=? AND status IN ('failed','cancelled')", (batch_id,)):
            db.ex("UPDATE tasks SET status='pending', message='retry requested', checks='{}', fired='[]' WHERE id=?",
                  (t["id"],))
            db.ex("UPDATE tasks SET status='pending', message='' WHERE molecule_id=? AND step_index>? AND "
                  "status IN ('skipped','cancelled')", (t["molecule_id"], t["step_index"]))
            n += 1
        batches.set_status(batch_id, "running")
        db.log(batch_id, f"Retry requested for {n} failed job(s)")
        self.poke()
        return n

    def status(self) -> dict:
        s = config.load_settings()
        used_c, used_m = self.used()
        queued = db.q1("SELECT COUNT(*) AS n FROM tasks t JOIN batches b ON b.id=t.batch_id "
                       "WHERE t.status='queued' AND b.status='running'")["n"]
        return {"cores_used": used_c, "cores_total": int(s["resources"]["total_cores"]), "mem_used_mb": used_m,
                "mem_total_mb": int(s["resources"].get("total_memory_mb") or 0), "running": len(self.jobs),
                "post_processing": len(self.post_threads),
                "queued": queued}


def cleanup(sd: Path, keep: str):
    """Delete files after success according to 'files to keep'; never .inp, .out or .xyz."""
    if keep not in KEEP:
        return
    pats = KEEP[keep]
    for p in list(sd.iterdir()):
        if not p.is_file():
            continue
        if p.suffix in (".inp", ".out", ".xyz") or any(fnmatch.fnmatch(p.name, pat) for pat in pats):
            continue
        try:
            p.unlink()
        except OSError:
            pass


def notify(text: str, level: str = "info", batch_id: int | None = None):
    db.notify(text, level, batch_id)
    cmd = (config.load_settings().get("notifications") or {}).get("command") or ""
    if cmd:
        import shlex
        try:
            args = [a.replace("{text}", text) for a in shlex.split(cmd)]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        except (OSError, ValueError):
            pass


RUNNER = Runner()
