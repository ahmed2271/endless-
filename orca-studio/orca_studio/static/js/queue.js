// Queue page: running and queued jobs across all batches.
"use strict";

App.register("queue", async (main) => {
  main.append(h("h1", null, "Queue"));
  const box = h("div");
  main.append(box);
  const draw = async () => {
    const q = await App.get("/api/queue");
    box.innerHTML = "";
    const s = q.status;
    box.append(h("p", {class: "help"}, `Cores in use ${s.cores_used} of ${s.cores_total}; memory ${s.mem_used_mb} of ${s.mem_total_mb} MB. Jobs start as soon as enough cores are free; batches take turns.`));
    box.append(h("h2", null, `Running (${q.running.length})`));
    box.append(h("div", {class: "card", style: {padding: 0}}, q.running.length ? h("table", null,
      h("tr", null, ["Batch", "Molecule", "Step", "Cores", "PID", "Running for", ""].map(x => h("th", null, x))),
      q.running.map(t => h("tr", null, h("td", null, h("a", {href: `#/batch/${t.batch_id}`}, t.batch)), h("td", null, t.molecule),
        h("td", null, `${t.step_index + 1}. ${t.step_name}`), h("td", null, t.cores), h("td", {class: "mono"}, t.pid || ""),
        h("td", null, fmtDur(Date.now() / 1000 - (t.started || Date.now() / 1000))),
        h("td", null, t.out_file ? h("button", {class: "small", onclick: async () => {
          const txt = await App.get(`/api/file?path=${encodeURIComponent(t.out_file)}&tail=20000`);
          App.modal(t.out_file.split("/").pop(), h("pre", {style: {maxHeight: "65vh"}}, txt), [{label: "Close"}], true);
        }}, "Live output") : null)))) : h("p", {style: {padding: "12px"}, class: "muted"}, "Nothing running.")));
    box.append(h("h2", null, `Queued (${q.queued.length})`));
    box.append(h("div", {class: "card", style: {padding: 0}}, q.queued.length ? h("table", null,
      h("tr", null, ["Batch", "Molecule", "Step"].map(x => h("th", null, x))),
      q.queued.map(t => h("tr", null, h("td", null, h("a", {href: `#/batch/${t.batch_id}`}, t.batch)), h("td", null, t.molecule), h("td", null, t.step_index + 1)))) :
      h("p", {style: {padding: "12px"}, class: "muted"}, "Nothing waiting.")));
  };
  await draw();
  App.every(3000, draw);
});
