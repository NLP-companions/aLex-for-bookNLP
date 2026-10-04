"use strict";
/* ---------- Comparing topics ---------- */
S.top.cmp = loadState("analyser.topcmp", { basis: "words", thr: null, thrBasis: null, by: "book", gval: "share", kind: "groups", types: ["PER"], min: 10, limit: 40, ival: "share", entType: "ALL" });
const saveCmp = () => saveState("analyser.topcmp", S.top.cmp);
/** A topic's colour (the same everywhere). */
const topicColor = id => PALETTE[id % PALETTE.length];
/** A topic's name, shortened. */
const shortName = (t, n = 34) => { const s = topicName(t); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
/** A background colour whose strength follows a value (blue for positive, red for negative). */
const heatBg = (v, max, neg) => { const a = Math.max(0, Math.min(1, v / (max || 1))) * 0.85; return `rgba(${neg ? "181,71,60" : "46,74,98"},${a})`; };

/** The similarity network: circles sized by share, placed by the server's map coordinates and nudged apart, lines above a threshold. */
function topicNetwork(topics, sim, coords, thr, onNode, onEdge) {
  const W = 900, H = 520, M = 80, n = topics.length;
  const xs = coords.map(c => c[0]), ys = coords.map(c => c[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const sc = Math.min((W - 2 * M) / ((x1 - x0) || 1), (H - 2 * M) / ((y1 - y0) || 1));
  const cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
  const maxShare = Math.max(...topics.map(t => t.share));
  const rad = topics.map(t => 6 + 15 * Math.sqrt(t.share / maxShare));
  const P = coords.map(c => [W / 2 + (c[0] - cx) * sc, H / 2 - (c[1] - cy) * sc]);
  for (let it = 0; it < 80; it++) {           // nudge overlapping circles (and their labels) apart
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      let dx = P[j][0] - P[i][0], dy = P[j][1] - P[i][1], d = Math.hypot(dx, dy);
      const need = rad[i] + rad[j] + 46;
      if (d < need) {
        if (d < 1e-6) { dx = Math.cos(i + j); dy = Math.sin(i + j); d = 1; }
        const push = (need - d) / 2 * 0.5;
        P[i][0] -= dx / d * push; P[i][1] -= dy / d * push * 1.6; P[j][0] += dx / d * push; P[j][1] += dy / d * push * 1.6;
      }
    }
    P.forEach(p => { p[0] = Math.max(M / 2, Math.min(W - M / 2, p[0])); p[1] = Math.max(30, Math.min(H - 40, p[1])); });
  }
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, "font-family": SVG_FONT, "font-size": 11.5, role: "img", "aria-label": "Similarity network of topics", style: "max-width:1000px" });
  g.append(svg("rect", { x: 1, y: 1, width: W - 2, height: H - 2, fill: "none", stroke: cssVar("--rule-soft") }));
  for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
    const v = sim[i][j];
    if (v < thr) continue;
    g.append(svg("line", { x1: P[i][0], y1: P[i][1], x2: P[j][0], y2: P[j][1], stroke: cssVar("--muted"), "stroke-opacity": 0.3 + 0.5 * Math.min(1, v), "stroke-width": 1 + 6 * Math.min(1, v), style: "cursor:pointer",
      onclick: () => onEdge(i, j) }, svg("title", {}, `${shortName(topics[i])} — ${shortName(topics[j])}: ${fmt(v, 2)}. Click to compare.`)));
  }
  topics.forEach((t, i) => {
    g.append(svg("circle", { cx: P[i][0], cy: P[i][1], r: rad[i], fill: topicColor(t.id), "fill-opacity": 0.88, stroke: cssVar("--panel"), "stroke-width": 1.5, style: "cursor:pointer", onclick: () => onNode(t.id) },
      svg("title", {}, `${topicName(t)} · ${fmt(100 * t.share, 1)}% of the words. Click to open.`)));
    g.append(svg("text", { x: P[i][0], y: P[i][1] + rad[i] + 13, "text-anchor": "middle", fill: cssVar("--ink"), stroke: cssVar("--panel"), "stroke-width": 3, "paint-order": "stroke", style: "pointer-events:none" }, shortName(t, 26)));
  });
  return g;
}

