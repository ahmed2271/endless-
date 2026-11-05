// ORCA Studio core helpers: element builder, API calls, router, dialogs, header status.
"use strict";

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
      else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
      else if (k === "html") el.innerHTML = v;
      else if (k === "value") el.value = v;
      else if (k === "checked") el.checked = !!v;
      else if (k === "dataset") Object.assign(el.dataset, v);
      else el.setAttribute(k, v === true ? "" : v);
    }
  }
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.appendChild(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c])); }
function fmtTime(t) { if (!t) return ""; const d = new Date(t * 1000); return d.toLocaleString(); }
function fmtDur(s) { if (s == null) return ""; s = Math.max(0, Math.round(s)); const hh = Math.floor(s / 3600), mm = Math.floor(s % 3600 / 60), ss = s % 60; return (hh ? hh + "h " : "") + (hh || mm ? mm + "m " : "") + ss + "s"; }
function pill(status) { return h("span", {class: "pill st-" + status}, status); }
function clone(o) { return JSON.parse(JSON.stringify(o)); }

const App = {
  pages: {},
  status: null,
  timers: [],

  async api(method, url, body, opts = {}) {
    const init = {method, headers: {}};
    if (body instanceof FormData) init.body = body;
    else if (body !== undefined) { init.body = JSON.stringify(body); init.headers["Content-Type"] = "application/json"; }
    const r = await fetch(url, init);
    if (r.status === 401) { location.href = "/login"; throw new Error("login required"); }
    const ct = r.headers.get("content-type") || "";
    const data = ct.includes("json") ? await r.json() : await r.text();
    if (!r.ok && !opts.allowError) {
      const msg = (data && data.detail) ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : r.statusText;
      App.toast(msg, "error");
      throw new Error(msg);
    }
    if (opts.allowError) return {ok: r.ok, status: r.status, data};
    return data;
  },
  get(u) { return App.api("GET", u); },
  post(u, b) { return App.api("POST", u, b === undefined ? {} : b); },
  put(u, b) { return App.api("PUT", u, b); },
  patch(u, b) { return App.api("PATCH", u, b); },
  del(u) { return App.api("DELETE", u); },

  toast(text, kind = "") {
    const t = h("div", {class: "toast " + kind}, text);
    document.getElementById("toasts").appendChild(t);
    setTimeout(() => t.remove(), kind === "error" ? 8000 : 3500);
  },

  modal(title, body, actions = [], wide = false) {
    return new Promise(resolve => {
      const close = v => { bg.remove(); resolve(v); };
      const acts = h("div", {class: "actions"});
      for (const a of actions) {
        acts.appendChild(h("button", {class: a.class || "", onclick: async () => {
          if (a.onclick) { const r = await a.onclick(); if (r === false) return; close(r === undefined ? a.value : r); }
          else close(a.value);
        }}, a.label));
      }
      const m = h("div", {class: "modal" + (wide ? " wide" : "")}, h("h2", null, title), body, acts);
      const bg = h("div", {class: "modal-bg", onmousedown: e => { if (e.target === bg) close(null); }}, m);
      bg.addEventListener("keydown", e => { if (e.key === "Escape") close(null); });
      document.body.appendChild(bg);
      const f = m.querySelector("input, select, textarea"); if (f) f.focus();
    });
  },
  confirm(title, text, okLabel = "OK", danger = false) {
    return App.modal(title, h("p", null, text), [{label: "Cancel", value: false}, {label: okLabel, value: true, class: danger ? "danger" : "primary"}]);
  },
  async prompt(title, label, value = "") {
    const inp = h("input", {value, style: {width: "100%"}});
    inp.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); bg_ok.click(); } });
    const body = h("div", null, h("label", {class: "f"}, label, inp));
    let bg_ok;
    const p = App.modal(title, body, [{label: "Cancel", value: null}, {label: "OK", class: "primary", onclick: () => inp.value}]);
    bg_ok = document.querySelector(".modal .actions button.primary");
    return p;
  },

  loadScript(src) {
    return new Promise((res, rej) => {
      if (document.querySelector(`script[src="${src}"]`)) return res();
      const s = h("script", {src}); s.onload = res; s.onerror = rej; document.head.appendChild(s);
    });
  },
  async plotly() { if (!window.Plotly) await App.loadScript("/static/vendor/plotly.min.js"); return window.Plotly; },

  // ---------------------------------------------------------------- router
  register(name, fn) { App.pages[name] = fn; },
  async route() {
    App.timers.forEach(clearInterval); App.timers = [];
    const hash = location.hash.replace(/^#\/?/, "") || "batches";
    const parts = hash.split("/");
    const page = parts[0].split("?")[0];
    document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("active", a.dataset.page === page));
    const main = document.getElementById("main");
    main.innerHTML = "";
    const fn = App.pages[page];
    if (!fn) { main.appendChild(h("p", null, "Page not found")); return; }
    try { await fn(main, ...parts.slice(1).map(decodeURIComponent)); }
    catch (e) { console.error(e); main.appendChild(h("div", {class: "msg error"}, "Error: " + e.message)); }
  },
  every(ms, fn) { const t = setInterval(fn, ms); App.timers.push(t); return t; },

  // ---------------------------------------------------------------- header
  async refreshHeader() {
    try {
      const s = await App.get("/api/status");
      App.status = s;
      const el = document.getElementById("hdr-stats");
      el.innerHTML = "";
      el.append(
        h("span", null, "Cores ", h("b", null, `${s.cores_used} / ${s.cores_total}`)),
        h("span", null, "Running ", h("b", null, s.running)),
        h("span", null, "Queued ", h("b", null, s.queued)));
      const n = document.getElementById("bell-n");
      const prev = +(n.textContent || 0);
      n.textContent = s.notifications ? s.notifications : "";
      if (s.notifications > prev && App._notifReady) App.browserNotify();
      App._notifReady = true;
    } catch (e) { /* offline */ }
  },
  async browserNotify() {
    if (!("Notification" in window)) return;
    const list = await App.get("/api/notifications?limit=1");
    if (!list.length) return;
    if (Notification.permission === "granted") new Notification("ORCA Studio", {body: list[0].text});
  },
  async toggleNotifications() {
    const p = document.getElementById("notif-panel");
    if (!p.classList.contains("hidden")) { p.classList.add("hidden"); return; }
    const list = await App.get("/api/notifications");
    p.innerHTML = "";
    p.appendChild(h("div", {class: "row"}, h("b", null, "Notifications"), h("span", {class: "spacer"}),
      ("Notification" in window && Notification.permission !== "granted") ?
        h("button", {class: "small", onclick: () => Notification.requestPermission()}, "Enable desktop pop-ups") : null));
    if (!list.length) p.appendChild(h("div", {class: "n muted"}, "Nothing yet."));
    for (const n of list) p.appendChild(h("div", {class: "n"}, h("div", {class: "small muted"}, fmtTime(n.ts)),
      h("span", {class: n.level === "error" ? "" : ""}, (n.seen ? "" : "● ") + n.text),
      n.batch_id ? h("a", {href: `#/batch/${n.batch_id}`, onclick: () => p.classList.add("hidden"), style: {marginLeft: "6px"}}, "open") : null));
    p.classList.remove("hidden");
    await App.post("/api/notifications/seen");
    App.refreshHeader();
  },

  start() {
    window.addEventListener("hashchange", App.route);
    document.getElementById("bell").onclick = App.toggleNotifications;
    App.refreshHeader();
    setInterval(App.refreshHeader, 4000);
    App.route();
  },
};

