"""Input assembly (section 6.6).

Program logic here only *arranges* text; every piece of ORCA text comes from the YAML
libraries (entries, column templates, step types and the 'assembly' templates list).
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from . import config, store

_PH = re.compile(r"\{([A-Za-z_][A-Za-z0-9_:]*)\}")


def fill(template: str, mapping: dict[str, Any]) -> str:
    """Replace {name} only for names in mapping (other braces, e.g. {B 0 1 C}, stay)."""

    def rep(m):
        k = m.group(1)
        if k.startswith("col:"):
            k = k[4:]
        if k in mapping and mapping[k] is not None:
            return str(mapping[k])
        return m.group(0)

    return _PH.sub(rep, template or "")


def tpl(entry_id: str, default: str = "") -> str:
    return store.text("assembly", entry_id, default)


# --------------------------------------------------------------------------- lookups
class Catalog:
    """Snapshot of libraries + columns used during one assembly/validation pass."""

    def __init__(self):
        self.libs = store.all_libraries()
        self.columns = store.columns()
        self.step_types = {e["id"]: e for e in self.libs.get("step_types", {}).get("entries", [])}

    def entry(self, list_ids, entry_id):
        for lid in list_ids or []:
            for e in (self.libs.get(lid) or {}).get("entries", []):
                if e["id"] == entry_id:
                    return e
        return None

    def step_type(self, type_id):
        return self.step_types.get(type_id) or {"id": type_id, "label": type_id, "orca_text": "", "kind": "custom"}


def column_applies(col: dict, step_type: dict) -> bool:
    targets = col.get("applies_to") or ["all"]
    ids = {step_type.get("id"), step_type.get("kind")}
    pos = [t for t in targets if not str(t).startswith("!")]
    neg = [t[1:] for t in targets if str(t).startswith("!")]
    if any(n in ids for n in neg):
        return False
    return "all" in pos or any(p in ids for p in pos)


def cell_value(profile: dict, step: dict, col_id: str, catalog: Catalog | None = None):
    """Step value -> profile defaults row -> column default. '' means blank (nothing written)."""
    vals = step.get("values") or {}
    if col_id in vals and vals[col_id] is not None and vals[col_id] != "__inherit__":
        return vals[col_id]
    d = profile.get("defaults") or {}
    if col_id in d and d[col_id] is not None:
        return d[col_id]
    if catalog and col_id in catalog.columns:
        return catalog.columns[col_id].get("default", "")
    return ""


def is_blank(v) -> bool:
    return v is None or v == "" or v is False or v == [] or v == "__blank__"


def profile_columns_in_use(profile: dict, catalog: Catalog) -> list[str]:
    """Column ids that may contribute: layout columns + any column with a value."""
    ids = [c["column"] for c in profile.get("columns") or [] if c.get("column") in catalog.columns]
    for s in profile.get("steps") or []:
        for k in (s.get("values") or {}):
            if k not in ids and k in catalog.columns:
                ids.append(k)
    for k in (profile.get("defaults") or {}):
        if k not in ids and k in catalog.columns:
            ids.append(k)
    for cid, c in catalog.columns.items():
        if cid not in ids and c.get("default") not in ("", None):
            ids.append(cid)
    return ids


# --------------------------------------------------------------------------- blocks
def parse_blocks_text(text: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Split free text like '%scf MaxIter 500 end\\n%geom ...' into (block, content) pairs.

    Content runs to the next line that starts with '%'; its final 'end' is the terminator.
    Directives such as %maxcore / %moinp have no 'end' and are returned as simple lines.
    """
    singles = set((tpl("single_line_directives", "maxcore moinp base") or "").lower().split())
    close = (tpl("block_close", "end") or "end").lower()
    blocks, simple = [], []
    chunks: list[list[str]] = []
    for line in (text or "").replace("\r", "").split("\n"):
        if line.strip().startswith("%"):
            chunks.append([line.strip()])
        elif chunks:
            chunks[-1].append(line.rstrip())
        elif line.strip():
            simple.append(line.strip())
    for ch in chunks:
        head = ch[0][1:].strip()
        name, _, rest = head.partition(" ")
        if name.lower() in singles:
            simple.append(ch[0])
            continue
        body = "\n".join([rest] + ch[1:]).strip()
        toks = body.rsplit(None, 1)
        if toks and toks[-1].lower() == close:
            body = toks[0] if len(toks) > 1 else ""
        elif body.lower() == close:
            body = ""
        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
        blocks.append((name, "\n".join(lines)))
    return blocks, simple