/** A table of numbers shaded by value, with row and column headers and a CSV download. */
function heatTable(o) {
  // o: {corner, cols:[{label, title, href}], rows:[{label, href, sub, cells:[v], text}], fmtCell, max, neg, csvName}
  const head = h("tr", {}, h("th", { style: { cursor: "default" } }, o.corner), o.cols.map(c => h("th", { class: "num", style: { cursor: "default", whiteSpace: "normal", minWidth: "60px", verticalAlign: "bottom" }, title: c.title || c.label },
    c.href ? h("a", { href: c.href }, c.label) : c.label)));
  const body = o.rows.map(r => h("tr", {}, h("td", { class: "heat-name", title: r.label }, r.href ? h("a", { href: r.href }, r.label) : r.label, r.sub ? h("span", { class: "muted small" }, " " + r.sub) : null),
    r.cells.map((v, j) => h("td", { class: "num cell", style: { background: v == null ? null : heatBg(Math.abs(v), o.max, o.neg && v < 0), color: v != null && Math.abs(v) / (o.max || 1) > 0.65 ? "#fff" : null },
      title: o.cols[j].label + ": " + o.fmtCell(v), onclick: o.onCell ? () => o.onCell(r, j) : null }, o.fmtCell(v)))));
  const csv = h("button", { class: "btn small", onclick: () => downloadCsv(slug(o.csvName), [o.corner, ...o.cols.map(c => c.title || c.label)], o.rows.map(r => [r.label, ...r.cells.map(v => v == null ? "" : fmt(o.csvVal ? o.csvVal(v) : v, 4).replace(/,/g, ""))])) }, "Download CSV");
  return h("div", {}, h("div", { class: "tbl-wrap" }, h("table", { class: "t2 heat" }, h("thead", {}, head), h("tbody", {}, body))), h("div", { class: "tbl-foot" }, h("span", {}, plural(o.rows.length, "row")), csv));
}

/** Compare topics: the map, two topics side by side, or the grids. */
async function topicCompare(body, mid, [sub, a, b]) {
  body.replaceChildren(loading("Loading…"));
  let M;
  try { M = await api("/api/topics/model", { id: mid }); } catch (e) { location.hash = "#/topics"; return; }
  sub = ["map", "pair", "grid"].includes(sub) ? sub : "map";
  const base = "#/topics/" + encodeURIComponent(mid) + "/compare/";
  const tabs = [["map", "Map of topics"], ["pair", "Side by side"], ["grid", "Grids"]];
  const out = h("div");
  body.replaceChildren(h("section", { class: "panel" },
    h("div", { class: "row" }, h("h3", { style: { margin: 0 } }, "Compare topics"), h("span", { class: "muted small" }, M.name), h("span", { class: "grow" }),
      h("a", { class: "small", href: "#/topics/" + encodeURIComponent(mid) }, "← Model overview")),
    h("div", { class: "subtabs", style: { marginTop: "10px", marginBottom: 0 } }, tabs.map(([k, l]) => h("button", { class: k === sub ? "on" : "", onclick: () => (location.hash = base + k) }, l)))), out);
  out.replaceChildren(loading("Loading…"));
  try {
    if (sub === "map") await cmpMap(out, M, mid);
    else if (sub === "pair") await cmpPair(out, M, mid, a, b);
    else await cmpGrid(out, M, mid);
  } catch (e) { out.replaceChildren(h("section", { class: "panel" }, h("p", { class: "warn small" }, e.message))); }
}

