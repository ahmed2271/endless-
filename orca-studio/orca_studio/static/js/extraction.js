// Extraction profiles (section 9): fields, sources, units, flags, pattern tester; plus "Analyze a folder".
"use strict";

App.register("extraction", async (main, id) => {
  if (id) return Ext.editor(main, id);
  main.append(h("div", {class: "row"}, h("h1", {style: {margin: 0}}, "Extraction profiles"), h("span", {class: "spacer"}),
    h("button", {class: "primary", onclick: async () => {
      const name = await App.prompt("New extraction profile", "Name"); if (!name) return;
      const r = await App.post("/api/items/extraction_profiles", {name, fields: []}); location.hash = `#/extraction/${r.id}`;
    }}, "+ New profile")));
  main.append(h("p", {class: "help"}, "An extraction profile lists what to read from one calculation step: each field becomes a column (or a sub-table) in a batch's results. Every step type has a default (Optimization, Opt + Freq, Single point, Excited states, ΔSCF); choose another one per step in the calculation profile, or per batch in its Results tab."));
  const list = await App.get("/api/items/extraction_profiles");
  const stLib = await App.get("/api/libraries/step_types");
  const defCard = h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Which profile each step type uses"),
    h("p", {class: "help"}, "Every step of a batch reads its values with the profile chosen here for its step type, unless the step (in the calculation profile) or the batch (Results tab) chooses another one."));
  const grid = h("div", {class: "form-grid", style: {gridTemplateColumns: "minmax(170px, max-content) minmax(260px, 420px)"}});
  for (const e of stLib.entries.filter(x => !x.hidden)) {
    grid.append(h("div", {class: "lbl"}, e.label), W.select([{value: "", label: "(nothing)"}, ...list.map(x => ({value: x.id, label: x.name || x.id}))], e.default_extraction || "", async v => {
      e.default_extraction = v;
      await App.put("/api/libraries/step_types", stLib); App.toast(`${e.label} steps now use ${(list.find(x => x.id === v) || {}).name || "nothing"}`);
    }));
  }
  defCard.append(grid);
  main.append(defCard, h("h2", null, "All extraction profiles"));
  main.append(h("div", {class: "card", style: {padding: 0}}, h("table", null, h("tr", null, ["Name", "Fields", ""].map(x => h("th", null, x))),
    list.map(p => h("tr", {class: "clickable", onclick: () => location.hash = `#/extraction/${p.id}`},
      h("td", null, h("b", null, p.name || p.id), h("div", {class: "small muted"}, p.description || "")),
      h("td", {class: "small"}, (p.fields || []).map(f => f.name).join(", ")),
      h("td", null, h("button", {class: "small", onclick: async e => { e.stopPropagation(); const name = await App.prompt("Duplicate", "Name", (p.name || p.id) + " (copy)"); if (!name) return; const c = clone(p); delete c.id; delete c.builtin; c.name = name; const r = await App.post("/api/items/extraction_profiles", c); location.hash = `#/extraction/${r.id}`; }}, "Duplicate")))))));
});

App.register("analyze", async (main) => {
  main.append(h("h1", null, "Analyze a folder of .out files"),
    h("p", {class: "help"}, "Runs an extraction profile on any folder of ORCA .out files (searched recursively), even ones this app did not create. The result appears as a batch with Results, Spectra and exports."));
  const eps = await App.get("/api/items/extraction_profiles");
  const d = {folder: "", extraction_profile_id: "standard", name: ""};
  const inp = (k, ph) => h("input", {placeholder: ph, style: {width: "100%"}, oninput: e => d[k] = e.target.value});
  main.append(h("div", {class: "card", style: {maxWidth: "760px"}}, h("div", {style: {display: "grid", gap: "10px"}},
    h("label", {class: "f"}, "Folder on this computer", inp("folder", "/home/utopia/old_calculations/set1")),
    h("label", {class: "f"}, "Extraction profile", W.select(eps.map(e => ({value: e.id, label: e.name || e.id})), d.extraction_profile_id, v => d.extraction_profile_id = v)),
    h("label", {class: "f"}, "Name (optional)", inp("name", "defaults to the folder name")),
    h("div", null, h("button", {class: "primary", onclick: async () => {
      if (!d.folder) return App.toast("Enter a folder", "error");
      const r = await App.post("/api/analyze", d); App.toast(`${r.files} output files analysed`); location.hash = `#/batch/${r.id}/results`;
    }}, "Analyze")))));
});

