// Calculation profiles (section 6): list + editor with column layout, step rows, workflow and live preview.
"use strict";

App.register("profiles", async (main, id, ver) => {
  if (id) return Prof.editor(main, id, ver ? +ver : null);
  main.append(h("div", {class: "row"}, h("h1", {style: {margin: 0}}, "Calculation profiles"), h("span", {class: "spacer"}),
    h("button", {class: "primary", onclick: async () => {
      const name = await App.prompt("New calculation profile", "Name"); if (!name) return;
      const p = await App.post("/api/calc_profiles", {name}); location.hash = `#/profiles/${p.id}`;
    }}, "+ New profile")));
  main.append(h("p", {class: "help"}, "A profile is a reusable recipe of steps. Saving an edited profile creates a new version; each batch remembers the exact version it ran with."));
  const list = await App.get("/api/calc_profiles");
  main.append(h("div", {class: "card", style: {padding: 0}}, h("table", null,
    h("tr", null, ["Name", "Steps", "Version", "Saved", ""].map(x => h("th", null, x))),
    list.map(p => h("tr", {class: "clickable", onclick: () => location.hash = `#/profiles/${p.id}`},
      h("td", null, h("b", null, p.name), h("div", {class: "small muted"}, p.description)),
      h("td", {class: "small"}, p.steps.join(" → ")),
      h("td", null, "v" + p.version), h("td", {class: "small muted"}, p.saved_at || (p.builtin ? "starter" : "")),
      h("td", null, h("button", {class: "small danger", onclick: async e => { e.stopPropagation(); await Prof.remove(p.id, p.name); }}, "Delete"),
        h("button", {class: "small", onclick: async e => {
        e.stopPropagation();
        const name = await App.prompt("Duplicate profile", "Name of the copy", p.name + " (copy)"); if (!name) return;
        const full = await App.get(`/api/calc_profiles/${p.id}`); delete full.versions;
        const c = await App.post("/api/calc_profiles", {name, profile: full}); location.hash = `#/profiles/${c.id}`;
      }}, "Duplicate")))))));
});