class Blocks:
    def __init__(self):
        self.data: "OrderedDict[str, tuple[str, list[str]]]" = OrderedDict()

    def add(self, name: str, content: str):
        if not content.strip():
            return
        key = name.lower()
        disp, lines = self.data.setdefault(key, (name, []))
        new_lines = [ln.strip() for ln in content.split("\n") if ln.strip()]
        if len(new_lines) == 1:
            ln = new_lines[0]
            k = ln.split()[0].lower()
            for i, old in enumerate(lines):
                if old == ln:
                    return
                if "\n" not in old and old.split()[0].lower() == k and len(old.split()) > 1 and len(ln.split()) > 1:
                    lines[i] = ln          # a later setting of the same key wins (e.g. retries)
                    return
            lines.append(ln)
        else:
            if "\n".join(new_lines) not in "\n".join(lines):
                lines.extend(new_lines)

    def render(self) -> list[str]:
        out = []
        close = tpl("block_close", "end")
        opener = tpl("block_open", "%{name}")
        for _, (name, lines) in self.data.items():
            if not lines:
                continue
            if len(lines) == 1 and len(lines[0]) < 60 and "\n" not in lines[0]:
                out.append(f"{fill(opener, {'name': name})} {lines[0]} {close}")
            else:
                out.append(fill(opener, {"name": name}))
                indent = 0
                for ln in lines:
                    if ln.lower() == close.lower() and indent > 0:
                        indent -= 1
                    out.append("  " * (indent + 1) + ln)
                    first = ln.split()[0].lower() if ln.split() else ""
                    if first in ("constraints", "scan", "modify_internal", "hybrid_hess") and ln.lower() == first:
                        indent += 1
                out.append(close)
        return out


# --------------------------------------------------------------------------- main
def dedupe_keywords(tokens: list[str]) -> list[str]:
    seen, out = set(), []
    for t in tokens:
        k = t.lower()
        if k and k not in seen:
            seen.add(k)
            out.append(t)
    return out


def resources(profile: dict, step: dict, settings: dict | None = None) -> tuple[int, int]:
    s = settings or config.load_settings()
    res = profile.get("resources") or {}
    vals = step.get("values") or {}

    def pick(key, fallback):
        v = vals.get(key)
        if is_blank(v) or v == "__inherit__":
            v = (profile.get("defaults") or {}).get(key)
        if is_blank(v):
            v = res.get(key)
        if is_blank(v):
            v = fallback
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return int(fallback)

    return pick("nprocs", s["resources"].get("default_nprocs", 2)), pick("maxcore", s["resources"].get("default_maxcore", 1000))