const Ext = {
  builtins: null, units: null,
  async load() {
    if (!Ext.builtins) [Ext.builtins, Ext.units] = await Promise.all([App.get("/api/extraction/builtins"), App.get("/api/extraction/units")]);
  },
  unitKind(f) {
    if (f.unit_kind) return f.unit_kind;
    if ((f.kind || "builtin") === "builtin") return (Ext.builtins.find(b => b.id === f.builtin) || {}).unit_kind || "none";
    return "none";
  },
  describe(f) {
    if (f.kind === "formula") return `= ${f.expr || ""}`;
    if (f.kind === "pattern") return `pattern "${f.pattern?.text || ""}" (${f.pattern?.occurrence || "last"}, number ${f.pattern?.number_index || 1}${f.pattern?.next_line ? ", next line" : ""})`;
    if (f.kind === "multiwfn") return `Multiwfn ${f.multiwfn?.recipe || ""}: ${f.multiwfn?.rule || ""}`;
    if (f.kind === "fukui") return `Fukui (${f.params?.scheme || "hirshfeld"}): N=${f.params?.step_n}, N+1=${f.params?.step_plus}, N−1=${f.params?.step_minus}`;
    if (f.kind === "dscf") return `ΔSCF ${f.params?.value || "de"}`;
    const b = Ext.builtins.find(x => x.id === f.builtin);
    const ps = Object.entries(f.params || {}).map(([k, v]) => `${k}=${v}`).join(", ");
    return (b ? b.label : f.builtin) + (ps ? ` (${ps})` : "") + (b && b.shape === "table" ? "  [table]" : "");
  },
  // suggested fields per step kind for "+ Fields for a step…"
  PRESETS: {
    xtb: [["final_energy", "Energy", "Eh"], ["opt_converged", "Opt converged"], ["opt_cycles", "Opt cycles"]],
    opt: [["final_energy", "Energy", "Eh"], ["opt_converged", "Opt converged"], ["opt_cycles", "Opt cycles"], ["rmsd_start", "RMSD from start"]],
    opt_freq: [["final_energy", "Energy", "Eh"], ["total_gibbs", "G", "Eh"], ["total_enthalpy", "H", "Eh"], ["zpe", "ZPE", "kcal/mol"],
      ["gibbs_correction", "G − E", "kcal/mol"], ["imag_count", "Imaginary freq."], ["lowest_freq", "Lowest freq."], ["opt_converged", "Opt converged"]],
    freq: [["final_energy", "Energy", "Eh"], ["total_gibbs", "G", "Eh"], ["zpe", "ZPE", "kcal/mol"], ["gibbs_correction", "G − E", "kcal/mol"], ["imag_count", "Imaginary freq."]],
    sp: [["final_energy", "Energy", "Eh"], ["homo", "HOMO", "eV"], ["lumo", "LUMO", "eV"], ["gap", "Gap", "eV"], ["dipole", "Dipole", "Debye"],
      ["charges", "Hirshfeld charges", null, {scheme: "hirshfeld"}], ["charges", "MBIS charges", null, {scheme: "mbis"}], ["s2", "⟨S²⟩", null, null, false]],
    tddft: [["s1_energy", "S1", "eV"], ["s1_energy", "S1 wavelength", "nm", null, true, "S1_nm"], ["s1_fosc", "S1 f"], ["t1_energy", "T1", "eV", null, false],
      ["brightest", "Brightest state", "nm", {nm_min: 250, nm_max: 800}], ["brightest_fosc", "Brightest f", null, {nm_min: 250, nm_max: 800}], ["excited_states", "Excited states"]],
    dscf: [],
    custom: [["final_energy", "Energy", "Eh"]],
  },
  steps: [],       // steps of the calculation profile chosen in the editor
  types: [],       // step types from the library
  sourceOptions(src) {
    const opts = [{value: JSON.stringify({mode: "last"}), label: "This step (the step the profile is used for)"}];
    Ext.steps.forEach((s, i) => opts.push({value: JSON.stringify({mode: "step_name", value: s.name}), label: `Step ${i + 1}: ${s.name}`}));
    for (const t of Ext.types) opts.push({value: JSON.stringify({mode: "last_of_type", value: t.id}), label: `Last ${t.label} step (any profile)`});
    const cur = JSON.stringify(src && src.mode ? (src.mode === "last" ? {mode: "last"} : {mode: src.mode, value: src.value}) : {mode: "last"});
    if (!opts.some(o => o.value === cur)) opts.push({value: cur, label: Ext.srcLabel(src) + (Ext.steps.length ? "  ⚠ not in this calculation profile" : "")});
    return {opts, cur};
  },
  sourceSelect(f, onchange) {
    const {opts, cur} = Ext.sourceOptions(f.source);
    return W.select(opts, cur, v => { f.source = JSON.parse(v); if (onchange) onchange(); });
  },
  srcLabel(s) {
    s = s || {mode: "last"};
    return {last: "this step", step_name: `step "${s.value}"`, last_of_type: `last ${s.value} step`, step_index: `step ${(+s.value) + 1}`}[s.mode] || s.mode;
  },

  async editor(main, id) {
    await Ext.load();
    const p = await App.get(`/api/items/extraction_profiles/${id}`);
    p.fields = p.fields || [];
    main.append(h("div", {class: "row"}, h("a", {href: "#/extraction"}, "← Extraction profiles")));
    const name = h("input", {value: p.name || "", style: {fontSize: "18px", fontWeight: 600, width: "100%"}, oninput: e => p.name = e.target.value});
    const desc = h("input", {value: p.description || "", placeholder: "Description", style: {width: "100%"}, oninput: e => p.description = e.target.value});
    const tbl = h("div", {class: "card", style: {padding: 0}});
    const [cps, libs] = await Promise.all([App.get("/api/calc_profiles"), App.get("/api/libraries/step_types")]);
    Ext.types = libs.entries.filter(e => !e.hidden);
    if (!p.calc_profile) p.calc_profile = (cps.find(c => c.extraction_profile === id) || {}).id || "";
    const loadSteps = async () => {
      Ext.steps = [];
      if (p.calc_profile) { try { Ext.steps = (await App.get(`/api/calc_profiles/${p.calc_profile}`)).steps || []; } catch (e) { /* deleted profile */ } }
    };
    await loadSteps();
    const cpSel = W.select([{value: "", label: "(none)"}, ...cps.map(c => ({value: c.id, label: c.name}))], p.calc_profile, async v => { p.calc_profile = v; await loadSteps(); draw(); });
    const save = async () => { await App.put(`/api/items/extraction_profiles/${id}`, p); App.toast("Saved"); };
    const startBox = h("div");
    main.append(h("div", {class: "card"}, name, h("div", {style: {marginTop: "8px"}}, desc),
        h("p", {class: "help", style: {marginBottom: 0}}, "An extraction profile is the list of values to read from ", h("b", null, "one calculation step"),
          " (one .out file), for example energy, HOMO/LUMO and charges from a single point, or the excited states from a TDDFT step. ",
          "Choose it for a step in the calculation profile (step settings → Extraction profile) or per batch in the Results tab. ",
          "Each field becomes a column (or a sub-table) in the results."),
        h("details", {style: {marginTop: "8px"}}, h("summary", {class: "small"}, "Advanced: read some fields from another step"),
          h("div", {class: "row", style: {marginTop: "6px"}}, h("label", {class: "f"}, "Show the steps of calculation profile", cpSel),
            h("span", {class: "small muted", style: {maxWidth: "560px"}}, "Only needed for an 'extra fields across steps' profile, e.g. a formula that subtracts a TDDFT value from an SP value. The steps then appear in each field's Source menu.")))),
      startBox,
      h("div", {class: "row", style: {margin: "8px 0"}},
        h("button", {class: "primary", onclick: () => chooseFields()}, "+ Choose fields…"),
        h("button", {onclick: () => readySet()}, "+ Ready-made set…"),
        h("button", {onclick: () => edit(null, "pattern")}, "+ Custom pattern"),
        h("button", {onclick: () => edit(null, "formula")}, "+ Formula"),
        h("button", {onclick: () => edit(null, "builtin")}, "+ Field with options (atoms, bonds…)"),
        h("button", {onclick: () => edit(null, "multiwfn")}, "+ Multiwfn result"),
        h("button", {onclick: () => edit(null, "fukui")}, "+ Fukui"),
        h("button", {onclick: () => edit(null, "dscf")}, "+ ΔSCF"),
        h("span", {class: "spacer"}),
        h("button", {class: "danger small", onclick: async () => { if (await App.confirm("Delete profile", `Delete "${p.name}"?`, "Delete", true)) { await App.del(`/api/items/extraction_profiles/${id}`); location.hash = "#/extraction"; } }}, "Delete profile"),
        h("button", {class: "primary", onclick: save}, "Save")),
      tbl);

    const READY = [["opt", "Optimization", "energy, convergence, cycles"], ["opt_freq", "Opt + Freq", "energy, G, H, ZPE, imaginary frequencies"],
      ["sp", "Single point", "energy, HOMO, LUMO, gap, dipole, Hirshfeld and MBIS charges"], ["tddft", "TDDFT", "S1 (eV, nm, f), T1, brightest state, all states"]];
    function addPreset(kind) {
      let n = 0;
      for (const [b, label, unit, params, on, fid] of (Ext.PRESETS[kind] || [])) {
        if (on === false) continue;
        const f = {kind: "builtin", builtin: b, name: label, source: {mode: "last"}, params: clone(params || {})};
        if (unit) f.unit = unit;
        if (b === "imag_count") f.params.threshold = 0;
        let i0 = (fid || label).replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "") || "f";
        let fidu = i0;
        while (p.fields.some(x => x.id === fidu)) fidu += "_2";
        f.id = fidu; p.fields.push(f); n++;
      }
      draw(); App.toast(`${n} fields added. Press Save to keep them.`);
    }
    async function readySet() {
      await App.modal("Add a ready-made set of fields", h("div", {style: {display: "grid", gap: "6px"}}, READY.map(([k, label, what]) =>
        h("button", {style: {textAlign: "left"}, onclick: () => { document.querySelector(".modal-bg").remove(); addPreset(k); }}, h("b", null, label), h("div", {class: "small muted"}, what)))),
        [{label: "Cancel"}]);
    }
    async function chooseFields() {
      // every simple field, grouped; charges listed per scheme
      const SKIP = new Set(["bond_length", "angle", "dihedral", "charge_on", "spin_on", "orbital", "bond_order", "brightest", "brightest_fosc", "charges", "spin_populations", "scheme_spread", "bond_orders", "imag_count"]);
      const items = [];
      SKIP.add("orbitals");
      for (const b of Ext.builtins) if (!SKIP.has(b.id)) items.push({group: b.group, label: b.label + (b.shape === "table" ? " (table)" : ""), make: () => ({builtin: b.id, name: b.label})});
      const add = (group, label, make) => items.push({group, label, make});
      for (const n of [1, 2, 3]) add("Orbitals and spin", `HOMO−${n} energy`, () => ({builtin: "orbital", name: `HOMO-${n}`, unit: "eV", params: {which: "homo", n}}));
      for (const n of [1, 2, 3]) add("Orbitals and spin", `LUMO+${n} energy`, () => ({builtin: "orbital", name: `LUMO+${n}`, unit: "eV", params: {which: "lumo", n}}));
      add("Orbitals and spin", "Orbital energies and occupations, all orbitals (table)", () => ({builtin: "orbitals", name: "Orbital energies"}));
      add("Thermochemistry", "Imaginary frequencies (count)", () => ({builtin: "imag_count", name: "Imaginary freq.", params: {threshold: 0}}));
      for (const [sch, lab] of [["hirshfeld", "Hirshfeld"], ["mbis", "MBIS"], ["chelpg", "CHELPG"], ["resp", "RESP"], ["npa", "NPA (needs NBO)"], ["mulliken", "Mulliken"], ["loewdin", "Löwdin"]])
        add("Charges", `${lab} charges (table)`, () => ({builtin: "charges", name: `${lab.replace(" (needs NBO)", "")} charges`, params: {scheme: sch}}));
      add("Charges", "Hirshfeld spin populations (table)", () => ({builtin: "spin_populations", name: "Spin populations", params: {scheme: "hirshfeld"}}));
      add("Charges", "Charge scheme comparison (flags atoms where schemes disagree)", () => ({builtin: "scheme_spread", name: "Scheme spread", params: {schemes: "hirshfeld mbis chelpg mulliken", threshold: 0.3}}));
      add("Excited states", "Brightest state between 250 and 800 nm (nm)", () => ({builtin: "brightest", name: "Brightest state", unit: "nm", params: {nm_min: 250, nm_max: 800}}));
      add("Excited states", "S1 wavelength (nm)", () => ({builtin: "s1_energy", name: "S1 wavelength", unit: "nm"}));
      add("Electric properties", "Mayer bond orders (table)", () => ({builtin: "bond_orders", name: "Mayer bond orders", params: {scheme: "mayer"}}));
      const order = ["Energies", "Orbitals and spin", "Charges", "Electric properties", "Excited states", "Thermochemistry", "Geometry", "Run info"];
      const groups = {};
      for (const it of items) (groups[it.group] = groups[it.group] || []).push(it);
      const chosen = new Set();
      const search = h("input", {placeholder: "Search…", style: {width: "100%"}});
      const listBox = h("div", {style: {maxHeight: "55vh", overflow: "auto", marginTop: "8px"}});
      const drawList = () => {
        listBox.innerHTML = "";
        const q = search.value.toLowerCase();
        for (const g of [...order, ...Object.keys(groups).filter(x => !order.includes(x))]) {
          const its = (groups[g] || []).filter(it => !q || it.label.toLowerCase().includes(q));
          if (!its.length) continue;
          listBox.append(h("h3", {style: {margin: "10px 0 4px"}}, g), ...its.map(it => h("label", {class: "row", style: {padding: "2px 0"}},
            h("input", {type: "checkbox", checked: chosen.has(it), onchange: e => e.target.checked ? chosen.add(it) : chosen.delete(it)}), it.label)));
        }
      };
      search.addEventListener("input", drawList); drawList();
      const ok = await App.modal("Choose fields", h("div", null, h("p", {class: "help"}, "Tick everything you want to read from the step's output. Units and names can be changed afterwards (Edit)."), search, listBox),
        [{label: "Cancel", value: false}, {label: "Add selected", class: "primary", value: true}], true);
      if (!ok || !chosen.size) return;
      for (const it of chosen) {
        const f = Object.assign({kind: "builtin", source: {mode: "last"}, params: {}}, it.make());
        let fid = f.name.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "") || "f";
        while (p.fields.some(x => x.id === fid)) fid += "_2";
        f.id = fid; p.fields.push(f);
      }
      draw(); App.toast(`${chosen.size} fields added. Press Save to keep them.`);
    }
    const draw = () => {
      startBox.innerHTML = "";
      if (!p.fields.length) startBox.append(h("div", {class: "card", style: {background: "var(--accent-2)"}},
        h("b", null, "How to start"), h("p", {class: "small", style: {margin: "4px 0 8px"}}, "Pick a ready-made set for the kind of step this profile is for, or tick fields from the full list:"),
        h("div", {class: "row"}, READY.map(([k, label]) => h("button", {onclick: () => addPreset(k)}, label)), h("button", {class: "primary", onclick: () => chooseFields()}, "Choose fields from the list…"))));
      tbl.innerHTML = "";
      tbl.append(h("table", null, h("tr", null, ["", "Column name", "What", "Source", "Unit", "Flag", ""].map(x => h("th", null, x))),
        p.fields.map((f, i) => h("tr", null,
          h("td", null, h("span", {class: "row", style: {flexWrap: "nowrap", gap: "2px"}},
            h("button", {class: "small", onclick: () => { if (i) { [p.fields[i - 1], p.fields[i]] = [p.fields[i], p.fields[i - 1]]; draw(); } }}, "↑"),
            h("button", {class: "small", onclick: () => { if (i < p.fields.length - 1) { [p.fields[i + 1], p.fields[i]] = [p.fields[i], p.fields[i + 1]]; draw(); } }}, "↓"))),
          h("td", null, h("b", null, f.name), h("div", {class: "small muted mono"}, f.id)),
          h("td", {class: "small"}, Ext.describe(f)),
          h("td", {class: "small"}, ["formula", "fukui"].includes(f.kind) ? "—" : Ext.sourceSelect(f)),
          h("td", {class: "small"}, f.unit || ""),
          h("td", {class: "small"}, f.flag?.op ? `${f.flag.op} ${f.flag.value} → ${f.flag.color}` : ""),
          h("td", null, h("button", {class: "small", onclick: () => edit(i)}, "Edit"), h("button", {class: "small danger", onclick: () => { p.fields.splice(i, 1); draw(); }}, "✕"))))));
    };
    async function edit(i, kind) {
      const f = i === null ? {kind, name: "", source: {mode: "last"}, params: {}} : clone(p.fields[i]);
      const r = await Ext.fieldDialog(f, p);
      if (!r) return;
      if (!r.id) r.id = (r.name || "field").replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "") || "f" + (p.fields.length + 1);
      while (p.fields.some((x, j) => x.id === r.id && j !== i)) r.id += "_2";
      if (i === null) p.fields.push(r); else p.fields[i] = r;
      draw();
    }
    draw();
  },

  async fieldDialog(f, prof) {
    const body = h("div", {style: {display: "grid", gap: "10px"}});
    const inp = (obj, k, attrs = {}) => { const el = h(attrs.rows ? "textarea" : "input", Object.assign({value: obj[k] ?? "", style: {width: "100%"}}, attrs)); el.addEventListener("input", () => obj[k] = attrs.type === "number" ? (el.value === "" ? null : +el.value) : el.value); return el; };
    f.params = f.params || {}; f.source = f.source || {mode: "last"};
    const kindBox = h("div");
    const unitBox = h("div");
    const drawUnits = () => {
      unitBox.innerHTML = "";
      const uk = Ext.unitKind(f);
      const units = Ext.units[uk] || [""];
      unitBox.append(h("div", {class: "row"},
        f.kind === "formula" || f.kind === "pattern" ? h("label", {class: "f"}, "Quantity", W.select(Object.keys(Ext.units).map(k => ({value: k, label: k})), f.unit_kind || "none", v => { f.unit_kind = v; f.unit = (Ext.units[v] || [""])[0]; drawUnits(); })) : null,
        h("label", {class: "f"}, "Unit", W.select(units.map(u => ({value: u, label: u || "(none)"})), f.unit || units[0], v => f.unit = v)),
        h("label", {class: "f"}, "Decimals", inp(f, "decimals", {type: "number", style: {width: "80px"}, placeholder: "default"}))));
    };
    const drawKind = () => {
      kindBox.innerHTML = "";
      if (f.kind === "builtin") {
        const groups = {};
        for (const b of Ext.builtins) (groups[b.group] = groups[b.group] || []).push(b);
        const sel = h("select", {style: {width: "100%"}});
        for (const [g, items] of Object.entries(groups)) {
          const og = h("optgroup", {label: g});
          for (const b of items) og.append(h("option", {value: b.id, selected: b.id === f.builtin}, b.label + (b.shape === "table" ? " [table]" : "")));
          sel.append(og);
        }
        if (!f.builtin) f.builtin = Ext.builtins[0].id;
        sel.value = f.builtin;
        const pbox = h("div");
        const drawParams = () => {
          pbox.innerHTML = "";
          const b = Ext.builtins.find(x => x.id === f.builtin) || {params: []};
          for (const prm of b.params) {
            if (prm === "scheme") pbox.append(h("label", {class: "f"}, "Scheme", W.select(["hirshfeld", "mbis", "chelpg", "resp", "npa", "mulliken", "loewdin"].filter(x => !(f.builtin.startsWith("bond") && !["mayer", "loewdin"].includes(x))).concat(f.builtin.startsWith("bond") ? ["mayer"] : []), (f.params.scheme = f.params.scheme || (f.builtin.startsWith("bond") ? "mayer" : "hirshfeld")), v => f.params.scheme = v)));
            else if (prm === "spin") pbox.append(h("label", {class: "f"}, "Spin (open shell)", W.select(["alpha", "beta"], f.params.spin || "alpha", v => f.params.spin = v)));
            else if (prm === "which") pbox.append(h("label", {class: "f"}, "Orbital", W.select([{value: "homo", label: "HOMO − n"}, {value: "lumo", label: "LUMO + n"}], f.params.which || "homo", v => f.params.which = v)));
            else if (prm === "value") pbox.append(h("label", {class: "f"}, "Value", W.select(["charge", "spin", "population"], f.params.value || "charge", v => f.params.value = v)));
            else if (prm === "atoms") pbox.append(h("label", {class: "f"}, "Atoms: 'all', indices like '0 3', an element like 'O', or a fragment name", inp(f.params, "atoms")));
            else pbox.append(h("label", {class: "f"}, prm + (["a", "b", "c", "d"].includes(prm) ? " (atom index from 0)" : ""), inp(f.params, prm)));
          }
        };
        sel.addEventListener("change", () => { f.builtin = sel.value; f.params = {}; f.unit = undefined; if (!f.name || f._auto) { f.name = sel.selectedOptions[0].textContent.replace(" [table]", ""); f._auto = true; nameInp.value = f.name; } drawParams(); drawUnits(); });
        if (!f.name) { f.name = sel.selectedOptions[0]?.textContent.replace(" [table]", ""); f._auto = true; }
        drawParams();
        kindBox.append(h("label", {class: "f"}, "Built-in field", sel), pbox);
      } else if (f.kind === "pattern") {
        f.pattern = f.pattern || {text: "", regex: false, occurrence: "last", number_index: 1, next_line: false};
        const P = f.pattern;
        kindBox.append(h("label", {class: "f"}, "Search text (or regular expression)", inp(P, "text")),
          h("div", {class: "row"},
            h("label", {class: "row small"}, h("input", {type: "checkbox", checked: P.regex, onchange: e => P.regex = e.target.checked}), "regular expression"),
            h("label", {class: "row small"}, h("input", {type: "checkbox", checked: P.ignore_case, onchange: e => P.ignore_case = e.target.checked}), "ignore case"),
            h("label", {class: "f"}, "Which occurrence", W.select([{value: "first", label: "first"}, {value: "last", label: "last"}, {value: "all", label: "all (table)"}], P.occurrence, v => P.occurrence = v)),
            h("label", {class: "f"}, "Which number (1 = first after the text, −1 = last)", inp(P, "number_index", {type: "number", style: {width: "80px"}})),
            h("label", {class: "row small"}, h("input", {type: "checkbox", checked: P.next_line, onchange: e => P.next_line = e.target.checked}), "number is on the next line")),
          h("button", {onclick: () => Ext.tester(f)}, "Test on a sample .out…"));
      } else if (f.kind === "formula") {
        const tpls = [["Relative to lowest (same composition)", "rel(G)"], ["Relative within each composition", "relsame(G)"], ["Relative to a reference molecule", "ref(G, 'name')"],
          ["Boltzmann population", "boltzmann(G, 298.15)"], ["High-level SP + low-level Gibbs correction", "E_sp + Gcorr"], ["Singlet–triplet gap", "E_T - E_S"],
          ["Koopmans IP (eV)", "-HOMO"], ["Koopmans EA (eV)", "-LUMO"], ["Chemical potential", "(HOMO + LUMO) / 2"], ["Hardness", "(LUMO - HOMO) / 2"],
          ["Electrophilicity", "((HOMO + LUMO) / 2)**2 / (LUMO - HOMO)"], ["Fragment charge sum", "fragsum(q, 'donor')"], ["Charge transfer between steps", "fragsum(q_anion, 'A') - fragsum(q_neutral, 'A')"],
          ["Reaction / binding energy (per molecule)", "E - ref(E, 'reactant')"]];
        const ex = inp(f, "expr", {placeholder: "e.g. rel(G)"});
        kindBox.append(h("label", {class: "f"}, "Expression", ex),
          h("div", {class: "small muted"}, "Use other fields by their id: " + (prof.fields.map(x => x.id).join(", ") || "(none yet)") +
            ". Values are in base units (energies in Eh, orbital and excitation energies in eV). Functions: rel, relsame, ref, boltzmann, fragsum, atomval, abs, sqrt, log, exp, min, max."),
          h("label", {class: "f"}, "Ready-made", W.select([{value: "", label: "choose…"}, ...tpls.map(([l, e]) => ({value: e, label: `${l}:  ${e}`}))], "", v => { if (v) { f.expr = v; ex.value = v; } })));
        if (!f.unit_kind) { f.unit_kind = "energy"; f.unit = "kcal/mol"; }
      } else if (f.kind === "multiwfn") {
        f.multiwfn = f.multiwfn || {};
        kindBox.append(h("div", {class: "small muted"}, "Takes a value from a recorded Multiwfn recipe (Scripts → Multiwfn recipes). The recipe runs on the source step's orbitals when needed."));
        App.get("/api/items/multiwfn_recipes").then(recs => {
          const rules = h("div");
          const drawRules = () => { rules.innerHTML = ""; const r = recs.find(x => x.id === f.multiwfn.recipe); if (!r) return; rules.append(h("label", {class: "f"}, "Result", W.select([{value: "", label: "choose…"}, ...(r.rules || []).map(x => ({value: x.id, label: x.label}))], f.multiwfn.rule || "", v => { f.multiwfn.rule = v; const rr = (r.rules || []).find(x => x.id === v); f.multiwfn.shape = rr && rr.table ? "table" : "scalar"; }))); };
          kindBox.append(h("label", {class: "f"}, "Recipe", W.select([{value: "", label: recs.length ? "choose…" : "(no recipes recorded yet)"}, ...recs.map(r => ({value: r.id, label: r.name || r.id}))], f.multiwfn.recipe || "", v => { f.multiwfn.recipe = v; drawRules(); })), rules);
          drawRules();
        });
      } else if (f.kind === "fukui") {
        f.params.scheme = f.params.scheme || "hirshfeld";
        kindBox.append(h("div", {class: "small muted"}, "Condensed Fukui functions f⁺, f⁻, f⁰ and the dual descriptor from single points at N, N+1 and N−1 electrons on the same geometry. Give the step names (or numbers from 0) of the three single points; use the 'Charge change' column (−1 / +1) on those steps."),
          h("label", {class: "f"}, "Charge scheme", W.select(["hirshfeld", "mulliken", "loewdin", "mbis", "chelpg"], f.params.scheme, v => f.params.scheme = v)),
          h("label", {class: "f"}, "Step with N electrons", inp(f.params, "step_n")),
          h("label", {class: "f"}, "Step with N+1 electrons (anion)", inp(f.params, "step_plus")),
          h("label", {class: "f"}, "Step with N−1 electrons (cation)", inp(f.params, "step_minus")));
      } else if (f.kind === "dscf") {
        f.params.value = f.params.value || "de";
        f.unit_kind = ["de", "pure"].includes(f.params.value) ? "excitation" : "none";
        kindBox.append(h("label", {class: "f"}, "Value", W.select([{value: "de", label: "ΔE (excited − ground)"}, {value: "pure", label: "Spin-purified ΔE (2E(mixed) − E(T))"}, {value: "s2", label: "⟨S²⟩ of the excited state"}, {value: "collapse", label: "Collapsed to the ground state?"}], f.params.value, v => { f.params.value = v; f.unit_kind = ["de", "pure"].includes(v) ? "excitation" : "none"; drawUnits(); })));
      }
      drawUnits();
    };
    const nameInp = inp(f, "name");
    nameInp.addEventListener("input", () => f._auto = false);
    const srcBox = h("div", {class: "row"}, h("label", {class: "f"}, "Source step (which calculation step this value is read from)", Ext.sourceSelect(f)));
    const flag = f.flag = f.flag || {};
    const flagBox = h("div", {class: "row"}, h("span", {class: "small"}, "Color the cell when the value is"),
      W.select(["", ">", "<", ">=", "<=", "==", "!=", "abs>"].map(x => ({value: x, label: x || "(no rule)"})), flag.op || "", v => flag.op = v),
      inp(flag, "value", {type: "number", step: "any", style: {width: "100px"}}),
      W.select(["red", "orange", "yellow", "blue"], flag.color || "yellow", v => flag.color = v));
    body.append(h("label", {class: "f"}, "Column name", nameInp), kindBox, ["formula", "fukui"].includes(f.kind) ? null : srcBox, unitBox, flagBox);
    drawKind();
    const ok = await App.modal(`${{builtin: "Built-in", pattern: "Custom pattern", formula: "Formula", multiwfn: "Multiwfn", fukui: "Fukui", dscf: "ΔSCF"}[f.kind]} field`, body,
      [{label: "Cancel", value: false}, {label: "OK", class: "primary", value: true}], true);
    if (!ok) return null;
    delete f._auto;
    if (!f.flag.op) delete f.flag;
    return f;
  },

  async tester(f) {
    const samples = await App.get("/api/extraction/sample_outs");
    let path = samples[0] || "";
    const file = h("input", {type: "file", accept: ".out,.log,.txt"});
    const out = h("div");
    const run = async () => {
      const fd = new FormData();
      fd.append("field", JSON.stringify(f)); fd.append("path", path);
      if (file.files.length) fd.append("file", file.files[0]);
      const r = await App.api("POST", "/api/extraction/test", fd);
      out.innerHTML = "";
      out.append(h("div", {class: "msg " + (r.error ? "error" : "ok")}, r.error ? r.error : `Value: ${JSON.stringify(r.value)}` + (r.converted != null && r.converted !== r.value ? `  →  ${r.converted} ${f.unit || ""}` : "")));
      for (const hit of r.hits) out.append(h("div", {class: "outline-lines", style: {marginTop: "6px"}}, hit.context.map(l => h("div", {class: l.hit ? "hit" : ""}, `${String(l.n).padStart(6)}  ${l.text}`))));
    };
    await App.modal("Test on a sample .out", h("div", {style: {display: "grid", gap: "8px"}},
      h("label", {class: "f"}, "Sample from finished jobs", W.select(samples.length ? samples : [{value: "", label: "(no finished jobs yet: upload a file)"}], path, v => path = v, {style: {width: "100%"}})),
      h("label", {class: "f"}, "…or upload an .out file", file),
      h("div", null, h("button", {class: "primary", onclick: run}, "Test")), out), [{label: "Close"}], true);
  },
};
