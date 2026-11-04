# ORCA Studio: build progress

Spec: `ORCA_Studio_SPEC.md` v1.0. This file is updated after every phase and major step.

## Environment where this was built (2026-11-04)

- Built in a cloud container, **not** on the workstation: no ORCA, no OpenMPI, no xtb, no Multiwfn here.
- 4 cores, 16 GB RAM, Ubuntu 24.04, Python 3.13 (code kept compatible with Python 3.10+).
- So every engine test here runs against `tests/fake_bin/orca`, a stand-in that writes ORCA 6-style
  output. The real checks (Appendix D) are packaged as **Settings → ORCA checks** (`orca_studio/verify.py`),
  to run once on the workstation.

## Status

| Phase | State | Acceptance test |
|---|---|---|
| 1 Core runner | done | passed with stand-in ORCA (tests/test_runner.py, tests/test_restart.py) |
| 2 Extraction | not started | |
| 3 Robustness | not started | |
| 4 Visuals | not started | |
| 5 Advanced | not started | |

## Log

- Machine check done; vendored 3Dmol.js 2.4.2, Plotly.js 2.35.2, xterm.js 5.5.0 (+ fit addon) from npm.

- Phase 1 built: settings (programs, tests, auto-detect, test job, backup), YAML libraries with all
  Appendix A/B starters, column library, calculation profile editor (columns, inherit/blank, preview,
  manual override, versions, step templates), validation, batches (drag and drop, .xyz/.inp/.zip),
  scheduler (stage-by-stage, core + memory budget, round-robin, pause/resume/cancel/retry), success
  checks, restart recovery (re-attach / judge / requeue), systemd user service, HOW_TO_USE.md.
- ORCA checks runner (Appendix D, all 9 checks) in Settings → ORCA checks; updates libraries itself.
- Tested: pytest tests/test_runner.py tests/test_restart.py tests/test_verify.py (all pass);
  Playwright walk through Settings, Libraries, Profiles, new batch, upload, validate: no JS errors.

## Open problems

- All [VERIFY] items are unconfirmed until `ORCA checks` runs on the workstation.
- Real acceptance run (water, methanol, formaldehyde with real ORCA 6.0.1, 2 cores) still has to be
  done on the workstation; here it ran with the stand-in.
- install_service.sh could not be tested here (no systemd user session in the container).
- cclib is not used: it could not be tested against ORCA 6.0.1 output here.
