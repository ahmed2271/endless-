"""Parsers for ORCA side files: property file (.property.txt), Hessian (.hess), cube files."""
from __future__ import annotations

import re
from pathlib import Path

BOHR = 0.529177210903


# --------------------------------------------------------------------------- property file
def parse_property_file(path) -> dict:
    """ORCA 6 {basename}.property.txt -> {section: [ {key: value} ... ]} (one dict per occurrence).

    Lines look like:  &SCF_ENERGY [&Type "Double"]      -7.6323501160375057e+01
    [VERIFY] Appendix D check 9: which values this file contains on 6.0.1.
    """
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[str, list[dict]] = {}
    cur = None
    rx = re.compile(r'^\s*&(\w+)\s*(?:\[&Type\s+"(\w+)"[^\]]*\])?\s*(.*)$')
    for ln in p.read_text(errors="replace").splitlines():
        s = ln.strip()
        if s.startswith("$") and s.lower() != "$end":
            cur = {}
            out.setdefault(s[1:].strip(), []).append(cur)
            continue
        if s.lower() == "$end":
            cur = None
            continue
        if cur is None:
            continue
        m = rx.match(ln)
        if m:
            key, typ, val = m.group(1), m.group(2), m.group(3).strip()
            if typ in ("Double", "Integer", "Boolean") or re.fullmatch(r"[-+]?\d+(\.\d*)?([eE][-+]?\d+)?", val):
                try:
                    cur[key] = float(val) if typ != "Integer" else int(float(val))
                except ValueError:
                    cur[key] = val.strip('"')
            else:
                cur[key] = val.strip('"')
    return out


def property_value(props: dict, *keys: str):
    """Last value of any of the given keys, searched in every section (case-insensitive)."""
    want = {k.lower() for k in keys}
    found = None
    for sec in props.values():
        for occ in sec:
            for k, v in occ.items():
                if k.lower() in want and isinstance(v, (int, float)):
                    found = v
    return found


# --------------------------------------------------------------------------- hess file
def parse_hess(path) -> dict:
    """Read frequencies, normal modes (columns) and atoms (Bohr) from an ORCA .hess file."""
    lines = Path(path).read_text(errors="replace").splitlines()
    out: dict = {}
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if s == "$vibrational_frequencies":
            n = int(lines[i + 1].split()[0])
            out["frequencies"] = [float(lines[i + 2 + k].split()[1]) for k in range(n)]
            i += 2 + n
            continue
        if s == "$normal_modes":
            nr, nc = (int(x) for x in lines[i + 1].split()[:2])
            mat = [[0.0] * nc for _ in range(nr)]
            j = i + 2
            filled = 0
            while filled < nc and j < len(lines):
                cols = [int(x) for x in lines[j].split()]
                for r in range(nr):
                    parts = lines[j + 1 + r].split()
                    for c, v in zip(cols, parts[1:]):
                        mat[r][c] = float(v)
                filled += len(cols)
                j += 1 + nr
            out["normal_modes"] = mat          # mat[coordinate][mode]
            i = j
            continue
        if s == "$atoms":
            n = int(lines[i + 1].split()[0])
            atoms = []
            for k in range(n):
                p = lines[i + 2 + k].split()
                atoms.append((p[0], float(p[1]), float(p[2]) * BOHR, float(p[3]) * BOHR, float(p[4]) * BOHR))
            out["atoms"] = atoms               # (symbol, mass, x, y, z) in Å
            i += 2 + n
            continue
        i += 1
    return out


def displace_along_mode(hess: dict, mode: int, amplitude: float = 0.15):
    """Geometry (Å) displaced along a normal mode so the largest atomic shift is `amplitude` Å."""
    atoms = hess["atoms"]
    vec = [row[mode] for row in hess["normal_modes"]]
    shifts = [(vec[3 * a], vec[3 * a + 1], vec[3 * a + 2]) for a in range(len(atoms))]
    biggest = max((dx * dx + dy * dy + dz * dz) ** 0.5 for dx, dy, dz in shifts) or 1.0
    k = amplitude / biggest
    return [(a[0], a[2] + k * d[0], a[3] + k * d[1], a[4] + k * d[2]) for a, d in zip(atoms, shifts)]


# --------------------------------------------------------------------------- cube files
def read_cube(path):
    """Gaussian cube -> dict(origin, axes (3x3), shape, atoms [(Z,x,y,z) bohr], data numpy array)."""
    import numpy as np

    with open(path) as fh:
        fh.readline(); fh.readline()
        parts = fh.readline().split()
        natoms = int(parts[0])
        origin = np.array([float(x) for x in parts[1:4]])
        shape, axes = [], []
        for _ in range(3):
            p = fh.readline().split()
            shape.append(int(p[0]))
            axes.append([float(x) for x in p[1:4]])
        atoms = []
        for _ in range(abs(natoms)):
            p = fh.readline().split()
            atoms.append((int(float(p[0])), float(p[2]), float(p[3]), float(p[4])))
        if natoms < 0:
            fh.readline()
        data = np.array(fh.read().split(), dtype=float)
    n = shape[0] * shape[1] * shape[2]
    data = data[:n].reshape(shape)
    return {"origin": origin, "axes": np.array(axes), "shape": shape, "atoms": atoms, "data": data}


def surface_extrema(density_cube, esp_cube, iso: float = 0.001):
    """V_min / V_max of the ESP on the density isosurface, with the nearest atom of each.

    Samples grid edges where the density crosses `iso` (linear interpolation of the ESP).
    """
    import numpy as np

    from ..elements import SYMBOLS

    d = read_cube(density_cube)
    e = read_cube(esp_cube)
    if d["shape"] != e["shape"]:
        raise ValueError("density and ESP cubes are on different grids")
    rho, V = d["data"], e["data"]
    pts, vals = [], []
    for ax in range(3):
        a = np.take(rho, range(rho.shape[ax] - 1), axis=ax)
        b = np.take(rho, range(1, rho.shape[ax]), axis=ax)
        va = np.take(V, range(V.shape[ax] - 1), axis=ax)
        vb = np.take(V, range(1, V.shape[ax]), axis=ax)
        cross = (a - iso) * (b - iso) < 0
        idx = np.argwhere(cross)
        if not len(idx):
            continue
        t = (iso - a[cross]) / (b[cross] - a[cross])
        vals.append(va[cross] + t * (vb[cross] - va[cross]))
        frac = idx.astype(float)
        frac[:, ax] += t
        pts.append(d["origin"] + frac @ d["axes"])
    if not vals:
        return None
    vals = np.concatenate(vals)
    pts = np.concatenate(pts)
    atoms = np.array([a[1:] for a in d["atoms"]])

    def nearest(p):
        k = int(np.argmin(((atoms - p) ** 2).sum(1)))
        z = d["atoms"][k][0]
        return {"atom": k, "element": SYMBOLS[z - 1] if 0 < z <= len(SYMBOLS) else str(z)}

    imin, imax = int(np.argmin(vals)), int(np.argmax(vals))
    return {"vmin_au": float(vals[imin]), "vmax_au": float(vals[imax]),
            "vmin_atom": nearest(pts[imin]), "vmax_atom": nearest(pts[imax]), "n_points": int(len(vals))}
