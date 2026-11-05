"""Multiwfn recipes (section 12.2): run recorded menu answers, parse results, record mode, re-test.

A recipe is a YAML file in multiwfn_recipes/: the answers fed to Multiwfn's menus, parser rules
that turn output lines into extraction values, citations, and a stored sample for re-testing.
"""
from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from . import batches, config, db, store, tools
from .parsers.orca_out import OrcaOut

NUM = r"[-+]?\d+\.\d+(?:[EeDd][-+]?\d+)?|[-+]?\d+"
MULTIWFN_CITATION = "T. Lu, F. Chen, Multiwfn: A multifunctional wavefunction analyzer, J. Comput. Chem. 33, 580-592 (2012). DOI 10.1002/jcc.22885"


def exe(s=None) -> str:
    s = s or config.load_settings()
    return os.path.expanduser(s["programs"].get("multiwfn") or "")


def samples_dir() -> Path:
    d = config.studio_dir() / "multiwfn_samples"
    d.mkdir(parents=True, exist_ok=True)
    return d


def env_for(s=None) -> dict:
    s = s or config.load_settings()
    env = tools.build_env(s)
    e = exe(s)
    if e:
        env["Multiwfnpath"] = str(Path(e).parent)
        env.setdefault("OMP_STACKSIZE", "200M")
    return env


def prepare_settings_ini(workdir: Path, s=None) -> str:
    """Multiwfn reads ./settings.ini before $Multiwfnpath/settings.ini [VERIFY, Appendix D check 8].

    Copy the installation's settings.ini into the working folder with nthreads from Settings."""
    s = s or config.load_settings()
    src = None
    for cand in (Path(exe(s)).parent / "settings.ini", Path(os.environ.get("Multiwfnpath", "/nonexistent")) / "settings.ini"):
        if cand.exists():
            src = cand
            break
    n = int(s["programs"].get("multiwfn_threads") or 4)
    if not src:
        return "no settings.ini found next to Multiwfn: it uses its built-in defaults"
    text = src.read_text(errors="replace")
    text, k = re.subn(r"(?m)^(\s*nthreads\s*=\s*)\d+", rf"\g<1>{n}", text)
    (workdir / "settings.ini").write_text(text)
    return f"settings.ini copied with nthreads={n}" + ("" if k else " (no nthreads line found)")


def fill(line: str, vals: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(vals.get(m.group(1), m.group(0))), line)


def run_recipe(recipe: dict, workdir: Path, molden: str, timeout: float = 3600) -> Path:
    """Multiwfn {molden} < {recipe}_answers.txt > {basename}_{recipe}.txt in workdir."""
    s = config.load_settings()
    e = exe(s)
    if not tools.is_exec(e):
        raise RuntimeError("Multiwfn is not set in Settings")
    base = Path(molden).stem
    vals = {"molden": molden, "basename": base, "nthreads": s["programs"].get("multiwfn_threads", 4)}
    answers = "\n".join(fill(str(a), vals) for a in recipe.get("answers") or []) + "\n"
    afile = workdir / f"{recipe['id']}_answers.txt"
    afile.write_text(answers)
    prepare_settings_ini(workdir, s)
    out = workdir / f"{base}_{recipe['id']}.txt"
    with open(afile) as fin, open(out, "w") as fout:
        try:
            subprocess.run([e, molden], cwd=workdir, stdin=fin, stdout=fout, stderr=subprocess.STDOUT, env=env_for(s),
                           timeout=timeout)
        except subprocess.TimeoutExpired:
            fout.write("\n[ORCA Studio] Multiwfn timed out\n")
    return out


def parse_rule(rule: dict, text: str):
    """Apply a parser rule to Multiwfn output text."""
    o = OrcaOut(text)
    if not rule.get("table"):
        v, _ = o.custom_pattern(rule.get("anchor", ""), bool(rule.get("regex")), rule.get("occurrence", "last"),
                                int(rule.get("column", 1) or 1), bool(rule.get("next_line")))
        return v
    lines = o.lines
    rx = re.compile(rule["anchor"] if rule.get("regex") else re.escape(rule.get("anchor", "")))
    hits = [i for i, ln in enumerate(lines) if rx.search(ln)]
    if not hits:
        return None
    start = hits[-1] if rule.get("occurrence", "last") == "last" else hits[0]
    cols = rule.get("columns") or ["value"]
    label_rx = re.compile(rule["label_regex"]) if rule.get("label_regex") else None
    rows, started, skipped = [], False, 0
    for ln in lines[start + 1:]:
        nums = re.findall(NUM, ln)
        if len(nums) >= len(cols):
            started = True
            pick = nums[-len(cols):] if rule.get("take") == "last" else nums[:len(cols)]
            row = {c: float(x.replace("D", "E").replace("d", "e")) for c, x in zip(cols, pick)}
            if label_rx:
                m = label_rx.search(ln)
                row["label"] = m.group(1) if m and m.groups() else (m.group(0) if m else "")
            rows.append(row)
        else:
            if started:
                break
            skipped += 1
            if skipped > int(rule.get("skip_lines", 3)):
                break
    return rows or None


