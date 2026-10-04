"use strict";
/* ---------- Network ---------- */
/** Display names of the network measures. */
const MEASURE_LABELS = { strength: "Strength", degree: "Degree", betweenness: "Betweenness", closeness: "Closeness", eigenvector: "Eigenvector",
  clustering: "Clustering", mentions: "Mentions", in_strength: "In-strength", out_strength: "Out-strength", in_degree: "In-degree", out_degree: "Out-degree" };

/** A node's colour: by type, community, or whether it has a tag. */
function nodeColor(n, mode, communities) {
  if (mode === "type") return TC[n.type];
  if (mode === "community") return n.community ? PALETTE[(n.community - 1) % PALETTE.length] : "#b7c0c2";
  if (mode.startsWith("tag:")) return n.tags.includes(mode.slice(4)) ? "#b5473c" : "#9aa6aa";
  return "#3b5ba5";
}

/** Draw a network as SVG from the server's {nodes (with x, y in 0…1), edges}: circles sized by a measure, labels for the largest,
    highlighting on hover, and optional zoom and pan. o: color, size, labels, focus, pan, onNode, height…

    Focus: hovering a circle highlights it and its neighbours until the pointer leaves; clicking a circle *pins* that focus (it stays
    when the pointer moves away, and hovering another circle shows that one meanwhile); clicking empty space unpins. A circle without
    a label gets one while it is hovered or pinned. `o.pinned` is the circle pinned at the start, `o.onPin(id or null)` hears changes,
    and the returned element has `setPinned(id)` for other parts of the page (a table row, say). */
