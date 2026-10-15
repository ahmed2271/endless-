#!/usr/bin/env python3
"""ORCA multi-part pipeline manager.

Put this file in the root folder that holds the numbered job folders (1/, 2/, 7/, ...)
and run it from there:

    python3 orca_pipeline.py          # every enabled part, every numbered folder
    python3 orca_pipeline.py 7 12     # only folders 7 and 12 (use this for a first test)

PART 1  single point in <n>/SP-<n>/, the SP_data table, orca_plot cubes, mep.py hook
PART 2  TDDFT            (placeholder)
PART 3  deltaSCF         (placeholder)
PART 4  SP cation/anion  (placeholder)

Every step is safe to rerun: finished calculations, plots and mep.py runs are skipped.
Standard library only, Python 3.8+.
"""

import argparse
import hashlib
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

# ============================================================================ #
# Settings
# ============================================================================ #
# ---- Parts to run -------------------------------------------------------------
RUN_PART_1 = True    # single point, SP_data, orca_plot, mep.py
RUN_PART_2 = False   # TDDFT run and analysis            (placeholder)
RUN_PART_3 = False   # deltaSCF run and analysis         (placeholder)
RUN_PART_4 = False   # SP cation/anion run and analysis  (placeholder)

# ---- ORCA ---------------------------------------------------------------------
ORCA_DIR = "/home/utopia/orca_6_0_1"
ORCA_CMD = ORCA_DIR + "/orca"            # full path: required for MPI (PAL) runs
ORCA_PLOT_CMD = ORCA_DIR + "/orca_plot"
MAX_PARALLEL_JOBS = 8                    # ORCA calculations at the same time
MAX_PARALLEL_POSTPROC = 8                # orca_plot / mep.py runs at the same time

# ---- PART 1: single point -------------------------------------------------------
SP_METHOD = "B3LYP"
SP_BASIS = "def2-SVP"
SP_NPROCS = 4                            # -> ! PAL4
SP_MAXCORE = 2000                        # -> %maxcore (MB per core)
SP_HEADER_TEMPLATE = """\
! {method} {basis}
! PAL{nprocs}
%maxcore {maxcore}
"""
DEFAULT_CHARGE = 0       # used when neither the folder's .inp nor the .xyz comment
DEFAULT_MULT = 1         # line ("charge=X mult=Y") gives charge and multiplicity
SKIP_IF_OPT_UNFINISHED = True   # skip a folder whose own .out lacks ORCA TERMINATED NORMALLY

# SP_data: one row per folder. Orbital energies in eV, dipole moment in Debye.
SP_DATA_FILE = "SP_data"
SP_DATA_SEPARATOR = "\t"                 # "\t\t" for wider spacing
SP_ORBITALS = ["HOMO-2", "HOMO-1", "HOMO", "LUMO", "LUMO+1", "LUMO+2", "LUMO+3"]
AU_TO_DEBYE = 2.541746

# orca_plot: keystrokes typed into "orca_plot <name>.gbw -i".
# {homo} and {lumo} (orbital numbers from the SP output) and {grid} are filled in per folder.
PART1_PLOTS = True
PLOT_GRID = 180
ORCA_PLOT_KEYS = [
    "2", "{homo}", "4", "{grid}", "11",      # HOMO cube
    "2", "{lumo}", "4", "{grid}", "11",      # LUMO cube
    "1", "2", "y", "4", "{grid}", "11",      # electron density cube (for the ESP map)
    "12",                                    # exit orca_plot
]

# mep.py hook: once every folder is plotted, MEP_SCRIPT (in the root folder) is copied
# into each SP-<n> folder and run there.
PART1_MEP = True
MEP_SCRIPT = "mep.py"
MEP_ARGS = []            # extra arguments for mep.py; "{name}" / "{number}" are filled in

# ---- Less commonly changed --------------------------------------------------------
LOG_FILE = "pipeline_log.txt"            # every step's summary is appended here
SUCCESS_MARK = "ORCA TERMINATED NORMALLY"
PLOT_OUTPUT_GLOB = "*.cube"              # files orca_plot writes
PLOTS_EXPECTED = 3                       # HOMO + LUMO + density
ORCA_PLOT_TIMEOUT = 3600                 # seconds per folder
MEP_TIMEOUT = 6 * 3600                   # seconds per folder
POSTPROC_LOG_LIMIT = 50 * 2 ** 20        # bytes: stops a program stuck re-printing its menu
STOP_GRACE_SECONDS = 15                  # Ctrl+C: SIGTERM first, SIGKILL after this long
PLOT_MARKER = ".orca_plot.done"          # rerun guards; they record what was done
MEP_MARKER = ".mep.done"