/** The similarity map: network, cluster tree, similarity matrix and the pairs table. */
async function cmpMap(out, M, mid) {
  const C = S.top.cmp, N = S.lib.topic_notes;
  const R = await api("/api/topics/compare", { id: mid, part: "map" });
  const T = R.topics, base = "#/topics/" + encodeURIComponent(mid);
  const toPair = (i, j) => (location.hash = `${base}/compare/pair/${i}/${j}`);
  const offDiag = basis => R.pairs.map(p => p[basis]).sort((x, y) => x - y);
  const defaultThr = basis => { const v = offDiag(basis); return Math.max(0.05, Math.round(v[Math.floor(0.7 * (v.length - 1))] * 20) / 20); };
  if (C.thr == null || C.thrBasis !== C.basis) { C.thr = defaultThr(C.basis); C.thrBasis = C.basis; }
  const draw = () => {
    const B = R.bases[C.basis];
    const leaves = []; const walk = t => { if (t.children) t.children.forEach(walk); else leaves.push(t.leaf); }; walk(B.tree);
    const pairs = R.pairs.slice().sort((p, q) => q[C.basis] - p[C.basis]);
    out.replaceChildren(
      h("section", { class: "panel", "data-toc": "Similarity map" },
        h("div", { class: "controls" },
          h("div", { class: "fld" }, "Topics are similar when they", seg([["words", "share words"], ["docs", "appear in the same chunks"]], C.basis, v => { C.basis = v; C.thr = defaultThr(v); C.thrBasis = v; saveCmp(); draw(); })),
          h("label", {}, `Draw lines from similarity ${fmt(C.thr, 2)}`, h("input", { type: "range", min: 0, max: Math.max(0.1, Math.ceil(Math.max(...offDiag(C.basis)) * 20) / 20), step: 0.05, value: C.thr, style: { width: "220px" },
            oninput: e => { C.thr = +e.target.value; e.target.closest("label").firstChild.textContent = `Draw lines from similarity ${fmt(C.thr, 2)}`; saveCmp(); redrawNet(); } }))),
        h("p", { class: "small muted", style: { margin: "0 0 6px" } }, `Larger circles are bigger topics; nearer circles are more similar (the two axes keep ${fmt(100 * (B.variance[0] + B.variance[1]), 0)}% of the differences). Click a circle to open the topic, a line to compare the two.`),
        netBox,
        note("How this is calculated", N.cmp_map)),
      h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Cluster tree"),
        chartBox(dendrogram(B.tree, T.map(t => ({ label: `${t.id + 1}. ${topicName(t)}` })), () => cssVar("--ink")), "topic-tree")),
      h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, C.basis === "words" ? "Shared words" : "Appearing together"),
        h("p", { class: "small muted", style: { marginTop: 0 } }, "Ordered like the tree. Click a cell to compare two topics."),
        heatTable({ corner: "Topic", cols: leaves.map(i => ({ label: String(i + 1), title: topicName(T[i]), href: `${base}/${i}` })),
          rows: leaves.map(i => ({ id: i, label: `${i + 1}. ${topicName(T[i])}`, href: `${base}/${i}`, cells: leaves.map(j => B.sim[i][j]) })),
          fmtCell: v => fmt(v, 2), max: 1, neg: true, csvName: "topic-similarity-" + C.basis, onCell: (r, j) => { if (r.id !== leaves[j]) toPair(r.id, leaves[j]); } })),
      h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Pairs"),
        table([{ k: "a", label: "Topic", fmt: v => `${v + 1}. ${shortName(T[v], 40)}`, sortVal: r => r.a, csv: v => topicName(T[v]) }, { k: "b", label: "Topic", fmt: v => `${v + 1}. ${shortName(T[v], 40)}`, sortVal: r => r.b, csv: v => topicName(T[v]) },
          { k: "words", label: "Shared words", num: true, fmt: v => fmt(v, 2) }, { k: "docs", label: "Appear together", num: true, fmt: v => fmt(v, 2) },
          { k: "shared", label: "Words in both top 20", fmt: v => v.join(", "), sortVal: r => r.shared.length, csv: v => v.join(" ") }],
          pairs, { sort: C.basis, limit: 15, csvName: "topic-pairs", onRow: r => toPair(r.a, r.b) })));
    redrawNet();
  };
  const netBox = h("div");
  const redrawNet = () => {
    const B = R.bases[C.basis];
    netBox.replaceChildren(chartBox(topicNetwork(T, B.sim, B.coords, C.thr, id => (location.hash = `${base}/${id}`), toPair), "topic-map"));
  };
  draw();
}

