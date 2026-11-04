# ORCA Studio: how to use it

ORCA Studio runs on your Ubuntu workstation and you use it in a web browser. It replaces the
`run_orca_batch.py` script: you drop in structures, pick a calculation recipe, and it runs every
molecule through every step, then collects the results into tables, spectra and pictures.

You never need to edit Python code. Everything chemistry-related (keywords, basis sets, solvents,
column definitions, recipes) lives in lists you edit in the app, stored as plain YAML files in
`~/dft_projects/.studio/`.

---

## 1. Install (once)

Copy the `orca-studio` folder onto the workstation (for example to `~/orca-studio`), then in a
terminal:

```bash
cd ~/orca-studio
./install_service.sh
```

This creates a private Python environment in `orca-studio/.venv`, installs what the app needs,
and sets ORCA Studio up as a background service that starts by itself when the computer boots and
keeps running when you log out. At the end it prints the address to open.

If it says `sudo apt install python3-venv`, run that command and then `./install_service.sh` again.
If it says it could not enable lingering, run `sudo loginctl enable-linger $USER` once.

## 2. Open it

Open **http://localhost:8080** in a browser on the workstation. This works through RustDesk or
AweSun too: open the browser on the workstation's desktop, and drag files from your own computer
into the page.

To open it from another computer on your network, see "Network access" below.

## 3. Start, stop, status, logs

| What | Command |
|---|---|
| Is it running? | `systemctl --user status orca-studio` |
| Stop the web app | `systemctl --user stop orca-studio` |
| Start it | `systemctl --user start orca-studio` |
| Restart (after changing access mode or port) | `systemctl --user restart orca-studio` |
| Show the last log lines | `journalctl --user -u orca-studio -n 50` |
| Follow the log live | `journalctl --user -u orca-studio -f` |

Stopping or restarting the web app does **not** kill running ORCA jobs. When it starts again it
finds them, keeps watching them, and judges any that finished in the meantime. Jobs that died while
it was stopped are put back in the queue.

Without the service you can also run it in a terminal: `./run.sh` (Ctrl+C stops it).

## 4. First-time setup in the app

1. **Settings**: check the ORCA path (`/home/utopia/orca_6_0_1/orca`) and set the
   **OpenMPI bin folder** (press **Auto-detect** to search for it). Press **Test** next to each.
2. Press **Run test job**: a 2-core H₂ calculation confirms ORCA and MPI work together.
3. Open **ORCA checks** (button on the Settings page) and press **Run all checks**. This takes a few
   minutes and confirms ORCA 6.0.1 syntax that the specification marked [VERIFY] (xtb keywords, the
   optimization-converged message, `%freq` options, ΔSCF, `orca_plot` menus and more). It fixes the
   library entries itself and lists every change. Until it has run, those entries show an
   "unverified" badge.
4. Set **Total cores** and **Total memory** for all jobs combined (default: all cores minus 2).

## 5. Run a batch

1. **Batches → + New batch**: give it a name, choose a calculation profile (for example
   "Pre-opt → Opt + Freq (B3LYP D3BJ def2-SVP)"), and press **Create**.
2. **Drag your `.xyz` / `.inp` files** (or a folder or a .zip) onto the dashed box. They are copied
   into the batch folder; your originals are never changed.
   - In `.xyz` files, write `charge=1 mult=2` in the comment (second) line to set charge and
     multiplicity. Without it the defaults (0, 1) are used and a ⚠ is shown.
   - From `.inp` files only the coordinate block and its charge/multiplicity are kept.
3. Check charges and multiplicities in the table (you can edit them), then press **Validate**.
   It checks electron count against multiplicity, basis-set coverage of every element, conflicting
   keywords and missing programs.
4. Press **Run**. Every molecule runs step 1 (several at once, within the core budget); step 2 starts
   when all molecules have finished step 1, and so on.
5. Watch progress in the table (click a status for details, `.out` and `.inp` files) or on the
   **Queue** page. The bell at the top shows notifications (batch finished, failures, waiting for
   review).

Buttons: **Pause** (running jobs finish, nothing new starts), **Resume**, **Cancel** (asks first,
then kills running jobs), **Retry failed**, **Continue** (after a "pause for review" step).

Files land in `{calculations root}/{batch}/{molecule}/{01_step}/` with `{molecule}.inp`,
`{molecule}.out` and `input.xyz`. Each step starts from the optimized geometry of the step before.
`batch_log.txt` in the batch folder records everything.

## 6. Calculation profiles

**Calculation profiles → + New profile** opens a table: one row per step, one column per setting.
New profiles show Step, Method and Basis; **+ Add column** adds any other setting (dispersion,
solvent, TDDFT roots, …) or a new column you define. Cells:

- **Inherit** takes the value from the *Profile defaults* row.
- **— blank —** writes nothing (ORCA's own default).
- Grey striped cells do not apply to that step type.
- **Add custom…** at the end of every dropdown adds a new entry to the list.

Click a step's name to see its details below the table: extra keywords and blocks, workflow
options (wait for all / pause for review, retries, files to keep, time limit…), success checks,
and the **input preview**, which is exactly the file that will be written. **Edit final input**
lets you hand-edit the whole input for one step (clearly marked in the table).

Saving creates a new version; batches keep the version they ran with.

## 7. Network access (optional)

Settings → Access → "Local network, with password", set a password, save, then
`systemctl --user restart orca-studio`. Others on the network open `http://<workstation-ip>:8080`
and log in. Requests from the workstation itself never need the password.

## 8. Backup

Settings → **Export settings, libraries and profiles (zip)**. Import the zip on another machine
or after a reinstall. Calculation folders and the job database (`studio.db`) are separate; copy the
`~/dft_projects` folder to back up everything.

## 9. Uninstall

`./uninstall_service.sh` removes the service. Your data stays where it is.