function networkSvg(N, o) {
  const W = 1000, H = o.height || 640, M = 50;
  const el = svg("svg", { viewBox: `0 0 ${W} ${H}`, "font-family": SVG_FONT, "font-size": 12, role: "img", "aria-label": "Network" });
  const val = n => n[o.size] ?? 0;
  const maxV = Math.max(1e-9, ...N.nodes.map(val)), maxW = Math.max(1, ...N.edges.map(e => e.weight));
  const F = o.font || 11.5, RS = o.radius || 1;
  const R = n => RS * (4 + 16 * Math.sqrt(val(n) / maxV));
  const pos = {}; N.nodes.forEach(n => (pos[n.id] = [M + n.x * (W - 2 * M), M + n.y * (H - 2 * M)]));
  const byId = Object.fromEntries(N.nodes.map(n => [n.id, n]));
  const defs = svg("defs");
  if (N.directed) defs.append(svg("marker", { id: "arr", viewBox: "0 0 10 10", refX: 10, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" },
    svg("path", { d: "M0,0 L10,5 L0,10 z", fill: "#7b878b" })));
  el.append(defs);
  const gE = svg("g"), gN = svg("g"), gL = svg("g");
  const edgeEls = N.edges.map(e => {
    const [x1, y1] = pos[e.source], [x2, y2] = pos[e.target];
    let x2e = x2, y2e = y2;
    if (N.directed) { const r = R(byId[e.target]) + 2, dx = x2 - x1, dy = y2 - y1, L = Math.hypot(dx, dy) || 1; x2e = x2 - dx / L * r; y2e = y2 - dy / L * r; }
    const line = svg("line", { x1, y1, x2: x2e, y2: y2e, stroke: "#7b878b", "stroke-opacity": 0.35, "stroke-width": 0.6 + 3.4 * Math.sqrt(e.weight / maxW),
      "marker-end": N.directed ? "url(#arr)" : null }, svg("title", {}, `${byId[e.source].name} ${N.directed ? "→" : "–"} ${byId[e.target].name}: ${e.weight}`));
    gE.append(line); return [e, line];
  });
  const labelled = new Set([...N.nodes].sort((a, b) => val(b) - val(a)).slice(0, o.labels === "all" ? Infinity : +o.labels).map(n => n.id));
  if (o.focus) labelled.add(o.focus);
  const nodeEls = {};
  let hover = null, pinned = byId[o.pinned] ? o.pinned : null;
  N.nodes.forEach(n => {
    const [x, y] = pos[n.id], r = R(n);
    const c = svg("circle", { cx: x, cy: y, r, fill: nodeColor(n, o.color), stroke: n.id === o.focus ? cssVar("--ink") : cssVar("--panel"), "stroke-width": n.id === o.focus ? 2.5 : 1.2, style: "cursor:pointer" },
      svg("title", {}, `${n.name} (${n.type}) — ${MEASURE_LABELS[o.size] || o.size}: ${fmtSig(val(n))}`));
    gN.append(c);
    // every circle has a label element; those not in `labelled` stay hidden until the circle is hovered or pinned
    const t = svg("text", { x: x + r + 3, y: y + 4, fill: cssVar("--ink"), stroke: cssVar("--panel"), "stroke-width": 3, "paint-order": "stroke", "font-size": n.id === o.focus ? F * 1.15 : F,
      visibility: labelled.has(n.id) ? "visible" : "hidden", "pointer-events": "none" }, n.name);
    gL.append(t);
    nodeEls[n.id] = [c, t];
    c.addEventListener("mouseenter", () => { hover = n.id; refresh(); });
    c.addEventListener("mouseleave", () => { hover = null; refresh(); });
    c.addEventListener("click", ev => { ev.stopPropagation(); setPinned(n.id); if (o.onNode) o.onNode(n); });
  });
  /** Redraw highlighting: the hovered circle wins over the pinned one; with neither, everything is shown normally. */
  function refresh() {
    const id = hover || pinned;
    const nb = new Set([id]);
    if (id) N.edges.forEach(e => { if (e.source === id) nb.add(e.target); if (e.target === id) nb.add(e.source); });
    for (const [e, line] of edgeEls) line.setAttribute("stroke-opacity", !id ? 0.35 : (e.source === id || e.target === id) ? 0.8 : 0.06);
    for (const [nid, [c, t]] of Object.entries(nodeEls)) {
      const lit = !id || nb.has(nid), shown = labelled.has(nid) || nid === hover || nid === pinned;
      c.setAttribute("fill-opacity", lit ? 1 : 0.18);
      c.setAttribute("stroke", nid === o.focus || nid === pinned ? cssVar("--ink") : cssVar("--panel"));
      c.setAttribute("stroke-width", nid === o.focus || nid === pinned ? 2.5 : 1.2);
      t.setAttribute("visibility", shown ? "visible" : "hidden");
      t.setAttribute("fill-opacity", lit ? 1 : 0.15);
    }
  }
  /** Pin the focus on a circle (null: unpin), and tell the page. */
  function setPinned(id) {
    pinned = byId[id] ? id : null;
    refresh();
    if (o.onPin) o.onPin(pinned);
  }
  el.setPinned = setPinned;
  // a click on empty space (not the end of a drag) unpins
  let moved = false;
  el.addEventListener("click", () => { if (!moved && pinned) setPinned(null); });
  el.append(gE, gN, gL);
  refresh();
  if (o.pan) {
    let vb = { x: 0, y: 0, w: W, h: H }, drag = null;
    const set = () => el.setAttribute("viewBox", `${vb.x} ${vb.y} ${vb.w} ${vb.h}`);
    el.addEventListener("wheel", e => {
      e.preventDefault();
      const r = el.getBoundingClientRect(), k = e.deltaY > 0 ? 1.15 : 1 / 1.15;
      const px = vb.x + (e.clientX - r.left) / r.width * vb.w, py = vb.y + (e.clientY - r.top) / r.height * vb.h;
      vb = { x: px - (px - vb.x) * k, y: py - (py - vb.y) * k, w: vb.w * k, h: vb.h * k }; set();
    }, { passive: false });
    el.addEventListener("pointerdown", e => {
      moved = false;
      if (e.target !== el) return;
      drag = [e.clientX, e.clientY, vb.x, vb.y]; el.setPointerCapture(e.pointerId);
    });
    el.addEventListener("pointermove", e => {
      if (!drag) return;
      if (Math.hypot(e.clientX - drag[0], e.clientY - drag[1]) > 4) moved = true;
      const r = el.getBoundingClientRect();
      vb.x = drag[2] - (e.clientX - drag[0]) / r.width * vb.w; vb.y = drag[3] - (e.clientY - drag[1]) / r.height * vb.h; set();
    });
    el.addEventListener("pointerup", () => (drag = null));
    el.resetView = () => { vb = { x: 0, y: 0, w: W, h: H }; set(); };
  }
  return el;
}

/** The Network page: controls, the network, a node's details on click, and tables of measures and links. */
async function renderNetwork(main) {
  const o = S.net, save = () => saveState("analyser.net", o);
  const body = () => withBooks({ kind: o.kind, types: o.types, min_weight: o.min_weight, keep_isolated: o.keep_isolated, max_nodes: o.max_nodes });
  const canvas = h("div", { class: "net-canvas" }, h("div", { class: "loading", style: { padding: "20px" } }, "Building network…"));
  const side = h("div", { class: "net-side" });
  const below = h("div");
  const info = h("div", { class: "muted small" });
  let N = null, el = null, pinned = null;      // pinned: the entity whose focus is kept (see networkSvg)
  const sideHint = () => side.replaceChildren(h("div", { class: "panel muted small" }, "Click an entity to pin its focus and see its measures and links; click empty space to release it. Scroll to zoom, drag to move."));
  const draw = () => {
    if (!N) return;
    if (!N.nodes.length) {
      canvas.replaceChildren(h("div", { class: "empty" }, "No links at these settings. Lower the minimum link strength, add types, or choose more books."));
      below.replaceChildren(); return;
    }
    el = networkSvg(N, { ...o, pan: true, pinned, onNode: showNode, onPin: id => { pinned = id; if (!id) sideHint(); } });
    canvas.replaceChildren(el);
    const sizes = sizeOptions();
    const mcols = [{ k: "name", label: "Entity" }, { k: "type", label: "Type" }, { k: "tags", label: "Tags", fmt: v => v.join(", "), csv: v => v.join("; ") },
      { k: "mentions", label: "Mentions", num: true, fmt: v => fmt(v) },
      ...sizes.filter(k => k !== "mentions").map(k => ({ k, label: MEASURE_LABELS[k], num: true, fmt: v => v == null ? "—" : Number.isInteger(v) ? fmt(v) : fmt(v, 3) })),
      { k: "community", label: "Community", num: true, fmt: v => v ?? "—" }];
    const names = Object.fromEntries(N.nodes.map(n => [n.id, n.name]));
    below.replaceChildren(
      h("section", { class: "panel" }, h("h2", {}, "Measures"), table(mcols, N.nodes, { sort: o.size, limit: 40, csvName: `network ${o.kind} nodes`, onRow: n => { showNode(n); el.setPinned(n.id); } }),
        note("How these are calculated", S.lib.network_notes[o.kind], S.lib.network_notes.measures)),
      h("section", { class: "panel" }, h("h2", {}, "Links"), table([
        { k: "source", label: N.directed ? "From" : "Entity", fmt: v => names[v], csv: v => names[v], sortVal: r => names[r.source] },
        { k: "target", label: N.directed ? "To" : "Entity", fmt: v => names[v], csv: v => names[v], sortVal: r => names[r.target] },
        { k: "weight", label: "Weight", num: true, fmt: v => fmt(v) }], N.edges, { sort: "weight", limit: 30, csvName: `network ${o.kind} edges` })));
  };
  const sizeOptions = () => ["strength", "degree", "betweenness", "closeness", "eigenvector", "mentions", ...(N && N.directed ? ["in_strength", "out_strength", "in_degree", "out_degree"] : [])];
  function showNode(n) {
    const nb = [];
    N.edges.forEach(e => { if (e.source === n.id) nb.push([e.target, e.weight, N.directed ? "→" : ""]); else if (e.target === n.id) nb.push([e.source, e.weight, N.directed ? "←" : ""]); });
    const byId = Object.fromEntries(N.nodes.map(x => [x.id, x]));
    nb.sort((a, b) => b[1] - a[1]);
    side.replaceChildren(h("section", { class: "panel" },
      h("div", { class: "row" }, typeChip(n.type), n.tags.map(t => h("span", { class: "tag" }, t))),
      h("h2", { style: { font: "500 22px var(--serif)", margin: "6px 0" } }, n.name),
      h("div", { class: "kv" }, ["mentions", ...sizeOptions().filter(k => k !== "mentions"), "clustering", "community"].flatMap(k =>
        [h("span", {}, MEASURE_LABELS[k] || "Community"), h("span", { class: "num" }, n[k] == null ? "—" : Number.isInteger(n[k]) ? fmt(n[k]) : fmt(n[k], 3))])),
      h("p", {}, h("a", { href: "#/entities/" + encodeURIComponent(n.id) }, "Open profile")),
      h("h3", { class: "small muted" }, "Linked to"),
      h("div", { class: "small" }, nb.slice(0, 25).map(([id, w, dir]) => h("div", {}, dir, " ", byId[id].name, h("span", { class: "muted" }, ` ${w}`))))));
  }
  const load = async () => {
    save();
    canvas.replaceChildren(h("div", { class: "loading", style: { padding: "20px" } }, "Building network…"));
    N = await api("/api/network", body());
    if (pinned && !N.nodes.some(n => n.id === pinned)) { pinned = null; sideHint(); }
    if (!sizeOptions().includes(o.size)) o.size = "strength";
    const cut = N.info.total_nodes > N.info.nodes ? ` (the ${fmt(N.info.nodes)} most strongly linked of ${fmt(N.info.total_nodes)}; raise “Show at most” or the minimum link strength to see others)` : "";
    info.textContent = `${plural(N.info.nodes || 0, "entity", "entities")}${cut}, ${plural(N.info.edges || 0, "link")}` + (N.nodes.length ?
      `, density ${fmt(N.info.density, 3)}, ${plural(N.info.components, "connected part")}, ${plural(N.info.communities, "community", "communities")}` : "");
    drawControls(); draw();
  };
  const exp = async fmtName => {
    const r = await api("/api/network/export", { ...body(), format: fmtName }, true);
    download(`network-${o.kind}.${fmtName}`, await r.blob());
  };
  const controls = h("div");
  function drawControls() {
    const tagOpts = S.lib.tags.map(t => ["tag:" + t, "Tag: " + t]);
    controls.replaceChildren(h("section", { class: "panel" },
      h("div", { class: "controls" },
        h("div", { class: "fld" }, "Links", seg(Object.entries(S.lib.network_kinds).map(([k, l]) => [k, l]), o.kind, v => { o.kind = v; if (v === "dialogue" && o.min_weight > 1) o.min_weight = 1; load(); })),
        h("div", { class: "fld" }, "Types", h("div", { class: "chips" }, TYPES.map(t => h("button", { class: "chip" + (o.types.includes(t) ? " on" : ""), title: TYPE_NAMES[t],
          onclick: () => { o.types = o.types.includes(t) ? o.types.filter(x => x !== t) : [...o.types, t]; if (!o.types.length) o.types = ["PER"]; load(); } }, t)))),
        h("label", { title: "Hide links weaker than this" }, "Minimum link strength", h("input", { type: "number", min: 1, value: o.min_weight, onchange: e => { o.min_weight = Math.max(1, +e.target.value || 1); load(); } })),
        h("label", { title: "A network of many entities is unreadable and slow to work out: only this many, those with the strongest links, are shown" }, "Show at most",
          h("input", { type: "number", min: 10, max: 1000, step: 50, value: o.max_nodes, onchange: e => { o.max_nodes = Math.min(1000, Math.max(10, +e.target.value || 300)); load(); } })),
        h("label", { class: "inline" }, h("input", { type: "checkbox", checked: o.keep_isolated, onchange: e => { o.keep_isolated = e.target.checked; load(); } }), "Show unlinked entities")),
      h("div", { class: "controls" },
        h("label", {}, "Colour by", h("select", { onchange: e => { o.color = e.target.value; save(); draw(); } },
          [["type", "Type"], ["community", "Community"], ...tagOpts].map(([v, l]) => h("option", { value: v, selected: o.color === v }, l)))),
        h("label", {}, "Size by", h("select", { onchange: e => { o.size = e.target.value; save(); draw(); } },
          sizeOptions().map(k => h("option", { value: k, selected: o.size === k }, MEASURE_LABELS[k])))),
        h("label", {}, "Labels", h("select", { onchange: e => { o.labels = e.target.value; save(); draw(); } },
          [["0", "None"], ["15", "Largest 15"], ["25", "Largest 25"], ["50", "Largest 50"], ["all", "All"]].map(([v, l]) => h("option", { value: v, selected: String(o.labels) === v }, l)))),
        h("div", { class: "row grow", style: { justifyContent: "flex-end" } },
          h("button", { class: "btn small", onclick: () => el && el.resetView() }, "Reset view"),
          h("button", { class: "btn small", onclick: () => el && exportSvg(el, `network-${o.kind}`) }, "SVG"),
          h("button", { class: "btn small", onclick: () => el && exportPng(el, `network-${o.kind}`) }, "PNG"),
          h("button", { class: "btn small", onclick: () => exp("gexf") }, "GEXF"),
          h("button", { class: "btn small", onclick: () => exp("graphml") }, "GraphML"))),
      info,
      o.color === "type" ? h("div", { class: "legend", style: { marginTop: "6px" } }, o.types.map(t => h("span", { style: { "--c": TC[t] } }, TYPE_NAMES[t]))) : null));
  }
  drawControls();
  sideHint();
  main.replaceChildren(controls, h("div", { class: "net" }, canvas, side), below);
  load();
}
