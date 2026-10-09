#!/usr/bin/env python3
"""Batch-run ORCA 6.0.1: every subfolder of the current directory is one job.

    cd /path/to/jobs                     # the folder that contains the job subfolders
    python3 run_orca_batch.py            # run every subfolder
    python3 run_orca_batch.py "mol 1"    # run only the named subfolder(s)
    python3 run_orca_batch.py --dry-run  # show what would happen; change nothing

Standard library only, Python 3.8+.
"""

import argparse
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #
ORCA_CMD = "/home/utopia/orca_6_0_1/orca"  # full path: ORCA needs it to find its MPI binaries
MAX_PARALLEL_JOBS = 8                      # folders running at the same time
INPUT_HEADER = """\
! B3LYP def2-SVP Opt Freq
! PAL4
%maxcore 2000
"""                                        # %maxcore = memory per core, in MB
DEFAULT_CHARGE = 0
DEFAULT_MULT = 1

LOG_FILE = "batch_log.txt"                 # the summary is appended here (root folder)
SUCCESS_MARK = "ORCA TERMINATED NORMALLY"
STOP_GRACE_SECONDS = 15                    # Ctrl+C: SIGTERM first, SIGKILL after this long

# First line of the coordinate block: "* xyz 0 1", "* int 0 1", "* xyzfile 0 1 geom.xyz", ...
COORD_LINE_RE = re.compile(r"^\s*\*\s*(xyzfile|xyz|gzmtfile|gzmt|internal|int)\b", re.I)
# Files ORCA writes itself (trajectories, optimised geometries, IRC/NEB paths, atomic-guess jobs).
# They are never treated as inputs.
ORCA_GENERATED_RE = re.compile(r"(_trj|\.opt|_IRC_[FB]|_NEB[-\w]*|_atom\d+)\.(xyz|inp)$", re.I)
CHARGE_RE = re.compile(r"\bcharge\s*=\s*([+-]?\d+)", re.I)
MULT_RE = re.compile(r"\bmult(?:iplicity)?\s*=\s*(\d+)", re.I)
UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.+-]")

PRINT_LOCK = threading.Lock()
STOP = threading.Event()  # set on Ctrl+C so that workers never start another ORCA run


@dataclass
class Job:
    name: str                       # folder name, used in status lines
    folder: Path
    inp: str                        # input file name inside the folder
    action: str = ""                # what was done to prepare the input
    warnings: List[str] = field(default_factory=list)

    @property
    def out(self):
        return os.path.splitext(self.inp)[0] + ".out"


@dataclass
class Result:
    name: str
    status: str                     # DONE / ERROR / SKIP
    detail: str = ""
    elapsed: Optional[float] = None


class SkipFolder(Exception):
    """The folder is deliberately not run; the message says why."""


class InputError(Exception):
    """The folder's input could not be prepared."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def log(msg=""):
    with PRINT_LOCK:
        try:
            print(msg, flush=True)
        except OSError:             # terminal went away; the log file still gets the summary
            pass


def fmt_time(seconds):
    return "--" if seconds is None else str(timedelta(seconds=int(seconds)))


def natural_key(name):
    """Sort "mol2" before "mol10"."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def status_line(res, progress=""):
    return "%s %-7s %s%s  %s  %s" % (time.strftime("%H:%M:%S"), "[%s]" % res.status,
                                     progress, res.name, fmt_time(res.elapsed), res.detail)


def read_text(path):
    # surrogateescape round-trips any byte, so odd characters in comments survive a rewrite
    return path.read_text(encoding="utf-8", errors="surrogateescape")