def field_value(b: dict, m: dict, k: int, f: dict, out_path: Path):
    spec = f.get("multiwfn") or {}
    recipe = store.get_item("multiwfn_recipes", spec.get("recipe", ""))
    if not recipe:
        return None, f"Multiwfn recipe '{spec.get('recipe')}' not found"
    rule = next((r for r in recipe.get("rules") or [] if r.get("id") == spec.get("rule")), None)
    if not rule:
        return None, f"rule '{spec.get('rule')}' not in recipe"
    sd = Path(out_path).parent
    base = Path(out_path).stem
    result = sd / f"{base}_{recipe['id']}.txt"
    if not result.exists() or result.stat().st_size == 0:
        if recipe.get("closed_shell_only") and (m.get("mult") or 1) > 1:
            return None, "this recipe supports closed-shell molecules only"
        from .scripts_reg import ensure_molden
        try:
            molden = ensure_molden(sd, base)
            result = run_recipe(recipe, sd, molden)
        except RuntimeError as e:
            return None, str(e)
    return parse_rule(rule, result.read_text(errors="replace")), None


# --------------------------------------------------------------------------- version / threads
def version_of(text: str) -> str | None:
    m = re.search(r"Version\s+([\w.()\-]+)", text)
    return m.group(1) if m else None


def probe_threads(s=None) -> dict:
    s = s or config.load_settings()
    e = exe(s)
    if not tools.is_exec(e):
        return {"ok": False, "message": "Multiwfn not found"}
    with tempfile.TemporaryDirectory() as td:
        note = prepare_settings_ini(Path(td), s)
        try:
            r = subprocess.run([e], cwd=td, input="nonexistent_file.molden\nq\n", capture_output=True, text=True,
                               timeout=30, env=env_for(s))
            text = r.stdout + r.stderr
        except (subprocess.TimeoutExpired, OSError) as ex:
            return {"ok": False, "message": f"Multiwfn did not answer: {ex}"}
    m = re.search(r"(\d+)\s+threads", text, re.I) or re.search(r"threads[^\d]{0,20}(\d+)", text, re.I)
    want = int(s["programs"].get("multiwfn_threads") or 4)
    v = version_of(text)
    if m:
        return {"ok": int(m.group(1)) == want, "message": f"{note}; Multiwfn {v or '?'} reports {m.group(1)} threads (wanted {want})"}
    return {"ok": True, "message": f"{note}; Multiwfn {v or '?'} started (it did not print a thread count)"}


# --------------------------------------------------------------------------- record mode
SESSIONS: dict[str, dict] = {}


def start_record(molecule_id: int | None = None, step: int | None = None, upload: tuple[str, bytes] | None = None) -> dict:
    d = Path(tempfile.mkdtemp(prefix="mwfn_rec_", dir=str(samples_dir())))
    if upload:
        name = re.sub(r"[^A-Za-z0-9._+-]+", "_", upload[0])
        (d / name).write_bytes(upload[1])
        sample = name
    else:
        from .runner import base_name
        from .visuals import last_step_with_gbw, step_paths
        m = db.q1("SELECT * FROM molecules WHERE id=?", (molecule_id,))
        if not m:
            raise ValueError("molecule not found")
        k = step if step is not None else last_step_with_gbw(m)
        if k is None:
            raise ValueError("no finished step with a .gbw")
        sd, base = step_paths(m, k)
        from .scripts_reg import ensure_molden
        sample = ensure_molden(sd, base)
        shutil.copy2(sd / sample, d / sample)
    sid = uuid.uuid4().hex[:12]
    SESSIONS[sid] = {"dir": str(d), "sample": sample, "answers": [], "output": "", "buf": "", "started": time.time(),
                     "done": False}
    return {"id": sid, "sample": sample}


def record_input(sess: dict, data: str):
    """Track what the user types: each Enter completes one answer line."""
    for ch in data:
        if ch in ("\r", "\n"):
            sess["answers"].append(sess["buf"])
            sess["buf"] = ""
        elif ch in ("\x7f", "\b"):
            sess["buf"] = sess["buf"][:-1]
        elif ch == "\x03":
            sess["buf"] = ""
        elif ch == "\x1b":
            continue
        elif ch.isprintable():
            sess["buf"] += ch


def recorded(sid: str) -> dict:
    sess = SESSIONS.get(sid)
    if not sess:
        raise ValueError("record session not found")
    out = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", sess["output"]).replace("\r\n", "\n").replace("\r", "\n")
    answers = [a.replace(sess["sample"], "{molden}") for a in sess["answers"]]
    return {"answers": answers, "output": out, "sample": sess["sample"], "version": version_of(out), "done": sess["done"]}


