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