def write_atomic(path, text):
    """Write via a temp file so an interrupted write never leaves a half-written input."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", errors="surrogateescape")
    os.replace(str(tmp), str(path))


def unique_path(path):
    """`path`, or path with _1, _2, ... added to the stem if it already exists."""
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name("%s_%d%s" % (path.stem, n, path.suffix))
        n += 1
    return candidate


def is_float(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


def read_tail(path, nbytes):
    """Last `nbytes` of a file as text ("" if it does not exist). ORCA .out files can be large."""
    try:
        with open(str(path), "rb") as f:
            f.seek(0, os.SEEK_END)
            f.seek(max(0, f.tell() - nbytes))
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def terminated_normally(out_path):
    return SUCCESS_MARK in read_tail(out_path, 256 * 1024)


def error_hint(out_path):
    """The most telling error line near the end of the .out, for the status line."""
    lines = read_tail(out_path, 64 * 1024).splitlines()
    for keys in (("error termination",), ("error", "abort")):
        for line in reversed(lines):
            if any(k in line.lower() for k in keys):
                return line.strip()[:100]
    return ""


def header_pal(header):
    m = (re.search(r"^\s*!.*\bPAL(\d+)\b", header, re.I | re.M)
         or re.search(r"%pal\b.*?\bnprocs\s+(\d+)", header, re.I | re.S))
    return int(m.group(1)) if m else 1


def header_maxcore(header):
    m = re.search(r"^\s*%maxcore\s+(\d+)", header, re.I | re.M)
    return int(m.group(1)) if m else None


# --------------------------------------------------------------------------- #
# Input preparation
# --------------------------------------------------------------------------- #
def discover_folders(root, only):
    """Every subfolder of `root` except hidden ones and __pycache__ (optionally only `only`)."""
    with os.scandir(str(root)) as it:
        names = [e.name for e in it
                 if e.is_dir() and not e.name.startswith(".") and e.name != "__pycache__"]
    if only:
        wanted = [Path(a).name or a for a in only]   # accept "mol1/" from tab completion
        for w in wanted:
            if w not in names:
                log("WARNING: '%s' is not a job folder in %s; ignored" % (w, root))
        names = [n for n in names if n in wanted]
    return [root / n for n in sorted(names, key=natural_key)]


def list_inputs(folder):
    """Candidate .inp and .xyz files in a folder, ignoring ORCA-generated ones."""
    inps, xyzs = [], []
    with os.scandir(str(folder)) as it:
        for e in it:
            if e.name.startswith(".") or not e.is_file() or ORCA_GENERATED_RE.search(e.name):
                continue
            ext = os.path.splitext(e.name)[1].lower()
            if ext == ".inp":
                inps.append(e.name)
            elif ext == ".xyz":
                xyzs.append(e.name)
    return sorted(inps), sorted(xyzs)


def ensure_not_finished(job):
    if terminated_normally(job.folder / job.out):
        raise SkipFolder("already finished (%s in %s)" % (SUCCESS_MARK, job.out))


def replace_header(inp_path, dry_run):
    """Option A: replace every line above the coordinate block with INPUT_HEADER.
    The coordinate block (with its charge/multiplicity) is kept as it is.
    Returns True if the file changes."""
    old = read_text(inp_path)
    lines = old.splitlines()            # also normalises Windows line endings
    start = next((i for i, line in enumerate(lines) if COORD_LINE_RE.match(line)), None)
    if start is None:
        raise InputError("%s: no coordinate block (* xyz / * int / * xyzfile) found" % inp_path.name)
    new = INPUT_HEADER.strip("\n") + "\n\n" + "\n".join(lines[start:]).rstrip() + "\n"
    if new == old:
        return False
    if not dry_run:
        backup = inp_path.parent / "backup" / inp_path.name
        if not backup.exists():         # keep the very first original
            backup.parent.mkdir(exist_ok=True)
            shutil.copy2(str(inp_path), str(backup))
        write_atomic(inp_path, new)
    return True


def build_from_xyz(job, xyz_name, dry_run):
    """Option B: write job.inp from an .xyz file, then move the .xyz into backup/."""
    xyz_path = job.folder / xyz_name
    lines = read_text(xyz_path).splitlines()
    try:
        natoms = int(lines[0].split()[0])
    except (IndexError, ValueError):
        raise InputError("%s: first line is not an atom count" % xyz_name) from None
    atoms = []
    for line in lines[2:2 + natoms]:    # skip the atom-count and comment lines
        parts = line.split()
        if len(parts) < 4 or not all(is_float(v) for v in parts[1:4]):
            raise InputError("%s: bad atom line %r" % (xyz_name, line.strip()))
        atoms.append(parts[:4])
    if natoms < 1 or len(atoms) != natoms:
        raise InputError("%s: atom count says %d but %d coordinate lines found"
                         % (xyz_name, natoms, len(atoms)))

    comment = lines[1] if len(lines) > 1 else ""
    m_charge, m_mult = CHARGE_RE.search(comment), MULT_RE.search(comment)
    charge = int(m_charge.group(1)) if m_charge else DEFAULT_CHARGE
    mult = int(m_mult.group(1)) if m_mult else DEFAULT_MULT
    defaults = [text for text, found in (("charge %d" % charge, m_charge), ("mult %d" % mult, m_mult))
                if not found]
    if defaults:
        job.warnings.append("no 'charge=X mult=Y' in the comment line of %s; using default %s"
                            % (xyz_name, " ".join(defaults)))

    coords = "\n".join("  %-2s  %14s  %14s  %14s" % tuple(a) for a in atoms)
    text = "%s\n\n* xyz %d %d\n%s\n*\n" % (INPUT_HEADER.strip("\n"), charge, mult, coords)
    job.action = "%s built from %s (charge %d, mult %d), %s -> backup/" % (
        job.inp, xyz_name, charge, mult, xyz_name)
    if dry_run:
        return
    write_atomic(job.folder / job.inp, text)
    backup = job.folder / "backup"
    backup.mkdir(exist_ok=True)
    shutil.move(str(xyz_path), str(unique_path(backup / xyz_name)))


def prepare(folder, dry_run):
    """Choose the folder's input and bring it into shape.
    Returns a Job, or raises SkipFolder / InputError."""
    inps, xyzs = list_inputs(folder)
    if len(inps) > 1:
        raise SkipFolder("WARNING: %d .inp files (%s); keep exactly one" % (len(inps), ", ".join(inps)))

    if inps:                                         # Option A: existing .inp
        job = Job(folder.name, folder, inps[0])
        ensure_not_finished(job)
        changed = replace_header(folder / job.inp, dry_run)
        job.action = "%s: header %s" % (job.inp, "-> INPUT_HEADER" if changed else "already up to date")
        if UNSAFE_NAME_RE.search(os.path.splitext(job.inp)[0]):
            job.warnings.append("file name has spaces/special characters; ORCA's parallel steps "
                                "may fail on it, consider renaming %s" % job.inp)
        return job

    if len(xyzs) > 1:
        raise SkipFolder("WARNING: %d .xyz files (%s) and no .inp; keep exactly one"
                         % (len(xyzs), ", ".join(xyzs)))
    if not xyzs:
        raise SkipFolder("no .inp or .xyz file")
    # Option B: build <name>.inp from the .xyz. Spaces/quotes in the name are replaced
    # with "_" because ORCA's MPI sub-programs cannot handle them.
    stem = UNSAFE_NAME_RE.sub("_", os.path.splitext(xyzs[0])[0])
    job = Job(folder.name, folder, stem + ".inp")
    ensure_not_finished(job)
    build_from_xyz(job, xyzs[0], dry_run)
    return job


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #
def run_job(job):
    """Run ORCA for one folder (in a worker thread). Never raises."""
    if STOP.is_set():
        return Result(job.name, "SKIP", "not started (interrupted)")
    log("%s [START] %s  (%s)" % (time.strftime("%H:%M:%S"), job.name, job.inp))
    out_path = job.folder / job.out
    t0 = time.monotonic()
    try:
        with open(str(out_path), "wb") as out:
            proc = subprocess.run(
                [ORCA_CMD, job.inp],      # argument list, no shell: any folder name is safe
                cwd=str(job.folder),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                start_new_session=True,   # own session, so Ctrl+C cleanup can find the whole MPI tree
            )
    except OSError as exc:
        return Result(job.name, "ERROR", "could not start ORCA: %s" % exc, time.monotonic() - t0)
    elapsed = time.monotonic() - t0

    rc = proc.returncode
    if rc == 0 and terminated_normally(out_path):
        return Result(job.name, "DONE", " | ".join([job.out] + job.warnings), elapsed)
    detail = "exit code %d" % rc
    if rc < 0:
        try:
            detail += " (killed by %s)" % signal.Signals(-rc).name
        except ValueError:
            detail += " (killed by signal %d)" % -rc
    if rc == 0:
        detail += ", but no '%s' in %s" % (SUCCESS_MARK, job.out)
    hint = error_hint(out_path)
    if hint:
        detail += ': "%s"' % hint
    return Result(job.name, "ERROR", detail, elapsed)


def orca_processes(sessions):
    """Live PIDs of everything ORCA started: ORCA itself, mpirun and the MPI ranks.

    Each ORCA run is a direct child of this script and leads its own session
    (start_new_session=True). Children found here are added to `sessions`, and every
    process in those sessions is returned, even ones re-parented after ORCA died."""
    me, procs = os.getpid(), []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % entry) as f:
                stat = f.read()
        except OSError:
            continue                    # the process just exited
        fields = stat[stat.rindex(")") + 2:].split()   # skip "pid (comm)"; comm may contain spaces
        procs.append((int(entry), fields[0], int(fields[1]), int(fields[3])))  # pid, state, ppid, sid
    sessions.update(pid for pid, _, ppid, _ in procs if ppid == me)
    return [pid for pid, state, _, sid in procs
            if state != "Z" and (pid in sessions or sid in sessions)]


def stop_all_orca(futures, force):
    """After Ctrl+C: SIGTERM every ORCA process tree, SIGKILL what is left after
    STOP_GRACE_SECONDS (at once if `force` gets set), and wait for the workers."""
    sessions, signalled = set(), set()
    kill_at = time.monotonic() + STOP_GRACE_SECONDS
    give_up_at = kill_at + 30
    while True:
        alive = orca_processes(sessions)
        if not alive and all(f.done() for f in futures):
            return
        if time.monotonic() > give_up_at:
            log("WARNING: could not stop PIDs %s; kill them by hand" % alive)
            return
        hard = force.is_set() or time.monotonic() > kill_at
        for pid in alive:
            if hard or pid not in signalled:
                try:
                    os.kill(pid, signal.SIGKILL if hard else signal.SIGTERM)
                except OSError:
                    pass
                signalled.add(pid)
        time.sleep(0.3)


def run_all(jobs, stop_signals):
    """Keep MAX_PARALLEL_JOBS folders running; the next starts as soon as one finishes.
    Returns (results, interrupted)."""
    results = []
    pool = ThreadPoolExecutor(max_workers=MAX_PARALLEL_JOBS)
    futures = {pool.submit(run_job, job): job for job in jobs}
    pending = set(futures)
    try:
        for fut in as_completed(futures):
            results.append(fut.result())
            pending.discard(fut)
            log(status_line(results[-1], "(%d/%d) " % (len(results), len(jobs))))
        return results, False
    except KeyboardInterrupt:
        force = threading.Event()       # first thing: a 2nd Ctrl+C must not abort the cleanup
        for sig in stop_signals:
            signal.signal(sig, lambda *_: force.set())
        STOP.set()
        log("\nInterrupted: stopping ORCA jobs (press Ctrl+C again to kill them at once)...")
        for fut in futures:
            fut.cancel()                # jobs that have not started never will
        stop_all_orca(futures, force)
        reported = {id(r) for r in results}
        for fut in sorted(pending, key=lambda f: natural_key(futures[f].name)):
            if fut.cancelled():
                res = Result(futures[fut].name, "SKIP", "not started (interrupted)")
            elif not fut.done():
                res = Result(futures[fut].name, "ERROR", "interrupted: ORCA could not be stopped")
            else:
                res = fut.result()
                if id(res) in reported:
                    continue
                if res.status == "ERROR":
                    res.detail = "interrupted: " + res.detail
            results.append(res)
            log(status_line(res))
        return results, True
    finally:
        pool.shutdown(wait=False)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def check_resources(n_jobs):
    """Print cores (and memory) needed vs. available; warn on oversubscription."""
    pal = header_pal(INPUT_HEADER)
    running = min(MAX_PARALLEL_JOBS, n_jobs)
    cores = running * pal
    cpus = os.cpu_count() or 1
    log("Cores: %d jobs at a time x PAL%d = %d needed, os.cpu_count() = %d"
        % (running, pal, cores, cpus))
    if cores > cpus:
        log("WARNING: oversubscribed (%d > %d): jobs will compete for CPUs and run slower. "
            "Lower MAX_PARALLEL_JOBS or PAL." % (cores, cpus))
    maxcore = header_maxcore(INPUT_HEADER)
    try:
        ram_mb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 20
    except (ValueError, OSError):
        ram_mb = 0
    if maxcore and ram_mb:
        log("Memory: %d cores x %%maxcore %d MB = %.1f GB of %.1f GB RAM"
            % (cores, maxcore, cores * maxcore / 1024, ram_mb / 1024))
        if cores * maxcore > 0.75 * ram_mb:
            log("WARNING: that is over 75% of RAM and ORCA can exceed %maxcore; "
                "lower %maxcore or MAX_PARALLEL_JOBS.")
    if pal > 1 and shutil.which("mpirun") is None:
        log("WARNING: 'mpirun' not found in PATH; PAL runs need OpenMPI on PATH and LD_LIBRARY_PATH.")


def write_summary(root, results, started_at, wall, interrupted):
    rows = sorted(results, key=lambda r: natural_key(r.name))
    width = max(len(r.name) for r in rows)
    counts = {s: sum(r.status == s for r in rows) for s in ("DONE", "ERROR", "SKIP")}
    lines = ["=" * 78,
             "ORCA batch summary   started %s   %s" % (started_at.strftime("%Y-%m-%d %H:%M:%S"), root),
             "-" * 78]
    lines += ["%-7s  %-*s  %8s  %s" % ("[%s]" % r.status, width, r.name, fmt_time(r.elapsed), r.detail)
              for r in rows]
    lines += ["-" * 78,
              "DONE: %(DONE)d   ERROR: %(ERROR)d   SKIP: %(SKIP)d" % counts
              + "   |   wall time %s%s" % (fmt_time(wall), "   (INTERRUPTED)" if interrupted else ""),
              "=" * 78]
    text = "\n".join(lines)
    log("\n" + text)
    try:
        with open(str(root / LOG_FILE), "a", encoding="utf-8", errors="replace") as f:
            f.write(text + "\n\n")
        log("Summary appended to %s" % (root / LOG_FILE))
    except OSError as exc:
        log("WARNING: could not write %s: %s" % (LOG_FILE, exc))


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def raise_interrupt(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(
        description="Batch-run ORCA: every subfolder of the current directory is one job.")
    parser.add_argument("folders", nargs="*", help="run only these subfolders (default: all)")
    parser.add_argument("--dry-run", action="store_true",
                        help="show what would be done without changing files or running ORCA")
    args = parser.parse_args()
    try:
        sys.stdout.reconfigure(errors="backslashreplace")   # odd bytes in folder names
    except AttributeError:
        pass

    # SIGTERM (kill PID) and a closed terminal (SIGHUP) clean up like Ctrl+C.
    # Under nohup SIGHUP stays ignored so the batch keeps running.
    stop_signals = [signal.SIGINT, signal.SIGTERM]
    signal.signal(signal.SIGTERM, raise_interrupt)
    if signal.getsignal(signal.SIGHUP) is not signal.SIG_IGN:
        signal.signal(signal.SIGHUP, raise_interrupt)
        stop_signals.append(signal.SIGHUP)

    root = Path.cwd()
    if not args.dry_run and not (os.path.isfile(ORCA_CMD) and os.access(ORCA_CMD, os.X_OK)):
        log("ERROR: ORCA executable not found or not executable: %s" % ORCA_CMD)
        return 2
    folders = discover_folders(root, args.folders)
    if not folders:
        log("No job folders found in %s" % root)
        return 1
    started_at, t0 = datetime.now(), time.monotonic()
    log("ORCA batch in %s: %d folder(s)%s" % (root, len(folders), "   [DRY RUN]" if args.dry_run else ""))

    # 1) Prepare inputs (quick, sequential)
    results, jobs = [], []
    try:
        for folder in folders:
            try:
                job = prepare(folder, args.dry_run)
            except SkipFolder as exc:
                results.append(Result(folder.name, "SKIP", str(exc)))
                log(status_line(results[-1]))
                continue
            except (InputError, OSError) as exc:
                results.append(Result(folder.name, "ERROR", "input: %s" % exc))
                log(status_line(results[-1]))
                continue
            jobs.append(job)
            log("%s [READY] %s: %s" % (time.strftime("%H:%M:%S"), job.name, job.action))
            for warning in job.warnings:
                log("         WARNING: %s" % warning)
    except KeyboardInterrupt:
        log("\nInterrupted while preparing inputs; no ORCA job was started.")
        return 130

    # 2) Resource check
    if jobs:
        log("")
        check_resources(len(jobs))
        log("")
    if args.dry_run:
        log("Dry run: %d job(s) would run. No files were changed." % len(jobs))
        return 0

    # 3) Run
    interrupted = False
    if jobs:
        run_results, interrupted = run_all(jobs, stop_signals)
        results += run_results
    else:
        log("Nothing to run.")
    write_summary(root, results, started_at, time.monotonic() - t0, interrupted)
    if interrupted:
        return 130
    return 1 if any(r.status == "ERROR" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
