// Extraction profiles (section 9): fields, sources, units, flags, pattern tester; plus "Analyze a folder".
"use strict";

App.register("extraction", async (main, id) => {
  if (id) return Ext.editor(main, id);
  main.append(h("div", {class: "row"}, h("h1", {style: {margin: 0}}, "Extraction profiles"), h("span", {class: "spacer"}),
    h("button", {class: "primary", onclick: async () => {
      const name = await App.prompt("New extraction profile", "Name"); if (!name) return;
      const r = await App.post("/api/items/extraction_profiles", {name, fields: []}); location.hash = `#/extraction/${r.id}`;
    }}, "+ New profile")));
  main.append(h("p", {class: "help"}, "An extraction profile is a list of fields; each field becomes a column (or a sub-table) in a batch's results."));
  const list = await App.get("/api/items/extraction_profiles");
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
  srcLabel(s) {
    s = s || {mode: "last"};
    return {last: "last step", step_name: `step "${s.value}"`, last_of_type: `last ${s.value} step`, step_index: `step ${(+s.value) + 1}`}[s.mode] || s.mode;
  },

  async editor(main, id) {
    await Ext.load();
    const p = await App.get(`/api/items/extraction_profiles/${id}`);
    p.fields = p.fields || [];
    main.append(h("div", {class: "row"}, h("a", {href: "#/extraction"}, "← Extraction profiles")));
    const name = h("input", {value: p.name || "", style: {fontSize: "18px", fontWeight: 600, width: "100%"}, oninput: e => p.name = e.target.value});
    const desc = h("input", {value: p.description || "", placeholder: "Description", style: {width: "100%"}, oninput: e => p.description = e.target.value});
    const tbl = h("div", {class: "card", style: {padding: 0}});
    main.append(h("div", {class: "card"}, name, h("div", {style: {marginTop: "8px"}}, desc)),
      h("div", {class: "row", style: {margin: "8px 0"}},
        h("button", {onclick: () => edit(null, "builtin")}, "+ Built-in field"),
        h("button", {onclick: () => edit(null, "pattern")}, "+ Custom pattern"),
        h("button", {onclick: () => edit(null, "formula")}, "+ Formula"),
        h("button", {onclick: () => edit(null, "multiwfn")}, "+ Multiwfn result"),
        h("button", {onclick: () => edit(null, "fukui")}, "+ Fukui functions"),
        h("button", {onclick: () => edit(null, "dscf")}, "+ ΔSCF value"),
        h("span", {class: "spacer"}),
        p.builtin ? h("span", {class: "small muted"}, "starter profile") : h("button", {class: "danger small", onclick: async () => { if (await App.confirm("Delete profile", `Delete "${p.name}"?`, "Delete", true)) { await App.del(`/api/items/extraction_profiles/${id}`); location.hash = "#/extraction"; } }}, "Delete profile"),
        h("button", {class: "primary", onclick: async () => { await App.put(`/api/items/extraction_profiles/${id}`, p); App.toast("Saved"); }}, "Save")),
      tbl);
    const draw = () => {
      tbl.innerHTML = "";
      tbl.append(h("table", null, h("tr", null, ["", "Column name", "What", "Source", "Unit", "Flag", ""].map(x => h("th", null, x))),
        p.fields.map((f, i) => h("tr", null,
          h("td", null, h("span", {class: "row", style: {flexWrap: "nowrap", gap: "2px"}},
            h("button", {class: "small", onclick: () => { if (i) { [p.fields[i - 1], p.fields[i]] = [p.fields[i], p.fields[i - 1]]; draw(); } }}, "↑"),
            h("button", {class: "small", onclick: () => { if (i < p.fields.length - 1) { [p.fields[i + 1], p.fields[i]] = [p.fields[i], p.fields[i + 1]]; draw(); } }}, "↓"))),
          h("td", null, h("b", null, f.name), h("div", {class: "small muted mono"}, f.id)),
          h("td", {class: "small"}, Ext.describe(f)),
          h("td", {class: "small"}, f.kind === "formula" ? "—" : Ext.srcLabel(f.source)),
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
    const srcVal = h("input", {value: f.source.value ?? "", style: {width: "200px"}, oninput: e => f.source.value = e.target.value});
    const srcBox = h("div", {class: "row"}, h("label", {class: "f"}, "Source step", W.select([{value: "last", label: "Last step"}, {value: "step_name", label: "Step by name"}, {value: "last_of_type", label: "Last step of type"}, {value: "step_index", label: "Step number (from 0)"}], f.source.mode, v => { f.source.mode = v; })),
      h("label", {class: "f"}, "Step name / type id / number", srcVal));
    const flag = f.flag = f.flag || {};
    const flagBox = h("div", {class: "row"}, h("span", {class: "small"}, "Color the cell when the value is"),
      W.select(["", ">", "<", ">=", "<=", "==", "!=", "abs>"].map(x => ({value: x, label: x || "(no rule)"})), flag.op || "", v => flag.op = v),
      inp(flag, "value", {type: "number", step: "any", style: {width: "100px"}}),
      W.select(["red", "orange", "yellow", "blue"], flag.color || "yellow", v => flag.color = v));
    body.append(h("label", {class: "f"}, "Column name", nameInp), kindBox, f.kind === "formula" ? null : srcBox, unitBox, flagBox);
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
