# ORCA Studio

A web app for running ORCA 6 batches on a workstation and analysing the results. It replaces
`orca-batch/run_orca_batch.py`. **Start with [HOW_TO_USE.md](HOW_TO_USE.md)**; build status and open items
are in [PROGRESS.md](PROGRESS.md).

## Layout

```
orca-studio/
├── install_service.sh / uninstall_service.sh   systemd user service (keeps running after logout)
├── run.sh                                      run in the foreground instead
├── orca_studio/
│   ├── defaults/          starter YAML: libraries, columns, calculation/extraction profiles, scripts
│   ├── main.py            FastAPI app (+ api_results.py, api_visuals.py, api_advanced.py)
│   ├── runner.py          scheduler, job threads, retries, restart recovery
│   ├── assemble.py        input assembly (all ORCA text comes from the YAML libraries)
│   ├── validate.py        checks before a batch runs
│   ├── parsers/           ORCA 6 .out parser, property file, .hess, cube files
│   ├── extraction.py      built-in fields, patterns, formulas, units, flags
│   ├── exports.py         CSV, Excel, geometries, SI, .pqr/.mol2
│   ├── visuals.py         orca_plot cubes, MEP and surface extrema
│   ├── scripts_reg.py     script registry (mep.py, …)
│   ├── multiwfn.py        Multiwfn recipes, record mode, re-test, citations
│   ├── verify.py          ORCA checks for the [VERIFY] items of the specification
│   └── static/            plain HTML/CSS/JS frontend; vendor/ holds 3Dmol.js, Plotly.js, xterm.js
└── tests/                 pytest suite; fake_bin/ holds stand-ins for ORCA, orca_plot, Multiwfn, …
```

User data lives outside the code: profiles, libraries, `settings.yaml` and `studio.db` in
`~/dft_projects/.studio/` (configurable), calculations in `~/dft_projects/<batch>/`.

## Tests

```bash
python3 -m pip install -r requirements.txt pytest httpx
```

```bash
python3 -m pytest tests
```

The tests run against `tests/fake_bin/orca`, a stand-in that writes ORCA-6-style output, so they work
without ORCA. Real ORCA outputs copied into `tests/data/real/` (see `tests/collect_real_outputs.py`)
are checked as well.
