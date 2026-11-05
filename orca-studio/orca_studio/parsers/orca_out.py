"""Dedicated parser for ORCA 6 .out files.

Every method returns plain Python values (None when the section is absent). For repeated
sections (optimizations print many SCFs) the LAST occurrence is used unless stated otherwise.
"""
from __future__ import annotations

import re
from functools import cached_property
from pathlib import Path

F = r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?"
DEBYE_PER_AU = 2.541746473


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class OrcaOut:
    def __init__(self, text: str, path: str | None = None):
        self.text = text
        self.path = path
        self.lines = text.splitlines()

    @classmethod
    def from_file(cls, path) -> "OrcaOut":
        p = Path(path)
        return cls(p.read_text(errors="replace"), str(p))

    # ------------------------------------------------------------------ helpers
    def _last(self, pattern: str, group: int = 1, flags=0, conv=_f):
        ms = list(re.finditer(pattern, self.text, flags | re.M))
        if not ms:
            return None
        return conv(ms[-1].group(group)) if conv else ms[-1].group(group)

    def _all(self, pattern: str, group: int = 1, flags=0, conv=_f):
        return [conv(m.group(group)) if conv else m.group(group) for m in re.finditer(pattern, self.text, flags | re.M)]

    def _section_starts(self, header_regex: str) -> list[int]:
        rx = re.compile(header_regex)
        return [i for i, ln in enumerate(self.lines) if rx.search(ln)]

    def _last_section(self, header_regex: str) -> int | None:
        s = self._section_starts(header_regex)
        return s[-1] if s else None

    def _rows_after(self, start: int, row_rx: str, max_gap: int = 6, stop_rx: str | None = None):
        """Collect regex matches for lines after `start` until the table ends."""
        rx = re.compile(row_rx)
        stop = re.compile(stop_rx) if stop_rx else None
        rows, gap, started = [], 0, False
        for ln in self.lines[start + 1:]:
            if stop and stop.search(ln) and started:
                break
            m = rx.match(ln)
            if m:
                rows.append(m)
                started, gap = True, 0
            else:
                gap += 1
                if (started and gap > 0 and ln.strip() == "") or gap > max_gap + (0 if started else 20):
                    if started:
                        break
                    if gap > max_gap + 20:
                        break
        return rows

    # ------------------------------------------------------------------ run info
    def matches(self, regex: str) -> bool:
        return bool(regex) and re.search(regex, self.text, re.I | re.M) is not None

    @cached_property
    def terminated_normally(self) -> bool:
        return "ORCA TERMINATED NORMALLY" in self.text

    @cached_property
    def version(self):
        return self._last(r"Program Version\s+(\S+)", conv=None)

    @cached_property
    def run_time_seconds(self):
        m = re.search(r"TOTAL RUN TIME:\s*(\d+) days (\d+) hours (\d+) minutes (\d+) seconds (\d+) msec", self.text)
        if not m:
            return None
        d, h, mi, s, ms = map(int, m.groups())
        return d * 86400 + h * 3600 + mi * 60 + s + ms / 1000

    @cached_property
    def input_text(self) -> str:
        return "\n".join(m.group(1) for m in re.finditer(r"^\|\s*\d+>\s?(.*)$", self.text, re.M))

    @cached_property
    def keywords(self) -> list[str]:
        out = []
        for ln in self.input_text.splitlines():
            if ln.strip().startswith("!"):
                out.extend(ln.strip()[1:].split())
        return out

    @cached_property
    def charge(self):
        v = self._last(r"Total Charge\s+Charge\s+\.+\s+(-?\d+)", conv=int)
        return v

    @cached_property
    def mult(self):
        return self._last(r"Multiplicity\s+Mult\s+\.+\s+(\d+)", conv=int)

    @cached_property
    def n_electrons(self):
        return self._last(r"Number of Electrons\s+NEL\s+\.+\s+(\d+)", conv=int)

    @cached_property
    def n_basis_functions(self):
        v = self._last(r"Number of basis functions\s+\.+\s+(\d+)", conv=int)
        if v is None:
            v = self._last(r"Basis Dimension\s+Dim\s+\.+\s+(\d+)", conv=int)
        return v

    @cached_property
    def scf_iterations(self):
        return self._last(r"SCF CONVERGED AFTER\s+(\d+)\s+CYCLES", conv=int)

    @cached_property
    def scf_converged(self) -> bool | None:
        if re.search(r"SCF NOT CONVERGED|wavefunction IS NOT CONVERGED", self.text, re.I):
            return False
        if "SCF CONVERGED AFTER" in self.text:
            return True
        return None

    # ------------------------------------------------------------------ energies
    @cached_property
    def final_energy(self):
        return self._last(rf"FINAL SINGLE POINT ENERGY\s+({F})")

    @cached_property
    def all_energies(self):
        return self._all(rf"FINAL SINGLE POINT ENERGY\s+({F})")

    @cached_property
    def energy_components(self) -> dict:
        c = {}
        pats = {
            "nuclear_repulsion": rf"Nuclear Repulsion\s*:\s*({F})",
            "electronic_energy": rf"Electronic Energy\s*:\s*({F})",
            "one_electron": rf"One Electron Energy\s*:\s*({F})",
            "two_electron": rf"Two Electron Energy\s*:\s*({F})",
            "e_x": rf"^\s*E\(X\)\s*:\s*({F})",
            "e_c": rf"^\s*E\(C\)\s*:\s*({F})",
            "e_xc": rf"^\s*E\(XC\)\s*:\s*({F})",
            "dispersion": rf"Dispersion correction\s+({F})",
            "gcp": rf"gCP correction\s+({F})",
            "solvation": rf"CPCM Dielectric\s*:\s*({F})",
            "smd_cds": rf"SMD CDS[^:\n]*:\s*({F})",
            "correlation": rf"(?:Final correlation energy|MP2 CORRELATION ENERGY|E\(CORR\)\(corrected\))\s*(?:\.\.\.|:)\s*({F})",
            "t1_diagnostic": rf"T1 diagnostic\s*\.+\s*({F})",
        }
        for k, p in pats.items():
            c[k] = self._last(p)
        if c["e_xc"] is None and c["e_x"] is not None and c["e_c"] is not None:
            c["e_xc"] = c["e_x"] + c["e_c"]
        return c

    # ------------------------------------------------------------------ geometry
    @cached_property
    def opt_cycles(self):
        v = self._all(r"GEOMETRY OPTIMIZATION CYCLE\s+(\d+)", conv=int)
        return max(v) if v else None

    def opt_converged(self, pattern: str = "THE OPTIMIZATION HAS CONVERGED") -> bool:
        return self.matches(pattern)

    @cached_property
    def geometries(self) -> list[list[tuple]]:
        out = []
        for st in self._section_starts(r"^CARTESIAN COORDINATES \(ANGSTROEM\)"):
            rows = self._rows_after(st, rf"^\s*([A-Z][a-z]?)\S*\s+({F})\s+({F})\s+({F})\s*$", max_gap=2)
            if rows:
                out.append([(m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))) for m in rows])
        return out

    @cached_property
    def final_geometry(self):
        g = self.geometries
        return g[-1] if g else None

    @cached_property
    def initial_geometry(self):
        g = self.geometries
        return g[0] if g else None

    @cached_property
    def rotational_constants_cm(self):
        m = list(re.finditer(rf"Rotational constants in cm-1:\s*({F})\s+({F})\s+({F})", self.text))
        return [float(x) for x in m[-1].groups()] if m else None

    # ------------------------------------------------------------------ frequencies / thermo
    @cached_property
    def frequencies(self):
        st = self._last_section(r"^VIBRATIONAL FREQUENCIES")
        if st is None:
            return None
        rows = self._rows_after(st, rf"^\s*(\d+):\s+({F})\s+cm\*\*-1", max_gap=4)
        return [float(m.group(2)) for m in rows]

    def imaginary_count(self, threshold: float = 0.0) -> int | None:
        """Number of frequencies below -|threshold| (threshold given as e.g. -30 or 30)."""
        fr = self.frequencies
        if fr is None:
            return None
        t = -abs(threshold)
        return sum(1 for f in fr if f < t) if t else sum(1 for f in fr if f < 0)

    @cached_property
    def lowest_frequency(self):
        fr = [f for f in (self.frequencies or []) if abs(f) > 1e-6]
        return min(fr) if fr else None

    @cached_property
    def ir_spectrum(self):
        st = self._last_section(r"^IR SPECTRUM")
        if st is None:
            return None
        rows = self._rows_after(st, rf"^\s*(\d+):\s+({F})\s+({F})\s+({F})\s+({F})", max_gap=6)
        return [{"mode": int(m.group(1)), "freq": float(m.group(2)), "eps": float(m.group(3)),
                 "intensity": float(m.group(4)), "t2": float(m.group(5))} for m in rows]

    @cached_property
    def raman_spectrum(self):
        st = self._last_section(r"^RAMAN SPECTRUM")
        if st is None:
            return None
        rows = self._rows_after(st, rf"^\s*(\d+):\s+({F})\s+({F})\s+({F})", max_gap=6)
        return [{"mode": int(m.group(1)), "freq": float(m.group(2)), "activity": float(m.group(3)),
                 "depolarization": float(m.group(4))} for m in rows]

    @cached_property
    def thermo(self) -> dict | None:
        if "Final Gibbs free energy" not in self.text and "Total Enthalpy" not in self.text:
            return None
        P = {
            "temperature": r"Temperature\s+\.+\s+(" + F + r"|\d+)\s*K",
            "pressure": r"Pressure\s+\.+\s+(" + F + r"|\d+)\s*atm",
            "electronic_energy": rf"Electronic energy\s+\.+\s+({F})\s+Eh",
            "zpe": rf"Zero point energy\s+\.+\s+({F})\s+Eh",
            "thermal_vib": rf"Thermal vibrational correction\s+\.+\s+({F})\s+Eh",
            "thermal_rot": rf"Thermal rotational correction\s+\.+\s+({F})\s+Eh",
            "thermal_trans": rf"Thermal translational correction\s+\.+\s+({F})\s+Eh",
            "total_thermal_energy": rf"Total thermal energy\s+({F})\s+Eh",
            "thermal_correction": rf"Total thermal correction\s+({F})\s+Eh",
            "total_correction": rf"Total correction\s+({F})\s+Eh",
            "enthalpy_correction_kT": rf"Thermal Enthalpy correction\s+\.+\s+({F})\s+Eh",
            "total_enthalpy": rf"Total Enthalpy\s+\.+\s+({F})\s+Eh",
            "s_el": rf"Electronic entropy\s+\.+\s+({F})\s+Eh",
            "s_vib": rf"Vibrational entropy\s+\.+\s+({F})\s+Eh",
            "s_rot": rf"Rotational entropy\s+\.+\s+({F})\s+Eh",
            "s_trans": rf"Translational entropy\s+\.+\s+({F})\s+Eh",
            "ts_total": rf"Final entropy term\s+\.+\s+({F})\s+Eh",
            "total_gibbs": rf"Final Gibbs free energy\s+\.+\s+({F})\s+Eh",
            "gibbs_correction": rf"G-E\(el\)\s+\.+\s+({F})\s+Eh",
        }
        t = {k: self._last(p) for k, p in P.items()}
        if t["total_enthalpy"] is not None and t["electronic_energy"] is not None:
            t["enthalpy_correction"] = t["total_enthalpy"] - t["electronic_energy"]
        else:
            t["enthalpy_correction"] = None
        if t["gibbs_correction"] is None and t["total_gibbs"] is not None and t["electronic_energy"] is not None:
            t["gibbs_correction"] = t["total_gibbs"] - t["electronic_energy"]
        return t

    # ------------------------------------------------------------------ orbitals / spin
    @cached_property
    def orbitals(self) -> dict | None:
        st = self._last_section(r"^ORBITAL ENERGIES\s*$")
        if st is None:
            return None
        alpha, beta, cur = [], [], None
        rx = re.compile(rf"^\s*(\d+)\s+({F})\s+({F})\s+({F})")
        started = False
        cur = alpha
        for ln in self.lines[st + 1:]:
            if "SPIN DOWN ORBITALS" in ln:
                cur = beta
                continue
            if "SPIN UP ORBITALS" in ln:
                cur = alpha
                continue
            m = rx.match(ln)
            if m:
                cur.append({"index": int(m.group(1)), "occ": float(m.group(2)), "e_eh": float(m.group(3)),
                            "e_ev": float(m.group(4))})
                started = True
            elif started and ln.strip() and not ln.strip().startswith("NO") and "SPIN" not in ln:
                if ln.strip().startswith("*") or ln.strip().startswith("-") or re.match(r"^\s*[A-Za-z]", ln):
                    break
        return {"alpha": alpha, "beta": beta, "restricted": not beta}

    def homo_lumo(self, spin: str = "alpha"):
        orbs = self.orbitals
        if not orbs:
            return None
        lst = orbs[spin] if orbs[spin] else orbs["alpha"]
        occ = [o for o in lst if o["occ"] > 0.5 * (1 if not orbs["restricted"] else 1)]
        vir = [o for o in lst if o["occ"] <= 0.5]
        homo = occ[-1] if occ else None
        lumo = vir[0] if vir else None
        return {"homo": homo, "lumo": lumo,
                "gap_ev": (lumo["e_ev"] - homo["e_ev"]) if homo and lumo else None}

    def orbital_index(self, which: str, n: int = 0, spin: str = "alpha"):
        """'homo', n=2 -> index of HOMO-2; 'lumo', n=1 -> LUMO+1 (ORCA numbering from 0)."""
        hl = self.homo_lumo(spin)
        if not hl:
            return None
        if which == "homo" and hl["homo"]:
            return hl["homo"]["index"] - n
        if which == "lumo" and hl["lumo"]:
            return hl["lumo"]["index"] + n
        return None

    @cached_property
    def s2(self) -> dict | None:
        e = self._last(rf"Expectation value of <S\*\*2>\s*:\s*({F})")
        if e is None:
            return None
        ideal = self._last(rf"Ideal value S\*\(S\+1\) for S=[\d.]+\s*:\s*({F})")
        dev = self._last(rf"Deviation\s*:\s*({F})")
        if dev is None and ideal is not None:
            dev = e - ideal
        return {"s2": e, "ideal": ideal, "deviation": dev}

    # ------------------------------------------------------------------ populations
    def _atom_table(self, header_rx: str, row_rx: str, cols: list[str], one_based=False, sym_first=False):
        st = self._last_section(header_rx)
        if st is None:
            return None
        rows = self._rows_after(st, row_rx, max_gap=8)
        out = []
        for m in rows:
            g = m.groups()
            if sym_first:
                sym, idx = g[0], int(g[1]) - 1
            else:
                idx, sym = int(g[0]), g[1]
                if one_based:
                    idx -= 1
            rec = {"atom": idx, "element": sym}
            for k, v in zip(cols, g[2:]):
                rec[k] = _f(v)
            out.append(rec)
        return out or None

    @cached_property
    def mulliken(self):
        return self._atom_table(r"^MULLIKEN ATOMIC CHARGES",
                                rf"^\s*(\d+)\s+([A-Z][a-z]?)\S*\s*:\s*({F})(?:\s+({F}))?\s*$", ["charge", "spin"])

    @cached_property
    def loewdin(self):
        return self._atom_table(r"^LOEWDIN ATOMIC CHARGES",
                                rf"^\s*(\d+)\s+([A-Z][a-z]?)\S*\s*:\s*({F})(?:\s+({F}))?\s*$", ["charge", "spin"])

    @cached_property
    def hirshfeld(self):
        return self._atom_table(r"^\s*HIRSHFELD ANALYSIS",
                                rf"^\s*(\d+)\s+([A-Z][a-z]?)\S*\s+({F})(?:\s+({F}))?\s*$", ["charge", "spin"])

    @cached_property
    def mbis(self):
        return self._atom_table(r"MBIS ANALYSIS",
                                rf"^\s*(\d+)\s+([A-Z][a-z]?)\S*\s+({F})(?:\s+({F}))?(?:\s+({F}))?\s*$",
                                ["charge", "population", "spin"])

    @cached_property
    def chelpg(self):
        return self._atom_table(r"^CHELPG Charges",
                                rf"^\s*(\d+)\s+([A-Z][a-z]?)\S*\s*:\s*({F})\s*$", ["charge"])

    @cached_property
    def resp(self):
        return self._atom_table(r"^RESP Charges",
                                rf"^\s*(\d+)\s+([A-Z][a-z]?)\S*\s*:\s*({F})\s*$", ["charge"])

    @cached_property
    def npa(self):
        return self._atom_table(r"Summary of Natural Population Analysis",
                                rf"^\s*([A-Z][a-z]?)\s+(\d+)\s+({F})\s+({F})\s+({F})\s+({F})\s+({F})",
                                ["charge", "core", "valence", "rydberg", "population"], sym_first=True)

    @cached_property
    def mayer_atoms(self):
        return self._atom_table(r"MAYER POPULATION ANALYSIS",
                                rf"^\s*(\d+)\s+([A-Z][a-z]?)\S*\s+({F})\s+({F})\s+({F})\s+({F})\s+({F})\s+({F})",
                                ["na", "za", "qa", "valence", "bonded_valence", "free_valence"])

    def _bond_orders(self, header_rx):
        st = self._last_section(header_rx)
        if st is None:
            return None
        rx = re.compile(rf"B\(\s*(\d+)-([A-Za-z]+)\s*,\s*(\d+)-([A-Za-z]+)\s*\)\s*:\s*({F})")
        out = []
        started = False
        for ln in self.lines[st + 1: st + 4000]:
            ms = list(rx.finditer(ln))
            if ms:
                started = True
                for m in ms:
                    out.append({"atom1": int(m.group(1)), "el1": m.group(2), "atom2": int(m.group(3)),
                                "el2": m.group(4), "order": float(m.group(5))})
            elif started and (ln.strip() == "" or ln.startswith("-")):
                break
        return out or None

    @cached_property
    def mayer_bond_orders(self):
        return self._bond_orders(r"Mayer bond orders larger than")

    @cached_property
    def loewdin_bond_orders(self):
        return self._bond_orders(r"^LOEWDIN BOND ORDERS")

    def charges(self, scheme: str):
        scheme = scheme.lower()
        return {
            "mulliken": self.mulliken, "loewdin": self.loewdin, "lowdin": self.loewdin,
            "hirshfeld": self.hirshfeld, "mbis": self.mbis, "chelpg": self.chelpg,
            "resp": self.resp, "npa": self.npa, "nbo": self.npa,
        }.get(scheme)

    # ------------------------------------------------------------------ electric properties
    @cached_property
    def dipole(self):
        m = list(re.finditer(rf"Total Dipole Moment\s*:\s*({F})\s+({F})\s+({F})", self.text))
        if not m:
            return None
        x, y, z = (float(v) for v in m[-1].groups())
        tot_au = self._last(rf"Magnitude \(a\.u\.\)\s*:\s*({F})")
        tot_d = self._last(rf"Magnitude \(Debye\)\s*:\s*({F})")
        if tot_au is None:
            tot_au = (x * x + y * y + z * z) ** 0.5
        if tot_d is None:
            tot_d = tot_au * DEBYE_PER_AU
        return {"x_au": x, "y_au": y, "z_au": z, "x": x * DEBYE_PER_AU, "y": y * DEBYE_PER_AU,
                "z": z * DEBYE_PER_AU, "total_au": tot_au, "total": tot_d}

    @cached_property
    def quadrupole_isotropic(self):
        return self._last(rf"Isotropic quadrupole\s*:\s*({F})")

    @cached_property
    def polarizability_isotropic(self):
        return self._last(rf"Isotropic polarizability\s*:\s*({F})")

    # ------------------------------------------------------------------ excited states
    @cached_property
    def excited_states(self):
        """All TDDFT/CIS states of the last calculation, with fosc and main transitions."""
        hdr = re.compile(r"(?:TD-DFT|CIS|TDA|RPA)[^\n]*EXCITED STATES\s*(?:\((SINGLETS|TRIPLETS|UNRESTRICTED|[A-Z]+)\))?")
        st_rx = re.compile(rf"^\s*STATE\s+(\d+):\s+E=\s+({F})\s+au\s+({F})\s+eV\s+({F})\s+cm\*\*-1"
                           rf"(?:\s+<S\*\*2>\s+=\s+({F}))?(?:\s+Mult\s+(\d+))?")
        tr_rx = re.compile(rf"^\s*(\d+)([ab])\s*->\s*(\d+)([ab])\s*:\s*({F})(?:\s*\(c=\s*({F})\))?")
        blocks = {}   # header kind -> list of states (last occurrence wins)
        cur, cur_state = None, None
        for ln in self.lines:
            h = hdr.search(ln)
            if h and not ln.lstrip().startswith("STATE"):
                kind = (h.group(1) or "STATES").upper()
                cur = []
                blocks[kind] = cur
                cur_state = None
                continue
            if cur is None:
                continue
            m = st_rx.match(ln)
            if m:
                mult = int(m.group(6)) if m.group(6) else {"SINGLETS": 1, "TRIPLETS": 3}.get(
                    [k for k, v in blocks.items() if v is cur][0])
                cur_state = {"state": int(m.group(1)), "energy_au": float(m.group(2)), "energy_ev": float(m.group(3)),
                             "energy_cm": float(m.group(4)), "s2": _f(m.group(5)), "mult": mult,
                             "nm": 1e7 / float(m.group(4)) if float(m.group(4)) else None,
                             "fosc": None, "transitions": []}
                cur.append(cur_state)
                continue
            t = tr_rx.match(ln)
            if t and cur_state is not None:
                cur_state["transitions"].append({"from": int(t.group(1)), "from_spin": t.group(2),
                                                 "to": int(t.group(3)), "to_spin": t.group(4),
                                                 "weight": float(t.group(5))})
        states = []
        for kind in ("SINGLETS", "STATES", "UNRESTRICTED", "TRIPLETS"):
            states.extend(blocks.get(kind, []))
        for kind, lst in blocks.items():
            if kind not in ("SINGLETS", "STATES", "UNRESTRICTED", "TRIPLETS"):
                states.extend(lst)
        if not states:
            return None
        absorb = self._spectrum_rows(r"^\s*ABSORPTION SPECTRUM VIA TRANSITION ELECTRIC DIPOLE MOMENTS")
        for s in states:
            key = (s["state"], s["mult"])
            row = absorb.get(key) or absorb.get((s["state"], None))
            if row:
                s["fosc"] = row["value"]
                s["tdm"] = row.get("vec")
            elif s["mult"] == 3:
                s["fosc"] = 0.0
        cd = self._spectrum_rows(r"^\s*CD SPECTRUM(?: VIA TRANSITION ELECTRIC DIPOLE MOMENTS)?\s*$")
        for s in states:
            row = cd.get((s["state"], s["mult"])) or cd.get((s["state"], None))
            s["rotatory_strength"] = row["value"] if row else None
        for s in states:
            if s["transitions"]:
                main = max(s["transitions"], key=lambda t: t["weight"])
                s["main_transition"] = f"{main['from']}{main['from_spin']}->{main['to']}{main['to_spin']} ({main['weight']:.2f})"
            else:
                s["main_transition"] = ""
        return states

    def _spectrum_rows(self, header_rx: str) -> dict:
        """Parse ORCA 6 ('0-1A  ->  1-1A ...') or ORCA 5 ('  1  cm  nm  fosc ...') spectrum tables."""
        starts = [i for i, ln in enumerate(self.lines) if re.search(header_rx, ln) and "SOC" not in ln]
        if not starts:
            return {}
        st = starts[-1]
        v6 = re.compile(rf"^\s*\d+-\d*[A-Za-z]*\s*->\s*(\d+)-(\d*)[A-Za-z]*\s+({F})\s+({F})\s+({F})\s+({F})"
                        rf"(?:\s+({F}))?(?:\s+({F}))?(?:\s+({F}))?(?:\s+({F}))?")
        v5 = re.compile(rf"^\s*(\d+)\s+({F})\s+({F})\s+({F})(?:\s+({F}))?(?:\s+({F}))?(?:\s+({F}))?(?:\s+({F}))?")
        out, started = {}, False
        for ln in self.lines[st + 1: st + 2000]:
            m = v6.match(ln)
            if m:
                started = True
                mult = int(m.group(2)) if m.group(2) else None
                extra = [_f(x) for x in m.groups()[6:] if x is not None]
                vec = extra[-3:] if len(extra) >= 4 else None
                out[(int(m.group(1)), mult)] = {"value": float(m.group(6)), "vec": vec}
                continue
            m = v5.match(ln)
            if m:
                started = True
                extra = [_f(x) for x in m.groups()[4:] if x is not None]
                vec = extra[-3:] if len(extra) >= 4 else None
                out[(int(m.group(1)), None)] = {"value": float(m.group(4)), "vec": vec}
                continue
            if started and (not ln.strip() or ln.strip().startswith("-") and len(out) > 0 and ln.count("-") > 20):
                if not ln.strip():
                    break
        return out

    # ------------------------------------------------------------------ custom patterns
    def custom_pattern(self, text: str, regex: bool = False, occurrence: str = "last", number_index: int = 1,
                       next_line: bool = False, ignore_case: bool = False):
        """Find a line by text/regex and return the n-th number on it (or on the next line).

        Returns (value or list of values, list of matched line numbers)."""
        flags = re.I if ignore_case else 0
        rx = re.compile(text if regex else re.escape(text), flags)
        hits = [i for i, ln in enumerate(self.lines) if rx.search(ln)]
        if not hits:
            return None, []
        if occurrence == "first":
            hits = hits[:1]
        elif occurrence == "last":
            hits = hits[-1:]
        vals, used = [], []
        for i in hits:
            j = i + 1 if next_line else i
            if j >= len(self.lines):
                continue
            line = self.lines[j]
            if not next_line:
                m = rx.search(line)
                line_after = line[m.end():] if m else line
            else:
                line_after = line
            nums = re.findall(r"[-+]?\d+\.\d+(?:[eE][-+]?\d+)?|[-+]?\d+(?:[eE][-+]?\d+)?", line_after)
            k = int(number_index)
            if nums and 1 <= k <= len(nums):
                vals.append(float(nums[k - 1]))
                used.append(j)
            elif nums and k < 0 and -k <= len(nums):
                vals.append(float(nums[k]))
                used.append(j)
        if not vals:
            return None, hits
        return (vals if occurrence == "all" else vals[0]), used


def parse(path) -> OrcaOut:
    return OrcaOut.from_file(path)