/** Two topics side by side: words, arcs, book shares, and the entities and speakers that lean towards each. */
async function cmpPair(out, M, mid, a, b) {
  const C = S.top.cmp, N = S.lib.topic_notes, base = "#/topics/" + encodeURIComponent(mid);
  const order = M.topics;
  if (order.length < 2) throw new Error("A model needs at least two topics to compare.");
  a = a == null ? order[0].id : +a; b = b == null ? (order.find(t => t.id !== a) || order[1]).id : +b;
  const pick = (val, onChange) => h("select", { onchange: e => onChange(+e.target.value) }, order.map(t => h("option", { value: t.id, selected: t.id === val }, `${t.id + 1}. ${topicName(t)}`)));
  const go = (x, y) => (location.hash = `${base}/compare/pair/${x}/${y}`);
  const R = await api("/api/topics/compare", { id: mid, part: "pair", a, b, seg: S.nar.seg });
  const T = Object.fromEntries(R.topics.map(t => [t.id, t])), A = T[a], B = T[b];
  const ca = topicColor(a), cb = topicColor(b);
  const form = M.cfg.form === "lemma" ? "lemma" : "word";
  const wordChip = (w, tip) => h("a", { class: "chip", href: "#", title: tip, style: { textDecoration: "none", color: "inherit" }, onclick: e => { e.preventDefault(); goKwic(...itemQuery(w, form)); } }, w);
  const col = (title, color, list, tip) => h("div", {}, h("div", { style: { fontWeight: 600, color, marginBottom: "4px" } }, title), h("div", { class: "chips" }, list.map(w => wordChip(w.w, tip(w)))));
  const pct = v => fmt(100 * v, 2) + "%";
  const arcBox = h("div");
  const drawArc = async () => {
    const r = await api("/api/topics/compare", { id: mid, part: "pair", a, b, seg: S.nar.seg });
    arcBox.replaceChildren(chartBox(arcChart(r.segments, [{ name: shortName(A, 22), values: r.arc_a.values, counts: r.arc_a.counts, color: ca }, { name: shortName(B, 22), values: r.arc_b.values, counts: r.arc_b.counts, color: cb }],
      { ylabel: "% of the words in each segment" }), `topics-${a + 1}-${b + 1}-arc`));
  };
  const assocTable = (rows, kind, title) => {
    const list = rows.filter(r => C.entType === "ALL" || r.type === C.entType || kind === "spk");
    const rest = [{ k: "count", label: kind === "ent" ? "Mentions" : "Words", num: true, fmt: v => fmt(v) },
      { k: "rate_a", label: `Per 1,000 in ${a + 1}`, num: true, fmt: v => fmt(v, 1) }, { k: "rate_b", label: `Per 1,000 in ${b + 1}`, num: true, fmt: v => fmt(v, 1) },
      { k: "ratio", label: "Ratio A ÷ B", num: true, fmt: ratioFmt, sortVal: r => r.ratio ?? 0, csv: v => v == null ? "" : fmt(v, 2) },
      { k: "ll", label: "Score", num: true, sortVal: r => Math.abs(r.ll), fmt: v => fmt(Math.abs(v), 1), csv: v => fmt(v, 2) }];
    const first = kind === "ent" ? [{ k: "name", label: "Entity", fmt: (v, x) => h("a", { href: "#/entities/" + encodeURIComponent(x.id) }, v) }, { k: "type", label: "Type", fmt: v => typeChip(v) }]
      : [{ k: "name", label: "Speaker", fmt: (v, x) => x.linked ? h("a", { href: "#/entities/" + encodeURIComponent(x.id) }, v) : v }];
    const mk = (rs, label, color) => h("div", {}, h("div", { style: { fontWeight: 600, color, margin: "4px 0" } }, label),
      table([...first, ...rest], rs, { sort: "ll", limit: 12, csvName: title, empty: "Nothing with enough mentions." }));
    return h("div", { class: "cols2" },
      mk(list.filter(r => r.ll > 0).sort((p, q) => q.ll - p.ll), `More in topic ${a + 1}'s text`, ca),
      mk(list.filter(r => r.ll < 0).sort((p, q) => p.ll - q.ll), `More in topic ${b + 1}'s text`, cb));
  };
  const types = ["ALL", ...TYPES.filter(t => R.entities.some(x => x.type === t))];
  const entBox = h("div");
  const drawEnt = () => entBox.replaceChildren(h("div", { class: "controls" }, h("div", { class: "fld" }, "Type", seg(types.map(t => [t, t === "ALL" ? "All" : t]), C.entType, v => { C.entType = v; saveCmp(); drawEnt(); }))),
    assocTable(R.entities, "ent", `topics-${a + 1}-${b + 1}-entities`));
  drawEnt();
  const maxBook = Math.max(...R.books.flatMap(x => [x.a, x.b]));
  out.replaceChildren(
    h("section", { class: "panel" },
      h("div", { class: "controls" }, h("label", {}, "First topic", pick(a, v => go(v, v === b ? a : b))), h("label", {}, "Second topic", pick(b, v => go(v === a ? b : a, v))),
        h("button", { class: "btn small", onclick: () => go(b, a) }, "Swap")),
      h("p", { style: { margin: "0 0 4px" } }, h("span", { style: { color: ca, fontWeight: 600 } }, `${a + 1}. ${topicName(A)}`), " against ", h("span", { style: { color: cb, fontWeight: 600 } }, `${b + 1}. ${topicName(B)}`)),
      h("p", { class: "small muted", style: { margin: 0 } }, `Shared words: cosine ${fmt(R.similarity.words, 2)}, ${R.similarity.overlap} of their top 20 words in common. Appear together: correlation ${fmt(R.similarity.docs, 2)} across ${plural(M.docs, "document")}. `,
        `Dialogue: ${pctFmt(R.dialogue.a, 0)} of the words where topic ${a + 1} is strong, ${pctFmt(R.dialogue.b, 0)} for topic ${b + 1} (${pctFmt(R.dialogue.base, 0)} overall).`)),
    h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Words"),
      h("div", { class: "cols3" },
        col(`Only in ${a + 1}`, ca, R.words.a.slice(0, 16), w => `topic ${a + 1}: ${pct(w.pa)}, topic ${b + 1}: ${pct(w.pb)}`),
        col("In both", cssVar("--ink"), R.words.shared.slice(0, 16), w => `topic ${a + 1}: ${pct(w.pa)}, topic ${b + 1}: ${pct(w.pb)}`),
        col(`Only in ${b + 1}`, cb, R.words.b.slice(0, 16), w => `topic ${a + 1}: ${pct(w.pa)}, topic ${b + 1}: ${pct(w.pb)}`)),
      note("How this is calculated", N.cmp_pair, "Hover over a word for its weight in each topic; click it to search for it.")),
    h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Along the books"), segControl(drawArc), arcBox,
      R.books.length > 1 ? table([{ k: "title", label: "Book" }, { k: "a", label: `Topic ${a + 1} share`, num: true, fmt: v => barFmt(100 * maxBook, 1)(100 * v), csv: v => fmt(100 * v, 2) },
        { k: "b", label: `Topic ${b + 1} share`, num: true, fmt: v => barFmt(100 * maxBook, 1)(100 * v), csv: v => fmt(100 * v, 2) }], R.books, { sort: "a", csvName: "topics-by-book" }) : null),
    h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Entities"), h("p", { class: "small muted", style: { marginTop: 0 } }, `Mentions in text weighted by each topic; entities with at least ${R.min_mentions} mentions.`), entBox),
    h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Speakers"), h("p", { class: "small muted", style: { marginTop: 0 } }, `Words spoken per 1,000 words of dialogue; speakers with at least ${R.min_words} words.`), assocTable(R.speakers, "spk", `topics-${a + 1}-${b + 1}-speakers`)));
  await drawArc();
}

