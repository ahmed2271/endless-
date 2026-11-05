"""Success checks after a job (section 8.5). Message texts come from libraries/output_patterns.yaml."""
from __future__ import annotations

import re
from pathlib import Path

from . import store
from .parsers.orca_out import OrcaOut

OPT_KINDS = ("xtb", "opt", "opt_freq")
FREQ_KINDS = ("opt_freq", "freq")


def pattern(pid: str, default: str) -> str:
    return store.text("output_patterns", pid, default) or default


def evaluate(out_path: Path, exit_code: int | None, kind: str, wf: dict, *, freq_expected: bool | None = None,
             opt_expected: bool | None = None) -> dict:
    """Return {'ok', 'failure', 'checks', 'fired', 'summary'}.

    failure: None | 'crash' | 'scf' | 'opt' | 'imag' | 's2'
    """
    checks: dict[str, dict] = {}
    fired: list[str] = []
    cfg = wf.get("checks") or {}
    if not out_path.exists():
        return {"ok": False, "failure": "crash", "checks": {"output": {"status": "fail", "detail": "no .out file"}},
                "fired": ["output"], "summary": "no output file"}
    out = OrcaOut.from_file(out_path)
    normal = out.matches(pattern("normal_termination", "ORCA TERMINATED NORMALLY"))
    exit_ok = exit_code in (0, None)
    checks["termination"] = {"status": "pass" if (normal and exit_ok) else "fail",
                             "detail": f"exit code {exit_code}" + ("" if normal else ", no normal termination")}
    scf_bad = out.matches(pattern("scf_not_converged", "SCF NOT CONVERGED"))
    if cfg.get("scf_converged", "fail") != "off":
        checks["scf"] = {"status": "fail" if scf_bad else "pass",
                         "detail": "SCF not converged" if scf_bad else "SCF converged"}
    failure = None
    if checks["termination"]["status"] == "fail":
        if scf_bad:
            failure = "scf"
        elif out.matches(pattern("opt_not_converged", "optimization did not converge")):
            failure = "opt"
        else:
            failure = "crash"
    elif scf_bad and cfg.get("scf_converged", "fail") == "fail":
        failure = "scf"

    is_opt = opt_expected if opt_expected is not None else kind in OPT_KINDS
    if is_opt and cfg.get("opt_converged", "fail") != "off":
        conv = out.matches(pattern("opt_converged", "THE OPTIMIZATION HAS CONVERGED"))
        checks["opt"] = {"status": "pass" if conv else "fail",
                         "detail": f"converged in {out.opt_cycles} cycles" if conv else
                         f"not converged after {out.opt_cycles} cycles"}
        if not conv:
            fired.append("opt")
            if failure is None and cfg.get("opt_converged", "fail") == "fail":
                failure = "opt"

    is_freq = freq_expected if freq_expected is not None else kind in FREQ_KINDS
    if is_freq and cfg.get("imaginary", "fail") != "off":
        thr = float(cfg.get("imag_threshold", -30.0))
        n = out.imaginary_count(thr)
        if n is None:
            checks["imaginary"] = {"status": "fail", "detail": "no frequencies found"}
            if failure is None:
                failure = "crash"
        else:
            bad = n > 0
            checks["imaginary"] = {"status": ("fail" if cfg.get("imaginary") == "fail" else "warn") if bad else "pass",
                                   "detail": f"{n} imaginary frequencies below {thr:g} cm-1",
                                   "count": n, "lowest": out.lowest_frequency}
            if bad:
                fired.append("imaginary")
                if failure is None and cfg.get("imaginary", "fail") == "fail":
                    failure = "imag"

    if cfg.get("s2", "warn") != "off" and cfg.get("s2_max_dev") not in (None, ""):
        s2 = out.s2
        if s2 and s2.get("deviation") is not None:
            bad = abs(s2["deviation"]) > float(cfg["s2_max_dev"])
            checks["s2"] = {"status": ("fail" if cfg.get("s2") == "fail" else "warn") if bad else "pass",
                            "detail": f"<S²> = {s2['s2']:.4f} (deviation {s2['deviation']:.4f})"}
            if bad:
                fired.append("s2")
                if failure is None and cfg.get("s2") == "fail":
                    failure = "s2"

    for k, v in checks.items():
        if v["status"] == "fail" and k not in fired:
            fired.append(k)
    summary = "; ".join(f"{k}: {v['detail']}" for k, v in checks.items() if v["status"] != "pass") or "all checks passed"
    return {"ok": failure is None, "failure": failure, "checks": checks, "fired": fired, "summary": summary}


def last_geometry_file(step_dir: Path, base: str) -> Path | None:
    """Latest geometry ORCA wrote in a step folder: trajectory last frame, then {base}.xyz."""
    for name in (f"{base}.xyz",):
        p = step_dir / name
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def uses_keyword(out_or_inp_text: str, word: str) -> bool:
    return re.search(rf"(?im)^\s*!.*\b{re.escape(word)}\b", out_or_inp_text) is not None
