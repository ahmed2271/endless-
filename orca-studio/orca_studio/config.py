"""Settings: where the studio folder is, and the settings.yaml inside it.

The "profiles and libraries" folder (studio folder) holds settings.yaml, all YAML
libraries/profiles and the SQLite database. Its location is itself a setting, so it is
stored in a tiny bootstrap file: ~/.config/orca-studio/location.yaml
(or overridden with the ORCA_STUDIO_HOME environment variable).
"""
from __future__ import annotations

import copy
import os
import threading
from pathlib import Path
from typing import Any

import yaml

HOME = Path.home()
BOOTSTRAP = Path(os.environ.get("XDG_CONFIG_HOME", HOME / ".config")) / "orca-studio" / "location.yaml"
DEFAULT_STUDIO_DIR = HOME / "dft_projects" / ".studio"
PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULTS_DIR = PACKAGE_DIR / "defaults"
STATIC_DIR = PACKAGE_DIR / "static"

_lock = threading.RLock()
_cache: dict[str, Any] = {}


def detect_cores() -> int:
    return os.cpu_count() or 1


def detect_memory_mb() -> int:
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        pass
    return 4096


def default_settings() -> dict:
    cores = detect_cores()
    mem = detect_memory_mb()
    return {
        "programs": {
            "orca": "/home/utopia/orca_6_0_1/orca",
            "openmpi_bin": "",
            "openmpi_lib": "",
            "python": "/usr/bin/python3",
            "xtb": "",
            "multiwfn": "",
            "multiwfn_threads": 4,
            "nbo": "",
            "orca_2mkl": "",
            "orca_plot": "",
            "orca_vpot": "",
            "orca_chelpg": "",
            "orca_pltvib": "",
        },
        # Scripts are referenced by name; only this path changes when a script moves.
        "script_paths": {"mep": ""},
        "folders": {
            "calculations_root": str(HOME / "dft_projects"),
            "layout": "{batch}/{molecule}/{step_no:02d}_{step_slug}",
            "scratch": "",
            "exports_mode": "batch",          # batch -> {batch}/results ; central -> exports_central
            "exports_central": "",
            "export_pattern": "{batch}_{profile}_{date}.csv",
            "csv_separator": ",",
            "decimals": 6,
        },
        "resources": {
            "total_cores": max(1, cores - 2),
            "total_memory_mb": int(mem * 0.8),
            "nice": 10,
            "default_nprocs": 2,
            "default_maxcore": 1000,
        },
        "access": {"mode": "local", "port": 8080, "password_hash": ""},
        "notifications": {"browser": True, "command": ""},
        "defaults": {"charge": 0, "mult": 1},
    }


def studio_dir() -> Path:
    env = os.environ.get("ORCA_STUDIO_HOME")
    if env:
        return Path(env).expanduser()
    if BOOTSTRAP.exists():
        try:
            data = yaml.safe_load(BOOTSTRAP.read_text()) or {}
            if data.get("studio_dir"):
                return Path(data["studio_dir"]).expanduser()
        except (OSError, yaml.YAMLError):
            pass
    return DEFAULT_STUDIO_DIR


def set_studio_dir(path: str) -> None:
    BOOTSTRAP.parent.mkdir(parents=True, exist_ok=True)
    BOOTSTRAP.write_text(yaml.safe_dump({"studio_dir": str(Path(path).expanduser())}))
    _cache.clear()


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def settings_path() -> Path:
    return studio_dir() / "settings.yaml"


def load_settings() -> dict:
    with _lock:
        p = settings_path()
        mtime = p.stat().st_mtime if p.exists() else None
        if _cache.get("path") == str(p) and _cache.get("mtime") == mtime and "data" in _cache:
            return copy.deepcopy(_cache["data"])
        data = default_settings()
        if p.exists():
            try:
                data = _deep_merge(data, yaml.safe_load(p.read_text()) or {})
            except yaml.YAMLError:
                pass
        _cache.update(path=str(p), mtime=mtime, data=data)
        return copy.deepcopy(data)


def save_settings(data: dict) -> dict:
    with _lock:
        merged = _deep_merge(default_settings(), data)
        p = settings_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".yaml.tmp")
        tmp.write_text(yaml.safe_dump(merged, sort_keys=False, allow_unicode=True))
        tmp.replace(p)
        _cache.clear()
        return merged


def orca_dir(settings: dict | None = None) -> Path:
    s = settings or load_settings()
    return Path(s["programs"]["orca"]).expanduser().parent


def utility_path(name: str, settings: dict | None = None) -> str:
    """Path of an ORCA utility (orca_plot, orca_2mkl, ...): explicit setting or ORCA folder."""
    s = settings or load_settings()
    explicit = s["programs"].get(name) or ""
    if explicit:
        return explicit
    return str(orca_dir(s) / name)


def mpi_lib(settings: dict | None = None) -> str:
    s = settings or load_settings()
    p = s["programs"]
    if p.get("openmpi_lib"):
        return p["openmpi_lib"]
    if p.get("openmpi_bin"):
        return str(Path(p["openmpi_bin"]).expanduser().parent / "lib")
    return ""


def db_path() -> Path:
    return studio_dir() / "studio.db"