/** Grids: topic × book (or series, author, year, tag), topic × character, topic × speaker. */
async function cmpGrid(out, M, mid) {
  const C = S.top.cmp, N = S.lib.topic_notes, base = "#/topics/" + encodeURIComponent(mid);
  const box = h("div");
  const kinds = [["groups", "Topic × book"], ["mentions", "Topic × character"], ["speakers", "Topic × speaker"]];
  const cur = () => C.kind === "mentions" || C.kind === "speakers" ? C.kind : "groups";
  const load = async () => {
    box.replaceChildren(loading("Loading…"));
    const k = cur();
    let R, table_, notes;
    if (k === "groups") {
      R = await api("/api/topics/compare", { id: mid, part: "groups", by: C.by });
      const T = R.topics.slice().sort((p, q) => q.share - p.share);
      const val = (sh, t) => C.gval === "ratio" ? (R.overall[t.id] ? sh / R.overall[t.id] : null) : sh;
      const rows = T.map(t => ({ label: `${t.id + 1}. ${topicName(t)}`, href: `${base}/${t.id}`, cells: [...R.columns.map(c => val(c.shares[t.id], t)), C.gval === "ratio" ? 1 : R.overall[t.id]] }));
      const max = Math.max(...rows.flatMap(r => r.cells.slice(0, -1)));
      table_ = heatTable({ corner: "Topic", cols: [...R.columns.map(c => ({ label: c.label.length > 26 ? c.label.slice(0, 25) + "…" : c.label, title: `${c.label} (${plural(c.docs, "document")}, ${fmt(c.words)} words)` })), { label: "All" }],
        rows, fmtCell: v => v == null ? "—" : C.gval === "ratio" ? "× " + fmt(v, 1) : fmt(100 * v, 1) + "%", max: C.gval === "ratio" ? Math.min(max, 4) : max, csvName: `${slug(M.name)}-topic-by-${C.by}`,
        csvVal: v => C.gval === "ratio" ? v : 100 * v });
      notes = N.cmp_grid_groups;
    } else {
      R = await api("/api/topics/compare", { id: mid, part: "items", kind: k, types: C.types, min: C.min, limit: C.limit });
      const T = R.topics.slice().sort((p, q) => q.share - p.share);
      const val = (sh, t) => C.ival === "lift" ? (R.overall[t.id] ? sh / R.overall[t.id] : null) : sh;
      const rows = R.rows.map(r => ({ label: r.name, href: r.linked ? "#/entities/" + encodeURIComponent(r.id) : null, sub: fmt(r.count) + (k === "speakers" ? " words" : " mentions"), cells: T.map(t => val(r.shares[t.id], t)) }));
      const max = Math.max(1e-9, ...rows.flatMap(r => r.cells.filter(v => v != null)));
      table_ = heatTable({ corner: k === "speakers" ? "Speaker" : "Entity", cols: T.map(t => ({ label: String(t.id + 1), title: topicName(t), href: `${base}/${t.id}` })), rows,
        fmtCell: v => v == null ? "—" : C.ival === "lift" ? "× " + fmt(v, 1) : fmt(100 * v, 0) + "%", max: C.ival === "lift" ? Math.min(max, 4) : max, csvName: `${slug(M.name)}-topic-by-${k}`, csvVal: v => C.ival === "lift" ? v : 100 * v });
      notes = N.cmp_grid_items;
      var legend = h("p", { class: "small muted" }, "Columns are topics, biggest first: ", T.map(t => h("a", { href: `${base}/${t.id}`, style: { marginRight: "10px" } }, `${t.id + 1}. ${shortName(t, 22)}`)));
    }
    const ctl = h("div", { class: "controls" },
      h("div", { class: "fld" }, "Grid", seg(kinds, k, v => { C.kind = v; saveCmp(); cmpGrid(out, M, mid); })),
      k === "groups" ? [h("label", {}, "Group books by", h("select", { onchange: e => { C.by = e.target.value; saveCmp(); load(); } }, [["book", "Book"], ["series", "Series"], ["author", "Author"], ["year", "Year"], ["tag", "Tag"]].map(([v, l]) => h("option", { value: v, selected: C.by === v }, l)))),
        h("div", { class: "fld" }, "Values", seg([["share", "Share of the words"], ["ratio", "Against all"]], C.gval, v => { C.gval = v; saveCmp(); load(); }))]
        : [h("div", { class: "fld" }, "Values", seg([["share", "Share of mentions"], ["lift", "Against topic average"]], C.ival, v => { C.ival = v; saveCmp(); load(); })),
          k === "mentions" ? h("div", { class: "fld" }, "Types", h("div", { class: "row", style: { gap: "8px" } }, TYPES.map(t => h("label", { class: "inline" }, h("input", { type: "checkbox", checked: C.types.includes(t),
            onchange: e => { C.types = e.target.checked ? [...C.types, t] : C.types.filter(x => x !== t); saveCmp(); load(); } }), t)))) : null,
          h("label", {}, k === "speakers" ? "Minimum words" : "Minimum mentions", h("input", { type: "number", min: 1, value: C.min, style: { width: "80px" }, onchange: e => { C.min = Math.max(1, +e.target.value || 1); saveCmp(); load(); } })),
          h("label", {}, "Show the top", h("select", { onchange: e => { C.limit = +e.target.value; saveCmp(); load(); } }, [20, 40, 80, 150].map(n => h("option", { value: n, selected: C.limit === n }, n))))]);
    box.replaceChildren(ctl, R.rows && !R.rows.length ? h("p", { class: "muted small" }, "Nothing meets those settings.") : null, legend, table_, note("How this is calculated", notes));
  };
  out.replaceChildren(h("section", { class: "panel" }, box));
  await load();
}
