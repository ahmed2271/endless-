// Spectra (section 14): UV-Vis from TDDFT states and IR / Raman from frequencies, with Plotly.
"use strict";

const Spectra = {
  HC_EV_NM: 1239.84193,
  KB_EH: 3.166811563e-6,

  broaden(lines, xs, fwhm, shape) {
    // lines: [{x, y}] ; Gaussian area-normalised to peak height y, Lorentzian likewise
    const out = new Array(xs.length).fill(0);
    if (shape === "gaussian") {
      const s = fwhm / (2 * Math.sqrt(2 * Math.log(2)));
      for (const l of lines) for (let i = 0; i < xs.length; i++) out[i] += l.y * Math.exp(-((xs[i] - l.x) ** 2) / (2 * s * s));
    } else {
      const g = fwhm / 2;
      for (const l of lines) for (let i = 0; i < xs.length; i++) out[i] += l.y * g * g / ((xs[i] - l.x) ** 2 + g * g);
    }
    return out;
  },
  grid(a, b, n = 1200) { const xs = []; for (let i = 0; i < n; i++) xs.push(a + (b - a) * i / (n - 1)); return xs; },

  async render(body, b) {
    const Plotly = await App.plotly();
    const data = await App.get(`/api/batches/${b.id}/spectra_data`);
    const hasUV = data.some(d => d.states && d.states.length), hasIR = data.some(d => d.ir && d.ir.length);
    if (!hasUV && !hasIR) { body.append(h("p", {class: "muted"}, "No excited states or frequencies in this batch yet.")); return; }
    if (hasUV) Spectra.uv(body, b, data, Plotly);
    if (hasIR) Spectra.ir(body, b, data, Plotly);
  },

  controls(st, keys, redraw) {
    const row = h("div", {class: "row"});
    for (const [k, label, type, opts] of keys) {
      let el;
      if (type === "select") el = W.select(opts, st[k], v => { st[k] = isNaN(+v) || v === "" ? v : +v; redraw(); });
      else if (type === "check") el = h("input", {type: "checkbox", checked: st[k], onchange: e => { st[k] = e.target.checked; redraw(); }});
      else el = h("input", {type: "number", step: "any", value: st[k], style: {width: "90px"}, oninput: e => { st[k] = +e.target.value; redraw(); }});
      row.append(type === "check" ? h("label", {class: "row small"}, el, label) : h("label", {class: "f"}, label, el));
    }
    return row;
  },

  molPicker(data, st, key, redraw) {
    return h("div", {class: "chips", style: {margin: "6px 0"}}, data.filter(d => d[key] && d[key].length).map(d => {
      const on = !st.hidden.has(d.name);
      return h("span", {class: "chip" + (on ? " on" : ""), onclick: e => { on ? st.hidden.add(d.name) : st.hidden.delete(d.name); e.target.classList.toggle("on"); redraw(); }}, d.name);
    }));
  },

  exportButtons(b, plot, csvFn, base) {
    return h("div", {class: "row", style: {marginTop: "6px"}},
      h("button", {class: "small", onclick: () => Plotly.downloadImage(plot, {format: "png", filename: base, width: 1400, height: 700, scale: 2})}, "PNG"),
      h("button", {class: "small", onclick: () => Plotly.downloadImage(plot, {format: "svg", filename: base, width: 1000, height: 500})}, "SVG"),
      h("button", {class: "small", onclick: () => W.saveText(base + ".csv", csvFn(), "text/csv")}, "CSV data"),
      h("button", {class: "small", onclick: async () => {
        const png = await Plotly.toImage(plot, {format: "png", width: 1400, height: 700, scale: 2});
        await App.post(`/api/batches/${b.id}/save_file`, {name: base + ".png", base64: png});
        await App.post(`/api/batches/${b.id}/save_file`, {name: base + ".csv", text: csvFn()});
        App.toast("Saved PNG and CSV in the results folder");
      }}, "Save to results folder"));
  },

  uv(body, b, data, Plotly) {
    const allNm = data.flatMap(d => (d.states || []).map(s => s.nm)).filter(x => x > 0);
    const st = {shape: "gaussian", fwhm: 0.3, axis: "nm", sticks: true, boltz: false, T: 298.15,
      xmin: Math.max(100, Math.floor((Math.min(...allNm, 200) - 30) / 10) * 10), xmax: Math.max(400, Math.ceil((Math.max(...allNm, 400) + 60) / 10) * 10), hidden: new Set(), exp: null};
    const plot = h("div", {style: {height: "460px"}});
    const card = h("div", {class: "card"});
    const expIn = h("input", {type: "file", accept: ".csv,.txt,.dat", onchange: async () => {
      const t = await expIn.files[0].text();
      const pts = t.split(/\r?\n/).map(l => l.split(/[,;\s\t]+/).map(Number)).filter(p => p.length >= 2 && !isNaN(p[0]) && !isNaN(p[1]));
      st.exp = {name: expIn.files[0].name, x: pts.map(p => p[0]), y: pts.map(p => p[1])}; redraw();
    }});
    let last = {xs: [], series: []};
    const redraw = () => {
      // the broadening is always done on an energy (eV) grid; the limits are given in nm
      const xsEv = Spectra.grid(Spectra.HC_EV_NM / Math.max(st.xmin, st.xmax), Spectra.HC_EV_NM / Math.max(1, Math.min(st.xmin, st.xmax)));
      const shown = data.filter(d => d.states && d.states.length && !st.hidden.has(d.name));
      const traces = [], series = [];
      const xOut = xs => st.axis === "nm" ? xs.map(x => Spectra.HC_EV_NM / x) : xs;
      const lineSet = d => d.states.filter(s => s.fosc != null).map(s => ({x: s.energy_ev, y: s.fosc}));
      if (st.boltz) {
        const groups = {};
        for (const d of shown) (groups[d.formula] = groups[d.formula] || []).push(d);
        for (const [f, ds] of Object.entries(groups)) {
          const es = ds.map(d => d.G ?? d.E);
          if (es.some(e => e == null)) continue;
          const e0 = Math.min(...es), w = es.map(e => Math.exp(-(e - e0) / (Spectra.KB_EH * st.T))), sw = w.reduce((a, c) => a + c, 0);
          const y = new Array(xsEv.length).fill(0);
          ds.forEach((d, i) => Spectra.broaden(lineSet(d), xsEv, st.fwhm, st.shape).forEach((v, j) => y[j] += v * w[i] / sw));
          traces.push({x: xOut(xsEv), y, name: `${f} (Boltzmann, ${st.T} K)`, mode: "lines"});
          series.push({name: `${f}_boltzmann`, y});
        }
      } else {
        for (const d of shown) {
          const y = Spectra.broaden(lineSet(d), xsEv, st.fwhm, st.shape);
          traces.push({x: xOut(xsEv), y, name: d.name, mode: "lines"});
          series.push({name: d.name, y});
          if (st.sticks) {
            const L = lineSet(d);
            traces.push({x: L.flatMap(l => [st.axis === "nm" ? Spectra.HC_EV_NM / l.x : l.x, st.axis === "nm" ? Spectra.HC_EV_NM / l.x : l.x, null]),
              y: L.flatMap(l => [0, l.y, null]), mode: "lines", line: {width: 1.5}, name: d.name + " (sticks)", showlegend: false, hoverinfo: "skip", opacity: 0.6});
          }
        }
      }
      if (st.exp) traces.push({x: st.exp.x, y: st.exp.y, name: "experiment: " + st.exp.name, mode: "lines", yaxis: "y2", line: {dash: "dot", color: "#111"}});
      last = {xs: xOut(xsEv), series};
      Plotly.react(plot, traces, {margin: {t: 20, r: 60, b: 50, l: 60}, xaxis: {title: st.axis === "nm" ? "Wavelength (nm)" : "Energy (eV)"},
        yaxis: {title: "Oscillator strength (broadened)"}, yaxis2: {overlaying: "y", side: "right", title: "Experiment", showgrid: false, visible: !!st.exp},
        legend: {orientation: "h", y: -0.2}}, {responsive: true, displaylogo: false});
    };
    const csv = () => ["x," + last.series.map(s => s.name).join(","), ...last.xs.map((x, i) => [x.toFixed(4), ...last.series.map(s => s.y[i].toExponential(5))].join(","))].join("\n");
    card.append(h("h2", {style: {marginTop: 0}}, "UV-Vis (TDDFT)"),
      Spectra.controls(st, [["shape", "Line shape", "select", [{value: "gaussian", label: "Gaussian"}, {value: "lorentzian", label: "Lorentzian"}]], ["fwhm", "FWHM (eV)"],
        ["axis", "x-axis", "select", [{value: "nm", label: "nm"}, {value: "ev", label: "eV"}]], ["xmin", "from (nm)"], ["xmax", "to (nm)"], ["sticks", "stick spectrum", "check"],
        ["boltz", "Boltzmann-weighted (per composition)", "check"], ["T", "T (K)"]], redraw),
      Spectra.molPicker(data, st, "states", redraw),
      h("div", {class: "row small"}, "Overlay experimental data (two columns, x in the same unit):", expIn),
      plot, Spectra.exportButtons(b, plot, csv, `${b.name}_uvvis`));
    body.append(card);
    redraw();
  },

  ir(body, b, data, Plotly) {
    const st = {fwhm: 15, scale: 1.0, xmin: 400, xmax: 4000, kind: "ir", hidden: new Set()};
    const plot = h("div", {style: {height: "420px"}});
    const card = h("div", {class: "card"});
    let last = {xs: [], series: []};
    const hasRaman = data.some(d => d.raman && d.raman.length);
    const redraw = () => {
      const xs = Spectra.grid(st.xmin, st.xmax, 1800);
      const key = st.kind === "raman" ? "raman" : "ir";
      const traces = [], series = [];
      for (const d of data.filter(d => d[key] && d[key].length && !st.hidden.has(d.name))) {
        const L = d[key].filter(l => l.freq > 0).map(l => ({x: l.freq * st.scale, y: key === "ir" ? l.intensity : l.activity}));
        const y = Spectra.broaden(L, xs, st.fwhm, "lorentzian");
        traces.push({x: xs, y, name: d.name, mode: "lines"});
        traces.push({x: L.flatMap(l => [l.x, l.x, null]), y: L.flatMap(l => [0, l.y, null]), mode: "lines", line: {width: 1}, showlegend: false, hoverinfo: "skip", opacity: 0.5, name: d.name});
        series.push({name: d.name, y});
      }
      last = {xs, series};
      Plotly.react(plot, traces, {margin: {t: 20, r: 20, b: 50, l: 60}, xaxis: {title: "Wavenumber (cm⁻¹)", autorange: "reversed"},
        yaxis: {title: st.kind === "raman" ? "Raman activity" : "IR intensity (km/mol)"}, legend: {orientation: "h", y: -0.2}}, {responsive: true, displaylogo: false});
    };
    const csv = () => ["wavenumber," + last.series.map(s => s.name).join(","), ...last.xs.map((x, i) => [x.toFixed(2), ...last.series.map(s => s.y[i].toExponential(5))].join(","))].join("\n");
    card.append(h("h2", {style: {marginTop: 0}}, "IR" + (hasRaman ? " / Raman" : "")),
      Spectra.controls(st, [...(hasRaman ? [["kind", "Spectrum", "select", [{value: "ir", label: "IR"}, {value: "raman", label: "Raman"}]]] : []),
        ["fwhm", "Lorentzian FWHM (cm⁻¹)"], ["scale", "Frequency scaling factor"], ["xmin", "from (cm⁻¹)"], ["xmax", "to (cm⁻¹)"]], redraw),
      Spectra.molPicker(data, st, "ir", redraw), plot, Spectra.exportButtons(b, plot, csv, `${b.name}_ir`));
    body.append(card);
    redraw();
  },
};
