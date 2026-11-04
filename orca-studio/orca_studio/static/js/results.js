// Results tab (section 13): main table, sub-tables, sorting, filtering, flags, exports.
"use strict";

const Results = {
  INT_COLS: ["atom", "atom1", "atom2", "state", "mult", "mode", "index"],
  async tab(body, b, tab) {
    if (tab === "results") return Results.render(body, b);
    if (tab === "spectra" && typeof Spectra !== "undefined") return Spectra.render(body, b);
    if (tab === "visuals" && typeof Visuals !== "undefined") return Visuals.batch(body, b);
    body.append(h("p", {class: "muted"}, "Not available."));
  },

  fmt(v, f) {
    if (v === null || v === undefined) return "";
    if (typeof v === "boolean") return v ? "yes" : "no";
    if (typeof v === "number") return Number.isInteger(v) && f.unit_kind === "none" ? String(v) : v.toFixed(f.decimals ?? 6);
    return String(v);
  },

  async render(body, b) {
    const eps = await App.get("/api/items/extraction_profiles");
    let res = await App.get(`/api/batches/${b.id}/results`);
    const st = {sort: null, dir: 1, filter: "", table: null};
    const bar = h("div", {class: "row", style: {marginBottom: "8px"}});
    const main = h("div");
    const sub = h("div");
    body.append(bar, main, sub);
    const epSel = W.select(eps.map(e => ({value: e.id, label: e.name || e.id})), b.extraction_profile_id || "standard", async v => {
      res = await App.post(`/api/batches/${b.id}/extract`, {extraction_profile_id: v}); b.extraction_profile_id = v; draw();
    });
    const exp = (kind) => W.download(`/api/batches/${b.id}/export/${kind}`);
    bar.append(h("span", {class: "small muted"}, "Extraction profile"), epSel,
      h("button", {onclick: async () => { res = await App.post(`/api/batches/${b.id}/extract`, {}); App.toast("Extraction done"); draw(); }}, "Re-extract"),
      h("input", {placeholder: "Filter molecules…", oninput: e => { st.filter = e.target.value.toLowerCase(); draw(); }}),
      h("span", {class: "spacer"}),
      h("button", {onclick: () => exp("csv")}, "CSV"), h("button", {onclick: () => exp("xlsx")}, "Excel"),
      h("button", {onclick: () => exp("geometries")}, "Geometries (zip)"), h("button", {onclick: () => exp("si")}, "SI file"),
      h("button", {onclick: () => exp("citations")}, "Citations"),
      h("button", {title: "Write CSV and Excel into the batch results folder", onclick: async () => {
        const a = await App.get(`/api/batches/${b.id}/export/csv?save=1`); const c = await App.get(`/api/batches/${b.id}/export/xlsx?save=1`);
        App.toast(`Saved:\n${a.path}\n${c.path}`);
      }}, "Save to results folder"));

    function draw() {
      main.innerHTML = ""; sub.innerHTML = "";
      const scal = res.fields.filter(f => f.shape !== "table");
      const tabs = res.fields.filter(f => f.shape === "table");
      let rows = res.rows.filter(r => !st.filter || r.name.toLowerCase().includes(st.filter) || (r.formula || "").toLowerCase().includes(st.filter));
      if (st.sort) {
        const key = st.sort;
        rows = [...rows].sort((a, c) => {
          const va = key === "name" ? a.name : a.values[key]?.v, vc = key === "name" ? c.name : c.values[key]?.v;
          if (va == null) return 1; if (vc == null) return -1;
          return (va > vc ? 1 : va < vc ? -1 : 0) * st.dir;
        });
      }
      const th = (key, label, unit) => h("th", {style: {cursor: "pointer"}, onclick: () => { st.dir = st.sort === key ? -st.dir : 1; st.sort = key; draw(); }},
        label, unit ? h("div", {class: "small", style: {fontWeight: 400}}, unit) : null, st.sort === key ? (st.dir > 0 ? " ▲" : " ▼") : "");
      main.append(h("div", {class: "card", style: {padding: 0, overflowX: "auto"}}, h("table", null,
        h("tr", null, th("name", "Molecule"), h("th", null, "Formula"), scal.map(f => th(f.id, f.name, f.unit))),
        rows.map(r => h("tr", null,
          h("td", null, h("a", {href: `#/batch/${b.id}/mol/${r.molecule_id}`}, r.name), r.status === "failed" ? h("span", {class: "pill st-failed", style: {marginLeft: "4px"}}, "failed") : null),
          h("td", {class: "mono small"}, r.formula),
          scal.map(f => {
            const c = r.values[f.id] || {};
            const fl = (c.flags || []).filter(x => x !== "grey");
            return h("td", {class: "num" + (fl.length ? " flag-" + fl[fl.length - 1] : ""), title: c.err || ""}, c.err && c.v == null ? h("span", {class: "muted small"}, c.err === "no output yet" ? "…" : "n/a") : Results.fmt(c.v, f));
          }))))));
      if (!res.rows.length) main.append(h("p", {class: "muted"}, "No molecules."));
      if (tabs.length) {
        if (!st.table || !tabs.find(t => t.id === st.table)) st.table = tabs[0].id;
        sub.append(h("h2", null, "Sub-tables"), W.tabs(tabs.map(t => [t.id, t.name]), st.table, t => { st.table = t; draw(); }));
        const f = tabs.find(t => t.id === st.table);
        let data = res.tables[st.table] || [];
        if (st.filter) data = data.filter(x => x.molecule.toLowerCase().includes(st.filter));
        const cols = [];
        for (const x of data) for (const k of Object.keys(x)) if (!cols.includes(k) && typeof x[k] !== "object") cols.push(k);
        const isCharge = /charge|spin/.test(cols.join(" ")) && cols.includes("atom");
        sub.append(h("div", {class: "row", style: {marginBottom: "6px"}}, h("span", {class: "small muted"}, `${data.length} rows`),
          isCharge ? h("span", {class: "row small"}, "Charge files:", ...res.rows.map(r => h("span", null, r.name + " ",
            h("a", {href: `/api/batches/${b.id}/charges/${r.molecule_id}?field=${f.id}&fmt=pqr`}, "pqr"), " ",
            h("a", {href: `/api/batches/${b.id}/charges/${r.molecule_id}?field=${f.id}&fmt=mol2`}, "mol2")))) : null));
        sub.append(h("div", {class: "card", style: {padding: 0, overflowX: "auto", maxHeight: "60vh"}}, h("table", null,
          h("tr", null, cols.map(c => h("th", null, c))),
          data.slice(0, 3000).map(x => h("tr", null, cols.map(c => h("td", {class: typeof x[c] === "number" ? "num" : ""}, typeof x[c] === "number" ? (Results.INT_COLS.includes(c) ? x[c] : x[c].toFixed(c.includes("nm") || c.includes("cm") || c === "freq" ? 2 : 5)) : String(x[c] ?? ""))))))));
      }
    }
    draw();
  },
};
