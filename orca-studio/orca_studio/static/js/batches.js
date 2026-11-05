// Batches (section 7): list, new batch, batch window with molecules, controls, log and files.
"use strict";

App.register("batches", async (main) => {
  main.append(h("div", {class: "row"}, h("h1", {style: {margin: 0}}, "Batches"), h("span", {class: "spacer"}),
    h("button", {class: "primary", onclick: () => Batch.newBatch()}, "+ New batch")));
  const wrap = h("div", {class: "card", style: {padding: 0, marginTop: "12px"}});
  main.append(wrap);
  const draw = async () => {
    const list = await App.get("/api/batches");
    wrap.innerHTML = "";
    if (!list.length) { wrap.append(h("p", {style: {padding: "16px"}}, "No batches yet. Press ", h("b", null, "+ New batch"), " to start.")); return; }
    wrap.append(h("table", null, h("tr", null, ["Batch", "Profile", "Molecules", "Progress", "Status", "Created", ""].map(x => h("th", null, x))),
      list.map(b => {
        const s = b.summary, tot = Object.values(s).reduce((a, c) => a + c, 0);
        return h("tr", {class: "clickable", onclick: () => location.hash = `#/batch/${b.id}`},
          h("td", null, h("b", null, b.name), h("div", {class: "small muted mono"}, b.folder)),
          h("td", {class: "small"}, b.kind === "external" ? "(analysed folder)" : `${b.calc_profile_id || ""} v${b.calc_profile_version || ""}`),
          h("td", null, b.molecules),
          h("td", {class: "small"}, tot ? `${s.done || 0}/${tot} done` + (s.failed ? `, ${s.failed} failed` : "") + (s.running ? `, ${s.running} running` : "") : ""),
          h("td", null, pill(b.status)), h("td", {class: "small muted"}, fmtTime(b.created)),
          h("td", null, h("button", {class: "small danger", title: "Delete batch", onclick: async e => { e.stopPropagation(); if (await Batch.deleteDialog(b)) draw(); }}, "Delete…")));
      })));
  };
  await draw();
  App.every(5000, draw);
});

App.register("batch", async (main, id, sub, arg) => {
  if (sub === "mol") return Batch.molecule(main, +id, +arg);
  return Batch.view(main, +id, sub || "molecules");
});

