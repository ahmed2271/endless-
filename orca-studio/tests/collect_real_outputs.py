#!/usr/bin/env python3
"""Copy real ORCA .out files (and .hess/.property.txt) from a batch folder into tests/data/real/.

    python tests/collect_real_outputs.py ~/dft_projects/acceptance
    python -m pytest tests/test_parsers.py
"""
import shutil
import sys
from pathlib import Path

dst = Path(__file__).resolve().parent / "data" / "real"
dst.mkdir(parents=True, exist_ok=True)
n = 0
for src in sys.argv[1:]:
    for p in Path(src).expanduser().rglob("*.out"):
        if ".attempt" in p.name:
            continue
        rel = p.relative_to(Path(src).expanduser())
        name = "__".join(rel.parts)
        shutil.copy2(p, dst / name)
        for side in (p.with_suffix(".hess"), p.with_suffix(".property.txt")):
            if side.exists():
                shutil.copy2(side, dst / (name[:-4] + side.name[len(p.stem):]))
        n += 1
print(f"copied {n} output files to {dst}")
