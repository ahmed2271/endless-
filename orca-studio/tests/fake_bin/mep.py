#!/usr/bin/env python3
"""Stand-in for the user's mep.py (tests only): python mep.py basename npoints nprocs."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _fakecube as fc  # noqa: E402

base, n = sys.argv[1], int(sys.argv[2])
atoms = fc.atoms_of(base)
fc.write(f"{base}_mep.cube", atoms, n, fc.esp(atoms))
print(f"wrote {base}_mep.cube with {n} points per side")