// Small reusable widgets ----------------------------------------------------
const W = {
  select(options, value, onchange, attrs = {}) {
    const s = h("select", attrs);
    for (const o of options) {
      const opt = typeof o === "object" ? o : {value: o, label: o};
      const el = h("option", {value: opt.value}, opt.label);
      if (opt.disabled) el.disabled = true;
      if (String(opt.value) === String(value)) el.selected = true;
      s.appendChild(el);
    }
    if (onchange) s.addEventListener("change", () => onchange(s.value, s));
    return s;
  },
  tabs(names, active, onpick) {
    const bar = h("div", {class: "tabs"});
    for (const [id, label] of names) {
      bar.appendChild(h("button", {class: id === active ? "active" : "", onclick: () => {
        bar.querySelectorAll("button").forEach(b => b.classList.remove("active"));
        bar.querySelector(`[data-t="${id}"]`).classList.add("active");
        onpick(id);
      }, "data-t": id}, label));
    }
    return bar;
  },
  dropzone(text, onfiles, accept = ".xyz,.inp,.zip") {
    const input = h("input", {type: "file", multiple: true, accept, class: "hidden"});
    const dz = h("div", {class: "dropzone"}, text, h("div", {class: "small", style: {marginTop: "6px"}},
      "or ", h("a", {href: "#", onclick: e => { e.preventDefault(); input.click(); }}, "choose files")), input);
    input.addEventListener("change", () => { if (input.files.length) onfiles([...input.files]); input.value = ""; });
    dz.addEventListener("dragover", e => { e.preventDefault(); dz.classList.add("over"); });
    dz.addEventListener("dragleave", () => dz.classList.remove("over"));
    dz.addEventListener("drop", async e => {
      e.preventDefault(); dz.classList.remove("over");
      const files = [];
      const items = e.dataTransfer.items ? [...e.dataTransfer.items] : [];
      const entries = items.map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
      if (entries.length && entries.some(en => en.isDirectory)) {
        const walk = en => new Promise(res => {
          if (en.isFile) en.file(f => { files.push(f); res(); });
          else en.createReader().readEntries(async ents => { for (const x of ents) await walk(x); res(); });
        });
        for (const en of entries) await walk(en);
      } else files.push(...e.dataTransfer.files);
      if (files.length) onfiles(files);
    });
    return dz;
  },
  download(url) { const a = h("a", {href: url, download: ""}); document.body.appendChild(a); a.click(); a.remove(); },
  saveText(name, text, type = "text/plain") {
    const blob = new Blob([text], {type}); const a = h("a", {href: URL.createObjectURL(blob), download: name});
    document.body.appendChild(a); a.click(); a.remove();
  },
};