# ============================================================================ #
# Patterns
# ============================================================================ #
# Files ORCA writes itself (trajectories, IRC/NEB paths, atomic-guess jobs): never inputs.
ORCA_GENERATED_RE = re.compile(r"(_trj|\.opt|_IRC_[FB]|_NEB[-\w]*|_atom\d+)\.(xyz|inp)$", re.I)
# "* xyz 0 1" / "* xyzfile 0 1 geom.xyz" / "* int 0 1" ... -> charge, multiplicity
COORD_CHARGE_MULT_RE = re.compile(
    r"^\s*\*\s*(?:xyzfile|xyz|gzmtfile|gzmt|internal|int)\s+([+-]?\d+)\s+(\d+)", re.I | re.M)
CHARGE_RE = re.compile(r"\bcharge\s*=\s*([+-]?\d+)", re.I)
MULT_RE = re.compile(r"\bmult(?:iplicity)?\s*=\s*(\d+)", re.I)
UNSAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_.+-]")
ORBITAL_LABEL_RE = re.compile(r"^(HOMO|LUMO)([+-]\d+)?$")
# Orbital table row:  NO   OCC   E(Eh)   E(eV)
ORBITAL_ROW_RE = re.compile(r"^\s*(\d+)\s+(\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$")
ENERGY_RE = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
DIPOLE_AU_RE = re.compile(r"Total Dipole Moment\s*:\s*(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)")
DIPOLE_DEBYE_RE = re.compile(r"Magnitude \(Debye\)\s*:\s*(-?\d+\.\d+)")

PRINT_LOCK = threading.Lock()
STOP = threading.Event()   # set on Ctrl+C so that workers never start another program


@dataclass
class Calc:
    """One calculation folder, e.g. 7/SP-7 with base name T9-2."""
    number: str                     # numbered folder, e.g. "7"
    dir: Path                       # e.g. <root>/7/SP-7
    name: str                       # base name of .inp/.out/.gbw, e.g. "T9-2"
    warnings: List[str] = field(default_factory=list)
    data: Optional[dict] = None     # parsed results (PART 1.2)
    plot_stamp: str = ""            # set once the cubes exist (PART 1.3)

    def file(self, ext):
        return self.dir / (self.name + ext)


@dataclass
class Context:
    """What every part needs."""
    root: Path
    folders: List[Path]             # numbered folders to work on
    partial: bool                   # True if only some folders were named on the command line
    stop_signals: list


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


class Stopped(Exception):
    """Ctrl+C (or SIGTERM) during a step: the pipeline stops."""


# ============================================================================ #
# Small helpers
# ============================================================================ #
def log(msg=""):
    with PRINT_LOCK:
        try:
            print(msg, flush=True)
        except OSError:             # terminal went away; the log file still gets summaries
            pass


def now():
    return time.strftime("%H:%M:%S")


def fmt_time(seconds):
    return "--" if seconds is None else str(timedelta(seconds=int(seconds)))


def status_line(res, progress=""):
    return "%s %-7s %s%s  %s  %s" % (now(), "[%s]" % res.status, progress, res.name,
                                     fmt_time(res.elapsed), res.detail)


def read_text(path):
    return path.read_text(encoding="utf-8", errors="surrogateescape")


