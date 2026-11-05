// Visuals (section 11): orbital picker, densities, MEP, charges on atoms, batch figure grids and snapshots.
"use strict";

const Visuals = {
  async cubeText(path) { return App.get(`/api/file?path=${encodeURIComponent(path)}`); },

  colorBar(range, label = "ESP (a.u.)") {
    const r = (+range).toFixed(3);
    return h("div", {style: {marginTop: "6px"}},
      h("div", {style: {height: "12px", borderRadius: "3px", background: "linear-gradient(90deg, #d7191c, #ffffff, #2b6cb0)"}}),
      h("div", {class: "row small muted", style: {justifyContent: "space-between"}}, h("span", null, "−" + r), h("span", null, label), h("span", null, "+" + r)));
  },

  // ------------------------------------------------------------------ molecule detail panel
  async panel(root, b, m, vbox) {
    const steps = (await App.get(`/api/molecules/${m.id}/steps`)).filter(s => s.gbw);
    const card = h("div", {class: "card"});
    root.append(card);
    card.append(h("h2", {style: {marginTop: 0}}, "Orbitals, densities and MEP"));
    if (!steps.length) { card.append(h("p", {class: "muted small"}, "No finished step with a kept .gbw file yet.")); return; }
    const st = {step: steps[steps.length - 1].step, spin: 0, grid: 80, iso: 0.03, chosen: new Set(["HOMO", "LUMO"]), current: null};
    const chipsBox = h("div"), cubeList = h("div"), status = h("div"), info = h("div", {class: "small"});
    const isoLabel = h("span", {class: "small mono"}, st.iso);
    const iso = h("input", {type: "range", min: 0.005, max: 0.1, step: 0.005, value: st.iso, style: {width: "200px"}, oninput: () => {
      st.iso = +iso.value; isoLabel.textContent = st.iso; if (st.current && st.current.kind !== "mep") Visuals.showCube(vbox, st.current, st.iso);
    }});
    card.append(h("div", {class: "row"},
      h("label", {class: "f"}, "Step", W.select(steps.map(s => ({value: s.step, label: `${s.step + 1}. ${s.name}`})), st.step, v => { st.step = +v; load(); })),
      h("label", {class: "f"}, "Grid points", W.select([{value: 80, label: "80 (preview)"}, {value: 120, label: "120 (figures)"}], st.grid, v => st.grid = +v)),
      h("label", {class: "f"}, "Isovalue", h("span", {class: "row"}, iso, isoLabel))),
      chipsBox, status, cubeList, info);

    async function load() {
      chipsBox.innerHTML = ""; cubeList.innerHTML = ""; status.innerHTML = "";
      let orb;
      try { orb = await App.get(`/api/molecules/${m.id}/orbitals?step=${st.step}`); } catch (e) { return; }
      const labels = ["HOMO-5", "HOMO-4", "HOMO-3", "HOMO-2", "HOMO-1", "HOMO", "LUMO", "LUMO+1", "LUMO+2", "LUMO+3", "LUMO+4", "LUMO+5"];
      const spinName = st.spin ? "beta" : "alpha";
      const sp = orb.spins[spinName] || orb.spins.alpha;
      const energy = l => (sp.orbitals.find(o => o.label === l) || {}).e_ev;
      const chips = h("div", {class: "chips"}, labels.map(l => h("span", {class: "chip" + (st.chosen.has(l) ? " on" : ""), title: energy(l) != null ? `${energy(l).toFixed(3)} eV` : "",
        onclick: e => { st.chosen.has(l) ? st.chosen.delete(l) : st.chosen.add(l); e.target.classList.toggle("on"); }}, l)));
      const range = h("input", {placeholder: "or a range: HOMO-3 to LUMO+3", style: {width: "220px"}});
      chipsBox.append(h("h3", null, "Orbitals"), chips, h("div", {class: "row", style: {marginTop: "6px"}}, range,
        !orb.restricted ? W.select([{value: 0, label: "α (alpha)"}, {value: 1, label: "β (beta)"}], st.spin, v => { st.spin = +v; load(); }) : null,
        h("button", {class: "primary", onclick: async () => {
          const items = [...st.chosen].map(l => ({kind: "mo", label: l, operator: st.spin}));
          if (range.value.trim()) items.push({kind: "mo", label: range.value.trim(), operator: st.spin});
          await make(items);
        }}, "Make orbital cubes")),
        h("h3", null, "Densities and potentials"),
        h("div", {class: "row"},
          h("button", {onclick: () => make([{kind: "density"}])}, "Electron density"),
          !orb.restricted ? h("button", {onclick: () => make([{kind: "spin_density"}])}, "Spin density") : null,
          h("button", {onclick: mep}, "MEP (density + ESP)")),
        orb.states.length ? h("div", {class: "row", style: {marginTop: "6px"}}, h("span", {class: "small"}, "TDDFT state"),
          (() => { const s = W.select(orb.states.map(x => ({value: x.state, label: `${x.state} (${x.energy_ev.toFixed(2)} eV, f=${(x.fosc ?? 0).toFixed(3)})`})), 1, v => st.state = +v); st.state = 1; return s; })(),
          h("button", {onclick: () => make([{kind: "tddft_difference", state: st.state}])}, "Difference density"),
          h("button", {onclick: () => make([{kind: "tddft_transition", state: st.state}])}, "Transition density")) : null,
        h("h3", null, "Atoms coloured by charge"),
        await Visuals.chargePicker(b, m, vbox),
        h("h3", null, "Cubes not appearing?"),
        h("div", {class: "row"}, h("button", {class: "small", onclick: async e => {
          e.target.disabled = true; e.target.textContent = "Testing both ways of making cubes (about a minute)…";
          const r = await App.post(`/api/molecules/${m.id}/cube_diagnose`, {step: st.step});
          e.target.disabled = false; e.target.textContent = "Diagnose cubes";
          const txt = JSON.stringify(r, null, 1);
          App.modal("Cube diagnosis", h("div", null, h("div", {class: "msg " + (r.ok ? "ok" : "error")}, r.summary),
            h("p", {class: "help"}, "Copy this text (or send the file " + (r.report_file || "") + ") so the menu answers or the %plots text can be corrected."),
            h("button", {class: "small", onclick: () => navigator.clipboard?.writeText(txt).then(() => App.toast("Copied"))}, "Copy everything"),
            h("pre", {style: {maxHeight: "55vh", marginTop: "6px"}}, txt)), [{label: "Close"}], true);
        }}, "Diagnose cubes")),
        h("div", {class: "row", style: {marginTop: "6px"}}, h("button", {class: "small", title: "Runs orca_chelpg on the saved .gbw; no need to rerun the job", onclick: async () => {
          const r = await App.post(`/api/molecules/${m.id}/chelpg`, {step: st.step});
          App.toast(`CHELPG charges added (${r.charges.length} atoms). Use a CHELPG charges field to see them in Results.`);
        }}, "Add CHELPG charges afterwards (orca_chelpg)")));
      await listCubes();
    }
    async function make(items) {
      status.innerHTML = ""; status.append(h("div", {class: "msg info"}, "Running orca_plot…"));
      const r = await App.post(`/api/molecules/${m.id}/cubes`, {step: st.step, grid: st.grid, items});
      status.innerHTML = "";
      for (const e of r.errors) status.append(h("div", {class: "msg error"}, e));
      await listCubes();
      if (r.cubes.length) Visuals.showCube(vbox, st.current = r.cubes[r.cubes.length - 1], st.iso);
    }
    async function mep() {
      status.innerHTML = ""; status.append(h("div", {class: "msg info"}, "Making density and ESP cubes…"));
      const r = await App.post(`/api/molecules/${m.id}/mep`, {step: st.step, grid: st.grid});
      status.innerHTML = "";
      const rng = (await App.get(`/api/batches/${b.id}/mep_range`)).range || Math.max(Math.abs(r.extrema.vmin_au), Math.abs(r.extrema.vmax_au));
      st.current = {kind: "mep"};
      Viewer.show(vbox, await App.get(`/api/molecules/${m.id}/xyz?step=${st.step}`));
      Viewer.addMEP(vbox, await Visuals.cubeText(r.density), await Visuals.cubeText(r.esp), 0.001, rng);
      const e = r.extrema;
      info.innerHTML = "";
      info.append(Visuals.colorBar(rng), h("div", {class: "kv", style: {marginTop: "6px"}},
        "V_min", `${e.vmin_au.toFixed(4)} a.u. (${(e.vmin_au * 627.5095).toFixed(1)} kcal/mol) near ${e.vmin_atom.element}${e.vmin_atom.atom}`,
        "V_max", `${e.vmax_au.toFixed(4)} a.u. (${(e.vmax_au * 627.5095).toFixed(1)} kcal/mol) near ${e.vmax_atom.element}${e.vmax_atom.atom}`,
        "Route", r.route || "", "Colour range", "fixed for the whole batch"));
      await listCubes();
    }
    async function listCubes() {
      const cubes = await App.get(`/api/molecules/${m.id}/cubes?step=${st.step}`);
      cubeList.innerHTML = "";
      if (!cubes.length) return;
      cubeList.append(h("h3", null, "Cubes for this step"), h("div", {class: "chips"}, cubes.map(c => h("span", {class: "chip", onclick: () => { st.current = c; Visuals.showCube(vbox, c, st.iso); }}, c.name.replace(".cube", "")))),
        h("div", {class: "row", style: {marginTop: "8px"}}, h("button", {class: "small", onclick: () => {
          const v = vbox._viewer; if (!v) return; const a = h("a", {href: v.pngURI(), download: `${m.name}.png`}); document.body.append(a); a.click(); a.remove();
        }}, "Download picture (PNG)")));
    }
    await load();
  },

  async showCube(vbox, c, iso) {
    const v = vbox._viewer;
    if (!v) return;
    const txt = await Visuals.cubeText(c.path);
    v.removeAllShapes();
    if (c.kind === "density" || c.kind === "spin_density") {
      const vol = new $3Dmol.VolumeData(txt, "cube");
      v.addIsosurface(vol, {isoval: c.kind === "density" ? Math.max(iso / 10, 0.001) : iso / 3, color: "#64748b", opacity: 0.6});
      if (c.kind === "spin_density") v.addIsosurface(vol, {isoval: -iso / 3, color: "#f59e0b", opacity: 0.6});
      v.render();
    } else Viewer.addOrbital(vbox, txt, iso);
  },

  async chargePicker(b, m, vbox) {
    const res = await App.get(`/api/batches/${b.id}/results`);
    const tabs = res.fields.filter(f => f.shape === "table" && (res.tables[f.id] || []).some(r => r.molecule === m.name && r.charge !== undefined));
    if (!tabs.length) return h("div", {class: "small muted"}, "Add a charges field to the extraction profile to colour atoms by charge.");
    return h("div", {class: "row"}, W.select([{value: "", label: "choose a charge table…"}, ...tabs.map(t => ({value: t.id, label: t.name}))], "", v => {
      if (!v) return;
      const rows = res.tables[v].filter(r => r.molecule === m.name).sort((a, c) => a.atom - c.atom);
      Viewer.colorByCharge(vbox, rows.map(r => r.charge));
    }), h("span", {class: "small muted"}, "red = negative, blue = positive"));
  },

  // ------------------------------------------------------------------ batch tab
  async batch(body, b) {
    const st = {what: "structure", label: "HOMO", grid: 80, iso: 0.03, cols: 4};
    const ctl = h("div", {class: "card"});
    const gridBox = h("div", {style: {display: "grid", gap: "10px"}});
    const prog = h("div");
    body.append(ctl, prog, gridBox);
    const labelSel = W.select(["HOMO-2", "HOMO-1", "HOMO", "LUMO", "LUMO+1", "LUMO+2"], st.label, v => st.label = v);
    ctl.append(h("p", {class: "help", style: {marginTop: 0}}, "Show every molecule with the same orientation, isovalue and colour range. Rotate the first one; the others follow."),
      h("div", {class: "row"},
        h("label", {class: "f"}, "Show", W.select([{value: "structure", label: "Structure"}, {value: "mo", label: "Orbital"}, {value: "mep", label: "MEP"}], st.what, v => st.what = v)),
        h("label", {class: "f"}, "Orbital", labelSel),
        h("label", {class: "f"}, "Grid", W.select([80, 120], st.grid, v => st.grid = +v)),
        h("label", {class: "f"}, "Isovalue", h("input", {type: "number", step: 0.005, value: st.iso, style: {width: "90px"}, oninput: e => st.iso = +e.target.value})),
        h("label", {class: "f"}, "Columns", h("input", {type: "number", min: 1, max: 8, value: st.cols, style: {width: "70px"}, oninput: e => st.cols = +e.target.value})),
        h("button", {onclick: generate}, "Make missing cubes for all"),
        h("button", {class: "primary", onclick: draw}, "Show"),
        h("button", {onclick: snapshots}, "Save snapshots (PNG per molecule)"),
        h("button", {onclick: figureGrid}, "Figure grid")));
    let viewers = [];

    async function generate() {
      const items = st.what === "mep" ? [{kind: "mep"}] : st.what === "mo" ? [{kind: "mo", label: st.label}] : [];
      if (!items.length) return App.toast("Choose Orbital or MEP first");
      await App.post(`/api/batches/${b.id}/cubes`, {items, grid: st.grid});
      const t = setInterval(async () => {
        const s = await App.get(`/api/batches/${b.id}/cubes/status`);
        prog.innerHTML = "";
        prog.append(h("div", {class: "msg " + (s.running ? "info" : "ok")}, s.running ? `Making cubes: ${s.done} / ${s.total}` : `Done (${s.done} / ${s.total})`),
          ...(s.errors || []).map(e => h("div", {class: "msg error"}, e)));
        if (!s.running) { clearInterval(t); draw(); }
      }, 1500);
      App.timers.push(t);
    }
    async function draw() {
      gridBox.innerHTML = ""; viewers = [];
      gridBox.style.gridTemplateColumns = `repeat(${st.cols}, 1fr)`;
      const mols = (await App.get(`/api/batches/${b.id}`)).molecules;
      const cubeName = st.what === "mep" ? "mep" : `${st.label}_a_g${st.grid}.cube`;
      const ov = st.what === "structure" ? mols.map(m => ({molecule_id: m.id, name: m.name})) : await App.get(`/api/batches/${b.id}/cube_overview?name=${encodeURIComponent(cubeName)}`);
      const rng = st.what === "mep" ? ((await App.get(`/api/batches/${b.id}/mep_range`)).range || 0.05) : null;
      for (const row of ov) {
        const el = h("div", {class: "viewer-small"});
        const cell = h("div", null, h("div", {class: "small", style: {fontWeight: 600, marginBottom: "2px"}}, row.name), el);
        gridBox.append(cell);
        Viewer.show(el, await App.get(`/api/molecules/${row.molecule_id}/xyz`));
        if (st.what === "mo" && row.path) Viewer.addOrbital(el, await Visuals.cubeText(row.path), st.iso);
        else if (st.what === "mep" && row.path) Viewer.addMEP(el, await Visuals.cubeText(row.path), await Visuals.cubeText(row.esp), 0.001, rng);
        else if (st.what !== "structure") el.append(h("div", {class: "small muted", style: {position: "absolute", top: "6px", left: "8px"}}, "no cube yet"));
        viewers.push({el, name: row.name});
      }
      if (rng) gridBox.before(Visuals.colorBar(rng));
      if (viewers.length > 1) {
        const lead = viewers[0].el._viewer;
        lead.setViewChangeCallback(view => viewers.slice(1).forEach(v => { v.el._viewer.setView(view); v.el._viewer.render(); }));
      }
    }
    async function snapshots() {
      if (!viewers.length) await draw();
      for (const v of viewers) {
        const png = v.el._viewer.pngURI();
        await App.post(`/api/batches/${b.id}/snapshot`, {name: `${v.name}_${st.what === "mo" ? st.label : st.what}.png`, png});
      }
      App.toast(`${viewers.length} snapshots saved in results/snapshots`);
    }
    async function figureGrid() {
      if (!viewers.length) await draw();
      const imgs = await Promise.all(viewers.map(v => new Promise(res => { const im = new Image(); im.onload = () => res({im, name: v.name}); im.src = v.el._viewer.pngURI(); })));
      const w = imgs[0].im.width, hgt = imgs[0].im.height, cols = st.cols, rows = Math.ceil(imgs.length / cols), lab = 34;
      const cv = h("canvas", {width: w * cols, height: (hgt + lab) * rows});
      const ctx = cv.getContext("2d");
      ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, cv.width, cv.height);
      ctx.fillStyle = "#111"; ctx.font = `${Math.round(lab * 0.6)}px sans-serif`; ctx.textAlign = "center";
      imgs.forEach((x, i) => { const cx = (i % cols) * w, cy = Math.floor(i / cols) * (hgt + lab); ctx.drawImage(x.im, cx, cy + lab, w, hgt); ctx.fillText(x.name, cx + w / 2, cy + lab * 0.75); });
      const url = cv.toDataURL("image/png");
      const name = `figure_grid_${st.what === "mo" ? st.label : st.what}.png`;
      await App.post(`/api/batches/${b.id}/snapshot`, {name, png: url});
      const a = h("a", {href: url, download: name}); document.body.append(a); a.click(); a.remove();
      App.toast("Figure grid saved in results/snapshots and downloaded");
    }
    draw();
  },
};
