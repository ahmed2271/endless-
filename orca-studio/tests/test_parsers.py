"""Parser tests.

1. Value tests on ORCA-6-style files in tests/data/synthetic/ (made by the stand-in ORCA here).
2. Invariant tests on every real ORCA .out in tests/data/real/ (copy them there on the workstation
   with:  python tests/collect_real_outputs.py <batch folder>). These check internal consistency
   (energies match the raw text, charges sum to the total charge, thermochemistry adds up, ...).
"""
import re
from pathlib import Path

import pytest

from conftest import DATA
from orca_studio.parsers.aux_files import parse_hess, parse_property_file, property_value
from orca_studio.parsers.orca_out import OrcaOut

SYN = DATA / "synthetic"
REAL = sorted((DATA / "real").glob("**/*.out"))


def test_water_optfreq():
    o = OrcaOut.from_file(SYN / "water_optfreq.out")
    assert o.terminated_normally and o.version == "6.0.1"
    assert o.opt_converged() and o.opt_cycles == 3
    assert o.final_energy == pytest.approx(o.all_energies[-1])
    assert o.charge == 0 and o.mult == 1 and o.n_electrons == 10
    assert len(o.final_geometry) == 3 and o.final_geometry[0][0] == "O"
    fr = o.frequencies
    assert len(fr) == 9 and fr[:6] == [0.0] * 6
    assert o.imaginary_count(-30) == 0
    t = o.thermo
    assert t["temperature"] == pytest.approx(298.15) and t["pressure"] == pytest.approx(1.0)
    assert t["total_gibbs"] == pytest.approx(t["total_enthalpy"] - t["ts_total"], abs=1e-6)
    assert t["gibbs_correction"] == pytest.approx(t["total_gibbs"] - t["electronic_energy"], abs=1e-6)
    assert len(o.ir_spectrum) == 3
    hl = o.homo_lumo()
    assert hl["homo"]["index"] == 4 and hl["lumo"]["index"] == 5 and hl["gap_ev"] > 0
    assert o.orbital_index("homo", 1) == 3 and o.orbital_index("lumo", 2) == 7
    assert sum(r["charge"] for r in o.mulliken) == pytest.approx(0, abs=1e-4)
    assert len(o.loewdin) == 3 and len(o.hirshfeld) == 3 and len(o.mbis) == 3 and len(o.chelpg) == 3
    assert o.mbis[0]["population"] > 8
    assert o.mayer_bond_orders and o.mayer_bond_orders[0]["atom1"] == 0
    assert o.dipole["total"] == pytest.approx(o.dipole["total_au"] * 2.541746, rel=1e-5)
    assert o.energy_components["dispersion"] < 0
    assert o.rotational_constants_cm[0] == pytest.approx(27.123456)
    assert o.scf_converged is True and o.scf_iterations == 12


def test_side_files():
    h = parse_hess(SYN / "water_optfreq.hess")
    assert len(h["frequencies"]) == 9 and len(h["atoms"]) == 3 and len(h["normal_modes"]) == 9
    props = parse_property_file(SYN / "water_optfreq.property.txt")
    o = OrcaOut.from_file(SYN / "water_optfreq.out")
    assert property_value(props, "SCF_ENERGY") == pytest.approx(o.final_energy)


def test_tddft_orca6_format():
    o = OrcaOut.from_file(SYN / "methanol_tddft.out")
    st = o.excited_states
    singlets = [s for s in st if s["mult"] == 1]
    triplets = [s for s in st if s["mult"] == 3]
    assert len(singlets) == 6 and len(triplets) == 6
    assert singlets[0]["fosc"] == pytest.approx(0.05) and singlets[1]["fosc"] == pytest.approx(0.0001)
    assert singlets[0]["nm"] == pytest.approx(1e7 / singlets[0]["energy_cm"])
    assert singlets[0]["transitions"][0]["from"] == 4 and singlets[0]["main_transition"].startswith("4a->5a")
    assert all(s["fosc"] == 0 for s in triplets)
    assert singlets[0]["tdm"] is not None


def test_tddft_orca5_format():
    o = OrcaOut.from_file(SYN / "orca5_style_tddft_snippet.out")
    st = o.excited_states
    assert [s["mult"] for s in st] == [1, 1]
    assert st[1]["fosc"] == pytest.approx(0.23456789)


def test_open_shell():
    o = OrcaOut.from_file(SYN / "oh_uks.out")
    assert o.mult == 2
    assert o.s2["s2"] == pytest.approx(0.7542) and o.s2["deviation"] == pytest.approx(0.0042)
    orb = o.orbitals
    assert not orb["restricted"] and orb["alpha"] and orb["beta"]
    assert o.homo_lumo("alpha")["homo"]["index"] == 4 and o.homo_lumo("beta")["homo"]["index"] == 3
    assert o.mulliken[0]["spin"] is not None


def test_custom_pattern():
    o = OrcaOut.from_file(SYN / "water_optfreq.out")
    v, lines = o.custom_pattern("Zero point energy", occurrence="last", number_index=1)
    assert v == pytest.approx(o.thermo["zpe"])
    v, _ = o.custom_pattern(r"FINAL SINGLE POINT ENERGY", occurrence="all")
    assert len(v) == len(o.all_energies)
    v, _ = o.custom_pattern(r"Magnitude \(Debye\)", regex=True)
    assert v == pytest.approx(o.dipole["total"])
    v, _ = o.custom_pattern("DIPOLE MOMENT", next_line=True)
    assert v is None


# ----------------------------------------------------------------------------- real files
@pytest.mark.skipif(not REAL, reason="no real ORCA outputs in tests/data/real yet")
@pytest.mark.parametrize("path", REAL, ids=[p.name for p in REAL])
def test_real_output_invariants(path):
    o = OrcaOut.from_file(path)
    text = o.text
    assert o.version and o.version.startswith("6.")
    raw = re.findall(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)", text)
    if raw:
        assert o.final_energy == pytest.approx(float(raw[-1]))
    if o.mulliken and o.charge is not None:
        assert sum(r["charge"] for r in o.mulliken) == pytest.approx(o.charge, abs=2e-3)
    if o.orbitals and o.n_electrons and o.orbitals["restricted"]:
        assert o.homo_lumo()["homo"]["index"] == o.n_electrons // 2 - 1
        assert o.orbitals["alpha"][0]["index"] == 0
    if o.frequencies is not None and o.final_geometry:
        n = len(o.final_geometry)
        assert len(o.frequencies) == 3 * n
    if o.thermo and o.thermo.get("total_gibbs") is not None:
        t = o.thermo
        assert t["total_gibbs"] == pytest.approx(t["total_enthalpy"] - t["ts_total"], abs=2e-6)
    if "THE OPTIMIZATION HAS CONVERGED" in text:
        assert o.opt_converged() and o.opt_cycles
    if o.excited_states:
        roots = re.search(r"NRoots\s+(\d+)", o.input_text, re.I)
        sing = [s for s in o.excited_states if s["mult"] in (1, None)]
        if roots:
            assert len(sing) >= int(roots.group(1))
        assert all(s["fosc"] is None or s["fosc"] >= 0 for s in sing)
    if o.dipole:
        assert o.dipole["total"] == pytest.approx(o.dipole["total_au"] * 2.541746, rel=1e-3)
