"""Element symbols, atomic numbers and masses."""
from __future__ import annotations

SYMBOLS = (
    "H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr "
    "Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu "
    "Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr "
    "Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og"
).split()
Z = {s: i + 1 for i, s in enumerate(SYMBOLS)}
_LOWER = {s.lower(): s for s in SYMBOLS}

# Standard atomic weights (first 86 elements; others approximated by 2.5*Z)
_MASSES = [
    1.008, 4.0026, 6.94, 9.0122, 10.81, 12.011, 14.007, 15.999, 18.998, 20.180, 22.990, 24.305, 26.982,
    28.085, 30.974, 32.06, 35.45, 39.948, 39.098, 40.078, 44.956, 47.867, 50.942, 51.996, 54.938, 55.845,
    58.933, 58.693, 63.546, 65.38, 69.723, 72.630, 74.922, 78.971, 79.904, 83.798, 85.468, 87.62, 88.906,
    91.224, 92.906, 95.95, 98.0, 101.07, 102.91, 106.42, 107.87, 112.41, 114.82, 118.71, 121.76, 127.60,
    126.90, 131.29, 132.91, 137.33, 138.91, 140.12, 140.91, 144.24, 145.0, 150.36, 151.96, 157.25, 158.93,
    162.50, 164.93, 167.26, 168.93, 173.05, 174.97, 178.49, 180.95, 183.84, 186.21, 190.23, 192.22, 195.08,
    196.97, 200.59, 204.38, 207.2, 208.98, 209.0, 210.0, 222.0,
]


def mass(sym: str) -> float:
    z = Z[sym]
    return _MASSES[z - 1] if z <= len(_MASSES) else 2.5 * z


def normalize_symbol(token: str) -> str | None:
    """'C', 'c', 'C1', 'C(1)', 'Cl' -> canonical symbol; None if not an element."""
    import re

    m = re.match(r"^([A-Za-z]{1,2})", token)
    if not m:
        return None
    t = m.group(1)
    if t.lower() in _LOWER and (len(t) == 1 or not t[1:].isdigit()):
        # prefer two-letter match only if it is a real element
        return _LOWER[t.lower()]
    if t[0].lower() in _LOWER:
        return _LOWER[t[0].lower()]
    return None


def parse_ranges(spec: str) -> set[str]:
    """'H-Rn' or 'H-Ar,Ca-Kr,I' -> set of symbols."""
    out: set[str] = set()
    for part in (spec or "").replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            if a in Z and b in Z:
                for z in range(Z[a], Z[b] + 1):
                    out.add(SYMBOLS[z - 1])
        elif part in Z:
            out.add(part)
    return out


def hill_formula(symbols: list[str]) -> str:
    from collections import Counter

    c = Counter(symbols)
    parts = []
    order = []
    if "C" in c:
        order = ["C"] + (["H"] if "H" in c else [])
    order += sorted(s for s in c if s not in order)
    for s in order:
        n = c[s]
        parts.append(s if n == 1 else f"{s}{n}")
    return "".join(parts)