const Batch = {
  async newBatch() {
    const [profiles, eps, st] = await Promise.all([App.get("/api/calc_profiles"), App.get("/api/items/extraction_profiles"), App.get("/api/settings")]);
    const d = {name: "", calc_profile_id: profiles[0]?.id || "", version: null, extraction_profile_id: "", root: st.settings.folders.calculations_root};
    const name = h("input", {placeholder: "e.g. dyes_set1", style: {width: "100%"}, oninput: e => { d.name = e.target.value; path(); }});
    const verSel = h("select");
    const fillVer = async () => {
      const p = await App.get(`/api/calc_profiles/${d.calc_profile_id}`);
      verSel.innerHTML = "";
      for (const v of [...p.versions].reverse()) verSel.append(h("option", {value: v}, `version ${v}` + (v === p.version ? " (latest)" : "")));
      d.version = p.version; epSel.value = p.extraction_profile || ""; d.extraction_profile_id = epSel.value;
    };
    verSel.onchange = () => d.version = +verSel.value;
    const profSel = W.select(profiles.map(p => ({value: p.id, label: p.name})), d.calc_profile_id, v => { d.calc_profile_id = v; fillVer(); });
    const epSel = W.select([{value: "", label: "(none)"}, ...eps.map(e => ({value: e.id, label: e.name || e.id}))], "", v => d.extraction_profile_id = v);
    const root = h("input", {value: d.root, style: {width: "100%"}, oninput: e => { d.root = e.target.value; path(); }});
    const pathOut = h("div", {class: "small muted mono"});
    const path = () => pathOut.textContent = `Folder: ${d.root.replace(/\/$/, "")}/${(d.name || "…").replace(/[^A-Za-z0-9._+-]+/g, "_")}`;
    path();
    if (d.calc_profile_id) await fillVer();
    const r = await App.modal("New batch", h("div", {style: {display: "grid", gap: "10px"}},
      h("label", {class: "f"}, "Batch name", name),
      h("div", {class: "row"}, h("label", {class: "f grow"}, "Calculation profile", profSel), h("label", {class: "f"}, "Version", verSel)),
      h("label", {class: "f"}, "Extra fields across steps (optional; each step has its own extraction profile)", epSel),
      h("label", {class: "f"}, "Calculations folder", root), pathOut),
      [{label: "Cancel", value: null}, {label: "Create", class: "primary", onclick: async () => {
        if (!d.name.trim()) { App.toast("Give the batch a name", "error"); return false; }
        return App.post("/api/batches", d);
      }}]);
    if (r) location.hash = `#/batch/${r.id}`;
  },

  async view(main, id, tab) {
    let b = await App.get(`/api/batches/${id}`);
    const head = h("div");
    const ctl = h("div", {class: "row", style: {margin: "10px 0"}});
    const issues = h("div");
    const body = h("div");
    main.append(h("div", {class: "row"}, h("a", {href: "#/batches"}, "← Batches")), head, ctl, issues);
    const tabs = [["molecules", "Molecules"], ["results", "Results"], ["spectra", "Spectra"], ["visuals", "Visuals"], ["log", "Log"], ["files", "Files"], ["settings", "Batch settings"]];
    main.append(W.tabs(tabs, tab, t => { location.hash = `#/batch/${id}/${t}`; }), body);

    const drawHead = () => {
      head.innerHTML = "";
      const s = b.summary, tot = Object.values(s).reduce((a, c) => a + c, 0);
      head.append(h("div", {class: "row", style: {marginTop: "6px"}}, h("h1", {style: {margin: 0}}, b.name), pill(b.status),
        h("span", {class: "spacer"}),
        h("span", {class: "small muted"}, tot ? `${s.done || 0} done · ${s.running || 0} running · ${s.queued || 0} queued · ${s.failed || 0} failed · ${s.skipped || 0} skipped` : "")),
        h("div", {class: "small muted"}, b.kind === "external" ? "Analysed folder " : `Profile ${b.profile.name || b.calc_profile_id} (v${b.calc_profile_version}) · `,
          h("span", {class: "mono"}, b.folder)));
      if (b.status === "review") head.append(h("div", {class: "msg warning"}, "A step has finished and this batch is waiting for your review. Check the results, then press ", h("b", null, "Continue"), "."));
      if (b.status === "stopped") head.append(h("div", {class: "msg error"}, "The batch was stopped after a failure (step setting 'stop the batch'). Use Retry failed or Resume."));
    };
    const act = async (a, confirmText) => {
      if (confirmText && !await App.confirm("Please confirm", confirmText, "Yes", true)) return;
      await App.post(`/api/batches/${id}/${a}`); await refresh();
    };
    const drawCtl = () => {
      ctl.innerHTML = "";
      if (b.kind === "external") { ctl.append(h("button", {onclick: async () => { await App.post(`/api/batches/${id}/extract`); App.toast("Extraction done"); refresh(); }}, "Re-extract")); return; }
      const st = b.status;
      const B = (label, fn, cls = "") => h("button", {class: cls, onclick: fn}, label);
      ctl.append(B("Validate", validateNow));
      if (["draft", "done", "cancelled"].includes(st)) ctl.append(B(st === "draft" ? "Run" : "Run again (pending jobs)", runNow, "primary"));
      if (st === "running") ctl.append(B("Pause", () => act("pause")));
      if (["paused", "stopped"].includes(st)) ctl.append(B("Resume", () => act("resume"), "primary"));
      if (st === "review") ctl.append(B("Continue", () => act("continue"), "primary"));
      if (["running", "paused", "review", "stopped"].includes(st)) ctl.append(B("Cancel", () => act("cancel", "Cancel this batch? Running ORCA jobs will be killed. Finished results are kept."), "danger"));
      if ((b.summary.failed || 0) + (b.summary.cancelled || 0) > 0) ctl.append(B("Retry failed", () => act("retry")));
      ctl.append(h("span", {class: "spacer"}), B("Add molecules", () => { location.hash = `#/batch/${id}/molecules`; setTimeout(() => document.querySelector(".dropzone")?.scrollIntoView(), 50); }));
    };
    async function validateNow() {
      const r = await App.post(`/api/batches/${id}/validate`);
      showIssues(r);
      return r;
    }
    function showIssues(list) {
      issues.innerHTML = "";
      if (!list.length) { issues.append(h("div", {class: "msg ok"}, "Validation passed.")); return; }
      for (const i of list) issues.append(h("div", {class: "msg " + i.level}, (i.level === "error" ? "Error: " : "Warning: ") + i.message,
        i.fix && b.status === "draft" ? h("button", {class: "small", style: {marginLeft: "8px"}, onclick: async () => {
          const r = await App.post(`/api/calc_profiles/${b.calc_profile_id}/fix`, {fix: i.fix});
          await App.patch(`/api/batches/${id}`, {calc_profile_id: b.calc_profile_id, version: r.version});
          App.toast(`Added to the profile (now version ${r.version})`); refresh(); validateNow();
        }}, i.fix.label || "Fix") : null));
    }
    async function runNow() {
      const r = await App.api("POST", `/api/batches/${id}/run`, {}, {allowError: true});
      if (r.ok) { App.toast("Batch started"); issues.innerHTML = ""; return refresh(); }
      if (r.status === 409) {
        showIssues(r.data.issues);
        if (await App.confirm("Validation errors", "Validation found errors (listed on the page). Run anyway?", "Run anyway", true)) {
          await App.post(`/api/batches/${id}/run`, {force: true}); refresh();
        }
      } else App.toast(r.data.detail || "Could not start", "error");
    }
    async function refresh() {
      b = await App.get(`/api/batches/${id}`);
      drawHead(); drawCtl();
      if (tab === "molecules") Batch.molecules(body, b, refresh);
    }
    drawHead(); drawCtl();
    if (tab === "molecules") { Batch.molecules(body, b, refresh); App.every(3000, () => { if (!document.querySelector(".modal-bg") && !document.activeElement?.closest?.("table")) refresh(); }); }
    else if (tab === "log") Batch.log(body, b);
    else if (tab === "files") Batch.files(body, b.folder);
    else if (tab === "settings") Batch.settings(body, b);
    else if (typeof Results !== "undefined") Results.tab(body, b, tab);
  },

  molecules(root, b, refresh) {
    root.innerHTML = "";
    const steps = b.steps;
    const upload = async files => {
      const fd = new FormData(); for (const f of files) fd.append("files", f, f.name);
      const r = await App.api("POST", `/api/batches/${b.id}/upload`, fd);
      const bad = r.filter(x => !x.ok), warn = r.filter(x => x.ok && x.warnings?.length);
      App.toast(`${r.filter(x => x.ok).length} molecule(s) added` + (bad.length ? `, ${bad.length} rejected` : ""));
      for (const x of bad) App.toast(`${x.file}: ${x.error}`, "error");
      if (warn.length) App.toast(`${warn.length} file(s) without charge=/mult= in the comment line: defaults used (see ⚠)`);
      refresh();
    };
    const tbl = h("table", {class: "step-matrix"});
    tbl.append(h("tr", null, h("th", null, "#"), h("th", null, "Name"), h("th", null, "Formula"), h("th", null, "Charge"), h("th", null, "Mult"),
      steps.map((s, k) => h("th", {class: "st"}, `${k + 1}. ${s.name}`)), h("th", null, "")));
    const editable = b.status === "draft";
    b.molecules.forEach((m, i) => {
      const startedAny = m.tasks.some(t => t && !["pending", "queued"].includes(t.status));
      const numInp = (k) => h("input", {type: "number", value: m[k], style: {width: "64px"}, disabled: startedAny, onchange: async e => {
        await App.patch(`/api/molecules/${m.id}`, {[k]: +e.target.value}); refresh();
      }});
      tbl.append(h("tr", null,
        h("td", {class: "muted"}, i + 1),
        h("td", null, h("input", {value: m.name, style: {width: "150px"}, onchange: async e => { await App.patch(`/api/molecules/${m.id}`, {name: e.target.value}); }}),
          m.warnings.length ? h("span", {title: m.warnings.join("\n"), style: {marginLeft: "4px", cursor: "help"}}, "⚠") : null),
        h("td", {class: "mono"}, m.formula),
        h("td", null, numInp("charge")), h("td", null, numInp("mult")),
        m.tasks.map((t, k) => h("td", {class: "st"}, t ? h("a", {href: `#/batch/${b.id}/mol/${m.id}`, title: t.message || ""}, pill(t.status)) : h("span", {class: "muted small"}, editable ? "–" : "pending"))),
        h("td", null, h("span", {class: "row", style: {flexWrap: "nowrap"}},
          h("button", {class: "small", onclick: () => Viewer.popup(m)}, "3D"),
          h("a", {class: "btn small", href: `#/batch/${b.id}/mol/${m.id}`}, "Details"),
          !startedAny ? h("button", {class: "small danger", title: "Remove from batch (files stay on disk)", onclick: async () => { if (await App.confirm("Remove molecule", `Remove ${m.name} from this batch? Its files stay on disk.`, "Remove", true)) { await App.del(`/api/molecules/${m.id}`); refresh(); } }}, "✕") : null))));
    });
    root.append(h("div", {class: "card", style: {padding: 0, overflowX: "auto"}}, b.molecules.length ? tbl : h("p", {style: {padding: "14px"}}, "No molecules yet: drop .xyz or .inp files below.")));
    root.append(W.dropzone(h("div", null, h("b", null, "Drop .xyz / .inp files (or a folder or .zip) here"),
      h("div", {class: "small"}, "Files are copied into the batch folder; originals are never changed. In .xyz files, 'charge=X mult=Y' in the comment line sets charge and multiplicity. From .inp files only the coordinate block and its charge/multiplicity are kept.",
        b.status !== "draft" ? " Molecules added to a running batch start at step 1." : "")), upload));
  },

  async log(root, b) {
    const pre = h("pre", {style: {maxHeight: "70vh"}});
    root.append(pre);
    const draw = async () => {
      const rows = await App.get(`/api/batches/${b.id}/log`);
      pre.textContent = rows.map(r => `${new Date(r.ts * 1000).toLocaleString()}  ${r.level.toUpperCase().padEnd(7)} ${r.text}`).join("\n");
    };
    await draw(); App.every(4000, draw);
  },

  async files(root, folder) {
    root.innerHTML = "";
    const list = await App.get(`/api/files?path=${encodeURIComponent(folder)}`);
    const viewer = h("div");
    root.append(h("div", {class: "row small mono", style: {marginBottom: "6px"}}, folder), h("div", {class: "cols"},
      h("div", {class: "card", style: {padding: 0}}, h("table", null, list.map(f => h("tr", {class: "clickable", onclick: () => f.dir ? Batch.files(root, f.path) : Batch.showFile(viewer, f)},
        h("td", null, (f.dir ? "📁 " : "") + f.name), h("td", {class: "num small muted"}, f.dir ? "" : (f.size / 1024).toFixed(1) + " kB"),
        h("td", null, h("span", {class: "row", style: {flexWrap: "nowrap", gap: "4px"}},
          f.dir ? null : h("a", {class: "btn small", href: `/api/file?download=1&path=${encodeURIComponent(f.path)}`, onclick: e => e.stopPropagation()}, "⬇"),
          h("button", {class: "small danger", title: "Delete", onclick: async e => {
            e.stopPropagation();
            if (!await App.confirm("Delete", `Delete ${f.dir ? "the folder" : ""} ${f.name}${f.dir ? " and everything in it" : ""}? This cannot be undone.`, "Delete", true)) return;
            await App.del(`/api/file?path=${encodeURIComponent(f.path)}`); App.toast("Deleted"); Batch.files(root, folder);
          }}, "🗑"))))),
        h("tr", {class: "clickable", onclick: () => Batch.files(root, folder.replace(/\/[^/]+\/?$/, ""))}, h("td", {colspan: 3, class: "muted"}, "⬆ up")))),
      viewer));
  },
  async showFile(box, f) {
    box.innerHTML = "";
    const big = f.size > 400000;
    const txt = await App.get(`/api/file?path=${encodeURIComponent(f.path)}${big ? "&tail=400000" : ""}`);
    box.append(h("div", {class: "card"}, h("div", {class: "row"}, h("b", null, f.name), big ? h("span", {class: "small muted"}, "(last 400 kB)") : null), h("pre", {style: {maxHeight: "70vh", marginTop: "6px"}}, typeof txt === "string" ? txt : JSON.stringify(txt))));
  },

  settings(root, b) {
    const frag = clone(b.fragments || {});
    const ta = h("textarea", {rows: 6}, Object.entries(frag).map(([k, v]) => `${k}: ${v.join(" ")}`).join("\n"));
    root.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Named fragments"),
      h("p", {class: "help"}, "One fragment per line: name followed by atom indices (ORCA numbering, from 0). Used for fragment charge sums and charge transfer. Example: donor: 0 1 2 3"),
      ta, h("button", {class: "primary", style: {marginTop: "8px"}, onclick: async () => {
        const out = {};
        for (const line of ta.value.split("\n")) { const m = line.match(/^\s*([^:]+):\s*(.*)$/); if (m) out[m[1].trim()] = m[2].split(/[\s,]+/).filter(Boolean).map(Number); }
        await App.patch(`/api/batches/${b.id}`, {fragments: out}); App.toast("Fragments saved");
      }}, "Save fragments")));
    const opts = b.options || {};
    root.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Exports"),
      h("label", {class: "row"}, h("input", {type: "checkbox", checked: opts.auto_export, onchange: async e => { await App.patch(`/api/batches/${b.id}`, {options: {auto_export: e.target.checked}}); App.toast("Saved"); }}),
        "Re-export CSV and Excel automatically whenever results change")));
    root.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Delete batch"),
      h("p", {class: "help"}, "Remove the batch from ORCA Studio, and optionally delete its folder with all calculation files."),
      h("button", {class: "danger", onclick: async () => { if (await Batch.deleteDialog(b)) location.hash = "#/batches"; }}, "Delete batch…")));
  },

  async deleteDialog(b) {
    if (["running", "paused", "review", "stopped"].includes(b.status) && b.kind !== "external") {
      App.toast("Cancel the batch first (running jobs must be stopped before deleting).", "error");
      return false;
    }
    let mode = "list";
    const sure = h("input", {type: "checkbox"});
    const ext = b.kind === "external";
    const body = h("div", {style: {display: "grid", gap: "10px"}},
      h("label", {class: "row", style: {flexWrap: "nowrap", alignItems: "flex-start"}}, h("input", {type: "radio", name: "delmode", checked: true, onchange: () => mode = "list"}),
        h("span", {style: {flex: 1, minWidth: 0}}, h("b", null, "Remove from the list only"), h("div", {class: "small muted"}, "All files stay on disk."))),
      ext ? h("div", {class: "small muted"}, "This is an analysed folder of your own .out files; ORCA Studio never deletes those.") :
        h("label", {class: "row", style: {flexWrap: "nowrap", alignItems: "flex-start"}}, h("input", {type: "radio", name: "delmode", onchange: () => mode = "files"}),
          h("span", {style: {flex: 1, minWidth: 0}}, h("b", {style: {color: "var(--err)"}}, "Delete the batch and its folder"),
            h("div", {class: "small mono", style: {wordBreak: "break-all"}}, b.folder),
            h("div", {class: "small muted"}, "Every input, output, cube and export in this folder is deleted. This cannot be undone. Your original files elsewhere are not touched."))),
      ext ? null : h("label", {class: "row small"}, sure, "I understand the folder will be deleted"));
    const r = await App.modal(`Delete batch "${b.name}"`, body, [{label: "Cancel", value: false}, {label: "Delete", class: "danger", onclick: async () => {
      if (mode === "files" && !sure.checked) { App.toast("Tick the box to confirm deleting the folder", "error"); return false; }
      return App.del(`/api/batches/${b.id}${mode === "files" ? "?delete_files=1" : ""}`);
    }}]);
    if (r) App.toast(r.note);
    return !!r;
  },

  async molecule(main, bid, mid) {
    const b = await App.get(`/api/batches/${bid}`);
    const m = b.molecules.find(x => x.id === mid);
    if (!m) return main.append(h("p", null, "Molecule not found"));
    const runs = await App.get(`/api/batches/${bid}/runs?molecule_id=${mid}`);
    main.append(h("div", {class: "row"}, h("a", {href: `#/batch/${bid}`}, `← ${b.name}`)),
      h("h1", null, m.name, " ", h("span", {class: "muted small mono"}, `${m.formula}, charge ${m.charge}, mult ${m.mult}`)));
    const vbox = h("div", {class: "viewer"});
    const visuals = h("div");
    const left = h("div", null, h("div", {class: "card"}, vbox), visuals);
    const right = h("div");
    main.append(h("div", {class: "cols"}, left, right));
    Viewer.show(vbox, await App.get(`/api/molecules/${mid}/xyz`));
    if (typeof Visuals !== "undefined") Visuals.panel(visuals, b, m, vbox);
    for (const [k, s] of b.steps.entries()) {
      const t = m.tasks[k];
      const card = h("div", {class: "card"});
      right.append(card);
      card.append(h("div", {class: "row"}, h("b", null, `${k + 1}. ${s.name}`), t ? pill(t.status) : null, h("span", {class: "spacer"}),
        t?.step_dir ? h("button", {class: "small", onclick: () => Batch.files(right.appendChild(h("div")), t.step_dir)}, "Files") : null));
      if (!t) continue;
      if (t.message) card.append(h("div", {class: "small muted"}, t.message));
      const chk = Object.entries(t.checks || {}).filter(([k]) => !k.startsWith("_"));
      if (chk.length) card.append(h("div", {class: "kv", style: {marginTop: "6px"}}, chk.flatMap(([k, v]) => [k, h("span", {style: {color: v.status === "pass" ? "var(--ok)" : v.status === "warn" ? "var(--warn)" : "var(--err)"}}, `${v.status}: ${v.detail}`)])));
      const rr = runs.filter(r => r.step_index === k);
      if (rr.length) card.append(h("table", {style: {marginTop: "6px"}}, h("tr", null, ["Attempt", "Status", "Cores", "Time", "Exit", ""].map(x => h("th", null, x))),
        rr.map(r => h("tr", null, h("td", null, r.attempt + (r.subjob ? " " + r.subjob : "")), h("td", null, pill(r.status === "running" ? "running" : r.status === "done" ? "done" : "failed")),
          h("td", null, r.nprocs), h("td", null, fmtDur((r.end || Date.now() / 1000) - r.start)), h("td", null, r.exit_code ?? ""),
          h("td", null, h("button", {class: "small", onclick: async () => {
            const txt = await App.get(`/api/file?path=${encodeURIComponent(r.out_file)}&tail=60000`);
            App.modal(r.out_file.split("/").pop(), h("pre", {style: {maxHeight: "65vh"}}, txt), [{label: "Close"}], true);
          }}, ".out"), h("button", {class: "small", onclick: async () => {
            const inp = r.out_file.replace(/\.out$/, ".inp");
            const txt = await App.get(`/api/file?path=${encodeURIComponent(inp)}`);
            App.modal(inp.split("/").pop(), h("pre", null, txt), [{label: "Close"}], true);
          }}, ".inp"))))));
    }
  },
};
