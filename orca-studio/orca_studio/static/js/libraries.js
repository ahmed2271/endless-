// Libraries page (section 5): every dropdown list and the column library.
"use strict";

App.register("libraries", async (main, which) => {
  main.append(h("h1", null, "Libraries"));
  main.append(h("p", {class: "help"}, "Every dropdown in the app is filled from these lists. ORCA text is inserted exactly as written. Built-in entries can be hidden but not deleted. Entries marked ",
    h("span", {class: "unverified"}, "unverified"), " still need the ORCA checks on this workstation."));
  const libs = await App.get("/api/libraries");
  const layout = h("div", {class: "row top", style: {alignItems: "flex-start", gap: "16px"}});
  const left = h("div", {class: "card", style: {width: "240px", flex: "none", padding: "8px"}});
  const right = h("div", {class: "grow", style: {minWidth: 0}});
  layout.append(left, right);
  main.append(layout);
  const items = [["__columns", "Column library"], ...libs.map(l => [l.id, `${l.label} (${l.count})`])];
  for (const [id, label] of items) {
    left.append(h("a", {href: `#/libraries/${id}`, style: {display: "block", padding: "5px 8px", borderRadius: "5px",
      textDecoration: "none", color: "inherit", background: id === (which || "__columns") ? "var(--accent-2)" : "",
      fontWeight: id === "__columns" ? "600" : ""}}, label));
  }
  left.append(h("button", {class: "small", style: {margin: "8px"}, onclick: async () => {
    const label = await App.prompt("New list", "Name of the new list"); if (!label) return;
    const r = await App.post("/api/libraries", {label}); location.hash = `#/libraries/${r.id}`;
  }}, "+ New list"));
  if (!which || which === "__columns") return Lib.columns(right);
  return Lib.list(right, which);
});

