"""YAML storage for libraries, columns, profiles, scripts, recipes and step templates.

Shipped starter files live in orca_studio/defaults/. On first start they are copied into the
studio folder; afterwards the user's copies are the source of truth. New built-in entries from a
newer app version are merged in (by id) without touching the user's edits.
"""
from __future__ import annotations

import copy
import io
import re
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Any

import yaml

from . import config

_lock = threading.RLock()

KINDS = ["columns", "calc_profiles", "extraction_profiles", "scripts", "multiwfn_recipes", "step_templates"]


# --------------------------------------------------------------------------- YAML helpers
class _Dumper(yaml.SafeDumper):
    pass


def _str_rep(dumper, s):
    if "\n" in s:
        return dumper.represent_scalar("tag:yaml.org,2002:str", s, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", s)


_Dumper.add_representer(str, _str_rep)


def dump_yaml(data: Any) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True)


def read_yaml(path: Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def write_yaml(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(dump_yaml(data), encoding="utf-8")
    tmp.replace(path)


def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "_", str(text)).strip("_").lower()
    return s or "item"


def safe_id(text: str) -> str:
    s = slugify(text)
    if not re.match(r"^[a-z0-9_]+$", s):
        raise ValueError("bad id")
    return s


# --------------------------------------------------------------------------- folders
def root() -> Path:
    return config.studio_dir()


def lib_dir() -> Path:
    return root() / "libraries"


def kind_dir(kind: str) -> Path:
    if kind not in KINDS:
        raise ValueError(f"unknown kind {kind}")
    return root() / kind


# --------------------------------------------------------------------------- entries
ENTRY_DEFAULTS = {
    "label": "",
    "orca_text": "",
    "destination": "keyword_line",
    "applies_to": ["all"],
    "tags": [],
    "notes": "",
    "hidden": False,
    "favorite": False,
}


def normalize_entry(e: dict, idx: int = 0) -> dict:
    out = copy.deepcopy(e)
    for k, v in ENTRY_DEFAULTS.items():
        out.setdefault(k, copy.deepcopy(v))
    out["id"] = str(out.get("id") or slugify(out.get("label") or f"entry{idx}"))
    if not out["label"]:
        out["label"] = out["id"]
    out.setdefault("order", (idx + 1) * 10)
    out["orca_text"] = "" if out["orca_text"] is None else str(out["orca_text"])
    return out


def normalize_library(lib: dict) -> dict:
    lib = copy.deepcopy(lib)
    lib.setdefault("label", lib.get("id", ""))
    lib["entries"] = [normalize_entry(e, i) for i, e in enumerate(lib.get("entries") or [])]
    return lib


# --------------------------------------------------------------------------- seeding
def seed() -> None:
    """Create the studio folder and copy/merge shipped defaults."""
    with _lock:
        r = root()
        r.mkdir(parents=True, exist_ok=True)
        # libraries: merge entries by id
        lib_dir().mkdir(parents=True, exist_ok=True)
        for src in sorted((config.DEFAULTS_DIR / "libraries").glob("*.yaml")):
            shipped = read_yaml(src) or {}
            for e in shipped.get("entries") or []:
                e["builtin"] = True
            dst = lib_dir() / src.name
            if not dst.exists():
                write_yaml(dst, shipped)
                continue
            user = read_yaml(dst) or {}
            ids = {e.get("id") for e in user.get("entries") or []}
            added = [e for e in shipped.get("entries") or [] if e.get("id") not in ids]
            changed = bool(added)
            # new keys of existing built-in entries (e.g. default_extraction) are filled in, never overwritten
            ship_by = {e.get("id"): e for e in shipped.get("entries") or []}
            for e in user.get("entries") or []:
                se = ship_by.get(e.get("id"))
                if se and e.get("builtin"):
                    for k, v in se.items():
                        if k not in e:
                            e[k] = v
                            changed = True
            if changed:
                user.setdefault("entries", []).extend(added)
                write_yaml(dst, user)
        # other kinds: copy missing files
        for kind in KINDS:
            d = root() / kind
            d.mkdir(parents=True, exist_ok=True)
            srcdir = config.DEFAULTS_DIR / kind
            if not srcdir.exists():
                continue
            gone = deleted_defaults()
            for src in sorted(srcdir.glob("*.yaml")):
                dst = d / src.name
                if f"{kind}/{src.name}" in gone:
                    continue
                data = read_yaml(src) or {}
                data["builtin"] = True
                if not dst.exists():
                    write_yaml(dst, data)
                    continue
                # a newer starter replaces the user's copy only if that copy was never edited
                user = read_yaml(dst) or {}
                if user.get("builtin") and not user.get("saved_at") and not user.get("edited") \
                        and int(user.get("version") or 1) < int(data.get("version") or 1):
                    bak = root() / ".trash" / "upgraded" / kind
                    bak.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(dst, bak / dst.name)
                    if kind == "calc_profiles":
                        keep = dict(user)
                        keep.pop("id", None)
                        write_yaml(d / "versions" / src.stem / f"v{int(user.get('version') or 1)}.yaml", keep)
                    write_yaml(dst, data)
        if not config.settings_path().exists():
            config.save_settings(config.load_settings())


# --------------------------------------------------------------------------- libraries
_lib_cache: dict[str, tuple[float, dict]] = {}


def list_library_ids() -> list[str]:
    return sorted(p.stem for p in lib_dir().glob("*.yaml"))


def get_library(list_id: str) -> dict | None:
    p = lib_dir() / f"{list_id}.yaml"
    if not p.exists():
        return None
    mtime = p.stat().st_mtime
    hit = _lib_cache.get(list_id)
    if hit and hit[0] == mtime:
        return copy.deepcopy(hit[1])
    lib = normalize_library(read_yaml(p) or {"id": list_id})
    lib["id"] = list_id
    _lib_cache[list_id] = (mtime, lib)
    return copy.deepcopy(lib)


def all_libraries() -> dict[str, dict]:
    return {i: get_library(i) for i in list_library_ids()}


def save_library(lib: dict) -> dict:
    with _lock:
        list_id = safe_id(lib["id"])
        old = get_library(list_id)
        entries = [normalize_entry(e, i) for i, e in enumerate(lib.get("entries") or [])]
        if old:
            # built-in entries can be hidden but not deleted
            new_ids = {e["id"] for e in entries}
            for e in old["entries"]:
                if e.get("builtin") and e["id"] not in new_ids:
                    e["hidden"] = True
                    entries.append(e)
            builtin_ids = {e["id"] for e in old["entries"] if e.get("builtin")}
            for e in entries:
                if e["id"] in builtin_ids:
                    e["builtin"] = True
        seen = set()
        for e in entries:
            if e["id"] in seen:
                raise ValueError(f"duplicate entry id '{e['id']}' in {list_id}")
            seen.add(e["id"])
        out = {"id": list_id, "label": lib.get("label") or list_id, "entries": entries}
        write_yaml(lib_dir() / f"{list_id}.yaml", out)
        _lib_cache.pop(list_id, None)
        return get_library(list_id)


def add_entry(list_id: str, entry: dict) -> dict:
    lib = get_library(list_id) or {"id": list_id, "label": list_id, "entries": []}
    e = normalize_entry(entry, len(lib["entries"]))
    base = e["id"]
    ids = {x["id"] for x in lib["entries"]}
    n = 2
    while e["id"] in ids:
        e["id"] = f"{base}_{n}"
        n += 1
    e["builtin"] = False
    lib["entries"].append(e)
    save_library(lib)
    return e


def get_entry(list_id: str, entry_id: str) -> dict | None:
    lib = get_library(list_id)
    if not lib:
        return None
    for e in lib["entries"]:
        if e["id"] == entry_id:
            return e
    return None


def text(list_id: str, entry_id: str, default: str = "") -> str:
    """orca_text of a library entry (used for templates and patterns)."""
    e = get_entry(list_id, entry_id)
    return e["orca_text"] if e else default


# --------------------------------------------------------------------------- generic items
def list_items(kind: str) -> list[dict]:
    out = []
    for p in sorted(kind_dir(kind).glob("*.yaml")):
        try:
            d = read_yaml(p) or {}
        except yaml.YAMLError:
            continue
        d["id"] = p.stem
        out.append(d)
    return out


def get_item(kind: str, item_id: str) -> dict | None:
    p = kind_dir(kind) / f"{safe_id(item_id)}.yaml"
    if not p.exists():
        return None
    d = read_yaml(p) or {}
    d["id"] = p.stem
    return d


def save_item(kind: str, data: dict) -> dict:
    with _lock:
        data = copy.deepcopy(data)
        item_id = safe_id(data.get("id") or data.get("name") or data.get("label") or "item")
        data["id"] = item_id
        write_yaml(kind_dir(kind) / f"{item_id}.yaml", data)
        return data


def unique_id(kind: str, base: str) -> str:
    base = slugify(base)
    i, cand = 2, base
    while (kind_dir(kind) / f"{cand}.yaml").exists():
        cand = f"{base}_{i}"
        i += 1
    return cand


def deleted_defaults() -> set[str]:
    p = root() / ".deleted_defaults.yaml"
    return set(read_yaml(p) or []) if p.exists() else set()


def delete_item(kind: str, item_id: str, allow_builtin: bool = False) -> None:
    """Move an item to .trash. A deleted starter item is remembered so seed() does not bring it back."""
    with _lock:
        p = kind_dir(kind) / f"{safe_id(item_id)}.yaml"
        d = read_yaml(p) if p.exists() else None
        if d and d.get("builtin"):
            if not allow_builtin:
                raise ValueError("Built-in items can be hidden but not deleted")
            gone = deleted_defaults() | {f"{kind}/{p.name}"}
            write_yaml(root() / ".deleted_defaults.yaml", sorted(gone))
        trash = root() / ".trash" / kind
        trash.mkdir(parents=True, exist_ok=True)
        if p.exists():
            shutil.move(str(p), str(trash / p.name))


# --------------------------------------------------------------------------- columns
def columns() -> dict[str, dict]:
    out = {}
    for c in list_items("columns"):
        c.setdefault("label", c["id"])
        c.setdefault("type", "text")
        c.setdefault("applies_to", ["all"])
        c.setdefault("default", "")
        c.setdefault("slot", "extras")
        out[c["id"]] = c
    return out


# --------------------------------------------------------------------------- profile versioning
def _profile_body(p: dict) -> dict:
    return {k: v for k, v in p.items() if k not in ("version", "saved_at", "id", "builtin")}


def save_calc_profile(profile: dict, mode: str = "new_version") -> dict:
    """Save a calculation profile.

    mode "new_version": a changed profile becomes the next version (section 6.5).
    mode "overwrite": the changes replace the current version in place. Batches are not affected:
    each batch keeps its own copy of the profile it ran with.
    """
    from datetime import datetime

    with _lock:
        profile = copy.deepcopy(profile)
        pid = safe_id(profile.get("id") or profile.get("name") or "profile")
        profile["id"] = pid
        old = get_item("calc_profiles", pid)
        version = 1
        if old:
            version = int(old.get("version") or 1)
            if dump_yaml(_profile_body(old)) == dump_yaml(_profile_body(profile)):
                return old
            if mode != "overwrite":
                version += 1
                vdir = kind_dir("calc_profiles") / "versions" / pid
                oldv = vdir / f"v{int(old.get('version') or 1)}.yaml"
                if not oldv.exists():
                    keep = dict(old)
                    keep.pop("id", None)
                    write_yaml(oldv, keep)
        profile["version"] = version
        profile["saved_at"] = datetime.now().isoformat(timespec="seconds")
        if old and old.get("builtin"):
            profile["builtin"] = True
        write_yaml(kind_dir("calc_profiles") / f"{pid}.yaml", profile)
        write_yaml(kind_dir("calc_profiles") / "versions" / pid / f"v{version}.yaml", profile)
        return profile


def calc_profile_version(pid: str, version: int | None = None) -> dict | None:
    cur = get_item("calc_profiles", pid)
    if version is None or (cur and int(cur.get("version") or 1) == int(version)):
        return cur
    p = kind_dir("calc_profiles") / "versions" / safe_id(pid) / f"v{int(version)}.yaml"
    return read_yaml(p) if p.exists() else None


def calc_profile_versions(pid: str) -> list[int]:
    d = kind_dir("calc_profiles") / "versions" / safe_id(pid)
    vs = sorted(int(p.stem[1:]) for p in d.glob("v*.yaml")) if d.exists() else []
    cur = get_item("calc_profiles", pid)
    if cur and int(cur.get("version") or 1) not in vs:
        vs.append(int(cur.get("version") or 1))
    return sorted(vs)


# --------------------------------------------------------------------------- backup
def export_zip() -> bytes:
    buf = io.BytesIO()
    r = root()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in r.rglob("*.yaml"):
            rel = p.relative_to(r)
            if rel.parts[0] in (".trash",):
                continue
            z.write(p, str(rel))
    return buf.getvalue()


def import_zip(data: bytes) -> list[str]:
    """Import a backup zip; existing files are moved to .trash/import-<time> first."""
    from datetime import datetime

    r = root()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    written = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if not name.endswith(".yaml") or name.startswith("/") or ".." in Path(name).parts:
                continue
            dst = r / name
            if dst.exists():
                bak = r / ".trash" / f"import-{stamp}" / name
                bak.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(dst, bak)
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(z.read(name))
            written.append(name)
    _lib_cache.clear()
    config._cache.clear()
    return written
