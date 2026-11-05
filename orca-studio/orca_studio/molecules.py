"""Reading structures from .xyz and .inp files (section 7)."""
from __future__ import annotations

import math
import re
from pathlib import Path

from .elements import Z, hill_formula, normalize_symbol

CHARGE_RE = re.compile(r"\bcharge\s*=\s*([+-]?\d+)", re.I)
MULT_RE = re.compile(r"\bmult(?:iplicity)?\s*=\s*(\d+)", re.I)
COORD_START_RE = re.compile(r"^\s*\*\s*(xyzfile|xyz|gzmtfile|gzmt|internal|int)\b(.*)$", re.I)
NUM = r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[eEdD][-+]?\d+)?"


class StructureError(ValueError):
    pass


def safe_name(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._+-]+", "_", name.strip()).strip("._")
    return s or "mol"


def molecule_record(name, atoms, charge, mult, warnings=None, coord_type="xyz", raw_block="", source=""):
    syms = [a[0] for a in atoms]
    nel = sum(Z[s] for s in syms) - int(charge)
    return {
        "name": name,
        "atoms": atoms,
        "charge": int(charge),
        "mult": int(mult),
        "formula": hill_formula(syms) if syms else "",
        "natoms": len(atoms),
        "nelectrons": nel,
        "coord_type": coord_type,
        "raw_block": raw_block,
        "warnings": warnings or [],
        "source": source,
    }


def parse_xyz_text(text: str, name: str = "mol", default_charge=0, default_mult=1, multi=False):
    """Parse a (multi-)xyz text. Returns one record, or a list if multi=True."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = []
    i = 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        try:
            n = int(lines[i].split()[0])
        except (ValueError, IndexError):
            raise StructureError(f"line {i + 1}: expected the atom count")
        comment = lines[i + 1] if i + 1 < len(lines) else ""
        atoms = []
        for j in range(i + 2, i + 2 + n):
            if j >= len(lines):
                raise StructureError(f"file ends before {n} atoms were read")
            parts = lines[j].split()
            if len(parts) < 4:
                raise StructureError(f"line {j + 1}: expected 'element x y z'")
            sym = normalize_symbol(parts[0])
            if sym is None:
                raise StructureError(f"line {j + 1}: unknown element '{parts[0]}'")
            try:
                atoms.append((sym, float(parts[1]), float(parts[2]), float(parts[3])))
            except ValueError:
                raise StructureError(f"line {j + 1}: bad coordinates")
        warnings = []
        cm, mm = CHARGE_RE.search(comment), MULT_RE.search(comment)
        charge = int(cm.group(1)) if cm else default_charge
        mult = int(mm.group(1)) if mm else default_mult
        if not cm or not mm:
            warnings.append(
                f"No 'charge=X mult=Y' in the comment line; using charge {charge}, multiplicity {mult}"
            )
        out.append(molecule_record(name, atoms, charge, mult, warnings))
        out[-1]["comment"] = comment.strip()
        i += 2 + n
        if not multi:
            break
    if not out:
        raise StructureError("no structure found")
    return out if multi else out[0]


def parse_inp_text(text: str, name: str = "mol", extra_files: dict[str, str] | None = None,
                   default_charge=0, default_mult=1):
    """Keep only the coordinate block of an ORCA input and its charge/multiplicity."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for i, line in enumerate(lines):
        m = COORD_START_RE.match(line)
        if not m:
            continue
        kind = m.group(1).lower()
        rest = m.group(2).split()
        if len(rest) < 2:
            raise StructureError(f"line {i + 1}: '* {kind}' needs charge and multiplicity")
        charge, mult = int(rest[0]), int(rest[1])
        if kind == "xyzfile":
            if len(rest) < 3:
                raise StructureError("'* xyzfile' line has no file name")
            fname = rest[2].strip('"')
            content = (extra_files or {}).get(Path(fname).name)
            if content is None:
                raise StructureError(f"this input reads '{fname}': drop that .xyz file together with the .inp")
            rec = parse_xyz_text(content, name, charge, mult)
            rec["charge"], rec["mult"], rec["warnings"] = charge, mult, []
            rec["nelectrons"] = sum(Z[a[0]] for a in rec["atoms"]) - charge
            return rec
        if kind in ("gzmtfile",):
            raise StructureError("'* gzmtfile' is not supported; convert to .xyz")
        block = []
        for j in range(i + 1, len(lines)):
            if lines[j].strip().startswith("*"):
                break
            if lines[j].strip() and not lines[j].strip().startswith("#"):
                block.append(lines[j].rstrip())
        else:
            raise StructureError("coordinate block has no closing '*'")
        atoms, simple = [], True
        for ln in block:
            parts = ln.split()
            sym = normalize_symbol(parts[0])
            if sym is None:
                raise StructureError(f"unknown element in '{ln.strip()}'")
            if kind == "xyz":
                nums = [p for p in parts[1:4] if re.fullmatch(NUM, p)]
                if len(nums) < 3:
                    raise StructureError(f"bad coordinate line '{ln.strip()}'")
                atoms.append((sym, float(nums[0]), float(nums[1]), float(nums[2])))
                if len(parts) > 4 or not re.fullmatch(r"[A-Za-z]{1,2}", parts[0]):
                    simple = False
            else:
                atoms.append((sym, 0.0, 0.0, 0.0))
                simple = False
        coord_type = "xyz" if (kind == "xyz" and simple) else kind
        rec = molecule_record(name, atoms, charge, mult, [], coord_type=coord_type,
                              raw_block="\n".join(block) if coord_type != "xyz" else "")
        if coord_type != "xyz":
            rec["warnings"].append(
                "Coordinate block has extra per-atom information (fragments, internal coordinates); "
                "step 1 uses it as written, later steps use ORCA's optimized .xyz"
            )
        return rec
    raise StructureError("no coordinate block (* xyz / * int / * xyzfile) found")


def write_xyz(atoms, comment: str = "") -> str:
    lines = [str(len(atoms)), comment]
    for s, x, y, z in atoms:
        lines.append(f"{s:<3s}{x:16.8f}{y:16.8f}{z:16.8f}")
    return "\n".join(lines) + "\n"


def read_xyz_file(path: Path):
    return parse_xyz_text(Path(path).read_text(errors="replace"), Path(path).stem)


def last_frame_of_trj(path: Path):
    frames = parse_xyz_text(Path(path).read_text(errors="replace"), Path(path).stem, multi=True)
    return frames[-1]


def parity_ok(nelectrons: int, mult: int) -> bool:
    return mult >= 1 and (nelectrons % 2) == ((mult - 1) % 2) and (mult - 1) <= nelectrons


def rmsd(a, b) -> float | None:
    """Plain RMSD after centering (no rotation fit), Å."""
    if len(a) != len(b) or not a:
        return None
    import numpy as np

    A = np.array([x[1:] for x in a]); B = np.array([x[1:] for x in b])
    A -= A.mean(0); B -= B.mean(0)
    # Kabsch fit
    H = A.T @ B
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1, 1, d])
    R = Vt.T @ D @ U.T
    A2 = (R @ A.T).T
    return float(math.sqrt(((A2 - B) ** 2).sum() / len(a)))
