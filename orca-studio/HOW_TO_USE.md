# ORCA Studio: how to use it

ORCA Studio runs on your Ubuntu workstation and you use it in a web browser. It replaces the
`run_orca_batch.py` script: you drop in structures, pick a calculation recipe, and it runs every
molecule through every step, then collects the results into tables, spectra and pictures.

You never need to edit Python code. Everything chemistry-related (keywords, basis sets, solvents,
column definitions, recipes) lives in lists you edit in the app, stored as plain YAML files in
`~/dft_projects/.studio/`.

---

## 1. Install (once)

Get the code onto the workstation (it is in the `orca-studio` folder of your GitHub repository),
then run the installer:

```bash
cd ~
git clone -b claude/compassionate-brahmagupta-wptsmq https://github.com/ahmed2271/endless-.git orca-studio-repo
```

```bash
cd ~/orca-studio-repo/orca-studio
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

To delete a batch, use **Delete…** in the Batches list (or the *Batch settings* tab): remove it from
the list only, or delete its folder too (asks for confirmation). Single files and step folders can be
deleted from the *Files* tab.

Buttons: **Pause** (running jobs finish, nothing new starts), **Resume**, **Cancel** (asks first,
then kills running jobs), **Retry failed**, **Continue** (after a "pause for review" step).

Files land in `{calculations root}/{batch}/{molecule}/{01_step}/` with `{molecule}.inp`,
`{molecule}.out` and `input.xyz`. Each step starts from the optimized geometry of the step before.
`batch_log.txt` in the batch folder records everything.

## 6. Results, spectra and pictures

Open a batch and use the tabs:

- **Results**: one row per molecule, one column per field of the extraction profile (energies,
  G, H, ZPE, imaginary frequencies, HOMO/LUMO, dipole, relative G, …). Click a header to sort, type in
  the filter box, hover a grey "n/a" to see why a value is missing. Red cells are flagged (for example
  imaginary frequencies or a non-converged optimization). Sub-tables (charges per atom, excited states,
  frequencies) are below the main table. The starter profiles compute **Hirshfeld and MBIS** charges
on the Opt + Freq step and the Standard extraction profile shows both as sub-tables; choose another
scheme (CHELPG, RESP, NPA, Mulliken, Löwdin) in a *charges* field if you need it. Buttons export **CSV**, **Excel** (one sheet per table),
  **final geometries** (zip with one .xyz per molecule plus one multi-structure .xyz), a **Supporting
  Information** text file and a **citations** list. *Save to results folder* writes CSV and Excel into
  `{batch}/results/`. Per-atom charge tables also offer `.pqr` and `.mol2` files.
- **Spectra**: UV-Vis from TDDFT states (Gaussian or Lorentzian broadening, FWHM in eV, nm or eV axis,
  sticks, Boltzmann-weighted conformer spectra, overlay of your experimental data from a two-column
  file) and IR / Raman (Lorentzian FWHM, frequency scaling). Each plot saves as PNG, SVG and CSV.
- **Visuals**: all molecules side by side with the same orientation, isovalue and colour range
  (structures, an orbital such as HOMO, or the MEP). *Make missing cubes for all* runs `orca_plot`
  for every molecule; *Save snapshots* writes one PNG per molecule and *Figure grid* one combined
  picture into `{batch}/results/snapshots/`.
- Click a molecule (**Details**) for its 3D viewer, step logs and files, and the orbital panel:
  pick HOMO−5 … LUMO+5 chips (or type a range such as `HOMO-3 to LUMO+3`), choose 80 points
  (preview) or 120 (figures), and drag the isovalue slider. Also: electron and spin density, TDDFT
  difference/transition densities, **MEP** (ESP coloured on the 0.001 a.u. density surface, with
  V_min / V_max and the nearest atom), atoms coloured by charge, and *Add CHELPG charges afterwards*.
  Cubes are made from the saved `.gbw`, so you can add orbitals later without rerunning anything.

**Extraction profiles** decide what goes into the Results tab. Every field reads **one step** of the
calculation. At the top of the extraction profile, choose the calculation profile it belongs to: its
steps then appear in each field's *Source* menu (for example *Step 2: SP* for energies and charges,
*Step 3: TDDFT* for excited states). **+ Fields for a step…** adds a ready set of fields for one step
in one go (Opt: energy, convergence; Opt + Freq: G, H, ZPE, imaginary frequencies; SP: energy, HOMO,
LUMO, gap, dipole, Hirshfeld and MBIS charges; TDDFT: S1, T1, brightest state, all states). The Results
table groups the columns under the step they come from. A ready-made pair, the calculation profile
**Opt → SP → TDDFT** and the extraction profile of the same name, shows how it fits together. Add built-in fields (Appendix C of
the specification), **custom patterns** (search text, which occurrence, which number; press
*Test on a sample .out* to see the matched line highlighted), **formulas** (`rel(G)`,
`boltzmann(G, 298.15)`, `fragsum(q, 'donor')`, `E_sp + Gcorr`, …), Fukui functions, ΔSCF values
and Multiwfn results. Choose the source step and the unit (Eh, kcal/mol, kJ/mol, eV, cm⁻¹, nm).
If a field needs something the calculation does not do (for example MBIS charges), validation tells
you and offers a button that adds it to the profile.

**Analyze a folder** (left menu) runs an extraction profile on any folder of old `.out` files.

## 7. Scripts and Multiwfn

- **Scripts → Script registry**: `mep.py` is registered already; set its path once in Settings. Any
  script can run in a step folder after the step succeeds (tick it in the step's workflow options).
- **Scripts → Record a new recipe**: pick a small finished molecule, and Multiwfn opens in a
  terminal inside the page. Click through the menus as usual; the app records every answer. Then
  click the output lines that hold your results (a number or a table) to turn them into result
  fields, give the recipe a name and save it. Use the results in an extraction profile with
  *+ Multiwfn result*. After updating Multiwfn, press *Re-test all recipes*: menu numbers can change
  between versions and the re-test shows exactly what changed. Settings → Multiwfn threads sets
  the thread count (the app copies Multiwfn's settings.ini into the work folder with that value).

## 8. Calculation profiles

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

**Save** stores your changes in the profile. **Save as new version** keeps the current version
unchanged and stores the changes as the next version (choose older versions in the menu at the top
right). Either way, batches are never affected: each batch keeps its own copy of the profile it ran
with. **Delete** (in the editor or the profile list) removes a profile; the file goes to the `.trash`
folder in the profiles folder, and deleted starter profiles do not come back.

Useful workflow options per step: **pause for review** (the batch waits for *Continue*), **run only
if a check fired** (for example re-optimize only molecules with an imaginary frequency), **retry on
SCF failure** (SlowConv, then KDIIS + SOSCF, …; the strategies are a library list), **restart
unconverged optimizations**, **fix imaginary frequencies** (displace along the mode and re-optimize),
**time limit**, **files to keep** and **orbital cubes / MEP after success**. **Save as template**
stores a configured step for reuse; *Update from template* pulls later template changes on request.

For Fukui functions, make three single-point steps on the same geometry and set the *Charge change*
column to 0, −1 (N+1 electrons) and +1 (N−1 electrons); multiplicity follows automatically unless
you set *Multiplicity override*. ΔSCF is a step type that runs ground state, excited state and
(optionally) triplet sub-jobs.

## 9. Network access (optional)

Settings → Access → "Local network, with password", set a password, save, then
`systemctl --user restart orca-studio`. Others on the network open `http://<workstation-ip>:8080`
and log in. Requests from the workstation itself never need the password.

## 10. Backup

Settings → **Export settings, libraries and profiles (zip)**. Import the zip on another machine
or after a reinstall. Calculation folders and the job database (`studio.db`) are separate; copy the
`~/dft_projects` folder to back up everything.

## 11. Uninstall

`./uninstall_service.sh` removes the service. Your data stays where it is.

## 12. Checking the parsers with your own outputs

After the first real batch, copy its outputs into the test folder and run the parser tests:

```bash
cd ~/orca-studio-repo/orca-studio
.venv/bin/python tests/collect_real_outputs.py ~/dft_projects/<batch name>
```

```bash
.venv/bin/python -m pip install pytest httpx
```

```bash
.venv/bin/python -m pytest tests/test_parsers.py
```