const Prof = {
  cat: null,
  async remove(id, name) {
    const used = await App.get(`/api/calc_profiles/${id}/batches`);
    const note = used.length ? ` ${used.length} batch(es) used it (${used.map(b => b.name).slice(0, 5).join(", ")}); they keep their own copy and their results.` : "";
    if (!await App.confirm("Delete profile", `Delete "${name}"?${note} The file is moved to the .trash folder in the profiles folder.`, "Delete", true)) return false;
    window.onbeforeunload = null;
    await App.del(`/api/calc_profiles/${id}`);
    App.toast(`Deleted "${name}"`);
    if (location.hash === "#/profiles") App.route(); else location.hash = "#/profiles";
    return true;
  },
  async catalog() {
    const [libs, cols, scripts, eps, tpls] = await Promise.all([App.get("/api/libraries?full=1"), App.get("/api/columns"),
      App.get("/api/items/scripts"), App.get("/api/items/extraction_profiles"), App.get("/api/items/step_templates")]);
    Prof.cat = {libs, cols, scripts, eps, tpls, stepTypes: libs.step_types.entries.filter(e => !e.hidden)};
    return Prof.cat;
  },
  entries(col) {
    const out = [];
    for (const lid of col.library || []) for (const e of (Prof.cat.libs[lid]?.entries || [])) if (!e.hidden) out.push(Object.assign({list: lid}, e));
    out.sort((a, b) => (b.favorite - a.favorite));
    return out;
  },
  entryLabel(col, v) {
    if (v === "" || v === undefined || v === null) return "blank";
    if (col.type === "dropdown") {
      const ids = Array.isArray(v) ? v : [v];
      return ids.map(id => (Prof.entries(col).find(e => e.id === id) || {label: id}).label).join(" + ");
    }
    if (col.type === "toggle") return v === true || v === "true" ? "on" : "off";
    return String(v);
  },
  applies(col, stype) {
    const t = col.applies_to || ["all"];
    const ids = [stype?.id, stype?.kind];
    if (t.filter(x => x.startsWith("!")).some(x => ids.includes(x.slice(1)))) return false;
    return t.includes("all") || t.some(x => ids.includes(x));
  },

  async editor(main, id, version) {
    await Prof.catalog();
    const url = version ? `/api/calc_profiles/${id}?version=${version}` : `/api/calc_profiles/${id}`;
    const p = await App.get(url);
    const versions = p.versions || [];
    delete p.versions;
    const st = {p, sel: 0, dirty: false, showHidden: false};
    p.columns = p.columns || []; p.defaults = p.defaults || {}; p.resources = p.resources || {};
    const C = Prof.cat;

    const nameInp = h("input", {value: p.name, style: {fontSize: "18px", fontWeight: 600, width: "100%"}, oninput: e => { p.name = e.target.value; dirty(); }});
    const descInp = h("input", {value: p.description || "", placeholder: "Description", style: {width: "100%"}, oninput: e => { p.description = e.target.value; dirty(); }});
    const verSel = W.select(versions.map(v => ({value: v, label: `version ${v}` + (v === Math.max(...versions) ? " (latest)" : "")})), p.version, v => location.hash = `#/profiles/${id}/${v}`);
    const epSel = W.select([{value: "", label: "(none)"}, ...C.eps.map(e => ({value: e.id, label: e.name || e.id}))], p.extraction_profile || "", v => { p.extraction_profile = v; dirty(); });
    const res = (k, label) => h("label", {class: "f"}, label, h("input", {type: "number", value: p.resources[k] ?? "", style: {width: "110px"}, oninput: e => { p.resources[k] = e.target.value === "" ? null : +e.target.value; dirty(); }}));
    const saveBtn = h("button", {class: "primary", title: "Save the changes into this profile", onclick: () => save("overwrite")}, "Save");
    const saveVerBtn = h("button", {title: "Keep the current version unchanged and store the changes as the next version", onclick: () => save("new_version")}, "Save as new version");
    const issuesBox = h("div");
    main.append(h("div", {class: "row", style: {marginBottom: "6px"}}, h("a", {href: "#/profiles"}, "← Calculation profiles")),
      h("div", {class: "card"},
        h("div", {class: "row"}, h("div", {class: "grow"}, nameInp), verSel),
        h("div", {class: "row", style: {marginTop: "8px"}}, h("div", {class: "grow"}, descInp)),
        h("div", {class: "row", style: {marginTop: "8px", alignItems: "flex-end"}},
          h("label", {class: "f"}, "Extraction profile (default for batches)", epSel), res("nprocs", "Cores per job"), res("maxcore", "Memory per core (MB)"),
          h("span", {class: "spacer"}),
          h("button", {class: "danger", onclick: () => Prof.remove(id, p.name)}, "Delete"),
          h("button", {onclick: validateNow}, "Validate"), saveVerBtn, saveBtn)),
      version && version !== Math.max(...versions) ? h("div", {class: "msg warning"}, `You are looking at the older version ${version}. Saving stores it as a new version (the latest is not overwritten).`) : "",
      issuesBox);

    const tableWrap = h("div", {class: "ptable"});
    const tools = h("div", {class: "row", style: {margin: "8px 0"}},
      h("button", {onclick: addStep}, "+ Add step"),
      h("button", {onclick: insertTemplate}, "+ Insert step template"),
      h("button", {onclick: addColumn}, "+ Add column"),
      h("label", {class: "row small"}, h("input", {type: "checkbox", onchange: e => { st.showHidden = e.target.checked; drawTable(); }}), "show hidden columns"),
      h("span", {class: "spacer"}),
      h("button", {class: "small", onclick: async () => { await App.post("/api/calc_profiles/default_layout", {columns: p.columns}); App.toast("This column layout is now the default for new profiles"); }}, "Use this layout for new profiles"));
    const detail = h("div");
    main.append(h("h2", null, "Steps"), tools, tableWrap, detail);

    function dirty() { st.dirty = true; saveBtn.textContent = "Save •"; schedulePreview(); }
    function layoutCols() { return p.columns.filter(c => C.cols[c.column] && (st.showHidden || !c.hidden)); }

    function cellControl(col, step, isDefaults) {
      const vals = isDefaults ? p.defaults : (step.values = step.values || {});
      const has = Object.prototype.hasOwnProperty.call(vals, col.id) && vals[col.id] !== null && vals[col.id] !== "__inherit__";
      const cur = has ? vals[col.id] : undefined;
      const inheritVal = p.defaults[col.id] ?? col.default ?? "";
      const inheritLabel = `Inherit (${Prof.entryLabel(col, inheritVal)})`;
      const set = v => { if (v === undefined) delete vals[col.id]; else vals[col.id] = v; dirty(); };
      if (col.type === "dropdown") {
        const ents = Prof.entries(col);
        if (col.multi) {
          const arr = has ? (Array.isArray(cur) ? cur : (cur ? [cur] : [])) : null;
          const lbl = arr === null ? (isDefaults ? "blank" : inheritLabel) : (arr.length ? Prof.entryLabel(col, arr) : "blank");
          return h("button", {class: "small", style: {width: "100%", textAlign: "left"}, onclick: async () => {
            const chosen = new Set(arr || []);
            let inherit = arr === null && !isDefaults;
            const box = h("div", {style: {display: "grid", gap: "4px"}},
              !isDefaults ? h("label", {class: "row"}, h("input", {type: "checkbox", checked: inherit, onchange: e => inherit = e.target.checked}), h("i", null, inheritLabel)) : null,
              ents.map(e => h("label", {class: "row"}, h("input", {type: "checkbox", checked: chosen.has(e.id), onchange: ev => ev.target.checked ? chosen.add(e.id) : chosen.delete(e.id)}), e.label, h("span", {class: "small muted mono"}, e.orca_text))));
            const ok = await App.modal(col.label, box, [{label: "Cancel", value: false}, {label: "OK", class: "primary", value: true}]);
            if (!ok) return;
            set(inherit ? undefined : [...chosen]); drawTable();
          }}, lbl);
        }
        const opts = [];
        if (!isDefaults) opts.push({value: "__inherit__", label: inheritLabel});
        opts.push({value: "", label: "— blank —"});
        for (const e of ents) opts.push({value: e.id, label: (e.favorite ? "★ " : "") + e.label + ((e.tags || []).includes("unverified") ? " (unverified)" : "")});
        if (has && cur !== "" && !ents.find(e => e.id === cur)) opts.push({value: cur, label: `${cur} (missing)`});
        opts.push({value: "__add__", label: "Add custom…"});
        const sel = W.select(opts, has ? cur : (isDefaults ? "" : "__inherit__"), async (v, el) => {
          if (v === "__add__") {
            const e = await Prof.addCustomEntry(col);
            if (e) { await Prof.catalog(); set(e.id); }
            drawTable(); return;
          }
          set(v === "__inherit__" ? undefined : v);
          el.parentElement.classList.toggle("inherit", v === "__inherit__");
        });
        return sel;
      }
      if (col.type === "toggle") {
        const opts = isDefaults ? [{value: "", label: "off"}, {value: "true", label: "on"}] : [{value: "__inherit__", label: inheritLabel}, {value: "", label: "off"}, {value: "true", label: "on"}];
        return W.select(opts, has ? (cur === true || cur === "true" ? "true" : "") : (isDefaults ? "" : "__inherit__"), v => set(v === "__inherit__" ? undefined : (v === "true" ? true : "")));
      }
      const inp = h("input", {type: col.type === "number" ? "number" : "text", value: has ? cur : "", step: "any",
        placeholder: isDefaults ? "" : (inheritVal !== "" ? `inherit: ${inheritVal}` : "")});
      inp.addEventListener("change", () => set(inp.value === "" ? undefined : (col.type === "number" ? +inp.value : inp.value)));
      if (col.type === "text" && (col.template || "").includes("\n")) {
        inp.addEventListener("dblclick", async () => {
          const ta = h("textarea", {rows: 6}, has ? cur : "");
          const ok = await App.modal(col.label, ta, [{label: "Cancel", value: false}, {label: "OK", class: "primary", value: true}]);
          if (ok) { set(ta.value === "" ? undefined : ta.value); drawTable(); }
        });
        inp.title = "Double-click for a multi-line editor";
      }
      return inp;
    }

    function drawTable() {
      tableWrap.innerHTML = "";
      const cols = layoutCols();
      const tbl = h("table", {class: "grid"});
      const hdr = h("tr", null, h("th", null, ""), h("th", null, "Step"));
      cols.forEach((lc) => {
        const col = C.cols[lc.column];
        const idx = p.columns.indexOf(lc);
        hdr.append(h("th", {title: col.notes || ""}, h("div", {class: "colhdr"},
          h("span", {style: {opacity: lc.hidden ? .5 : 1}}, lc.label || col.label),
          (col.tags || []).includes("unverified") ? h("span", {class: "unverified"}, "?") : null,
          h("span", {class: "ctl"},
            h("button", {title: "Move left", onclick: () => { if (idx > 0) { [p.columns[idx - 1], p.columns[idx]] = [p.columns[idx], p.columns[idx - 1]]; dirty(); drawTable(); } }}, "◀"),
            h("button", {title: "Move right", onclick: () => { if (idx < p.columns.length - 1) { [p.columns[idx + 1], p.columns[idx]] = [p.columns[idx], p.columns[idx + 1]]; dirty(); drawTable(); } }}, "▶"),
            h("button", {title: "Rename header (label only)", onclick: async () => { const n = await App.prompt("Rename column", "Header label (the ORCA text does not change)", lc.label || col.label); if (n !== null) { lc.label = n === col.label ? undefined : n; dirty(); drawTable(); } }}, "✎"),
            h("button", {title: lc.hidden ? "Show" : "Hide", onclick: () => { lc.hidden = !lc.hidden; dirty(); drawTable(); }}, lc.hidden ? "👁" : "◌"),
            h("button", {title: "Remove column from this profile", onclick: async () => {
              const used = p.steps.some(s => s.values && col.id in s.values) || col.id in p.defaults;
              if (used && !await App.confirm("Remove column", `Steps have values in "${col.label}". Remove the column and those values?`, "Remove", true)) return;
              p.columns.splice(idx, 1); delete p.defaults[col.id]; p.steps.forEach(s => s.values && delete s.values[col.id]); dirty(); drawTable();
            }}, "✕")))));
      });
      tbl.append(hdr);
      // defaults row
      const dr = h("tr", {class: "defaults"}, h("td", null, ""), h("td", null, h("i", null, "Profile defaults")));
      cols.forEach(lc => { const col = C.cols[lc.column]; dr.append(h("td", null, col.special === "nprocs" || col.special === "maxcore" ? h("span", {class: "small muted"}, "see top") : cellControl(col, null, true))); });
      tbl.append(dr);
      p.steps.forEach((s, i) => {
        const stype = C.stepTypes.find(t => t.id === s.type) || {id: s.type, kind: "custom", label: s.type};
        const tr = h("tr", {class: i === st.sel ? "sel" : ""});
        tr.append(h("td", null, h("span", {class: "row", style: {flexWrap: "nowrap", gap: "2px"}},
          h("button", {class: "small", title: "Move up", onclick: () => { if (i) { [p.steps[i - 1], p.steps[i]] = [p.steps[i], p.steps[i - 1]]; st.sel = i - 1; dirty(); drawAll(); } }}, "↑"),
          h("button", {class: "small", title: "Move down", onclick: () => { if (i < p.steps.length - 1) { [p.steps[i + 1], p.steps[i]] = [p.steps[i], p.steps[i + 1]]; st.sel = i + 1; dirty(); drawAll(); } }}, "↓"))));
        tr.append(h("td", {style: {minWidth: "190px", cursor: "pointer"}, onclick: () => { st.sel = i; drawAll(); }},
          h("b", null, `${i + 1}. ${s.name || stype.label}`), s.manual_input ? h("span", {class: "manual-flag", style: {marginLeft: "6px"}}, "MANUAL INPUT") : null,
          h("div", {class: "small muted"}, stype.label)));
        cols.forEach(lc => {
          const col = C.cols[lc.column];
          if (!Prof.applies(col, stype)) { tr.append(h("td", {class: "na", title: `Does not apply to ${stype.label} steps`})); return; }
          const td = h("td", null, cellControl(col, s, false));
          if (!(s.values && Object.prototype.hasOwnProperty.call(s.values, col.id))) td.classList.add("inherit");
          tr.append(td);
        });
        tbl.append(tr);
      });
      if (!p.steps.length) tbl.append(h("tr", null, h("td", {colspan: cols.length + 2, style: {padding: "14px", color: "var(--muted)"}},
        "No steps yet. Press ", h("b", null, "+ Add step"), " to add the first one (for example XTB pre-opt, Opt + Freq, Single point or TDDFT).")));
      tableWrap.append(tbl);
    }

    // ------------------------------------------------------------ step detail
    let previewTimer = null;
    const preview = h("pre", {style: {minHeight: "160px", maxHeight: "460px"}});
    const pvWarn = h("div");
    const pvMol = {charge: 0, mult: 1, name: "molecule"};
    function schedulePreview() { clearTimeout(previewTimer); previewTimer = setTimeout(refreshPreview, 250); }
    async function refreshPreview() {
      if (!p.steps.length) { preview.textContent = ""; return; }
      const r = await App.post("/api/preview", {profile: p, step_index: st.sel, molecule: pvMol});
      preview.textContent = r.text;
      pvWarn.innerHTML = "";
      for (const w of r.warnings || []) pvWarn.append(h("div", {class: "msg warning"}, w));
      if (r.subjob) pvWarn.append(h("div", {class: "msg info"}, `ΔSCF: showing the excited-state (es) sub-job input.`));
    }

    function drawDetail() {
      detail.innerHTML = "";
      const s = p.steps[st.sel];
      if (!s) return;
      s.workflow = s.workflow || {};
      const wf = s.workflow; wf.checks = wf.checks || {};
      const stype = C.stepTypes.find(t => t.id === s.type) || {};
      const isOpt = ["xtb", "opt", "opt_freq"].includes(stype.kind) || /\b(opt|optts|copt)\b/i.test(s.extra_keywords || "");
      const isFreq = ["freq", "opt_freq"].includes(stype.kind) || /\b(num)?freq\b/i.test(s.extra_keywords || "");
      const inp = (obj, k, attrs = {}) => { const el = h(attrs.rows ? "textarea" : "input", Object.assign({value: obj[k] ?? ""}, attrs)); el.addEventListener("input", () => { obj[k] = attrs.type === "number" ? (el.value === "" ? null : +el.value) : el.value; dirty(); }); return el; };
      const sel = (obj, k, opts, def) => W.select(opts, obj[k] ?? def, v => { obj[k] = v; dirty(); });
      const typeSel = W.select(C.stepTypes.map(t => ({value: t.id, label: t.label})), s.type, v => {
        const oldT = C.stepTypes.find(x => x.id === s.type);
        const t = C.stepTypes.find(x => x.id === v);
        if (t && (!s.name || (oldT && s.name === oldT.label))) { s.name = t.label; s.slug = ""; }
        s.type = v;
        if (t && t.default_values) { s.values = s.values || {}; for (const [k, val] of Object.entries(t.default_values)) if (!(k in s.values)) s.values[k] = val; ensureCols(Object.keys(t.default_values)); }
        dirty(); drawAll();
      });
      const manualBox = h("div");
      const drawManual = () => {
        manualBox.innerHTML = "";
        if (s.manual_input) {
          manualBox.append(h("div", {class: "msg warning"}, "This step uses a manually edited input. Placeholders {charge} {mult} {nprocs} {maxcore} {xyzfile} {molecule} are filled per molecule; the table above is ignored for this step."),
            inp(s, "manual_input", {rows: 14}),
            h("button", {class: "small danger", onclick: () => { s.manual_input = null; dirty(); drawAll(); }}, "Remove manual override"));
        } else {
          manualBox.append(h("button", {onclick: async () => { const r = await App.post("/api/manual_template", {profile: p, step_index: st.sel}); s.manual_input = r.text; dirty(); drawAll(); }}, "Edit final input (manual override)…"));
        }
      };
      drawManual();
      const retryOpts = (C.libs.retry_strategies?.entries || []).filter(e => !e.hidden);
      const retryBox = h("div", {class: "chips"}, retryOpts.map(e => {
        const on = (wf.scf_retry || []).includes(e.id);
        return h("span", {class: "chip" + (on ? " on" : ""), title: e.orca_text, onclick: () => {
          wf.scf_retry = wf.scf_retry || [];
          const i = wf.scf_retry.indexOf(e.id); if (i >= 0) wf.scf_retry.splice(i, 1); else wf.scf_retry.push(e.id);
          dirty(); drawDetail();
        }}, (on ? (wf.scf_retry.indexOf(e.id) + 1) + ". " : "") + e.label);
      }));
      const scriptBox = h("div", {class: "chips"}, C.scripts.map(sc => {
        const on = (wf.scripts || []).includes(sc.id);
        return h("span", {class: "chip" + (on ? " on" : ""), onclick: () => { wf.scripts = wf.scripts || []; const i = wf.scripts.indexOf(sc.id); if (i >= 0) wf.scripts.splice(i, 1); else wf.scripts.push(sc.id); dirty(); drawDetail(); }}, sc.name || sc.id);
      }));
      if (!C.scripts.length) scriptBox.append(h("span", {class: "small muted"}, "No scripts registered."));
      wf.cubes = wf.cubes || {};
      const cubeTxt = h("input", {value: (wf.cubes.orbitals || []).join(" "), placeholder: "e.g. HOMO LUMO HOMO-1", style: {width: "100%"}, oninput: e => { wf.cubes.orbitals = e.target.value.split(/\s+/).filter(Boolean); dirty(); }});
      const tplBtn = s.template ? h("button", {class: "small", onclick: async () => {
        const t = C.tpls.find(x => x.id === s.template); if (!t) return App.toast("Template not found", "error");
        if (!await App.confirm("Update from template", `Replace this step's settings with the current "${t.name}" template?`, "Update")) return;
        const name = s.name; Object.assign(s, clone(t.step), {name, template: t.id, template_saved: t.saved_at}); dirty(); drawAll();
      }}, `Update from template "${(C.tpls.find(x => x.id === s.template) || {}).name || s.template}"`) : null;

      detail.append(h("div", {class: "cols", style: {marginTop: "14px"}},
        h("div", {class: "card"},
          h("div", {class: "row"}, h("h2", {style: {margin: 0}}, `Step ${st.sel + 1}`), h("span", {class: "spacer"}),
            tplBtn,
            h("button", {class: "small", onclick: async () => { const name = await App.prompt("Save step template", "Template name", s.name); if (!name) return; await App.post("/api/items/step_templates", {name, step: clone(s), saved_at: new Date().toISOString()}); await Prof.catalog(); App.toast("Template saved"); }}, "Save as template"),
            h("button", {class: "small", onclick: () => { p.steps.splice(st.sel + 1, 0, clone(s)); p.steps[st.sel + 1].name += " (copy)"; st.sel++; dirty(); drawAll(); }}, "Duplicate"),
            h("button", {class: "small danger", onclick: async () => { if (!await App.confirm("Delete step", `Delete step "${s.name}"?`, "Delete", true)) return; p.steps.splice(st.sel, 1); st.sel = Math.max(0, st.sel - 1); dirty(); drawAll(); }}, "Delete")),
          h("div", {class: "form-grid", style: {gridTemplateColumns: "150px 1fr", marginTop: "10px"}},
            h("div", {class: "lbl"}, "Name"), inp(s, "name", {oninput: () => drawTable()}),
            h("div", {class: "lbl"}, "Folder name"), inp(s, "slug", {placeholder: "from the name"}),
            h("div", {class: "lbl"}, "Step type"), typeSel,
            h("div", {class: "lbl"}, "Extra keywords"), inp(s, "extra_keywords", {placeholder: "added to the ! line"}),
            h("div", {class: "lbl"}, "Extra blocks"), inp(s, "extra_blocks", {rows: 4, placeholder: "%scf\n  MaxIter 300\nend"})),
          h("h3", null, "Manual override"), manualBox,
          h("h3", null, "Workflow (app side, never written to the input)"),
          h("div", {class: "form-grid", style: {gridTemplateColumns: "190px 1fr"}},
            h("div", {class: "lbl"}, "After this step"), sel(wf, "between", [{value: "wait_all", label: "Wait for all molecules"}, {value: "pause", label: "Pause for review"}, {value: "per_molecule", label: "Continue per molecule"}], "wait_all"),
            h("div", {class: "lbl"}, "Run this step"), sel(wf, "run_condition", [{value: "always", label: "Always"}, {value: "prev_success", label: "Only if the previous step succeeded"}, {value: "check_fired", label: "Only if a check fired in the previous step"}], "always"),
            h("div", {class: "lbl"}, "Retry on SCF failure"), retryBox,
            isOpt ? h("div", {class: "lbl"}, "Restart unconverged opt") : null, isOpt ? inp(wf, "opt_restarts", {type: "number", min: 0, placeholder: "0 = off", style: {width: "90px"}}) : null,
            isFreq ? h("div", {class: "lbl"}, "Fix imaginary frequencies") : null, isFreq ? inp(wf, "imag_fix", {type: "number", min: 0, placeholder: "0 = off", style: {width: "90px"}}) : null,
            h("div", {class: "lbl"}, "After final failure"), sel(wf, "after_failure", [{value: "skip", label: "Skip later steps for that molecule"}, {value: "stop", label: "Stop the batch"}], "skip"),
            h("div", {class: "lbl"}, "Time limit (hours)"), inp(wf, "time_limit_h", {type: "number", min: 0, step: "any", placeholder: "none", style: {width: "90px"}}),
            h("div", {class: "lbl"}, "Order within the step"), sel(wf, "order", [{value: "list", label: "List order"}, {value: "smallest", label: "Smallest first"}, {value: "largest", label: "Largest first"}], "list"),
            h("div", {class: "lbl"}, "Files to keep"), sel(wf, "keep", [{value: "all", label: "All"}, {value: "results", label: "Results only (.out .xyz .hess .gbw densities)"}, {value: "minimal", label: "Minimal (.out .xyz)"}], "all"),
            h("div", {class: "lbl"}, "Scripts after success"), scriptBox,
            h("div", {class: "lbl"}, "Orbital cubes after success"), cubeTxt,
            h("div", {class: "lbl"}, "Densities / MEP"), h("div", {class: "row"},
              h("label", {class: "row small"}, h("input", {type: "checkbox", checked: wf.cubes.densities, onchange: e => { wf.cubes.densities = e.target.checked; dirty(); }}), "density cubes"),
              h("label", {class: "row small"}, h("input", {type: "checkbox", checked: wf.cubes.mep, onchange: e => { wf.cubes.mep = e.target.checked; dirty(); }}), "MEP (adds KeepDens)"))),
          h("h3", null, "Success checks"),
          h("div", {class: "form-grid", style: {gridTemplateColumns: "190px 1fr"}},
            isOpt ? h("div", {class: "lbl"}, "Optimization converged") : null, isOpt ? sel(wf.checks, "opt_converged", ["fail", "warn", "off"], "fail") : null,
            h("div", {class: "lbl"}, "SCF converged"), sel(wf.checks, "scf_converged", ["fail", "warn", "off"], "fail"),
            isFreq ? h("div", {class: "lbl"}, "Imaginary frequencies") : null, isFreq ? h("div", {class: "row"}, sel(wf.checks, "imaginary", ["fail", "warn", "off"], "fail"), "below", inp(wf.checks, "imag_threshold", {type: "number", placeholder: "-30", style: {width: "80px"}}), "cm⁻¹") : null,
            h("div", {class: "lbl"}, "⟨S²⟩ deviation"), h("div", {class: "row"}, sel(wf.checks, "s2", ["warn", "fail", "off"], "warn"), "limit", inp(wf.checks, "s2_max_dev", {type: "number", step: "any", placeholder: "0.1", style: {width: "80px"}})))),
        h("div", {class: "card"},
          h("div", {class: "row"}, h("h2", {style: {margin: 0}}, "Input preview"), h("span", {class: "spacer"}),
            h("span", {class: "small muted"}, "sample charge/mult:"),
            h("input", {type: "number", value: pvMol.charge, style: {width: "60px"}, oninput: e => { pvMol.charge = +e.target.value; schedulePreview(); }}),
            h("input", {type: "number", value: pvMol.mult, min: 1, style: {width: "60px"}, oninput: e => { pvMol.mult = +e.target.value; schedulePreview(); }})),
          h("p", {class: "help"}, "Exactly the file that will be written (byte-identical)."),
          pvWarn, preview)));
      refreshPreview();
    }

    function drawAll() { drawTable(); drawDetail(); }
    function ensureCols(ids) { for (const cid of ids) if (C.cols[cid] && !p.columns.some(c => c.column === cid)) p.columns.push({column: cid}); }

    async function addStep() {
      const t = await App.modal("Add step", h("div", null, h("p", {class: "help"}, "Choose the step type:"),
        h("div", {style: {display: "grid", gap: "6px"}}, C.stepTypes.map(t => h("button", {style: {textAlign: "left"}, onclick: () => { document.querySelector(".modal-bg").remove(); resolveAdd(t); }}, h("b", null, t.label), h("span", {class: "small muted"}, " " + (t.orca_text || "(single point)")))))), [{label: "Cancel", value: null}]);
    }
    function resolveAdd(t) {
      const s = {name: t.label, slug: "", type: t.id, values: clone(t.default_values || {})};
      ensureCols(Object.keys(t.default_values || {}));
      p.steps.push(s); st.sel = p.steps.length - 1; dirty(); drawAll();
    }
    async function insertTemplate() {
      await Prof.catalog();
      if (!C.tpls.length && !Prof.cat.tpls.length) return App.toast("No step templates yet: use 'Save as template' on a step.");
      const tpls = Prof.cat.tpls;
      await App.modal("Insert step template", h("div", {style: {display: "grid", gap: "6px"}}, tpls.map(t => h("button", {style: {textAlign: "left"}, onclick: () => {
        document.querySelector(".modal-bg").remove();
        const s = Object.assign(clone(t.step), {template: t.id, template_saved: t.saved_at});
        ensureCols(Object.keys(s.values || {}));
        p.steps.push(s); st.sel = p.steps.length - 1; dirty(); drawAll();
      }}, h("b", null, t.name), h("span", {class: "small muted"}, " " + (t.step?.name || ""))))), [{label: "Close", value: null}]);
    }
    async function addColumn() {
      const used = new Set(p.columns.map(c => c.column));
      const search = h("input", {placeholder: "Search columns…", style: {width: "100%"}});
      const list = h("div", {style: {display: "grid", gap: "4px", maxHeight: "50vh", overflow: "auto", marginTop: "8px"}});
      const draw = () => {
        list.innerHTML = "";
        const q = search.value.toLowerCase();
        Object.values(C.cols).filter(c => !used.has(c.id) && (c.label.toLowerCase().includes(q) || c.id.includes(q))).sort((a, b) => a.label.localeCompare(b.label))
          .forEach(c => list.append(h("button", {style: {textAlign: "left"}, onclick: () => { document.querySelector(".modal-bg").remove(); p.columns.push({column: c.id}); dirty(); drawTable(); }},
            h("b", null, c.label), h("span", {class: "small muted"}, ` ${c.type}${c.type === "dropdown" ? " · " + (c.library || []).join(", ") : c.template ? " · " + c.template.replace(/\n/g, " ⏎ ") : ""}`))));
      };
      search.addEventListener("input", draw); draw();
      await App.modal("Add column", h("div", null, search, list), [{label: "Create a new column…", onclick: async () => {
        const libs = await App.get("/api/libraries");
        const r = await Lib.editColumn(null, libs);
        if (r && r.id) { await Prof.catalog(); Object.assign(C, Prof.cat); p.columns.push({column: r.id}); dirty(); drawAll(); }
        return true;
      }}, {label: "Close", value: null}]);
    }
    async function validateNow() {
      const issues = await App.post("/api/validate", {profile: p});
      issuesBox.innerHTML = "";
      if (!issues.length) issuesBox.append(h("div", {class: "msg ok"}, "No problems found."));
      for (const i of issues) issuesBox.append(h("div", {class: "msg " + i.level}, i.message,
        i.fix ? h("button", {class: "small", style: {marginLeft: "8px"}, onclick: async () => { await save(); const r = await App.post(`/api/calc_profiles/${id}/fix`, {fix: i.fix}); App.toast(`Added; saved as version ${r.version}`); App.route(); }}, i.fix.label || "Fix") : null));
    }
    async function save(mode = "overwrite") {
      const viewingOld = version && version !== Math.max(...versions);
      if (mode === "overwrite" && viewingOld) mode = "new_version";   // never overwrite the latest from an old version
      const r = await App.put(`/api/calc_profiles/${id}?mode=${mode}`, p);
      const changed = r.saved_at !== p.saved_at;
      st.dirty = false; saveBtn.textContent = "Save";
      if (!changed) App.toast("No changes to save");
      else if (mode === "new_version") App.toast(`Saved as version ${r.version}; version ${p.version} is kept`);
      else App.toast(`Saved (version ${r.version})`);
      p.version = r.version; p.saved_at = r.saved_at;
      if (changed && (mode === "new_version" || viewingOld)) {
        if (location.hash === `#/profiles/${id}`) App.route(); else location.hash = `#/profiles/${id}`;
      }
      return r;
    }
    window.onbeforeunload = () => st.dirty ? "unsaved" : undefined;
    drawAll();
  },

  async addCustomEntry(col) {
    const lid = (col.library || [])[0];
    const e = {label: "", orca_text: "", destination: "keyword_line", notes: ""};
    const lists = col.library || [];
    let target = lid;
    const f = k => { const el = h("input", {style: {width: "100%"}}); el.addEventListener("input", () => e[k] = el.value); return el; };
    const body = h("div", {style: {display: "grid", gap: "8px"}},
      lists.length > 1 ? h("label", {class: "f"}, "Add to list", W.select(lists, lid, v => target = v)) : null,
      h("label", {class: "f"}, "Display name", f("label")),
      h("label", {class: "f"}, "ORCA text (inserted exactly)", f("orca_text")),
      h("label", {class: "f"}, "Destination", W.select(Lib.DESTS, "keyword_line", v => e.destination = v)),
      h("label", {class: "f"}, "Notes", f("notes")));
    const ok = await App.modal(`Add custom entry to ${col.label}`, body, [{label: "Cancel", value: false}, {label: "Add", class: "primary", value: true}]);
    if (!ok || !e.label) return null;
    return App.post(`/api/libraries/${target}/entries`, e);
  },
};
