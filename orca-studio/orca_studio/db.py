"""SQLite storage for batches, molecules, tasks, runs, logs and results."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

from . import config

_local = threading.local()
_write_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'calc',          -- calc | external
  folder TEXT NOT NULL,
  calc_profile_id TEXT, calc_profile_version INTEGER,
  profile_json TEXT,                          -- exact profile snapshot the batch runs with
  extraction_profile_id TEXT,
  status TEXT NOT NULL DEFAULT 'draft',       -- draft running paused review stopped done cancelled
  released_steps TEXT NOT NULL DEFAULT '[]',  -- steps released after 'pause for review'
  fragments TEXT NOT NULL DEFAULT '{}',       -- named fragments: {name: [atom indices]}
  options TEXT NOT NULL DEFAULT '{}',
  created REAL, updated REAL
);
CREATE TABLE IF NOT EXISTS molecules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL,
  name TEXT NOT NULL, dirname TEXT NOT NULL,
  formula TEXT, charge INTEGER, mult INTEGER, natoms INTEGER, nelectrons INTEGER,
  coord_type TEXT DEFAULT 'xyz', raw_block TEXT DEFAULT '',
  source_file TEXT, warnings TEXT DEFAULT '[]', order_idx INTEGER DEFAULT 0,
  removed INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tasks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER NOT NULL, molecule_id INTEGER NOT NULL, step_index INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',     -- pending queued running done failed skipped cancelled
  step_dir TEXT, attempts INTEGER DEFAULT 0, message TEXT DEFAULT '',
  checks TEXT DEFAULT '{}', fired TEXT DEFAULT '[]', updated REAL,
  UNIQUE(molecule_id, step_index)
);
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id INTEGER NOT NULL, batch_id INTEGER, attempt INTEGER, subjob TEXT DEFAULT '',
  status TEXT NOT NULL,                       -- running done failed killed lost
  pid INTEGER, pid_start TEXT, nprocs INTEGER, mem_mb INTEGER,
  start REAL, end REAL, exit_code INTEGER, note TEXT DEFAULT '', out_file TEXT
);
CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id INTEGER, ts REAL, level TEXT, text TEXT
);
CREATE TABLE IF NOT EXISTS results (
  batch_id INTEGER, molecule_id INTEGER, field_id TEXT, value TEXT, flags TEXT DEFAULT '[]', updated REAL,
  PRIMARY KEY (batch_id, molecule_id, field_id)
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, level TEXT, text TEXT, batch_id INTEGER, seen INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE INDEX IF NOT EXISTS ix_tasks_batch ON tasks(batch_id);
CREATE INDEX IF NOT EXISTS ix_runs_task ON runs(task_id);
CREATE INDEX IF NOT EXISTS ix_logs_batch ON logs(batch_id);
"""


def connect() -> sqlite3.Connection:
    path = str(config.db_path())
    con = getattr(_local, "con", None)
    if con is not None and getattr(_local, "path", None) == path:
        return con
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=30000")
    _local.con, _local.path = con, path
    return con


def init() -> None:
    con = connect()
    with _write_lock:
        con.executescript(SCHEMA)
        con.commit()


def reset_connection() -> None:
    con = getattr(_local, "con", None)
    if con is not None:
        con.close()
    _local.con = None


@contextmanager
def tx():
    con = connect()
    with _write_lock:
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback()
            raise


def q(sql: str, args=()) -> list[dict]:
    return [dict(r) for r in connect().execute(sql, args).fetchall()]


def q1(sql: str, args=()) -> dict | None:
    r = connect().execute(sql, args).fetchone()
    return dict(r) if r else None


def ex(sql: str, args=()) -> int:
    with tx() as con:
        cur = con.execute(sql, args)
        return cur.lastrowid


def j(v) -> str:
    return json.dumps(v)


def uj(s, default=None):
    if s is None or s == "":
        return default
    try:
        return json.loads(s)
    except (TypeError, ValueError):
        return default


def log(batch_id: int | None, text: str, level: str = "info") -> None:
    ex("INSERT INTO logs(batch_id, ts, level, text) VALUES (?,?,?,?)", (batch_id, time.time(), level, text))
    if batch_id:
        b = q1("SELECT folder FROM batches WHERE id=?", (batch_id,))
        if b:
            try:
                with open(Path(b["folder"]) / "batch_log.txt", "a") as fh:
                    fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {level.upper():7s} {text}\n")
            except OSError:
                pass


def notify(text: str, level: str = "info", batch_id: int | None = None) -> None:
    ex("INSERT INTO notifications(ts, level, text, batch_id) VALUES (?,?,?,?)", (time.time(), level, text, batch_id))


def kv_get(k: str, default=None):
    r = q1("SELECT v FROM kv WHERE k=?", (k,))
    return uj(r["v"], default) if r else default


def kv_set(k: str, v) -> None:
    ex("INSERT INTO kv(k, v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, j(v)))
