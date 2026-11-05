// Multiwfn recipes (section 12.2): record in a browser terminal, turn output lines into rules, re-test.
"use strict";

const MW = {
  async xterm() {
    if (!window.Terminal) { await App.loadScript("/static/vendor/xterm.js"); await App.loadScript("/static/vendor/addon-fit.js"); }
  },

  async list(box) {
    const recs = await App.get("/api/items/multiwfn_recipes");
    box.append(h("h2", null, "Multiwfn recipes"),
      h("p", {class: "help"}, "Multiwfn is menu-driven, so a recipe is the list of menu answers you give it, recorded once on a sample molecule. Lines of its output become extraction fields (Extraction profiles → + Multiwfn result). After a Multiwfn update, press Re-test: menu numbers can change between versions."),
      h("div", {class: "row", style: {marginBottom: "8px"}}, h("a", {class: "btn primary", href: "#/scripts/record"}, "Record a new recipe"),
        h("button", {onclick: async e => {
          e.target.disabled = true; const r = await App.post("/api/multiwfn/retest_all"); e.target.disabled = false;
          App.modal("Re-test results", h("div", null, r.map(x => h("div", {class: "msg " + (x.ok ? "ok" : "error")}, `${x.id}: ${x.message}` + (x.version_now ? ` (recorded with ${x.version_recorded}, now ${x.version_now})` : "")))), [{label: "Close"}]);
        }}, "Re-test all recipes")),
      h("div", {class: "card", style: {padding: 0}}, recs.length ? h("table", null, h("tr", null, ["Recipe", "Answers", "Results", "Multiwfn version", "Recorded"].map(x => h("th", null, x))),
        recs.map(r => h("tr", {class: "clickable", onclick: () => location.hash = `#/scripts/recipe/${r.id}`},
          h("td", null, h("b", null, r.name || r.id), r.closed_shell_only ? h("span", {class: "pill", style: {marginLeft: "6px"}}, "closed-shell only") : null),
          h("td", {class: "mono small"}, (r.answers || []).join(" ⏎ ")),
          h("td", {class: "small"}, (r.rules || []).map(x => x.label).join(", ")),
          h("td", {class: "small"}, r.multiwfn_version || ""), h("td", {class: "small muted"}, r.recorded || "")))) :
        h("p", {class: "muted", style: {padding: "12px"}}, "No recipes yet. Ideas to record: ESP surface analysis (main function 12), hole-electron analysis (18 → 1), ADCH / CM5 / Becke / Hirshfeld-I charges (7), orbital composition, QTAIM critical points, NCI/IGMH, ELF/LOL, bond orders, HOMA, DOS/PDOS.")));
  },

  // ------------------------------------------------------------------ record
  async record(main) {
    main.append(h("div", {class: "row"}, h("a", {href: "#/scripts"}, "← Scripts")), h("h1", null, "Record a Multiwfn recipe"));
    const st = await App.get("/api/settings");
    if (!st.settings.programs.multiwfn) { main.append(h("div", {class: "msg error"}, "Set the Multiwfn program in Settings first.")); return; }
    const stepBox = h("div", {class: "card"});
    main.append(stepBox);
    const batches = await App.get("/api/batches");
    let mid = null;
    const molSel = h("select");
    const bSel = W.select([{value: "", label: "choose a batch…"}, ...batches.map(b => ({value: b.id, label: b.name}))], "", async v => {
      molSel.innerHTML = ""; if (!v) return;
      const b = await App.get(`/api/batches/${v}`);
      for (const m of b.molecules) molSel.append(h("option", {value: m.id}, m.name));
      mid = b.molecules[0]?.id;
    });
    molSel.onchange = () => mid = +molSel.value;
    const up = h("input", {type: "file", accept: ".molden,.input,.wfn,.wfx,.fch,.fchk"});
    stepBox.append(h("h2", {style: {marginTop: 0}}, "1. Sample molecule"),
      h("p", {class: "help"}, "Pick a finished molecule (its .gbw is converted to .molden with orca_2mkl) or upload a .molden file. Use a small molecule."),
      h("div", {class: "row"}, bSel, molSel, h("span", {class: "muted"}, "or"), up,
        h("button", {class: "primary", onclick: async () => {
          let s;
          if (up.files.length) { const fd = new FormData(); fd.append("file", up.files[0]); s = await App.api("POST", "/api/multiwfn/record/upload", fd); }
          else if (mid) s = await App.post("/api/multiwfn/record/start", {molecule_id: mid});
          else return App.toast("Choose a molecule or a file", "error");
          stepBox.remove(); MW.terminal(main, s);
        }}, "Start Multiwfn")));
  },

  async terminal(main, s) {
    await MW.xterm();
    const termEl = h("div", {class: "term"});
    const card = h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "2. Click through the menus"),
      h("p", {class: "help"}, `Multiwfn is running on ${s.sample}. Type your answers as usual; each line you enter is recorded. Exit Multiwfn with q (or press Finish).`),
      termEl, h("div", {class: "row", style: {marginTop: "8px"}}, h("button", {class: "primary", onclick: () => finish()}, "Finish recording")));
    main.append(card);
    const term = new Terminal({fontSize: 13, convertEol: false, cursorBlink: true, scrollback: 5000});
    const fit = new FitAddon.FitAddon();
    term.loadAddon(fit);
    term.open(termEl);
    fit.fit();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/multiwfn/record/${s.id}`);
    ws.onopen = () => ws.send(JSON.stringify({type: "resize", rows: term.rows, cols: term.cols}));
    ws.onmessage = e => { const m = JSON.parse(e.data); if (m.type === "out") term.write(m.data); else if (m.type === "exit") { term.write("\r\n[Multiwfn finished]\r\n"); finish(); } };
    term.onData(d => ws.readyState === 1 && ws.send(JSON.stringify({type: "in", data: d})));
    term.focus();
    let finished = false;
    const finish = async () => {
      if (finished) return; finished = true;
      if (ws.readyState === 1) ws.send(JSON.stringify({type: "stop"}));
      setTimeout(() => ws.close(), 500);
      const rec = await App.get(`/api/multiwfn/record/${s.id}`);
      card.querySelector(".row").remove();
      MW.build(main, {id: null, name: "", answers: rec.answers, rules: [], citations: [], multiwfn_version: rec.version}, rec.output, s.id);
    };
  },

  // ------------------------------------------------------------------ rules from output lines
  build(main, r, output, session) {
    const box = h("div", {class: "card"});
    main.append(box);
    const lines = (output || "").split("\n");
    const answers = h("textarea", {rows: Math.min(14, Math.max(4, r.answers.length + 1))}, r.answers.join("\n"));
    const name = h("input", {value: r.name || "", placeholder: "e.g. ESP surface analysis", style: {width: "100%"}});
    const cites = h("textarea", {rows: 3, placeholder: "One reference per line (the main Multiwfn paper is added automatically)"}, (r.citations || []).filter(c => !c.includes("jcc.22885")).join("\n"));
    const closed = h("input", {type: "checkbox", checked: r.closed_shell_only});
    const warn = h("input", {value: r.warnings || "", placeholder: "e.g. heavy elements with ECPs need Molden2AIM", style: {width: "100%"}});
    const rulesBox = h("div");
    const drawRules = () => {
      rulesBox.innerHTML = "";
      if (!r.rules.length) { rulesBox.append(h("p", {class: "muted small"}, "No results yet: click a line of the output that holds a value.")); return; }
      rulesBox.append(h("table", null, h("tr", null, ["Result", "Anchor text", "Takes", ""].map(x => h("th", null, x))),
        r.rules.map((x, i) => h("tr", null, h("td", null, x.label), h("td", {class: "mono small"}, x.anchor),
          h("td", {class: "small"}, x.table ? `table: ${x.columns.join(", ")}` : `number ${x.column} (${x.occurrence || "last"})`),
          h("td", null, h("button", {class: "small", onclick: async () => {
            const t = await App.post("/api/multiwfn/test_rule", {rule: x, session, recipe: session ? null : r.id, text: session || r.id ? undefined : output});
            App.toast(`${x.label}: ${JSON.stringify(t.value)?.slice(0, 300)}`);
          }}, "Test"), h("button", {class: "small danger", onclick: () => { r.rules.splice(i, 1); drawRules(); }}, "✕"))))));
    };
    const outBox = h("div", {class: "outline-lines"}, lines.map((ln, i) => h("div", {onclick: () => MW.ruleDialog(lines, i, r, drawRules)}, `${String(i + 1).padStart(5)}  ${ln}`)));
    box.append(h("h2", {style: {marginTop: 0}}, session ? "3. Make the recipe" : "Recipe"),
      h("div", {class: "cols"},
        h("div", null,
          h("label", {class: "f"}, "Name", name),
          h("label", {class: "f", style: {marginTop: "8px"}}, "Menu answers, one per line ({molden} = the input file)", answers),
          h("label", {class: "row small", style: {marginTop: "6px"}}, closed, "supports closed-shell molecules only"),
          h("label", {class: "f", style: {marginTop: "6px"}}, "Warning shown with the recipe", warn),
          h("label", {class: "f", style: {marginTop: "6px"}}, "Citations", cites),
          h("h3", null, "Results taken from the output"), rulesBox),
        h("div", null, h("h3", {style: {marginTop: 0}}, "Output (click a line holding a result)"), outBox)),
      h("div", {class: "row", style: {marginTop: "12px"}}, h("span", {class: "spacer"}),
        r.id ? h("button", {onclick: async () => {
          const t = await App.post(`/api/multiwfn/recipes/${r.id}/retest`);
          App.modal("Re-test", h("div", null, h("div", {class: "msg " + (t.ok ? "ok" : "error")}, t.message),
            h("table", null, (t.rules || []).map(x => h("tr", null, h("td", null, x.rule), h("td", {class: "small mono"}, JSON.stringify(x.recorded)?.slice(0, 120)), h("td", {class: "small mono"}, JSON.stringify(x.now)?.slice(0, 120))))),
            t.diff && t.diff.length ? h("pre", {style: {maxHeight: "40vh", marginTop: "8px"}}, t.diff.join("\n")) : null), [{label: "Close"}], true);
        }}, "Re-test on the stored sample") : null,
        h("button", {class: "primary", onclick: async () => {
          if (!name.value.trim()) return App.toast("Give the recipe a name", "error");
          const rec = Object.assign({}, r, {name: name.value.trim(), answers: answers.value.split("\n").map(x => x.trimEnd()).filter((x, i, a) => x !== "" || i < a.length - 1),
            citations: cites.value.split("\n").map(x => x.trim()).filter(Boolean), closed_shell_only: closed.checked, warnings: warn.value});
          const saved = await App.post("/api/multiwfn/recipes", {session, recipe: rec});
          App.toast("Recipe saved"); location.hash = `#/scripts/recipe/${saved.id}`;
        }}, "Save recipe")));
    drawRules();
  },

  async ruleDialog(lines, i, r, redraw) {
    const ln = lines[i];
    const nums = ln.match(/[-+]?\d+\.\d+(?:[EeDd][-+]?\d+)?|[-+]?\d+/g) || [];
    const firstNum = ln.search(/[-+]?\d/);
    const rule = {id: "", label: "", anchor: (firstNum > 0 ? ln.slice(0, firstNum) : ln).trim(), column: 1, occurrence: "last", table: false, columns: ["value"]};
    const anchor = h("input", {value: rule.anchor, style: {width: "100%"}, oninput: e => rule.anchor = e.target.value});
    const label = h("input", {placeholder: "e.g. Surface minimum (kcal/mol)", style: {width: "100%"}, oninput: e => rule.label = e.target.value});
    const after = rule.anchor ? ln.slice(ln.indexOf(rule.anchor) + rule.anchor.length) : ln;
    const numsAfter = after.match(/[-+]?\d+\.\d+(?:[EeDd][-+]?\d+)?|[-+]?\d+/g) || [];
    const chips = h("div", {class: "chips"}, numsAfter.map((n, k) => h("span", {class: "chip" + (k === 0 ? " on" : ""), onclick: e => {
      rule.column = k + 1; chips.querySelectorAll(".chip").forEach(c => c.classList.remove("on")); e.target.classList.add("on");
    }}, n)));
    const cols = h("input", {placeholder: "column names, e.g. atom charge", style: {width: "100%"}, oninput: e => rule.columns = e.target.value.split(/\s+/).filter(Boolean)});
    const mode = W.select([{value: "value", label: "One number on this line"}, {value: "table", label: "A table that starts after this line"}], "value", v => {
      rule.table = v === "table"; one.classList.toggle("hidden", rule.table); tab.classList.toggle("hidden", !rule.table);
    });
    const one = h("div", null, h("div", {class: "small muted"}, "Which number (after the anchor text)?"), chips,
      h("label", {class: "f"}, "If the line appears several times, use", W.select(["last", "first"], "last", v => rule.occurrence = v)));
    const tab = h("div", {class: "hidden"}, h("label", {class: "f"}, "Column names for the numbers on each row (from the left)", cols),
      h("label", {class: "f"}, "Atom/label pattern (optional regular expression with one group)", h("input", {placeholder: "e.g. Atom:\\s+\\d+(\\w+)", style: {width: "100%"}, oninput: e => rule.label_regex = e.target.value})));
    const ok = await App.modal("New result from this line", h("div", {style: {display: "grid", gap: "8px"}},
      h("pre", null, ln), h("label", {class: "f"}, "Name of the result", label), h("label", {class: "f"}, "Anchor text (identifies the line)", anchor), mode, one, tab),
      [{label: "Cancel", value: false}, {label: "Add", class: "primary", value: true}]);
    if (!ok) return;
    rule.label = rule.label || rule.anchor;
    rule.id = rule.label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "r" + (r.rules.length + 1);
    while (r.rules.some(x => x.id === rule.id)) rule.id += "_2";
    r.rules.push(rule);
    redraw();
  },

  async editor(main, id) {
    const r = await App.get(`/api/items/multiwfn_recipes/${id}`);
    main.append(h("div", {class: "row"}, h("a", {href: "#/scripts"}, "← Scripts")), h("h1", null, r.name || id),
      h("p", {class: "help"}, `Recorded ${r.recorded || "?"} with Multiwfn ${r.multiwfn_version || "?"}.`));
    let output = "";
    if (r.sample && r.sample.output) { try { output = await App.get(`/api/file?path=${encodeURIComponent(r.sample.output)}`); } catch (e) { /* missing sample */ } }
    MW.build(main, r, output, null);
    main.append(h("div", {class: "card"}, h("h2", {style: {marginTop: 0}}, "Run on a molecule"), h("div", {id: "mw-run"})));
    const batches = await App.get("/api/batches");
    let mid = null;
    const molSel = h("select", {onchange: e => mid = +e.target.value});
    const out = h("div");
    document.getElementById("mw-run").append(h("div", {class: "row"},
      W.select([{value: "", label: "choose a batch…"}, ...batches.map(b => ({value: b.id, label: b.name}))], "", async v => {
        molSel.innerHTML = ""; if (!v) return; const b = await App.get(`/api/batches/${v}`);
        for (const m of b.molecules) molSel.append(h("option", {value: m.id}, m.name)); mid = b.molecules[0]?.id;
      }), molSel, h("button", {onclick: async () => {
        if (!mid) return; out.innerHTML = "Running…";
        const res = await App.post(`/api/multiwfn/recipes/${id}/run`, {molecule_id: mid});
        out.innerHTML = "";
        out.append(h("div", {class: "kv"}, res.rules.flatMap(x => [x.label, JSON.stringify(x.value)?.slice(0, 200)])), h("pre", {style: {maxHeight: "40vh", marginTop: "8px"}}, res.output));
      }}, "Run")), out);
    if (!r.builtin) main.append(h("button", {class: "danger", onclick: async () => { if (await App.confirm("Delete recipe", `Delete "${r.name}"?`, "Delete", true)) { await App.del(`/api/items/multiwfn_recipes/${id}`); location.hash = "#/scripts"; } }}, "Delete recipe"));
  },
};
