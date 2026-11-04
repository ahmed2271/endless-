// 3Dmol.js viewer helpers: structures, orbitals (isovalue slider), MEP surfaces, charges.
"use strict";

const Viewer = {
  make(el) {
    el.innerHTML = "";
    const v = $3Dmol.createViewer(el, {backgroundColor: "white", antialias: true, preserveDrawingBuffer: true});
    el._viewer = v;
    return v;
  },
  show(el, xyz, opts = {}) {
    const v = el._viewer || Viewer.make(el);
    v.removeAllModels(); v.removeAllShapes(); v.removeAllSurfaces(); v.removeAllLabels();
    if (xyz && xyz.trim() && !xyz.startsWith("0")) {
      v.addModel(xyz, "xyz");
      v.setStyle({}, {stick: {radius: 0.14}, sphere: {scale: 0.24}});
      if (opts.labels) v.getModel().selectedAtoms({}).forEach((a, i) => v.addLabel(String(i), {position: a, fontSize: 11, backgroundOpacity: 0.4, inFront: true}));
    }
    v.zoomTo(); v.render();
    return v;
  },
  colorByCharge(el, charges, range) {
    const v = el._viewer; if (!v || !charges) return;
    const m = v.getModel(); if (!m) return;
    const r = range || Math.max(0.1, ...charges.map(Math.abs));
    const grad = new $3Dmol.Gradient.RWB(-r, r);
    m.selectedAtoms({}).forEach((a, i) => { a.properties = a.properties || {}; a.properties.q = charges[i] ?? 0; });
    v.setStyle({}, {stick: {radius: 0.14, colorscheme: {prop: "q", gradient: grad}}, sphere: {scale: 0.28, colorscheme: {prop: "q", gradient: grad}}});
    v.render();
  },
  addOrbital(el, cubeText, iso = 0.03) {
    const v = el._viewer;
    const vol = new $3Dmol.VolumeData(cubeText, "cube");
    v.removeAllShapes();
    v.addIsosurface(vol, {isoval: iso, color: "#2563eb", alpha: 0.85, smoothness: 3});
    v.addIsosurface(vol, {isoval: -iso, color: "#dc2626", alpha: 0.85, smoothness: 3});
    v.render();
    return vol;
  },
  addMEP(el, densText, espText, iso = 0.001, range = 0.05) {
    const v = el._viewer;
    v.removeAllShapes();
    const dens = new $3Dmol.VolumeData(densText, "cube");
    const esp = new $3Dmol.VolumeData(espText, "cube");
    v.addIsosurface(dens, {isoval: iso, smoothness: 2, opacity: 0.92, voldata: esp, volscheme: new $3Dmol.Gradient.RWB(-range, range)});
    v.render();
  },
  async popup(m) {
    const el = h("div", {class: "viewer"});
    const p = App.modal(`${m.name} (${m.formula})`, el, [{label: "Close"}], true);
    Viewer.show(el, await App.get(`/api/molecules/${m.id}/xyz`), {labels: true});
    return p;
  },
};
