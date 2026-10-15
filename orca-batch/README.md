# ORCA batch runner

`run_orca_batch.py` runs ORCA 6.0.1 on every subfolder of the current directory, keeping
`MAX_PARALLEL_JOBS` folders running at once. It needs Python 3.8+ and uses only the
standard library. The settings are at the top of the script: `ORCA_CMD`, `MAX_PARALLEL_JOBS`,
`INPUT_HEADER`, `DEFAULT_CHARGE` and `DEFAULT_MULT`.

## Layout it expects

```
jobs/                     <- run the script from here
├── mol 1/water.xyz       <- no .inp: water.inp is built, water.xyz moves to backup/
├── benzene/benzene.inp   <- has .inp: lines above "* xyz" are replaced by INPUT_HEADER
└── batch_log.txt         <- written by the script (summaries are appended)
```

* In an `.xyz` comment line, `charge=1 mult=2` sets the charge and multiplicity. If the
  line doesn't have them, the defaults are used and the script prints a warning.
* Before an `.inp` is rewritten for the first time, the original is copied to `backup/`.
* Folders with more than one `.inp` (or more than one `.xyz` and no `.inp`) are skipped
  with a warning. Hidden folders and `__pycache__` are ignored.
* A folder whose `.out` already contains `ORCA TERMINATED NORMALLY` is skipped, so it is
  safe to rerun the script after a crash or a Ctrl+C. To force a rerun, delete that `.out`.
* Everything above the coordinate block is replaced, including per-molecule blocks such as
  `%geom Constraints`. Anything you need in every job must go into `INPUT_HEADER`.

## Run

```bash
cd /path/to/jobs
python3 /path/to/run_orca_batch.py --dry-run   # preview: changes nothing
python3 /path/to/run_orca_batch.py             # run all folders
```

For long batches, run it in `tmux`/`screen`, or detach it:

```bash
nohup python3 /path/to/run_orca_batch.py > batch_console.txt 2>&1 &
tail -f batch_console.txt
kill <python PID>        # same clean stop as Ctrl+C
```

Ctrl+C (or `kill <PID>`) sends SIGTERM to every running ORCA, `mpirun` and MPI rank, and then
SIGKILL to whatever is still alive 15 s later. A second Ctrl+C kills them at once. Jobs
that haven't started stay untouched and run on the next invocation.

For `! PAL4`, ORCA needs the matching OpenMPI (4.1.x for ORCA 6.0.1) on `PATH` and
`LD_LIBRARY_PATH`. The script warns at startup if `mpirun` is not found.

## Test on one folder first

1. Preview everything without changing anything:
   `python3 run_orca_batch.py --dry-run`
2. Run a single small molecule. Use either of these:
   * Pass the folder name: `python3 run_orca_batch.py "mol 1"`
   * Copy one folder into an empty test directory and run the script there:
     ```bash
     mkdir ~/orca_test && cp -r "/path/to/jobs/mol 1" ~/orca_test/
     cd ~/orca_test && python3 /path/to/run_orca_batch.py
     ```
3. Check the results:
   * `[DONE]` is printed.
   * `<name>.out` ends with `ORCA TERMINATED NORMALLY`.
   * The generated `<name>.inp` has the header you expect, plus the right charge and
     multiplicity.
   * While the job runs, `top` shows 4 `orca_*_mpi` processes.
4. Optionally, start the one-folder run again and press Ctrl+C after a few seconds. Then
   `pgrep -fa orca` should show nothing.

---

# ORCA pipeline (`orca_pipeline.py`)

`orca_pipeline.py` runs a multi-part workflow over the **numbered** subfolders (`1/`, `7/`, …)
of the folder it is run from. Copy it into that root folder. The switches at the top turn
each part on or off:

| Switch | Part | Status |
| --- | --- | --- |
| `RUN_PART_1` | Single point, `SP_data` table, `orca_plot` cubes, `mep.py` hook | implemented |
| `RUN_PART_2` | TDDFT | placeholder |
| `RUN_PART_3` | deltaSCF | placeholder |
| `RUN_PART_4` | SP cation/anion | placeholder |

## Part 1 steps

1. **Single points:** for each folder `n`, the script creates `n/SP-n/`, copies the folder's
   `.xyz` file into it, writes `<name>.inp` (from `SP_HEADER_TEMPLATE`) and runs ORCA.
   * **Which `.xyz`:** after an optimisation, the folder holds `<name>.inp` and ORCA's
     optimised `<name>.xyz`, so that one is used. Otherwise the folder must contain exactly
     one `.xyz`. `*_trj.xyz` is ignored.
   * **Charge and multiplicity:** taken from the folder's `.inp` (`* xyz 0 1`), else from
     `charge=X mult=Y` in the `.xyz` comment line, else from the defaults (with a warning).
   * **Unfinished optimisation:** a folder whose own `.out` lacks `ORCA TERMINATED NORMALLY`
     is skipped (see `SKIP_IF_OPT_UNFINISHED`).
2. **`SP_data`:** written to the root folder only after every SP has finished. It is
   tab-separated and has one row per folder with these columns:
   * folder number and base name
   * final single-point energy (Eh)
   * the orbitals listed in `SP_ORBITALS` (eV, last column of ORCA's orbital table)
   * dipole X, Y and Z (a.u. × 2.541746 = Debye) and the total dipole (Debye, as printed
     by ORCA)

   Values that are missing show as `NA`. HOMO is the last orbital with occupation > 0
   (2.0000 for closed shells); LUMO is the first with 0.0000. For open shells, the
   spin-up set is used.
3. **`orca_plot`:** runs `orca_plot <name>.gbw -i` in each `SP-n` and types the keys in
   `ORCA_PLOT_KEYS`: the HOMO cube, the LUMO cube, then the electron density, then exit.
   Output goes to `orca_plot.log`. If your orca_plot menu numbers differ, edit that list.
4. **`mep.py`:** once all plots are done, `mep.py` (from the root folder) is copied into
   each `SP-n` and run there. Output goes to `mep.log`. If `mep.py` is missing, this step
   is skipped with a note.

## Reruns and logs

Every step is safe to rerun:
* A finished SP is skipped.
* A folder is plotted again only if its `.gbw` or the key list changed.
* `mep.py` runs again only if `mep.py` or the plots changed.

Each step's summary is appended to `pipeline_log.txt`. Ctrl+C or `kill <PID>` stops
everything cleanly; rerun the script to continue where it stopped.

## Test on one folder first

```bash
cd /path/to/root                 # contains 1/, 2/, 7/, ..., mep.py and orca_pipeline.py
python3 orca_pipeline.py 7       # only folder 7; SP_data keeps the other folders' rows
```

Then check:
* `7/SP-7/<name>.inp` has the right header, charge and multiplicity.
* `<name>.out` ends with `ORCA TERMINATED NORMALLY`.
* The `SP_data` row matches the values in the `.out`.
* `orca_plot.log` shows the menu accepting each key, and three `.cube` files exist.
* `mep.log` looks right.