const Lib = {
  DESTS: ["keyword_line", "block:scf", "block:geom", "block:freq", "block:tddft", "block:cpcm", "block:method", "block:elprop", "block:chelpg", "none"],

  async list(root, id) {
    const lib = await App.get(`/api/libraries/${id}`);
    const tbl = h("table", {class: "grid"});
    const draw = () => {
      tbl.innerHTML = "";
      tbl.append(h("tr", null, ["", "★", "Label", "ORCA text", "Destination", "Applies to", "Tags", "Notes", "Hidden", ""].map(x => h("th", null, x))));
      lib.entries.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
      lib.entries.forEach((e, i) => {
        const txt = (k, attrs = {}) => { const el = h(attrs.multi ? "textarea" : "input", Object.assign({value: e[k] ?? ""}, attrs.multi ? {rows: 2, style: {minWidth: "200px"}} : {style: {width: "100%"}})); el.addEventListener("input", () => e[k] = el.value); return el; };
        const arr = (k) => { const el = h("input", {value: (e[k] || []).join(", "), style: {width: "100%"}}); el.addEventListener("input", () => e[k] = el.value.split(",").map(x => x.trim()).filter(Boolean)); return el; };
        const dest = W.select([...new Set([...Lib.DESTS, e.destination])].map(d => ({value: d, label: d})), e.destination, v => e.destination = v);
        tbl.append(h("tr", {style: {opacity: e.hidden ? .5 : 1}},
          h("td", null, h("span", {class: "row", style: {gap: "2px", flexWrap: "nowrap"}},
            h("button", {class: "small", title: "Move up", onclick: () => { if (i) { const a = lib.entries[i - 1]; [a.order, e.order] = [e.order, a.order]; if (a.order === e.order) e.order -= 1; draw(); } }}, "↑"),
            h("button", {class: "small", title: "Move down", onclick: () => { if (i < lib.entries.length - 1) { const a = lib.entries[i + 1]; [a.order, e.order] = [e.order, a.order]; if (a.order === e.order) e.order += 1; draw(); } }}, "↓"))),
          h("td", null, h("input", {type: "checkbox", checked: e.favorite, onchange: ev => e.favorite = ev.target.checked})),
          h("td", null, txt("label")),
          h("td", null, txt("orca_text", {multi: (e.orca_text || "").includes("\n") || e.destination !== "keyword_line"}),
            (e.tags || []).includes("unverified") ? h("span", {class: "unverified"}, "unverified") : null,
            e.also && e.also.length ? h("div", {class: "small muted"}, "also: " + e.also.map(a => `${a.destination}: ${a.orca_text}`).join("; ")) : null),
          h("td", null, dest),
          h("td", null, arr("applies_to")),
          h("td", null, arr("tags"), e.elements !== undefined ? h("div", {class: "small"}, "elements: ", txt("elements")) : null),
          h("td", null, txt("notes")),
          h("td", null, h("input", {type: "checkbox", checked: e.hidden, onchange: ev => { e.hidden = ev.target.checked; draw(); }})),
          h("td", null, e.builtin ? h("span", {class: "small muted"}, "built-in") :
            h("button", {class: "small danger", onclick: () => { lib.entries.splice(i, 1); draw(); }}, "Delete"))));
      });
    };
    draw();
    root.append(h("div", {class: "card"},
      h("div", {class: "row"}, h("h2", {style: {margin: 0}}, lib.label), h("span", {class: "muted small mono"}, `libraries/${id}.yaml`), h("span", {class: "spacer"}),
        h("button", {onclick: () => { const n = lib.entries.length; lib.entries.push({id: "custom_" + Date.now().toString(36), label: "New entry", orca_text: "", destination: lib.entries[0]?.destination || "keyword_line", applies_to: ["all"], tags: [], notes: "", order: (n + 1) * 10, hidden: false, favorite: false}); draw(); }}, "+ Add entry"),
        h("button", {class: "primary", onclick: async () => { await App.put(`/api/libraries/${id}`, lib); App.toast("Saved"); App.route(); }}, "Save list")),
      h("div", {style: {overflowX: "auto", marginTop: "10px"}}, tbl)));
  },

  async columns(root) {
    const cols = await App.get("/api/columns");
    const libs = await App.get("/api/libraries");
    root.append(h("div", {class: "card"},
      h("div", {class: "row"}, h("h2", {style: {margin: 0}}, "Column library"), h("span", {class: "spacer"}),
        h("button", {class: "primary", onclick: () => Lib.editColumn(null, libs)}, "+ New column")),
      h("p", {class: "help"}, "Columns are the settings you can add to a calculation profile. Dropdown columns take their ORCA text from a library list; other columns use a write template where {value} is the cell value."),
      h("table", null, h("tr", null, ["Label", "Type", "Writes", "Applies to", ""].map(x => h("th", null, x))),
        Object.values(cols).sort((a, b) => a.label.localeCompare(b.label)).map(c => h("tr", {class: "clickable", onclick: () => Lib.editColumn(c, libs)},
          h("td", null, c.label, (c.tags || []).includes("unverified") ? h("span", {class: "unverified", style: {marginLeft: "6px"}}, "unverified") : null),
          h("td", null, c.type + (c.multi ? " (multi)" : "")),
          h("td", {class: "mono small"}, c.special ? `(${c.special})` : c.type === "dropdown" ? `list: ${(c.library || []).join(", ")}` : `${c.destination || "keyword_line"}: ${(c.template || "").replace(/\n/g, " ⏎ ")}`),
          h("td", {class: "small"}, (c.applies_to || []).join(", ")),
          h("td", null, c.builtin ? h("span", {class: "small muted"}, "built-in") : null))))));
  },

  async editColumn(c, libs) {
    const isNew = !c;
    c = c ? clone(c) : {label: "", type: "number", destination: "block:scf", template: "", applies_to: ["all"], default: "", slot: "extras"};
    const body = Lib.columnForm(c, libs);
    const actions = [{label: "Cancel", value: null}];
    if (!isNew && !c.builtin) actions.unshift({label: "Delete", class: "danger", onclick: async () => { await App.del(`/api/columns/${c.id}`); return true; }});
    actions.push({label: "Save", class: "primary", onclick: async () => {
      if (!c.label) { App.toast("Give the column a name", "error"); return false; }
      return isNew ? await App.post("/api/columns", c) : await App.put(`/api/columns/${c.id}`, c);
    }});
    const r = await App.modal(isNew ? "New column" : `Column: ${c.label}`, body, actions);
    if (r) App.route();
    return r;
  },

  columnForm(c, libs) {
    const f = (k, attrs = {}) => { const el = h(attrs.rows ? "textarea" : "input", Object.assign({value: c[k] ?? ""}, attrs)); el.addEventListener("input", () => c[k] = el.value); return el; };
    const libSel = h("select", {multiple: true, size: 6, style: {width: "100%"}});
    for (const l of libs) { const o = h("option", {value: l.id}, l.label); if ((c.library || []).includes(l.id)) o.selected = true; libSel.append(o); }
    libSel.addEventListener("change", () => c.library = [...libSel.selectedOptions].map(o => o.value));
    const applies = h("input", {value: (c.applies_to || ["all"]).join(", "), style: {width: "100%"}});
    applies.addEventListener("input", () => c.applies_to = applies.value.split(",").map(x => x.trim()).filter(Boolean));
    const dd = h("div", null, h("label", {class: "f"}, "Library list(s)", libSel),
      h("label", {class: "row small"}, h("input", {type: "checkbox", checked: c.multi, onchange: e => c.multi = e.target.checked}), "allow several choices"));
    const tplBox = h("div", null,
      h("label", {class: "f"}, "Destination", W.select(Lib.DESTS.filter(d => d !== "none"), c.destination || "keyword_line", v => c.destination = v)),
      h("label", {class: "f"}, "Write template ({value} = cell value)", f("template", {rows: 3})));
    const show = () => { dd.classList.toggle("hidden", c.type !== "dropdown"); tplBox.classList.toggle("hidden", c.type === "dropdown" || !!c.special); };
    const typeSel = W.select([{value: "dropdown", label: "Dropdown (from a library list)"}, {value: "number", label: "Number"}, {value: "toggle", label: "On/off"}, {value: "text", label: "Free text"}], c.type, v => { c.type = v; show(); });
    show();
    return h("div", {style: {display: "grid", gap: "10px"}},
      h("label", {class: "f"}, "Name (column header)", f("label")),
      h("label", {class: "f"}, "Type", typeSel), dd, tplBox,
      h("label", {class: "f"}, "Keyword position (for keyword-line text)", W.select(["job", "method", "dispersion", "basis", "aux", "ri", "relativistic", "scf", "grid", "solvent", "properties", "extras"], c.slot || "extras", v => c.slot = v)),
      h("label", {class: "f"}, "Applies to step types (ids or kinds, 'all', '!xtb' to exclude)", applies),
      h("label", {class: "f"}, "Default value for new profiles", f("default")),
      h("label", {class: "f"}, "Notes", f("notes")),
      c.special ? h("div", {class: "msg info"}, `This column is handled by the app (${c.special}).`) : null);
  },
};