def save_recipe(sid: str | None, recipe: dict) -> dict:
    recipe = dict(recipe)
    rid = recipe.get("id") or store.unique_id("multiwfn_recipes", recipe.get("name") or "recipe")
    recipe["id"] = rid
    if sid and sid in SESSIONS:
        sess = SESSIONS[sid]
        dest = samples_dir() / rid
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(sess["dir"]) / sess["sample"], dest / sess["sample"])
        rec = recorded(sid)
        (dest / "output.txt").write_text(rec["output"])
        recipe["sample"] = {"molden": str(dest / sess["sample"]), "output": str(dest / "output.txt")}
        recipe.setdefault("multiwfn_version", rec["version"])
        recipe["recorded"] = time.strftime("%Y-%m-%d")
    cites = recipe.setdefault("citations", [])
    if MULTIWFN_CITATION not in cites:
        cites.insert(0, MULTIWFN_CITATION)
    return store.save_item("multiwfn_recipes", recipe)


def retest(recipe_id: str) -> dict:
    """Re-run a recipe on its stored sample and compare with the stored output."""
    r = store.get_item("multiwfn_recipes", recipe_id)
    if not r or not r.get("sample"):
        return {"id": recipe_id, "ok": False, "message": "no stored sample"}
    sample = Path(r["sample"]["molden"])
    with tempfile.TemporaryDirectory(dir=str(samples_dir())) as td:
        shutil.copy2(sample, Path(td) / sample.name)
        out = run_recipe(r, Path(td), sample.name, timeout=1800)
        new = out.read_text(errors="replace")
    old = Path(r["sample"]["output"]).read_text(errors="replace") if Path(r["sample"]["output"]).exists() else ""
    norm = lambda t: [ln.rstrip() for ln in t.splitlines() if not re.search(r"took|time|Date|elapsed|wall", ln, re.I)]
    diff = list(difflib.unified_diff(norm(old), norm(new), "recorded", "now", n=1, lineterm=""))
    rules = []
    for rule in r.get("rules") or []:
        a, b = parse_rule(rule, old), parse_rule(rule, new)
        rules.append({"rule": rule.get("label") or rule.get("id"), "recorded": a, "now": b, "same": a == b})
    ok = all(x["same"] for x in rules)
    return {"id": recipe_id, "ok": ok, "version_recorded": r.get("multiwfn_version"), "version_now": version_of(new),
            "diff": diff[:400], "rules": rules,
            "message": "all results identical" if ok else "results changed: check the menu answers for this Multiwfn version"}


# --------------------------------------------------------------------------- citations
def citation_report(batch_id: int) -> str:
    """Citations for a batch: ORCA's own suggestions, method entries, Multiwfn recipes used."""
    b = batches.get(batch_id)
    from .extraction import load_out, out_path_for, profile_for
    cites: list[str] = []

    def add(c):
        c = c.strip()
        if c and c not in cites:
            cites.append(c)

    suggested = []
    for m in batches.molecules(batch_id):
        for k in range(len(b["profile"].get("steps") or [1])):
            p = out_path_for(b, m, k)
            o = load_out(p) if p else None
            if not o:
                continue
            i = next((n for n, ln in enumerate(o.lines) if "SUGGESTED CITATIONS" in ln.upper()), None)
            if i is not None:
                block = []
                for ln in o.lines[i + 1:i + 120]:
                    if "TOTAL RUN TIME" in ln or "ORCA TERMINATED" in ln:
                        break
                    block.append(ln.rstrip())
                suggested.append("\n".join(block).strip())
        if suggested:
            break
    from .assemble import Catalog
    cat = Catalog()
    for step in b["profile"].get("steps") or []:
        for cid, v in (step.get("values") or {}).items():
            col = cat.columns.get(cid, {})
            if col.get("type") == "dropdown":
                for eid in (v if isinstance(v, list) else [v]):
                    e = cat.entry(col.get("library"), eid)
                    if e and e.get("cite"):
                        add(e["cite"])
    for c in (store.get_library("citations") or {}).get("entries", []):
        if "always" in (c.get("tags") or []):
            add(c["orca_text"])
    used = set()
    for f in profile_for(b).get("fields") or []:
        if f.get("kind") == "multiwfn":
            used.add((f.get("multiwfn") or {}).get("recipe"))
    for rid in used:
        r = store.get_item("multiwfn_recipes", rid or "")
        if r:
            add(MULTIWFN_CITATION)
            for c in r.get("citations") or []:
                add(c)
    lines = [f"Citations for batch '{b['name']}' (generated {time.strftime('%Y-%m-%d')})", ""]
    if suggested:
        lines += ["ORCA's suggested citations for these runs (from the output file):", suggested[0], ""]
    lines += ["References:"] + [f"[{i + 1}] {c}" for i, c in enumerate(cites)]
    return "\n".join(lines) + "\n"
