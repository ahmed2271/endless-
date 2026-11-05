"""Shared cube writer for the stand-in orca_plot and mep.py (tests only)."""
import math

BOHR = 1 / 0.529177210903
ZN = {"H": 1, "C": 6, "N": 7, "O": 8, "F": 9, "S": 16, "Cl": 17}
Q = {"H": 0.3, "C": 0.1, "N": -0.5, "O": -0.6}


def atoms_of(base):
    lines = open(f"{base}.xyz").read().splitlines()
    n = int(lines[0].split()[0])
    return [(p.split()[0], *(float(x) * BOHR for x in p.split()[1:4])) for p in lines[2:2 + n]]


def write(path, atoms, n, func):
    lo = [min(a[i] for a in atoms) - 6.0 for i in (1, 2, 3)]
    hi = [max(a[i] for a in atoms) + 6.0 for i in (1, 2, 3)]
    step = [(hi[i] - lo[i]) / (n - 1) for i in range(3)]
    with open(path, "w") as fh:
        fh.write("stand-in cube\ngenerated for tests\n")
        fh.write(f"{len(atoms):5d}{lo[0]:12.6f}{lo[1]:12.6f}{lo[2]:12.6f}\n")
        for i in range(3):
            v = [0.0, 0.0, 0.0]
            v[i] = step[i]
            fh.write(f"{n:5d}{v[0]:12.6f}{v[1]:12.6f}{v[2]:12.6f}\n")
        for a in atoms:
            fh.write(f"{ZN.get(a[0], 6):5d}{float(ZN.get(a[0], 6)):12.6f}{a[1]:12.6f}{a[2]:12.6f}{a[3]:12.6f}\n")
        vals = []
        for ix in range(n):
            x = lo[0] + ix * step[0]
            for iy in range(n):
                y = lo[1] + iy * step[1]
                for iz in range(n):
                    z = lo[2] + iz * step[2]
                    vals.append(func(x, y, z))
        for i in range(0, len(vals), 6):
            fh.write("".join(f"{v:13.5E}" for v in vals[i:i + 6]) + "\n")


def density(atoms):
    def f(x, y, z):
        return sum(ZN.get(a[0], 6) * 0.2 * math.exp(-0.6 * ((x - a[1]) ** 2 + (y - a[2]) ** 2 + (z - a[3]) ** 2)) for a in atoms)
    return f


def esp(atoms):
    def f(x, y, z):
        return sum(Q.get(a[0], 0.0) / max(0.3, math.sqrt((x - a[1]) ** 2 + (y - a[2]) ** 2 + (z - a[3]) ** 2)) for a in atoms)
    return f


def mo(atoms, idx):
    c = atoms[idx % len(atoms)]

    def f(x, y, z):
        r2 = (x - c[1]) ** 2 + (y - c[2]) ** 2 + (z - c[3]) ** 2
        return (z - c[3]) * math.exp(-0.5 * r2) * (1 if idx % 2 else -1)
    return f
