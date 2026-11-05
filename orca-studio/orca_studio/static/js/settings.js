// Settings page (section 4)
"use strict";

App.register("settings", async (main) => {
  const data = await App.get("/api/settings");
  const s = data.settings;
  main.append(h("h1", null, "Settings"));

  const field = (obj, key, attrs = {}) => {
    const inp = h("input", Object.assign({value: obj[key] ?? ""}, attrs));
    inp.addEventListener("input", () => { obj[key] = attrs.type === "number" ? (inp.value === "" ? "" : +inp.value) : inp.value; });
    return inp;
  };
  const testBtn = (key) => {
    const out = h("span", {class: "small muted"});
    const b = h("button", {class: "small", onclick: async () => {
      await save(true);
      out.textContent = "testing…";
      const r = await App.post("/api/settings/test", {key});
      out.textContent = (r.ok ? "✔ " : "✘ ") + r.message;
      out.style.color = r.ok ? "var(--ok)" : "var(--err)";
    }}, "Test");
    return h("span", {class: "row"}, b, out);
  };

  // ---------------------------------------------------------------- programs
  const P = s.programs;
  const progs = h("div", {class: "form-grid"});
  const progRow = (label, key, note, obj = P, testKey = key, wide = true) => {
    progs.append(h("div", {class: "lbl"}, label), field(obj, key, {style: {width: "100%"}, placeholder: "not set"}), testBtn(testKey));
    if (note) progs.append(h("div", {class: "note"}, note));
  };
  progRow("ORCA executable", "orca", "Full path; ORCA is always called by its full path (needed for MPI runs).");
  progRow("OpenMPI bin folder", "openmpi_bin", "Optional: found automatically at start-up (the mpirun your terminal uses). ORCA itself picks mpirun from PATH; the app runs as a background service that does not read .bashrc, so it puts this folder on PATH for every job. ORCA 6.0.1 is built for OpenMPI 4.1.x.");
  progs.append(h("div", {class: "lbl"}, "OpenMPI lib folder"), field(P, "openmpi_lib", {placeholder: `derived: ${data.derived.openmpi_lib || "(bin/../lib)"}`, style: {width: "100%"}}), h("span"));
  progRow("Python for scripts", "python");
  progRow("mep.py script", "mep", "Your MEP script (section 11). Scripts are referenced by name, so moving it needs only this path.", s.script_paths, "script:mep");
  progRow("xtb", "xtb", "Optional. Empty = ORCA uses its own otool_xtb if present. [VERIFY with ORCA checks]");
  progRow("Multiwfn", "multiwfn", "Optional.");
  progs.append(h("div", {class: "lbl"}, "Multiwfn threads"), field(P, "multiwfn_threads", {type: "number", min: 1, style: {width: "90px"}}), h("span"));
  progRow("NBO", "nbo", "Optional; licensed separately. Exported to ORCA as NBOEXE.");
  for (const u of ["orca_2mkl", "orca_plot", "orca_vpot", "orca_chelpg", "orca_pltvib"]) {
    progs.append(h("div", {class: "lbl muted"}, u), field(P, u, {placeholder: "derived: " + data.derived[u], style: {width: "100%"}}), testBtn(u));
  }

  const autodet = h("div");
  const testOut = h("div");
  main.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Programs and scripts"),
    h("p", {class: "help"}, "Optional tools left empty hide the features that need them."),
    progs,
    h("div", {class: "row", style: {marginTop: "12px"}},
      h("button", {onclick: async (e) => {
        e.target.disabled = true; autodet.innerHTML = "Searching $HOME, /opt, /usr/local and PATH…";
        const r = await App.post("/api/settings/autodetect"); e.target.disabled = false;
        autodet.innerHTML = "";
        const map = {orca: [P, "orca"], openmpi_bin: [P, "openmpi_bin"], xtb: [P, "xtb"], multiwfn: [P, "multiwfn"], nbo: [P, "nbo"], mep: [s.script_paths, "mep"]};
        for (const [k, paths] of Object.entries(r)) {
          if (!paths.length) { autodet.append(h("div", {class: "small muted"}, `${k}: nothing found`)); continue; }
          autodet.append(h("div", {class: "row small"}, h("b", null, k + ":"), ...paths.map(p => h("button", {class: "small", onclick: () => {
            map[k][0][map[k][1]] = p; App.route(); save(true);
          }}, "use " + p))));
        }
      }}, "Auto-detect"),
      h("button", {onclick: async (e) => {
        await save(true);
        e.target.disabled = true; testOut.innerHTML = ""; testOut.append(h("div", {class: "msg info"}, "Running H₂ HF/def2-SVP with 2 cores…"));
        const r = await App.post("/api/settings/testjob"); e.target.disabled = false;
        testOut.innerHTML = ""; testOut.append(h("div", {class: "msg " + (r.ok ? "ok" : "error")}, h("pre", {style: {background: "none", border: 0, padding: 0}}, r.message)));
      }}, "Run test job"),
      h("a", {class: "btn", href: "#/settings/checks"}, "ORCA checks (Appendix D)…")),
    autodet, testOut));

  // ---------------------------------------------------------------- folders
  const F = s.folders;
  const fg = h("div", {class: "form-grid"});
  const frow = (label, key, note, attrs = {}) => { fg.append(h("div", {class: "lbl"}, label), field(F, key, Object.assign({style: {width: "100%"}}, attrs)), h("span")); if (note) fg.append(h("div", {class: "note"}, note)); };
  frow("Calculations root", "calculations_root", "Default folder for new batches. Each batch stores its own path, so changing this never breaks old batches.");
  frow("Folder layout", "layout", "Placeholders: {batch} {molecule} {step_no:02d} {step_slug}");
  frow("Scratch folder", "scratch", "Optional. If set, jobs run there and results are copied back.");
  fg.append(h("div", {class: "lbl"}, "Exports go to"), W.select([{value: "batch", label: "Inside each batch (results/)"}, {value: "central", label: "One central folder"}], F.exports_mode, v => F.exports_mode = v), h("span"));
  frow("Central export folder", "exports_central");
  frow("Export file name", "export_pattern", "Placeholders: {batch} {profile} {date}");
  fg.append(h("div", {class: "lbl"}, "CSV separator"), W.select([{value: ",", label: "comma ,"}, {value: ";", label: "semicolon ;"}], F.csv_separator, v => F.csv_separator = v), h("span"));
  frow("Decimal places", "decimals", null, {type: "number", min: 0, max: 12, style: {width: "90px"}});
  main.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Folders"), fg));

  // ---------------------------------------------------------------- resources
  const R = s.resources;
  const rg = h("div", {class: "form-grid"});
  rg.append(h("div", {class: "lbl"}, "Total cores for all jobs"), field(R, "total_cores", {type: "number", min: 1, style: {width: "90px"}}), h("span"),
    h("div", {class: "note"}, `This computer has ${data.detected_cores} cores. Default: detected minus 2.`),
    h("div", {class: "lbl"}, "Total memory for all jobs (MB)"), field(R, "total_memory_mb", {type: "number", min: 256, style: {width: "120px"}}), h("span"),
    h("div", {class: "note"}, `This computer has ${data.detected_memory_mb} MB. A job uses cores × %maxcore.`),
    h("div", {class: "lbl"}, "Job priority (nice)"), field(R, "nice", {type: "number", min: 0, max: 19, style: {width: "90px"}}), h("span"),
    h("div", {class: "note"}, "10 keeps the PC usable while jobs run. 0 = normal priority."),
    h("div", {class: "lbl"}, "Default cores per job"), field(R, "default_nprocs", {type: "number", min: 1, style: {width: "90px"}}), h("span"),
    h("div", {class: "lbl"}, "Default memory per core (MB)"), field(R, "default_maxcore", {type: "number", min: 100, style: {width: "120px"}}), h("span"));
  main.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Resources"), rg));

  // ---------------------------------------------------------------- access + notifications
  const A = s.access;
  const pw = h("input", {type: "password", placeholder: A.password_set ? "(unchanged)" : "set a password", autocomplete: "new-password"});
  const ag = h("div", {class: "form-grid"});
  ag.append(h("div", {class: "lbl"}, "Who can open the app"), W.select([{value: "local", label: "This computer only (safe default)"}, {value: "lan", label: "Local network, with password"}], A.mode, v => A.mode = v), h("span"),
    h("div", {class: "lbl"}, "Port"), field(A, "port", {type: "number", style: {width: "100px"}}), h("span"),
    h("div", {class: "lbl"}, "Password (LAN mode)"), pw, h("span"),
    h("div", {class: "note"}, "Access mode and port take effect after a service restart (see HOW_TO_USE.md)."));
  const N = s.notifications;
  ag.append(h("div", {class: "lbl"}, "Notification command"), field(N, "command", {style: {width: "100%"}, placeholder: 'e.g. notify-send "ORCA Studio" "{text}"'}), h("span"),
    h("div", {class: "note"}, "Optional program run when a batch finishes, fails or waits for review. {text} is replaced by the message."));
  main.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Access and notifications"), ag));

  // ---------------------------------------------------------------- defaults + backup
  const D = s.defaults;
  const dg = h("div", {class: "form-grid"});
  dg.append(h("div", {class: "lbl"}, "Default charge"), field(D, "charge", {type: "number", style: {width: "90px"}}), h("span"),
    h("div", {class: "lbl"}, "Default multiplicity"), field(D, "mult", {type: "number", min: 1, style: {width: "90px"}}), h("span"),
    h("div", {class: "note"}, "Used for .xyz files whose comment line has no charge=X mult=Y."));
  main.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Molecule defaults"), dg));

  const restore = h("input", {type: "file", accept: ".zip", class: "hidden", onchange: async () => {
    if (!restore.files.length) return;
    if (!await App.confirm("Import backup", "Settings, libraries and profiles in the zip replace the current ones (current files are kept in .trash).", "Import")) return;
    const fd = new FormData(); fd.append("file", restore.files[0]);
    const r = await App.api("POST", "/api/settings/restore", fd);
    App.toast(`Imported ${r.files.length} files`); App.route();
  }});
  main.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Backup and storage"),
    h("p", {class: "help"}, "Profiles and libraries folder: ", h("span", {class: "mono"}, data.studio_dir)),
    h("div", {class: "row"},
      h("a", {class: "btn", href: "/api/settings/backup"}, "Export settings, libraries and profiles (zip)"),
      h("button", {onclick: () => restore.click()}, "Import from zip…"), restore,
      h("button", {onclick: async () => {
        const p = await App.prompt("Profiles and libraries folder", "New folder (restart the service afterwards)", data.studio_dir);
        if (!p) return; const r = await App.post("/api/settings/studio_dir", {path: p}); App.toast(r.note);
      }}, "Change folder…"))));

  async function save(quiet) {
    const body = clone(s);
    if (pw.value) body.access.new_password = pw.value;
    const r = await App.put("/api/settings", {settings: body});
    if (!quiet) App.toast(r.restart_needed ? "Saved. Restart the service for access/port changes." : "Settings saved");
  }
  main.append(h("div", {class: "sticky-actions"}, h("button", {class: "primary", onclick: () => save(false)}, "Save settings")));
});