def write_atomic(path, text):
    """Write via a temp file so an interrupted write never leaves a half-written file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8", errors="surrogateescape")
    os.replace(str(tmp), str(path))


def read_tail(path, nbytes):
    """Last `nbytes` of a file as text ("" if it does not exist)."""
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
    """The most telling error line near the end of an output file."""
    lines = read_tail(out_path, 64 * 1024).splitlines()
    for keys in (("error termination",), ("error", "abort")):
        for line in reversed(lines):
            if any(k in line.lower() for k in keys):
                return line.strip()[:100]
    return ""


def is_executable(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def file_stamp(path):
    """Size + mtime: changes whenever the file is rewritten."""
    st = path.stat()
    return "%d:%d" % (st.st_size, st.st_mtime_ns)


def marker_matches(path, stamp):
    try:
        return read_text(path) == stamp
    except OSError:
        return False


# ============================================================================ #
# Running programs
# ============================================================================ #
def run_logged(cmd, cwd, log_path, stdin_text=None, timeout=None, max_bytes=None):
    """Run `cmd` in `cwd` with stdout+stderr written to `log_path`.

    `stdin_text` is typed into the program (orca_plot's menu). `timeout` and `max_bytes`
    kill it if it hangs or floods the log, e.g. a menu waiting for input it never gets.
    Returns (exit code, reason it was killed or "")."""
    killed = []

    def kill(reason):
        if not killed:
            killed.append(reason)
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass

    with open(str(log_path), "wb") as out:
        proc = subprocess.Popen(
            cmd, cwd=str(cwd),
            stdin=subprocess.DEVNULL if stdin_text is None else subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True,   # own session: Ctrl+C cleanup finds the whole process tree
        )
        timer = None
        if timeout:
            timer = threading.Timer(timeout, kill, ["timed out after %d s" % timeout])
            timer.daemon = True
            timer.start()
        try:
            if stdin_text is not None:
                try:
                    proc.stdin.write(stdin_text.encode())
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
            written = 0
            for chunk in iter(lambda: proc.stdout.read1(65536), b""):
                if max_bytes and written + len(chunk) > max_bytes:
                    out.write(chunk[:max_bytes - written])
                    kill("output passed %d MB (stuck in a menu?)" % (max_bytes // 2 ** 20))
                    break
                out.write(chunk)
                written += len(chunk)
            proc.wait()
        finally:
            if timer:
                timer.cancel()
            proc.stdout.close()
    return proc.returncode, (killed[0] if killed else "")


def describe_exit(rc):
    text = "exit code %d" % rc
    if rc < 0:
        try:
            text += " (killed by %s)" % signal.Signals(-rc).name
        except ValueError:
            text += " (killed by signal %d)" % -rc
    return text


def child_processes(sessions):
    """Live PIDs of everything this script started (ORCA, mpirun, MPI ranks, orca_plot, ...).

    Each program is a direct child that leads its own session (start_new_session=True).
    Children found here are added to `sessions`, and every process in those sessions is
    returned, including ones re-parented after their parent died."""
    me, procs = os.getpid(), []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % entry) as f:
                stat = f.read()
        except OSError:
            continue                    # the process just exited
        fields = stat[stat.rindex(")") + 2:].split()   # skip "pid (comm)"; comm may hold spaces
        procs.append((int(entry), fields[0], int(fields[1]), int(fields[3])))  # pid, state, ppid, sid
    sessions.update(pid for pid, _, ppid, _ in procs if ppid == me)
    return [pid for pid, state, _, sid in procs
            if state != "Z" and (pid in sessions or sid in sessions)]


def stop_children(futures, force):
    """After Ctrl+C: SIGTERM every child process tree, SIGKILL what is left after
    STOP_GRACE_SECONDS (at once if `force` gets set), and wait for the workers."""
    sessions, signalled = set(), set()
    kill_at = time.monotonic() + STOP_GRACE_SECONDS
    give_up_at = kill_at + 30
    while True:
        alive = child_processes(sessions)
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


def run_parallel(tasks, workers, stop_signals):
    """Run tasks [(label, func)] with at most `workers` at once; the next one starts as
    soon as one finishes. Each func returns a Result. Returns (results, interrupted)."""
    def guarded(label, func):
        if STOP.is_set():
            return Result(label, "SKIP", "not started (interrupted)")
        try:
            return func()
        except Exception as exc:        # a bug or I/O error must not kill the whole batch
            return Result(label, "ERROR", "%s: %s" % (type(exc).__name__, exc))

    results = []
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = {pool.submit(guarded, label, func): label for label, func in tasks}
    pending = set(futures)
    try:
        for fut in as_completed(futures):
            results.append(fut.result())
            pending.discard(fut)
            log(status_line(results[-1], "(%d/%d) " % (len(results), len(tasks))))
        return results, False
    except KeyboardInterrupt:
        force = threading.Event()       # first thing: a 2nd Ctrl+C must not abort the cleanup
        for sig in stop_signals:
            signal.signal(sig, lambda *_: force.set())
        STOP.set()
        log("\nInterrupted: stopping running programs (press Ctrl+C again to kill them at once)...")
        for fut in futures:
            fut.cancel()                # tasks that have not started never will
        stop_children(futures, force)
        reported = {id(r) for r in results}
        for fut in pending:
            if fut.cancelled():
                res = Result(futures[fut], "SKIP", "not started (interrupted)")
            elif not fut.done():
                res = Result(futures[fut], "ERROR", "interrupted: could not be stopped")
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


def summarize(root, step, results, interrupted=False):
    """Print a step's summary table and append it to LOG_FILE. Returns True on any ERROR."""
    if not results:
        return False
    rows = sorted(results, key=lambda r: (int(r.name) if r.name.isdigit() else 0, r.name))
    width = max(len(r.name) for r in rows)
    counts = {s: sum(r.status == s for r in rows) for s in ("DONE", "ERROR", "SKIP")}
    lines = ["=" * 78,
             "%s   (%s)" % (step, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
             "-" * 78]
    lines += ["%-7s  %-*s  %8s  %s" % ("[%s]" % r.status, width, r.name, fmt_time(r.elapsed), r.detail)
              for r in rows]
    lines += ["-" * 78,
              "DONE: %(DONE)d   ERROR: %(ERROR)d   SKIP: %(SKIP)d" % counts
              + ("   (INTERRUPTED)" if interrupted else ""),
              "=" * 78]
    text = "\n".join(lines)
    log("\n" + text + "\n")
    try:
        with open(str(root / LOG_FILE), "a", encoding="utf-8", errors="replace") as f:
            f.write(text + "\n\n")
    except OSError as exc:
        log("WARNING: could not write %s: %s" % (LOG_FILE, exc))
    return counts["ERROR"] > 0


def check_resources(n_jobs, nprocs, maxcore):
    """Print cores (and memory) needed vs. available; warn on oversubscription."""
    running = min(MAX_PARALLEL_JOBS, n_jobs)
    cores = running * nprocs
    cpus = os.cpu_count() or 1
    log("Cores: %d jobs at a time x PAL%d = %d needed, os.cpu_count() = %d" % (running, nprocs, cores, cpus))
    if cores > cpus:
        log("WARNING: oversubscribed (%d > %d): jobs will compete for CPUs and run slower. "
            "Lower MAX_PARALLEL_JOBS or the PAL setting." % (cores, cpus))
    try:
        ram_mb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 2 ** 20
    except (ValueError, OSError):
        ram_mb = 0
    if ram_mb:
        log("Memory: %d cores x %%maxcore %d MB = %.1f GB of %.1f GB RAM"
            % (cores, maxcore, cores * maxcore / 1024, ram_mb / 1024))
        if cores * maxcore > 0.75 * ram_mb:
            log("WARNING: that is over 75% of RAM and ORCA can exceed %maxcore; "
                "lower %maxcore or MAX_PARALLEL_JOBS.")
    if nprocs > 1 and shutil.which("mpirun") is None:
        log("WARNING: 'mpirun' not found in PATH; PAL runs need OpenMPI on PATH and LD_LIBRARY_PATH.")


# ============================================================================ #
# Folder setup (shared by all parts)
# ============================================================================ #
def numbered_folders(root, only):
    """Subfolders of `root` whose name is a number, in numeric order."""
    with os.scandir(str(root)) as it:
        names = [e.name for e in it if e.is_dir() and e.name.isdigit()]
    if only:
        wanted = [Path(a).name or a for a in only]   # accept "7/" from tab completion
        for w in wanted:
            if w not in names:
                log("WARNING: '%s' is not a numbered folder in %s; ignored" % (w, root))
        names = [n for n in names if n in wanted]
    return [root / n for n in sorted(names, key=int)]


def list_inputs(folder):
    """Candidate .inp and .xyz files directly in `folder`, ignoring ORCA-generated ones."""
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


def find_geometry(folder):
    """The folder's .xyz geometry, plus its .inp if there is exactly one.

    After an optimisation the folder holds <name>.inp and ORCA's optimised <name>.xyz
    (next to <name>_trj.xyz, which is ignored); that .xyz is preferred."""
    inps, xyzs = list_inputs(folder)
    inp = inps[0] if len(inps) == 1 else None
    if inp and os.path.splitext(inp)[0] + ".xyz" in xyzs:
        return os.path.splitext(inp)[0] + ".xyz", inp
    if len(xyzs) == 1:
        return xyzs[0], inp
    if not xyzs:
        raise SkipFolder("no .xyz file")
    raise SkipFolder("WARNING: %d .xyz files (%s); cannot tell which geometry to use"
                     % (len(xyzs), ", ".join(xyzs)))


def read_xyz(path):
    """(atoms, comment line) of an .xyz file; atoms are [symbol, x, y, z] strings."""
    lines = read_text(path).splitlines()
    try:
        natoms = int(lines[0].split()[0])
    except (IndexError, ValueError):
        raise InputError("%s: first line is not an atom count" % path.name) from None
    atoms = []
    for line in lines[2:2 + natoms]:    # skip the atom-count and comment lines
        parts = line.split()
        try:
            [float(v) for v in parts[1:4]]
        except ValueError:
            parts = []
        if len(parts) < 4:
            raise InputError("%s: bad atom line %r" % (path.name, line.strip()))
        atoms.append(parts[:4])
    if natoms < 1 or len(atoms) != natoms:
        raise InputError("%s: atom count says %d but %d coordinate lines found"
                         % (path.name, natoms, len(atoms)))
    return atoms, (lines[1] if len(lines) > 1 else "")


def charge_and_mult(folder, inp, xyz_comment, calc):
    """Charge/multiplicity from the folder's .inp, else the .xyz comment line, else defaults."""
    if inp:
        m = COORD_CHARGE_MULT_RE.search(read_text(folder / inp))
        if m:
            return int(m.group(1)), int(m.group(2))
    m_charge, m_mult = CHARGE_RE.search(xyz_comment), MULT_RE.search(xyz_comment)
    charge = int(m_charge.group(1)) if m_charge else DEFAULT_CHARGE
    mult = int(m_mult.group(1)) if m_mult else DEFAULT_MULT
    if not (m_charge and m_mult):
        calc.warnings.append("charge/multiplicity not found in the folder's .inp or .xyz; "
                             "using charge %d mult %d" % (charge, mult))
    return charge, mult


def setup_calc(folder, prefix, header):
    """Create <folder>/<prefix>-<n>/, copy the folder's .xyz into it and write <name>.inp.

    Returns (calc, already_finished). Raises SkipFolder / InputError. Written generically
    so later parts can reuse it with their own prefix and header."""
    xyz, inp = find_geometry(folder)
    name = UNSAFE_NAME_RE.sub("_", os.path.splitext(xyz)[0])   # ORCA dislikes spaces/quotes
    calc = Calc(folder.name, folder / ("%s-%s" % (prefix, folder.name)), name)
    if terminated_normally(calc.file(".out")):
        return calc, True
    if inp and SKIP_IF_OPT_UNFINISHED:
        parent_out = folder / (os.path.splitext(inp)[0] + ".out")
        if parent_out.exists() and not terminated_normally(parent_out):
            raise SkipFolder("WARNING: %s did not terminate normally, so %s may not be optimised "
                             "(set SKIP_IF_OPT_UNFINISHED = False to use it anyway)"
                             % (parent_out.name, xyz))
    atoms, comment = read_xyz(folder / xyz)
    charge, mult = charge_and_mult(folder, inp, comment, calc)
    calc.dir.mkdir(exist_ok=True)
    shutil.copy2(str(folder / xyz), str(calc.dir / xyz))
    coords = "\n".join("  %-2s  %14s  %14s  %14s" % tuple(a) for a in atoms)
    write_atomic(calc.file(".inp"), "%s\n\n* xyz %d %d\n%s\n*\n"
                 % (header.strip("\n"), charge, mult, coords))
    return calc, False


def run_orca(calc):
    """Run ORCA on <name>.inp inside calc.dir (in a worker thread)."""
    log("%s [START] %s  (%s/%s)" % (now(), calc.number, calc.dir.name, calc.name + ".inp"))
    t0 = time.monotonic()
    out = calc.file(".out")
    rc, _ = run_logged([ORCA_CMD, calc.name + ".inp"], calc.dir, out)  # argument list, no shell
    elapsed = time.monotonic() - t0
    if rc == 0 and terminated_normally(out):
        return Result(calc.number, "DONE", " | ".join([out.name] + calc.warnings), elapsed)
    detail = describe_exit(rc)
    if rc == 0:
        detail += ", but no '%s' in %s" % (SUCCESS_MARK, out.name)
    hint = error_hint(out)
    if hint:
        detail += ': "%s"' % hint
    return Result(calc.number, "ERROR", detail, elapsed)


def setup_and_run(ctx, prefix, header, nprocs, maxcore, step):
    """Set up <n>/<prefix>-<n> for every folder and run the ORCA jobs that are not finished.
    Returns (calcs, had_errors); every calc whose folder could be set up is returned."""
    calcs, todo, results = [], [], []
    for folder in ctx.folders:
        try:
            calc, finished = setup_calc(folder, prefix, header)
        except SkipFolder as exc:
            results.append(Result(folder.name, "SKIP", str(exc)))
            log(status_line(results[-1]))
            continue
        except (InputError, OSError) as exc:
            results.append(Result(folder.name, "ERROR", "input: %s" % exc))
            log(status_line(results[-1]))
            continue
        calcs.append(calc)
        if finished:
            results.append(Result(calc.number, "SKIP", "already finished (%s)" % calc.file(".out").name))
            log(status_line(results[-1]))
            continue
        todo.append(calc)
        log("%s [READY] %s: %s/%s" % (now(), calc.number, calc.dir.name, calc.name + ".inp"))
        for warning in calc.warnings:
            log("         WARNING: %s" % warning)

    interrupted = False
    if todo:
        log("")
        check_resources(len(todo), nprocs, maxcore)
        log("")
        tasks = [(c.number, lambda c=c: run_orca(c)) for c in todo]
        run_results, interrupted = run_parallel(tasks, MAX_PARALLEL_JOBS, ctx.stop_signals)
        results += run_results
    had_errors = summarize(ctx.root, step, results, interrupted)
    if interrupted:
        raise Stopped
    return calcs, had_errors


# ============================================================================ #
# PART 1: single point, SP_data, orca_plot, mep.py
# ============================================================================ #
def parse_orbitals(lines):
    """Last ORBITAL ENERGIES table (spin-up set for open shells): [(no, occ, E in eV as text)]."""
    starts = [i for i, line in enumerate(lines) if line.strip() == "ORBITAL ENERGIES"]
    if not starts:
        return []
    orbitals = []
    for line in lines[starts[-1] + 1:starts[-1] + 100000]:
        m = ORBITAL_ROW_RE.match(line)
        if m:
            orbitals.append((int(m.group(1)), float(m.group(2)), m.group(4)))  # E(eV) = last column
        elif orbitals:
            break           # end of the table (blank line or "SPIN DOWN ORBITALS")
    return orbitals


def parse_sp_output(path):
    """Energy, frontier orbitals and dipole moment from an ORCA single-point output.
    Anything not found is None."""
    text = path.read_text(encoding="utf-8", errors="replace")
    data = {"energy": None, "homo": None, "lumo": None, "orbitals": {},
            "dipole": None, "dipole_total": None}

    energies = ENERGY_RE.findall(text)
    if energies:
        data["energy"] = energies[-1]

    orbitals = parse_orbitals(text.splitlines())
    occupied = [i for i, (_, occ, _) in enumerate(orbitals) if occ > 0]   # 2.0000 (closed shell)
    virtual = [i for i, (_, occ, _) in enumerate(orbitals) if occ == 0]   # 0.0000
    if occupied and virtual:
        homo, lumo = occupied[-1], virtual[0]
        data["homo"], data["lumo"] = orbitals[homo][0], orbitals[lumo][0]  # orbital numbers
        for label in SP_ORBITALS:
            m = ORBITAL_LABEL_RE.match(label)
            i = (homo if m.group(1) == "HOMO" else lumo) + int(m.group(2) or 0)
            if 0 <= i < len(orbitals):
                data["orbitals"][label] = orbitals[i][2]

    dipoles = DIPOLE_AU_RE.findall(text)
    if dipoles:
        data["dipole"] = ["%.6f" % (float(v) * AU_TO_DEBYE) for v in dipoles[-1]]
    totals = DIPOLE_DEBYE_RE.findall(text)
    if totals:
        data["dipole_total"] = totals[-1]
    return data


def write_sp_data(ctx, calcs):
    """Write the SP_data table (one row per folder; NA where a value is missing).
    When only some folders were run, the other folders' rows of the old table are kept."""
    header = (["Folder", "Name", "E_SP(Eh)"]
              + ["%s(eV)" % label for label in SP_ORBITALS]
              + ["Dipole_X(Debye)", "Dipole_Y(Debye)", "Dipole_Z(Debye)", "Dipole_Total(Debye)"])
    rows = []
    for calc in calcs:
        d = calc.data or {}
        rows.append([calc.number, calc.name, d.get("energy") or "NA"]
                    + [d.get("orbitals", {}).get(label, "NA") for label in SP_ORBITALS]
                    + (d.get("dipole") or ["NA"] * 3)
                    + [d.get("dipole_total") or "NA"])
    path = ctx.root / SP_DATA_FILE
    if ctx.partial and path.exists():
        done = {f.name for f in ctx.folders}
        old = [line.split(SP_DATA_SEPARATOR) for line in read_text(path).splitlines() if line]
        if old and old[0] == header:
            rows += [r for r in old[1:] if r[0] not in done]
        else:
            log("WARNING: %s has different columns; rows of folders not run now are dropped. "
                "Run without folder arguments to rebuild the full table." % SP_DATA_FILE)
    rows.sort(key=lambda r: int(r[0]) if r[0].isdigit() else -1)
    write_atomic(path, "".join(SP_DATA_SEPARATOR.join(r) + "\n" for r in [header] + rows))
    return len(rows)


def analyse_sp(ctx, calcs):
    """PART 1.2: parse every SP output (after all runs finished) and write SP_data."""
    results = []
    for calc in calcs:
        out = calc.file(".out")
        if not terminated_normally(out):
            results.append(Result(calc.number, "ERROR", "no finished SP in %s" % out.name))
            log(status_line(results[-1]))
            continue
        calc.data = d = parse_sp_output(out)
        missing = [what for what, ok in (("energy", d["energy"]), ("orbital energies", d["homo"] is not None),
                                         ("dipole moment", d["dipole"] and d["dipole_total"])) if not ok]
        summary = "E = %s Eh" % d["energy"]
        if d["homo"] is not None:
            summary += ", HOMO #%d = %s eV, LUMO #%d = %s eV" % (
                d["homo"], d["orbitals"].get("HOMO", "?"), d["lumo"], d["orbitals"].get("LUMO", "?"))
        if d["dipole_total"]:
            summary += ", dipole %s D" % d["dipole_total"]
        if missing:
            results.append(Result(calc.number, "ERROR", "%s not found in %s" % (", ".join(missing), out.name)))
        else:
            results.append(Result(calc.number, "DONE", summary))
        log(status_line(results[-1]))
    n_rows = write_sp_data(ctx, calcs)
    log("%s Wrote %s (%d rows)" % (now(), ctx.root / SP_DATA_FILE, n_rows))
    return summarize(ctx.root, "PART 1.2  SP_data", results)


def plot_one(calc):
    """PART 1.3: HOMO, LUMO and electron-density cubes with orca_plot (in a worker thread)."""
    gbw = calc.file(".gbw")
    if not gbw.exists():
        return Result(calc.number, "ERROR", "%s not found" % gbw.name)
    keys = [k.format(homo=calc.data["homo"], lumo=calc.data["lumo"], grid=PLOT_GRID)
            for k in ORCA_PLOT_KEYS]
    stamp = "keys: %s\ngbw: %s\n" % (" ".join(keys), file_stamp(gbw))
    marker = calc.dir / PLOT_MARKER
    if marker_matches(marker, stamp):
        calc.plot_stamp = stamp
        return Result(calc.number, "SKIP", "already plotted")

    log("%s [START] %s  orca_plot %s (HOMO %d, LUMO %d)"
        % (now(), calc.number, gbw.name, calc.data["homo"], calc.data["lumo"]))
    before = {p.name: p.stat().st_mtime_ns for p in calc.dir.glob(PLOT_OUTPUT_GLOB)}
    t0 = time.monotonic()
    rc, killed = run_logged([ORCA_PLOT_CMD, gbw.name, "-i"], calc.dir, calc.dir / "orca_plot.log",
                            stdin_text="\n".join(keys) + "\n", timeout=ORCA_PLOT_TIMEOUT,
                            max_bytes=POSTPROC_LOG_LIMIT)
    elapsed = time.monotonic() - t0
    new = sorted(p.name for p in calc.dir.glob(PLOT_OUTPUT_GLOB)
                 if before.get(p.name) != p.stat().st_mtime_ns)
    if rc == 0 and not killed and len(new) >= PLOTS_EXPECTED:
        write_atomic(marker, stamp)
        calc.plot_stamp = stamp
        return Result(calc.number, "DONE", ", ".join(new), elapsed)
    detail = killed or describe_exit(rc)
    detail += "; %d of %d plot files written%s - see orca_plot.log" % (
        len(new), PLOTS_EXPECTED, (" (%s)" % ", ".join(new)) if new else "")
    return Result(calc.number, "ERROR", detail, elapsed)


def mep_one(calc, script, digest):
    """PART 1.4: run the mep.py hook inside calc.dir (in a worker thread)."""
    stamp = "mep.py sha256: %s\n%s" % (digest, calc.plot_stamp)
    marker = calc.dir / MEP_MARKER
    if marker_matches(marker, stamp):
        return Result(calc.number, "SKIP", "mep.py already run on these plots")
    args = [a.format(name=calc.name, number=calc.number) for a in MEP_ARGS]
    log("%s [START] %s  %s %s" % (now(), calc.number, script, " ".join(args)))
    t0 = time.monotonic()
    rc, killed = run_logged([sys.executable, script] + args, calc.dir, calc.dir / "mep.log",
                            timeout=MEP_TIMEOUT, max_bytes=POSTPROC_LOG_LIMIT)
    elapsed = time.monotonic() - t0
    if rc == 0 and not killed:
        write_atomic(marker, stamp)
        return Result(calc.number, "DONE", "see mep.log", elapsed)
    return Result(calc.number, "ERROR", "%s - see mep.log" % (killed or describe_exit(rc)), elapsed)


def run_part_1(ctx):
    """PART 1: SP runs -> SP_data -> orca_plot -> mep.py. Returns True on any ERROR."""
    header = SP_HEADER_TEMPLATE.format(method=SP_METHOD, basis=SP_BASIS,
                                       nprocs=SP_NPROCS, maxcore=SP_MAXCORE)
    # 1.1  <n>/SP-<n>: copy the geometry, write the input, run every unfinished SP
    calcs, errors = setup_and_run(ctx, "SP", header, SP_NPROCS, SP_MAXCORE, "PART 1.1  single points")
    if not calcs:
        return errors
    # 1.2  only now that every SP has finished: parse the outputs, write SP_data
    errors |= analyse_sp(ctx, calcs)

    # 1.3  orca_plot in every SP-<n> folder with orbital data
    plottable = [c for c in calcs if c.data and c.data["homo"] is not None]
    if PART1_PLOTS and plottable:
        tasks = [(c.number, lambda c=c: plot_one(c)) for c in plottable]
        results, interrupted = run_parallel(tasks, MAX_PARALLEL_POSTPROC, ctx.stop_signals)
        errors |= summarize(ctx.root, "PART 1.3  orca_plot", results, interrupted)
        if interrupted:
            raise Stopped

    # 1.4  mep.py hook, after all plots are done
    if PART1_MEP:
        script = ctx.root / MEP_SCRIPT
        if not PART1_PLOTS:     # plots made by an earlier run still count
            for c in plottable:
                if (c.dir / PLOT_MARKER).exists():
                    c.plot_stamp = read_text(c.dir / PLOT_MARKER)
        ready = [c for c in plottable if c.plot_stamp]
        if not script.is_file():
            log("%s NOTE: %s not found in %s; mep.py step skipped" % (now(), MEP_SCRIPT, ctx.root))
        elif ready:
            digest = hashlib.sha256(script.read_bytes()).hexdigest()
            for c in ready:     # copy into every folder first, then run
                shutil.copy2(str(script), str(c.dir / script.name))
            tasks = [(c.number, lambda c=c: mep_one(c, script.name, digest)) for c in ready]
            results, interrupted = run_parallel(tasks, MAX_PARALLEL_POSTPROC, ctx.stop_signals)
            errors |= summarize(ctx.root, "PART 1.4  mep.py", results, interrupted)
            if interrupted:
                raise Stopped
    return errors


# ============================================================================ #
# PARTS 2-4: placeholders
# ============================================================================ #
# Each future part can follow PART 1's pattern:
#     calcs, errors = setup_and_run(ctx, "<PREFIX>", <header>, <nprocs>, <maxcore>, "PART n.1  <title>")
# then parse the outputs and write a table, as analyse_sp() does.

def run_part_2(ctx):
    """PART 2: TDDFT run and analysis (not implemented yet)."""
    log("%s PART 2 (TDDFT) is not implemented yet; nothing done." % now())
    return False


def run_part_3(ctx):
    """PART 3: deltaSCF run and analysis (not implemented yet)."""
    log("%s PART 3 (deltaSCF) is not implemented yet; nothing done." % now())
    return False


def run_part_4(ctx):
    """PART 4: SP cation/anion run and analysis (not implemented yet)."""
    log("%s PART 4 (SP cation/anion) is not implemented yet; nothing done." % now())
    return False


PARTS = [
    ("RUN_PART_1", "PART 1: single point, SP_data, orca_plot, mep.py", run_part_1),
    ("RUN_PART_2", "PART 2: TDDFT", run_part_2),
    ("RUN_PART_3", "PART 3: deltaSCF", run_part_3),
    ("RUN_PART_4", "PART 4: SP cation/anion", run_part_4),
]


# ============================================================================ #
# Main
# ============================================================================ #
def check_settings():
    """Problems in the settings block that would only show up halfway through a run."""
    problems = []
    for label in SP_ORBITALS:
        if not ORBITAL_LABEL_RE.match(label):
            problems.append("SP_ORBITALS: %r is not like HOMO, HOMO-1, LUMO or LUMO+2" % label)
    for name, items, fields in (("ORCA_PLOT_KEYS", ORCA_PLOT_KEYS, dict(homo=1, lumo=2, grid=3)),
                                ("MEP_ARGS", MEP_ARGS, dict(name="x", number="1"))):
        for item in items:
            try:
                item.format(**fields)
            except (KeyError, IndexError, ValueError):
                problems.append("%s: %r uses an unknown {placeholder}" % (name, item))
    if RUN_PART_1:
        if not is_executable(ORCA_CMD):
            problems.append("ORCA executable not found or not executable: %s" % ORCA_CMD)
        if PART1_PLOTS and not is_executable(ORCA_PLOT_CMD):
            problems.append("orca_plot not found or not executable: %s" % ORCA_PLOT_CMD)
    return problems


def raise_interrupt(signum, frame):
    raise KeyboardInterrupt


def main():
    parser = argparse.ArgumentParser(
        description="ORCA multi-part pipeline over the numbered subfolders of the current directory.")
    parser.add_argument("folders", nargs="*", help="only these numbered folders (default: all)")
    args = parser.parse_args()

    # SIGTERM (kill PID) and a closed terminal (SIGHUP) clean up like Ctrl+C.
    # Under nohup SIGHUP stays ignored so the pipeline keeps running.
    stop_signals = [signal.SIGINT, signal.SIGTERM]
    signal.signal(signal.SIGTERM, raise_interrupt)
    if signal.getsignal(signal.SIGHUP) is not signal.SIG_IGN:
        signal.signal(signal.SIGHUP, raise_interrupt)
        stop_signals.append(signal.SIGHUP)

    root = Path.cwd()
    problems = check_settings()
    if problems:
        for p in problems:
            log("ERROR: %s" % p)
        return 2
    folders = numbered_folders(root, args.folders)
    if not folders:
        log("No numbered folders found in %s" % root)
        return 1

    ctx = Context(root, folders, bool(args.folders), stop_signals)
    enabled = [(title, func) for flag, title, func in PARTS if globals()[flag]]
    log("ORCA pipeline in %s: %d numbered folder(s): %s" % (
        root, len(folders), " ".join(f.name for f in folders)))
    log("Parts enabled: %s" % (", ".join(t.split(":")[0] for t, _ in enabled) or "none"))
    errors = False
    try:
        for title, func in enabled:
            log("\n" + "#" * 78 + "\n#  " + title + "\n" + "#" * 78)
            errors |= func(ctx)
    except (KeyboardInterrupt, Stopped):
        log("\nPipeline stopped. Rerun the script to continue where it left off.")
        return 130
    log("\nPipeline finished%s. Summaries are in %s"
        % (" with errors" if errors else "", root / LOG_FILE))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
