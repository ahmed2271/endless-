// Simple views: calculation profile steps as cards with menus, sliders and on/off switches,
// and extraction profiles as a list of on/off switches. They edit the same profile data as the
// advanced (table) views.
"use strict";

const Simple = {
  toggle(checked, onchange, label, hint) {
    const inp = h("input", {type: "checkbox", checked, onchange: e => onchange(e.target.checked)});
    return h("label", {class: "switch-row", title: hint || ""}, h("span", {class: "switch"}, inp, h("span", {class: "slider"})), h("span", null, label));
  },
  slider(value, min, max, step, onchange, fmt = v => v) {
    const out = h("b", {class: "mono", style: {minWidth: "56px", display: "inline-block"}}, fmt(value));
    const r = h("input", {type: "range", min, max, step, value, style: {flex: 1}, oninput: e => { out.textContent = fmt(+e.target.value); onchange(+e.target.value); }});
    return h("div", {class: "row", style: {flexWrap: "nowrap"}}, r, out);
  },

  // ------------------------------------------------------------------ calculation profile
  calc(root, p, C, hooks) {
    root.innerHTML = "";
    const libEntries = col => Prof.entries(C.cols[col] || {library: []});
    const val = (s, cid) => {
      const v = (s.values || {})[cid];
      if (v !== undefined && v !== null && v !== "__inherit__") return v;
      return (p.defaults || {})[cid] ?? "";
    };
    const set = (s, cid, v) => { s.values = s.values || {}; s.values[cid] = v; hooks.ensureCols([cid]); hooks.dirty(); };
    const pick = (label, s, cid, opts, blank = "— none —") => h("label", {class: "f"}, label,
      W.select([{value: "", label: blank}, ...opts], val(s, cid), v => { set(s, cid, v); Simple.calc(root, p, C, hooks); }));

    if (!p.steps.length) root.append(h("div", {class: "card", style: {background: "var(--accent-2)"}}, "No steps yet. Add the first step:"));
    p.steps.forEach((s, i) => {
      const stype = C.stepTypes.find(t => t.id === s.type) || {kind: "custom", label: s.type};
      const kind = stype.kind;
      const wf = s.workflow = s.workflow || {};
      wf.cubes = wf.cubes || {};
      const method = C.cols.method ? Prof.entries(C.cols.method).find(e => e.id === val(s, "method")) : null;
      const mtags = (method && method.tags) || [];
      const card = h("div", {class: "card step-card"});
      const head = h("div", {class: "row"},
        h("b", {style: {fontSize: "15px"}}, `Step ${i + 1}`),
        h("input", {value: s.name || "", style: {width: "220px"}, oninput: e => { s.name = e.target.value; hooks.dirty(); }}),
        W.select(C.stepTypes.map(t => ({value: t.id, label: t.label})), s.type, v => {
          const old = C.stepTypes.find(t => t.id === s.type);
          const t = C.stepTypes.find(t => t.id === v);
          if (t && (!s.name || (old && s.name === old.label))) { s.name = t.label; s.slug = ""; }
          s.type = v;
          for (const [k, dv] of Object.entries((t && t.default_values) || {})) if (!(k in (s.values || {}))) set(s, k, dv);
          hooks.dirty(); Simple.calc(root, p, C, hooks);
        }),
        h("span", {class: "spacer"}),
        s.manual_input ? h("span", {class: "manual-flag"}, "MANUAL INPUT") : null,
        h("button", {class: "small", title: "Move up", onclick: () => { if (i) { [p.steps[i - 1], p.steps[i]] = [p.steps[i], p.steps[i - 1]]; hooks.dirty(); Simple.calc(root, p, C, hooks); } }}, "↑"),
        h("button", {class: "small", title: "Move down", onclick: () => { if (i < p.steps.length - 1) { [p.steps[i + 1], p.steps[i]] = [p.steps[i], p.steps[i + 1]]; hooks.dirty(); Simple.calc(root, p, C, hooks); } }}, "↓"),
        h("button", {class: "small", onclick: () => Simple.showInput(p, i)}, "Show input"),
        h("button", {class: "small", onclick: () => hooks.open(i)}, "More settings…"),
        h("button", {class: "small danger", onclick: async () => { if (await App.confirm("Delete step", `Delete step ${i + 1} (${s.name})?`, "Delete", true)) { p.steps.splice(i, 1); hooks.dirty(); Simple.calc(root, p, C, hooks); } }}, "✕"));
      card.append(head);

      // --- method & basis
      const grid = h("div", {class: "simple-grid"});
      grid.append(pick("Method", s, "method", libEntries("method").map(e => ({value: e.id, label: e.label + ((e.tags || []).includes("unverified") ? " (unverified)" : "")}))));
      if (kind !== "xtb" && !mtags.includes("includes_basis")) grid.append(pick("Basis set", s, "basis", libEntries("basis").map(e => ({value: e.id, label: e.label}))));
      if (kind !== "xtb" && !mtags.includes("includes_dispersion")) grid.append(pick("Dispersion", s, "dispersion", libEntries("dispersion").filter(e => e.orca_text).map(e => ({value: e.id, label: e.label}))));
      // solvent: one menu; the model next to it
      const solv = val(s, "solvent");
      grid.append(h("label", {class: "f"}, "Solvent", W.select([{value: "", label: "— gas phase —"}, ...libEntries("solvent").map(e => ({value: e.id, label: e.label}))], solv, v => {
        set(s, "solvent", v);
        if (!v) set(s, "solvent_model", "");
        else if (!val(s, "solvent_model")) set(s, "solvent_model", kind === "xtb" ? "alpb" : "cpcm");
        Simple.calc(root, p, C, hooks);
      })));
      if (solv) grid.append(h("label", {class: "f"}, "Solvent model", W.select(libEntries("solvent_model").filter(e => kind === "xtb" ? e.id === "alpb" : e.id !== "alpb")
        .map(e => ({value: e.id, label: e.label})), val(s, "solvent_model"), v => set(s, "solvent_model", v))));
      card.append(grid);

      // --- switches
      const sw = h("div", {class: "simple-switches"});
      const on = (cid, v) => { const x = val(s, cid); return Array.isArray(x) ? x.includes(v) : x === v || x === true; };
      if (["opt", "opt_freq"].includes(s.type))
        sw.append(Simple.toggle(s.type === "opt_freq", c => { s.type = c ? "opt_freq" : "opt"; if (s.name === "Opt" || s.name === "Opt + Freq") s.name = c ? "Opt + Freq" : "Opt"; hooks.dirty(); Simple.calc(root, p, C, hooks); },
          "Frequencies after the optimization", "Adds Freq: G, H, ZPE and a check for imaginary frequencies"));
      if (kind !== "xtb") {
        sw.append(Simple.toggle(on("scf_convergence", "tightscf"), c => set(s, "scf_convergence", c ? "tightscf" : ""), "Tight SCF"));
        sw.append(Simple.toggle(on("populations", "hirshfeld") && on("populations", "mbis"), c => {
          let cur = val(s, "populations"); cur = Array.isArray(cur) ? cur.filter(x => !["hirshfeld", "mbis"].includes(x)) : (cur ? [cur] : []);
          set(s, "populations", c ? [...cur, "hirshfeld", "mbis"] : cur);
        }, "Hirshfeld + MBIS charges"));
      }
      if (kind === "tddft" || s.type === "tddft_opt")
        sw.append(Simple.toggle(val(s, "triplets") === true || val(s, "triplets") === "true", c => set(s, "triplets", c ? true : ""), "Triplet states too"));
      if (kind !== "xtb") {
        sw.append(Simple.toggle((wf.cubes.orbitals || []).length > 0, c => { wf.cubes.orbitals = c ? ["HOMO", "LUMO"] : []; hooks.dirty(); Simple.calc(root, p, C, hooks); },
          "Orbital pictures (HOMO, LUMO)", "Cube files made after the step; see the Visuals tab"));
        sw.append(Simple.toggle(!!wf.cubes.densities, c => { wf.cubes.densities = c; hooks.dirty(); }, "Electron density cube"));
        sw.append(Simple.toggle(!!wf.cubes.mep, c => { wf.cubes.mep = c; if (c) wf.cubes.densities = true; hooks.dirty(); Simple.calc(root, p, C, hooks); }, "MEP map (needs mep.py in Settings)"));
      }
      card.append(sw);
      if ((wf.cubes.orbitals || []).length) card.append(h("label", {class: "f", style: {maxWidth: "420px"}}, "Which orbitals",
        h("input", {value: wf.cubes.orbitals.join(" "), placeholder: "e.g. HOMO-1 HOMO LUMO LUMO+1", oninput: e => { wf.cubes.orbitals = e.target.value.split(/\s+/).filter(Boolean); hooks.dirty(); }})));

      // --- sliders
      const sl = h("div", {class: "simple-grid"});
      if (kind === "tddft" || s.type === "tddft_opt") {
        const nr = +val(s, "nroots") || 10;
        sl.append(h("label", {class: "f"}, "Number of excited states", Simple.slider(nr, 1, 50, 1, v => set(s, "nroots", v))));
      }
      const maxCores = (App.status && App.status.cores_total) || 16;
      const np = +val(s, "nprocs") || +(p.resources || {}).nprocs || 2;
      sl.append(h("label", {class: "f"}, "Cores for this step", Simple.slider(Math.min(np, maxCores), 1, Math.max(maxCores, np), 1, v => set(s, "nprocs", v))));
      const mc = +val(s, "maxcore") || +(p.resources || {}).maxcore || 1000;
      sl.append(h("label", {class: "f"}, "Memory per core", Simple.slider(mc, 250, 16000, 250, v => set(s, "maxcore", v), v => `${v} MB`)));
      card.append(sl);

      // --- extraction
      const def = stype.default_extraction || {xtb: "step_opt", opt: "step_opt", opt_freq: "step_optfreq", freq: "step_optfreq", sp: "step_sp", tddft: "step_tddft", dscf: "step_dscf"}[kind] || "step_sp";
      const defName = (C.eps.find(e => e.id === def) || {}).name || def;
      const cur = s.extraction_profile === undefined || s.extraction_profile === null ? "__default__" : s.extraction_profile;
      card.append(h("div", {class: "row", style: {marginTop: "6px"}}, h("span", {class: "small"}, "Results read from this step:"),
        W.select([{value: "__default__", label: `${defName} (default)`}, {value: "", label: "(nothing)"}, ...C.eps.map(e => ({value: e.id, label: e.name || e.id}))], cur,
          v => { if (v === "__default__") delete s.extraction_profile; else s.extraction_profile = v; hooks.dirty(); }),
        h("a", {class: "small", href: `#/extraction/${cur === "__default__" ? def : cur || def}`}, "change what is read")));
      root.append(card);
    });
    const quick = [["xtb_preopt", "XTB pre-opt"], ["opt_freq", "Opt + Freq"], ["sp", "Single point"], ["tddft", "TDDFT"]];
    root.append(h("div", {class: "row"}, h("span", {class: "small muted"}, "Add a step:"),
      quick.map(([id, label]) => h("button", {onclick: () => {
        const t = C.stepTypes.find(x => x.id === id) || {label};
        const prev = p.steps[p.steps.length - 1];
        const values = Object.assign({}, prev && prev.type !== "xtb_preopt" ? {method: (prev.values || {}).method, basis: (prev.values || {}).basis, dispersion: (prev.values || {}).dispersion,
          solvent: (prev.values || {}).solvent, solvent_model: (prev.values || {}).solvent_model} : {}, t.default_values || {});
        for (const k of Object.keys(values)) if (values[k] === undefined) delete values[k];
        p.steps.push({name: t.label, slug: "", type: id, values});
        hooks.ensureCols(Object.keys(values)); hooks.dirty(); Simple.calc(root, p, C, hooks);
      }}, "+ " + label)),
      h("button", {onclick: () => hooks.addStep()}, "+ Other step type…")));
  },

  async showInput(p, i) {
    const r = await App.post("/api/preview", {profile: p, step_index: i, molecule: {charge: 0, mult: 1, name: "molecule"}});
    App.modal(`Input for step ${i + 1}`, h("div", null, ...(r.warnings || []).map(w => h("div", {class: "msg warning"}, w)), h("pre", null, r.text)), [{label: "Close"}], true);
  },

  // ------------------------------------------------------------------ extraction profile
  CATALOG: [
    ["Energies", [
      {label: "Final energy", b: "final_energy", unitKind: "energy", name: "Energy"},
      {label: "Dispersion correction", b: "dispersion", unitKind: "energy", name: "Dispersion"},
      {label: "Solvation energy (CPCM)", b: "solvation", unitKind: "energy", name: "Solvation"}]],
    ["Orbitals", [
      {label: "HOMO", b: "homo", unit: "eV", name: "HOMO"}, {label: "LUMO", b: "lumo", unit: "eV", name: "LUMO"},
      {label: "HOMO–LUMO gap", b: "gap", unit: "eV", name: "Gap"},
      {label: "HOMO−1", b: "orbital", params: {which: "homo", n: 1}, unit: "eV", name: "HOMO-1"},
      {label: "HOMO−2", b: "orbital", params: {which: "homo", n: 2}, unit: "eV", name: "HOMO-2"},
      {label: "LUMO+1", b: "orbital", params: {which: "lumo", n: 1}, unit: "eV", name: "LUMO+1"},
      {label: "LUMO+2", b: "orbital", params: {which: "lumo", n: 2}, unit: "eV", name: "LUMO+2"},
      {label: "All orbital energies (table)", b: "orbitals", name: "Orbital energies"},
      {label: "⟨S²⟩ (open shell)", b: "s2", name: "S2"}]],
    ["Charges (per atom, as tables)", [
      {label: "Hirshfeld", b: "charges", params: {scheme: "hirshfeld"}, name: "Hirshfeld charges"},
      {label: "MBIS", b: "charges", params: {scheme: "mbis"}, name: "MBIS charges"},
      {label: "CHELPG", b: "charges", params: {scheme: "chelpg"}, name: "CHELPG charges"},
      {label: "RESP", b: "charges", params: {scheme: "resp"}, name: "RESP charges"},
      {label: "NPA (needs NBO)", b: "charges", params: {scheme: "npa"}, name: "NPA charges"},
      {label: "Mulliken", b: "charges", params: {scheme: "mulliken"}, name: "Mulliken charges"},
      {label: "Löwdin", b: "charges", params: {scheme: "loewdin"}, name: "Löwdin charges"},
      {label: "Spin populations (Hirshfeld)", b: "spin_populations", params: {scheme: "hirshfeld"}, name: "Spin populations"},
      {label: "Mayer bond orders", b: "bond_orders", params: {scheme: "mayer"}, name: "Mayer bond orders"}]],
    ["Dipole and polarizability", [
      {label: "Dipole moment", b: "dipole", unit: "Debye", name: "Dipole"},
      {label: "Polarizability (isotropic)", b: "polarizability", name: "Polarizability"}]],
    ["Thermochemistry (Freq steps)", [
      {label: "Gibbs free energy G", b: "total_gibbs", unitKind: "energy", name: "G"},
      {label: "Enthalpy H", b: "total_enthalpy", unitKind: "energy", name: "H"},
      {label: "Zero-point energy", b: "zpe", unit: "kcal/mol", name: "ZPE"},
      {label: "G − E correction", b: "gibbs_correction", unit: "kcal/mol", name: "G − E"},
      {label: "Imaginary frequencies (count)", b: "imag_count", params: {threshold: 0}, name: "Imaginary freq."},
      {label: "Lowest frequency", b: "lowest_freq", name: "Lowest freq."},
      {label: "IR frequencies and intensities (table)", b: "ir_spectrum", name: "IR spectrum"}]],
    ["Geometry", [
      {label: "Optimization converged", b: "opt_converged", name: "Opt converged"},
      {label: "Optimization cycles", b: "opt_cycles", name: "Opt cycles"},
      {label: "RMSD from start structure", b: "rmsd_start", name: "RMSD from start"},
      {label: "Final coordinates (table)", b: "final_geometry", name: "Final geometry"}]],
    ["Excited states (TDDFT steps)", [
      {label: "S1 energy (eV)", b: "s1_energy", unit: "eV", name: "S1"},
      {label: "S1 wavelength (nm)", b: "s1_energy", unit: "nm", name: "S1 wavelength"},
      {label: "S1 oscillator strength", b: "s1_fosc", name: "S1 f"},
      {label: "T1 energy (eV)", b: "t1_energy", unit: "eV", name: "T1"},
      {label: "Brightest state 250–800 nm (nm)", b: "brightest", params: {nm_min: 250, nm_max: 800}, unit: "nm", name: "Brightest state"},
      {label: "Brightest state oscillator strength", b: "brightest_fosc", params: {nm_min: 250, nm_max: 800}, name: "Brightest f"},
      {label: "All excited states (table)", b: "excited_states", name: "Excited states"}]],
    ["Run information", [
      {label: "Run time", b: "run_time", unit: "min", name: "Run time"},
      {label: "Normal termination", b: "termination", name: "Termination"},
      {label: "ORCA version", b: "orca_version", name: "ORCA version"}]],
  ],

  sameParams(a, b) {
    const ka = Object.keys(a || {}).filter(k => a[k] !== "" && a[k] !== null), kb = Object.keys(b || {}).filter(k => b[k] !== "" && b[k] !== null);
    return ka.length === kb.length && ka.every(k => String(a[k]) === String((b || {})[k]));
  },
  findField(p, it) {
    return p.fields.findIndex(f => (f.kind || "builtin") === "builtin" && f.builtin === it.b && Simple.sameParams(f.params, it.params)
      && (it.b !== "s1_energy" || (it.unit === "nm") === (f.unit === "nm")));
  },

  extraction(root, p, hooks) {
    root.innerHTML = "";
    root.append(h("p", {class: "help"}, "Switch on what you want in the results table. Energies can be shown in Eh, kcal/mol, kJ/mol or eV."));
    for (const [group, items] of Simple.CATALOG) {
      const card = h("div", {class: "card"}, h("h3", {style: {marginTop: 0}}, group));
      const list = h("div", {class: "simple-switches"});
      for (const it of items) {
        const idx = Simple.findField(p, it);
        const f = idx >= 0 ? p.fields[idx] : null;
        const row = h("div", {class: "row", style: {flexWrap: "nowrap"}}, Simple.toggle(!!f, c => {
          const i = Simple.findField(p, it);
          if (c && i < 0) {
            const nf = {kind: "builtin", builtin: it.b, name: it.name, source: {mode: "last"}, params: clone(it.params || {})};
            if (it.unit) nf.unit = it.unit;
            if (it.unitKind === "energy") nf.unit = "Eh";
            let fid = it.name.replace(/[^A-Za-z0-9]+/g, "_").replace(/^_|_$/g, "") || "f";
            while (p.fields.some(x => x.id === fid)) fid += "_2";
            nf.id = fid;
            p.fields.push(nf);
          } else if (!c && i >= 0) {
            p.fields.splice(i, 1);
          }
          hooks.dirty(); Simple.extraction(root, p, hooks);
        }, it.label));
        if (f && it.unitKind === "energy") row.append(W.select(["Eh", "kcal/mol", "kJ/mol", "eV"], f.unit || "Eh", v => { f.unit = v; hooks.dirty(); }, {class: "small"}));
        list.append(row);
      }
      card.append(list);
      root.append(card);
    }
    // relative energies (formula on G or E)
    const card = h("div", {class: "card"}, h("h3", {style: {marginTop: 0}}, "Comparisons between molecules"));
    const list = h("div", {class: "simple-switches"});
    for (const [label, src, id] of [["Relative G (kcal/mol, among molecules with the same formula)", "total_gibbs", "relG"], ["Relative energy (kcal/mol, same formula)", "final_energy", "relE"]]) {
      const has = p.fields.find(f => f.kind === "formula" && f.id === id);
      list.append(Simple.toggle(!!has, c => {
        if (c) {
          let base = p.fields.find(f => f.builtin === src);
          if (!base) { base = {kind: "builtin", builtin: src, name: src === "total_gibbs" ? "G" : "Energy", id: src === "total_gibbs" ? "G" : "Energy", unit: "Eh", source: {mode: "last"}, params: {}}; p.fields.push(base); }
          p.fields.push({kind: "formula", id, name: label.split(" (")[0], expr: `relsame(${base.id})`, unit_kind: "energy", unit: "kcal/mol", decimals: 2});
        } else p.fields = p.fields.filter(f => f.id !== id);
        hooks.dirty(); Simple.extraction(root, p, hooks);
      }, label));
    }
    card.append(list);
    root.append(card);
    const custom = p.fields.filter(f => Simple.CATALOG.every(([, its]) => its.every(it => Simple.findField({fields: [f]}, it) < 0)) && !["relG", "relE"].includes(f.id));
    if (custom.length) root.append(h("div", {class: "card"}, h("h3", {style: {marginTop: 0}}, "Other fields in this profile"),
      h("p", {class: "small muted"}, custom.map(f => f.name).join(", ") + " — edit them in the Advanced view.")));
  },
};