def assemble(profile: dict, step_index: int, mol: dict | None = None, *, subjob: str | None = None,
             xyzfile: str = "input.xyz", inline_block: str | None = None, coord_type: str = "xyz",
             gbw: str | None = None, additions: list[dict] | None = None, catalog: Catalog | None = None,
             settings: dict | None = None, molecule_name: str | None = None,
             allow_moread: bool = True) -> dict:
    """Build the ORCA input for one step (and molecule). Returns text plus details.

    mol: {'charge','mult','name'}; None -> placeholders for the preview.
    additions: extra contributions [{'destination','orca_text','slot'}] (retry strategies, KeepDens...).
    gbw: orbital file for MORead (only used when the step asks for it).
    """
    cat = catalog or Catalog()
    step = profile["steps"][step_index]
    stype = cat.step_type(step.get("type"))
    warnings: list[str] = []
    slots_order = (tpl("keyword_slots") or "job method dispersion basis aux ri scf grid solvent properties extras").split()
    slots: dict[str, list[str]] = {k: [] for k in slots_order}
    blocks = Blocks()
    simple_lines: list[str] = []

    def add_kw(text_: str, slot: str):
        if not text_.strip():
            return
        slots.setdefault(slot if slot in slots else "extras", []).extend(text_.split())

    def contribute(dest: str, text_: str, slot: str):
        dest = (dest or "keyword_line").strip()
        if dest == "none" or not (text_ or "").strip():
            return
        if dest == "keyword_line":
            add_kw(text_, slot)
        elif dest.startswith("block:"):
            blocks.add(dest.split(":", 1)[1], text_)
        else:
            warnings.append(f"unknown destination '{dest}'")

    # job keywords from the step type
    job_tokens = (stype.get("orca_text") or "").split()

    col_ids = profile_columns_in_use(profile, cat)
    # first pass: the ORCA text each column resolves to (for {solvent}-style placeholders)
    resolved: dict[str, str] = {}
    chosen: dict[str, Any] = {}
    for cid in col_ids:
        col = cat.columns[cid]
        if col.get("subjob") and col.get("subjob") != subjob:
            continue
        if not column_applies(col, stype):
            continue
        v = cell_value(profile, step, cid, cat)
        if is_blank(v):
            continue
        chosen[cid] = v
        if col.get("type") == "dropdown":
            ids = v if isinstance(v, list) else [v]
            texts = []
            for eid in ids:
                e = cat.entry(col.get("library"), eid)
                if e:
                    texts.append(e["orca_text"])
            resolved[cid] = " ".join(texts)
        else:
            resolved[cid] = str(v)

    for cid, v in chosen.items():
        col = cat.columns[cid]
        if col.get("special") or col.get("slot") == "none":
            continue
        for tok in col.get("replaces_tokens") or []:
            job_tokens = [t for t in job_tokens if t.lower() != str(tok).lower()]
        slot = col.get("slot") or "extras"
        if col.get("type") == "dropdown":
            ids = v if isinstance(v, list) else [v]
            for eid in ids:
                e = cat.entry(col.get("library"), eid)
                if not e:
                    warnings.append(f"{col['label']}: '{eid}' is not in the library")
                    continue
                if not column_applies({"applies_to": e.get("applies_to") or ["all"]}, stype):
                    warnings.append(f"{col['label']}: {e['label']} does not apply to {stype['label']} steps")
                if "{solvent}" in e["orca_text"] and not resolved.get("solvent"):
                    warnings.append(f"{e['label']} needs a solvent: set the Solvent column")
                    continue
                contribute(e.get("destination", "keyword_line"), fill(e["orca_text"], resolved), slot)
                for extra in e.get("also") or []:
                    contribute(extra.get("destination", "keyword_line"), fill(extra.get("orca_text", ""), resolved),
                               extra.get("slot", slot))
        elif col.get("type") == "toggle":
            if v in (True, "true", "on", 1, "1", "yes"):
                contribute(col.get("destination", "keyword_line"), fill(col.get("template", ""), resolved), slot)
        else:
            mapping = dict(resolved)
            mapping["value"] = v
            contribute(col.get("destination", "keyword_line"), fill(col.get("template", "{value}"), mapping), slot)

    for a in additions or []:
        contribute(a.get("destination", "keyword_line"), a.get("orca_text", ""), a.get("slot", "extras"))

    slots["job"] = job_tokens + slots.get("job", [])

    # MORead of previous orbitals
    moread = chosen.get("moread") in (True, "true", "on", 1, "1", "yes") or bool(gbw and subjob)
    moread = moread and allow_moread
    if moread:
        g = gbw or "previous.gbw"
        add_kw(tpl("moread_keyword", "MORead"), "scf")
        simple_lines.append(fill(tpl("moinp", '%moinp "{gbw}"'), {"gbw": g}))

    # step extras
    add_kw(step.get("extra_keywords") or "", "extras")
    bl, simple = parse_blocks_text(step.get("extra_blocks") or "")
    for name, content in bl:
        blocks.add(name, content)
    singles_skip = {"maxcore", "pal"}
    for s in simple:
        if s.startswith("%") and s[1:].split()[0].lower() in singles_skip:
            warnings.append(f"'{s}' ignored: cores and memory come from the step resources")
            continue
        simple_lines.append(s)
    if "pal" in blocks.data:
        blocks.data.pop("pal")
        warnings.append("%pal in extra blocks ignored: cores come from the step resources")

    tokens = []
    for k in slots_order + [k for k in slots if k not in slots_order]:
        tokens.extend(slots.get(k, []))
    tokens = dedupe_keywords(tokens)

    nprocs, maxcore = resources(profile, step, settings)

    # charge / multiplicity
    if mol is not None:
        charge = int(mol.get("charge", 0))
        mult = int(mol.get("mult", 1))
        off = chosen.get("charge_offset")
        try:
            off = int(float(off)) if not is_blank(off) else 0
        except (TypeError, ValueError):
            off = 0
        charge += off
        mo = chosen.get("mult_override")
        if not is_blank(mo):
            mult = int(float(mo))
        elif off % 2:
            mult = mult + 1 if mult == 1 else mult - 1
        if subjob:
            sj = next((x for x in stype.get("subjobs") or [] if x.get("id") == subjob), {})
            if sj.get("force_mult"):
                mult = int(sj["force_mult"])
    else:
        charge, mult = "{charge}", "{mult}"

    name = molecule_name or (mol or {}).get("name") or "{molecule}"
    lines = []
    header = tpl("header_comment")
    if header:
        lines.append(fill(header, {
            "profile": profile.get("name", profile.get("id", "")), "version": profile.get("version", 1),
            "step_no": step_index + 1, "step_name": step.get("name") or stype["label"], "molecule": name,
        }) + (f" | {subjob}" if subjob else ""))
    prefix = tpl("keyword_prefix", "!")
    if tokens:
        lines.append(f"{prefix} " + " ".join(tokens))
    lines.append(fill(tpl("maxcore", "%maxcore {maxcore}"), {"maxcore": maxcore}))
    lines.append(fill(tpl("pal", "%pal nprocs {nprocs} end"), {"nprocs": nprocs}))
    lines.extend(simple_lines)
    rendered = blocks.render()
    if rendered:
        lines.append("")
        lines.extend(rendered)
    lines.append("")
    if inline_block is not None:
        lines.append(fill(tpl("geometry_inline", "* {coord_type} {charge} {mult}"),
                          {"coord_type": coord_type, "charge": charge, "mult": mult}))
        lines.append(inline_block)
        lines.append(tpl("geometry_inline_end", "*"))
    else:
        lines.append(fill(tpl("geometry_xyzfile", "* xyzfile {charge} {mult} {xyzfile}"),
                          {"charge": charge, "mult": mult, "xyzfile": xyzfile}))
    text = "\n".join(lines) + "\n"

    manual = step.get("manual_input")
    if manual and not subjob:
        text = fill(manual, {"charge": charge, "mult": mult, "nprocs": nprocs, "maxcore": maxcore,
                             "xyzfile": xyzfile, "molecule": name, "gbw": gbw or "previous.gbw"})
        if not text.endswith("\n"):
            text += "\n"

    return {
        "text": text, "keywords": tokens, "blocks": {k: v[1] for k, v in blocks.data.items()},
        "warnings": warnings, "nprocs": nprocs, "maxcore": maxcore, "charge": charge, "mult": mult,
        "manual": bool(manual and not subjob), "step_type": stype, "chosen": chosen, "moread": moread,
    }


def manual_template(profile: dict, step_index: int) -> str:
    """Starting text for 'Edit final input': the assembled input with placeholders."""
    p = dict(profile)
    steps = [dict(s) for s in profile["steps"]]
    steps[step_index] = dict(steps[step_index], manual_input=None)
    p["steps"] = steps
    r = assemble(p, step_index, None, molecule_name="{molecule}")
    text = r["text"]
    text = text.replace(f"nprocs {r['nprocs']} end", "nprocs {nprocs} end").replace(
        f"%maxcore {r['maxcore']}", "%maxcore {maxcore}")
    return text