// ORCA checks page (Appendix D)
const _settingsRoute = App.pages.settings;
App.pages.settings = async (main, sub) => {
  if (sub === "checks") return App.pages.checks(main);
  return _settingsRoute(main);
};

// ORCA checks (Appendix D) ---------------------------------------------------
App.pages.checks = async (main) => {
  main.append(h("div", {class: "row"}, h("a", {href: "#/settings"}, "← Settings")),
    h("h1", null, "ORCA checks"),
    h("p", {class: "help"}, "These checks confirm ORCA 6.0.1 syntax marked [VERIFY] in the specification with tiny real runs (H₂ / water, 2 cores) on this workstation. They take a few minutes. When a check finds the correct syntax, the library entry is updated and the change is listed here; entries that cannot work are hidden. A report is saved as verify_report.md in the profiles folder."));
  const box = h("div");
  const runBtn = h("button", {class: "primary", onclick: async () => { await App.post("/api/verify/run", {}); draw(); }}, "Run all checks");
  main.append(h("div", {class: "row"}, runBtn), box);
  async function draw() {
    const st = await App.get("/api/verify");
    runBtn.disabled = st.running;
    box.innerHTML = "";
    if (st.running) box.append(h("div", {class: "msg info"}, "Running: " + st.current));
    const done = Object.fromEntries((st.results || []).map(r => [r.id, r]));
    for (const c of st.checks) {
      const r = done[c.id];
      box.append(h("div", {class: "card"}, h("div", {class: "row"}, h("b", null, c.title), h("span", {class: "spacer"}),
        r ? pill(r.status === "pass" ? "done" : r.status === "skipped" ? "skipped" : "failed") : h("span", {class: "muted small"}, "not run"),
        h("button", {class: "small", disabled: st.running, onclick: async () => { await App.post("/api/verify/run", {only: [c.id]}); draw(); }}, "Run")),
        r ? h("ul", {class: "small"}, r.details.map(d => h("li", null, d))) : null,
        r && r.changes.length ? h("div", {class: "msg ok"}, h("b", null, "Library changes: "), r.changes.join("; ")) : null));
    }
  }
  await draw();
  App.every(3000, draw);
};
