// Scripts page (section 12): script registry and Multiwfn recipes (record, re-test, rules).
"use strict";

App.register("scripts", async (main, kind, id) => {
  if (kind === "recipe" && id) return typeof MW !== "undefined" ? MW.editor(main, id) : null;
  if (kind === "record") return typeof MW !== "undefined" ? MW.record(main) : null;
  main.append(h("h1", null, "Scripts"));
  const [scripts, st] = await Promise.all([App.get("/api/items/scripts"), App.get("/api/settings")]);
  main.append(h("h2", null, "Script registry"),
    h("p", {class: "help"}, "Scripts run in a step folder after that step succeeds (choose them in the step's workflow). Placeholders in the command: {python} {script} {basename} {step_dir} {nprocs} {npoints} {gbw} {molden} {out}. The script path is set once in Settings, so moving a script needs only one change."));
  const card = h("div", {class: "card", style: {padding: 0}});
  card.append(h("table", null, h("tr", null, ["Name", "Command", "Path (Settings)", "Outputs", ""].map(x => h("th", null, x))),
    scripts.map(sc => h("tr", {class: "clickable", onclick: () => Scripts.edit(sc)},
      h("td", null, h("b", null, sc.name || sc.id), h("div", {class: "small muted"}, sc.description || "")),
      h("td", {class: "mono small"}, sc.command),
      h("td", {class: "mono small"}, st.settings.script_paths[sc.path_setting || sc.id] || h("span", {style: {color: "var(--err)"}}, "not set")),
      h("td", {class: "small"}, (sc.outputs || []).map(o => `${o.glob} (${o.type})`).join(", ")),
      h("td", null, h("button", {class: "small", onclick: e => { e.stopPropagation(); Scripts.test(sc); }}, "Test on a molecule…"))))));
  main.append(card, h("button", {onclick: () => Scripts.edit(null)}, "+ Register a script"));
  const mwBox = h("div");
  main.append(mwBox);
  if (typeof MW !== "undefined") MW.list(mwBox);
});

const Scripts = {
  async edit(sc) {
    const isNew = !sc;
    sc = sc ? clone(sc) : {name: "", command: "{python} {script} {basename}", outputs: [], cores: 1, timeout: 3600};
    const st = await App.get("/api/settings");
    const pathKey = sc.path_setting || sc.id || "";
    let path = st.settings.script_paths[pathKey] || "";
    const f = (k, attrs = {}) => { const el = h("input", Object.assign({value: sc[k] ?? "", style: {width: "100%"}}, attrs)); el.addEventListener("input", () => sc[k] = attrs.type === "number" ? +el.value : el.value); return el; };
    const outs = h("textarea", {rows: 3}, (sc.outputs || []).map(o => `${o.glob} ${o.type}${o.role ? " " + o.role : ""}`).join("\n"));
    const body = h("div", {style: {display: "grid", gap: "8px"}},
      h("label", {class: "f"}, "Name", f("name")),
      h("label", {class: "f"}, "Description", f("description")),
      h("label", {class: "f"}, "Script file on this computer (stored in Settings)", h("input", {value: path, style: {width: "100%"}, oninput: e => path = e.target.value})),
      h("label", {class: "f"}, "Command template", f("command")),
      h("label", {class: "f"}, "Declared outputs: one per line, 'glob type [role]' (type: cube, image, table, value)", outs),
      h("div", {class: "row"}, h("label", {class: "f"}, "Cores", f("cores", {type: "number", style: {width: "80px"}})),
        h("label", {class: "f"}, "Timeout (s)", f("timeout", {type: "number", style: {width: "100px"}})),
        h("label", {class: "f"}, "Default grid points", f("npoints", {type: "number", style: {width: "100px"}}))));
    const r = await App.modal(isNew ? "Register a script" : `Script: ${sc.name}`, body, [{label: "Cancel", value: null}, {label: "Save", class: "primary", onclick: async () => {
      sc.outputs = outs.value.split("\n").map(l => l.trim().split(/\s+/)).filter(p => p[0]).map(p => ({glob: p[0], type: p[1] || "file", role: p[2] || ""}));
      const saved = isNew ? await App.post("/api/items/scripts", sc) : await App.put(`/api/items/scripts/${sc.id}`, sc);
      const key = saved.path_setting || saved.id;
      st.settings.script_paths[key] = path;
      await App.put("/api/settings", {settings: st.settings});
      return saved;
    }}], true);
    if (r) App.route();
  },
  async test(sc) {
    const batches = await App.get("/api/batches");
    const out = h("div");
    let mid = null, bid = null;
    const molSel = h("select");
    const bSel = W.select([{value: "", label: "choose a batch…"}, ...batches.map(b => ({value: b.id, label: b.name}))], "", async v => {
      bid = v; molSel.innerHTML = "";
      if (!v) return;
      const b = await App.get(`/api/batches/${v}`);
      for (const m of b.molecules) molSel.append(h("option", {value: m.id}, m.name));
      mid = b.molecules[0]?.id;
    });
    molSel.onchange = () => mid = molSel.value;
    await App.modal(`Test ${sc.name}`, h("div", {style: {display: "grid", gap: "8px"}}, h("div", {class: "row"}, bSel, molSel),
      h("p", {class: "help"}, "Runs the script in the last finished step (with a kept .gbw) of that molecule."),
      h("div", null, h("button", {class: "primary", onclick: async () => {
        out.innerHTML = "Running…";
        const r = await App.post(`/api/scripts/${sc.id}/run`, {molecule_id: +mid});
        out.innerHTML = "";
        out.append(h("div", {class: "msg " + (r.ok ? "ok" : "error")}, `${r.ok ? "Finished" : "Failed"} in ${r.seconds.toFixed(1)} s. Outputs: ${r.outputs.map(o => o.path.split("/").pop()).join(", ") || "none"}`),
          h("pre", {style: {maxHeight: "40vh"}}, r.log_text));
      }}, "Run")), out), [{label: "Close"}], true);
  },
};
