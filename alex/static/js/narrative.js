"use strict";
/* ---------- Arcs and style ---------- */
S.nar = loadState("analyser.nar", { sub: "arcs", seg: { mode: "slices", scope: "book", n: 10, rules: { numbered: true, caps: true, short: false }, min_words: 500 },
  arcKind: "entities", ids: [], cats: null, topicModel: null, topicIds: [], styleBy: "book", styleMetric: "sent_len",
  stylo: { units: "books", mfw: 100, culling: 0, measure: "cosine", linkage: "average", scope: "all", exclude_pronouns: false, color: "book" },
  sentIds: [], emoCats: null });
/** Save the Arcs and style settings. */
const saveNar = () => saveState("analyser.nar", S.nar);
/** Style figures: [key, label, decimals]. */
const STYLE_COLS = [
  ["words", "Words", 0], ["sentences", "Sentences", 0], ["sent_len", "Sentence length", 1], ["sent_sd", "Sentence length SD", 1],
  ["word_len", "Word length", 2], ["mattr", "MATTR", 3], ["hapax", "Hapaxes %", 1], ["density", "Lexical density %", 1],
  ["dep_dist", "Dependency distance", 2], ["depth", "Tree depth", 2], ["subord", "Subordinate clauses per sentence", 2],
  ["passive", "Passives per 1,000", 2], ["questions", "Questions %", 1], ["dialogue", "Dialogue %", 1],
  ["flesch", "Flesch Reading Ease", 1], ["fk_grade", "Flesch–Kincaid grade", 1]];

/** A chart over segments: lines per series across the books' chapters or slices, with book labels and hover values.
    opts.continuous: one unbroken line per series across every selected book ("Whole corpus" timeline), instead of a
    separate line per book (the default, so a trend never appears to cross a book's end). */
function arcChart(segs, series, opts = {}) {
  const W = 900, left = 50, right = 180, top = 28, bottom = 30, H = opts.height || 320, pw = W - left - right, ph = H - top - bottom;
  const books = [...new Set(segs.map(s => s.book))];
  const gap = 1.2, n = segs.length + gap * (books.length - 1);
  const xi = segs.map((s, k) => k + gap * books.indexOf(s.book));
  const x = k => left + (n <= 1 ? pw / 2 : pw * xi[k] / (n - 1));
  const vals = series.flatMap(s => s.values.filter(v => v != null));
  let lo = Math.min(0, ...vals), hi = Math.max(1e-9, ...vals);
  if (opts.symmetric) { const m = Math.max(Math.abs(lo), Math.abs(hi)); lo = -m; hi = m; }
  const pad = (hi - lo) * 0.08; hi += pad; if (lo < 0) lo -= pad;
  const y = v => top + ph - ph * (v - lo) / (hi - lo);
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, "font-family": SVG_FONT, "font-size": 11.5, role: "img", style: "max-width:1000px" });
  const span = hi - lo, raw = span / 5, mag = Math.pow(10, Math.floor(Math.log10(raw))), step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
  for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) {
    g.append(svg("line", { x1: left, x2: left + pw, y1: y(v), y2: y(v), stroke: Math.abs(v) < step / 1e6 ? "#9aa6aa" : "#e6eae9" }));
    g.append(svg("text", { x: left - 6, y: y(v) + 4, "text-anchor": "end", fill: cssVar("--faint") }, fmt(v, step < 0.1 ? 2 : step < 1 ? 1 : 0)));
  }
  books.forEach((b, bi) => {
    const ks = segs.map((s, k) => k).filter(k => segs[k].book === b);
    const x0 = x(ks[0]), x1 = x(ks[ks.length - 1]);
    if (bi) g.append(svg("line", { x1: x0 - pw * gap / (2 * (n - 1)), x2: x0 - pw * gap / (2 * (n - 1)), y1: top - 16, y2: top + ph, stroke: cssVar("--rule"), "stroke-dasharray": "3 3" }));
    const t = segs[ks[0]].title;
    if (books.length <= 12) g.append(svg("text", { x: (x0 + x1) / 2, y: top - 10, "text-anchor": "middle", fill: cssVar("--muted"), "font-weight": 600 }, t.length > 30 ? t.slice(0, 29) + "…" : t));     // more titles than that would overlap: hover a point for its book
    if (ks.length <= 30) ks.forEach((k, j) => g.append(svg("text", { x: x(k), y: top + ph + 14, "text-anchor": "middle", fill: cssVar("--faint"), "font-size": 9.5 }, String(j + 1))));
  });
  series.forEach((s, si) => {
    const color = s.color || PALETTE[si % PALETTE.length];
    const scopes = opts.continuous ? [null] : books;   // null: one line over every point, ignoring book boundaries
    scopes.forEach(b => {
      const pts = segs.map((sg, k) => [sg, k]).filter(([sg, k]) => (b === null || sg.book === b) && s.values[k] != null).map(([sg, k]) => `${x(k)},${y(s.values[k])}`);
      if (pts.length) g.append(svg("polyline", { points: pts.join(" "), fill: "none", stroke: color, "stroke-width": 1.8 }));
    });
    s.values.forEach((v, k) => { if (v != null) g.append(svg("circle", { cx: x(k), cy: y(v), r: segs.length > 60 ? 1.8 : 3, fill: color },
      svg("title", {}, `${s.name} — ${segs[k].title}, ${segs[k].label}: ${fmt(v, Math.abs(v) < 1 ? 3 : 1)}${s.counts ? ` (${s.counts[k]})` : ""}`))); });
    const ly = top + si * 17;
    g.append(svg("rect", { x: left + pw + 14, y: ly - 9, width: 12, height: 3, fill: color }));
    g.append(svg("text", { x: left + pw + 32, y: ly - 4, fill: cssVar("--ink") }, s.name.length > 22 ? s.name.slice(0, 21) + "…" : s.name));
  });
  if (opts.ylabel) g.append(svg("text", { x: left, y: H - 6, fill: cssVar("--faint"), "font-size": 10.5 }, opts.ylabel));
  return g;
}
/** The table behind an arc chart. */
function arcTable(segs, series, name, dec = 2) {
  const rows = segs.map((sg, k) => { const r = { title: sg.title, label: sg.label, words: sg.words }; series.forEach((s, i) => (r["s" + i] = s.values[k])); return r; });
  return table([{ k: "title", label: "Book" }, { k: "label", label: "Segment" }, { k: "words", label: "Words", num: true, fmt: v => fmt(v) },
    ...series.map((s, i) => ({ k: "s" + i, label: s.name, num: true, fmt: v => v == null ? "—" : fmt(v, dec) }))], rows, { limit: 25, csvName: name });
}

/** The chapters-or-slices setting every Arcs page shares, with a way to check the chapters found. */
function segControl(onChange) {
  const g = S.nar.seg;
  const ch = () => { saveNar(); onChange(); };
  const check = h("div");
  return h("div", {},
    h("div", { class: "controls", style: { marginBottom: "4px" } },
      h("div", { class: "fld" }, "Measure over", seg([["slices", "Equal slices"], ["chapters", "Chapters"]], g.mode, v => { g.mode = v; ch(); })),
      selected().length > 1 ? h("div", { class: "fld" }, "Timeline", seg([["book", "Book by book"], ["corpus", "Whole corpus"]], g.scope, v => { g.scope = v; ch(); })) : null,
      g.mode === "slices" ? h("label", {}, g.scope === "corpus" ? "Slices across the corpus" : "Slices per book", h("select", { onchange: e => { g.n = +e.target.value; ch(); } }, [5, 10, 20, 50].map(n => h("option", { value: n, selected: g.n === n }, n))))
        : [h("label", { class: "inline" }, h("input", { type: "checkbox", checked: g.rules.numbered, onchange: e => { g.rules.numbered = e.target.checked; ch(); } }), "Heading words and numerals"),
          h("label", { class: "inline" }, h("input", { type: "checkbox", checked: g.rules.caps, onchange: e => { g.rules.caps = e.target.checked; ch(); } }), "Lines in capitals"),
          h("label", { class: "inline" }, h("input", { type: "checkbox", checked: g.rules.short, onchange: e => { g.rules.short = e.target.checked; ch(); } }), "Short lines without closing punctuation"),
          h("label", {}, "Minimum chapter length (words)", h("input", { type: "number", min: 0, value: g.min_words, onchange: e => { g.min_words = Math.max(0, +e.target.value || 0); ch(); } }))]),
    h("details", { class: "note", style: { marginTop: 0 }, ontoggle: async e => { if (!e.target.open) return;
      const r = await api("/api/narrative/segments", withBooks({ seg: g }));
      const warn = Object.entries(r.info).filter(([b, i]) => i.fallback).map(([b]) => bookTitle(b));
      check.replaceChildren(warn.length ? h("p", { class: "warn" }, `No chapters found in ${warn.join(", ")}; using ${g.n} slices instead.`) : null,
        table([{ k: "title", label: "Book" }, { k: "label", label: "Segment" }, { k: "pos", label: "Starts at %", num: true, fmt: v => fmt(v, 1) }, { k: "words", label: "Words", num: true, fmt: v => fmt(v) },
          ...(g.mode === "chapters" ? [{ k: "source", label: "Chapter start", fmt: v => v === "yours" ? "set by you" : v === "auto" ? "found" : "" }] : [])],
          r.segments, { limit: 60, csvName: "segments" }),
        g.mode === "chapters" ? h("p", { class: "small" }, "Wrong chapters? Start, rename or remove them in the text: ",
          selected().map((b, i) => [i ? " · " : "", h("a", { href: "#/chapters/" + encodeURIComponent(b) }, bookTitle(b) + (r.info[b] && r.info[b].edited ? " (edited)" : ""))])) : null); } },
      h("summary", {}, g.mode === "chapters" ? "Check the chapters found" : "List the segments"), check, h("p", {}, S.lib.narrative_notes.segments)));
}

/** The Arcs and style pages (arcs, style, stylometry, sentiment and emotion). */
async function renderNarrative(main, sub) {
  const N = S.nar;
  N.sub = sub || N.sub;
  const tabs = [["arcs", "Arcs"], ["style", "Style"], ["stylometry", "Stylometry"], ["sentiment", "Sentiment and emotion"]];
  const body = h("div");
  main.replaceChildren(h("section", { class: "panel" },
    h("div", { class: "subtabs", style: { marginBottom: "10px" } }, tabs.map(([k, l]) => h("button", { class: k === N.sub ? "on" : "", onclick: () => (location.hash = "#/narrative/" + k) }, l))),
    N.sub === "stylometry" && N.stylo.units === "books" ? h("p", { class: "small muted", style: { margin: 0 } }, "Comparing whole books. Choose Chapters or slices below to compare parts of books.") :
      segControl(() => renderNarrative(main, N.sub))), body);
  await ({ arcs: narArcs, style: narStyle, stylometry: narStylo, sentiment: narSentiment }[N.sub] || narArcs)(body);
}

/** Removable chips for chosen entities, with a box to add one. */
function entityChips(ids, onChange, U) {
  const byId = Object.fromEntries(U.rows.map(r => [r.id, r]));
  return h("div", { class: "row" },
    ids.map(id => byId[id] ? h("span", { class: "tag" }, typeChip(byId[id].type), " ", byId[id].name, h("button", { title: "Remove", onclick: () => onChange(ids.filter(x => x !== id)) }, "×")) : null),
    picker(null, v => { if (v.kind === "unit" && !ids.includes(v.id)) onChange([...ids, v.id]); }, { unitOnly: true }));
}

/** Arcs: characters, events, supersenses, dialogue or topics across the books. */
async function narArcs(body) {
  const N = S.nar, U = await units();
  const top = types => U.rows.filter(r => types.includes(r.type)).slice(0, 5).map(r => r.id);
  const present = new Set(U.rows.map(r => r.id));
  N.ids = N.ids.filter(id => present.has(id));            // entities remembered from earlier may be gone (linked since, or below the minimum now)
  if (!N.ids.length) N.ids = top(["PER"]);
  const out = h("div", {}, loading("Loading…"));
  const run = async () => {
    out.replaceChildren(loading("Loading…"));
    const extra = [];
    let r;
    if (N.arcKind === "topics") {
      const models = (await api("/api/topics/models")).models;
      if (!models.length) { out.className = ""; out.replaceChildren(h("p", { class: "muted small" }, "There's no topic model yet. Fit one under ", h("a", { href: "#/topics" }, "Topics"), ".")); return; }
      if (!models.some(m => m.id === N.topicModel)) { N.topicModel = models[0].id; N.topicIds = []; }
      const pickModel = h("div", { class: "controls" }, h("label", {}, "Topic model", h("select", { onchange: e => { N.topicModel = e.target.value; N.topicIds = []; saveNar(); run(); } },
        models.map(m => h("option", { value: m.id, selected: m.id === N.topicModel }, `${m.name} (${m.k} topics)`)))));
      try { r = await api("/api/narrative/arcs", withBooks({ seg: N.seg, kind: "topics", model: N.topicModel, ids: N.topicIds })); }
      catch (e) { out.className = ""; out.replaceChildren(pickModel, h("p", { class: "warn small" }, e.message)); return; }
      N.topicIds = r.series.map(s => s.id); saveNar();
      r.series.forEach(s => (s.color = topicColor(s.id)));
      const cur = new Set(N.topicIds);
      extra.push(pickModel, h("p", { class: "small muted", style: { margin: "0 0 6px" } }, `Model fitted on ${r.info.model.books.join(", ")}. Topics not covered by the selected books show nothing there.`),
        h("div", { class: "chips", style: { marginBottom: "8px" } }, r.info.topics.map(t => h("button", { class: "chip" + (cur.has(t.id) ? " on" : ""), title: `${fmt(100 * t.share, 1)}% of the model's words`,
          onclick: () => { const next = cur.has(t.id) ? [...cur].filter(x => x !== t.id) : [...cur, t.id]; if (!next.length) return; N.topicIds = next; saveNar(); run(); } }, h("span", { class: "tdot", style: { background: topicColor(t.id), marginRight: "5px" } }), `${t.id + 1}. ${t.name}`))));
    } else r = await api("/api/narrative/arcs", withBooks({ seg: N.seg, kind: N.arcKind, ids: N.ids, cats: N.cats }));
    if (N.arcKind === "entities") extra.push(h("div", { class: "row", style: { marginBottom: "8px" } }, entityChips(N.ids, v => { N.ids = v; saveNar(); run(); }, U),
      h("button", { class: "btn small", onclick: () => { N.ids = top(["PER"]); saveNar(); run(); } }, "Top 5 people"),
      h("button", { class: "btn small", onclick: () => { N.ids = top(["LOC", "FAC", "GPE"]); saveNar(); run(); } }, "Top 5 places")));
    if (N.arcKind === "supersenses") {
      const cur = new Set(r.series.map(s => s.name));
      extra.push(h("div", { class: "chips", style: { marginBottom: "8px" } }, (r.info.available || []).slice(0, 40).map(a => h("button", { class: "chip" + (cur.has(a.item) ? " on" : ""),
        onclick: () => { const next = cur.has(a.item) ? [...cur].filter(x => x !== a.item) : [...cur, a.item]; N.cats = next.length ? next : null; saveNar(); run(); } },
        a.item.replace(/^(verb|noun)\./, m => m === "verb." ? "v. " : "n. "), h("span", { class: "n" }, fmt(a.n))))));
    }
    const fb = Object.entries(r.info).filter(([b, i]) => i && i.fallback).map(([b]) => bookTitle(b));
    const unit = N.arcKind === "dialogue" ? "% of words" : N.arcKind === "topics" ? "% of the words in each segment" : "per 1,000 words";
    out.className = "";
    out.replaceChildren(...extra,
      fb.length ? h("p", { class: "warn small" }, `No chapters found in ${fb.join(", ")}; slices are used there.`) : null,
      r.series.length ? chartBox(arcChart(r.segments, r.series, { ylabel: unit, continuous: S.nar.seg.scope === "corpus" }), `arc-${N.arcKind}`) : h("p", { class: "muted small" }, "Choose something to plot."),
      r.series.length ? arcTable(r.segments, r.series, `arc ${N.arcKind}`) : null,
      note("How this is calculated", N.arcKind === "topics" ? "Each point is the topic's share of the words in that chapter or slice: the average share over the model's documents whose middle falls there, weighted by the words kept. The count is the number of documents. Segments with no document are left blank. The chapter or slice setting above decides the segments; topic pages and comparisons use the same measure."
        : S.lib.narrative_notes.arcs, "Hover over a point for its value and count. Segments are numbered along the bottom within each book."));
  };
  body.append(h("section", { class: "panel" },
    h("div", { class: "controls" }, h("div", { class: "fld" }, "Plot", seg([["entities", "Characters and places"], ["events", "Events"], ["supersenses", "Supersenses"], ["dialogue", "Dialogue"], ["topics", "Topics"]], N.arcKind, v => { N.arcKind = v; saveNar(); renderNarrative($("#main"), "arcs"); }))),
    out));
  run();
}

/** Style figures per book or per segment, with a chart and a parts-of-speech profile. */
async function narStyle(body) {
  const N = S.nar;
  const out = h("div", {}, loading("Calculating…"));
  const r = await api("/api/narrative/style", withBooks({ seg: N.seg, by: N.styleBy }));
  const cols = [{ k: "title", label: "Book" }, ...(N.styleBy === "segment" ? [{ k: "label", label: "Segment" }] : []),
    ...STYLE_COLS.map(([k, l, d]) => ({ k, label: l, num: true, fmt: (v, row) => v == null ? "—" : k === "mattr" && !row.mattr_ok ? `(${fmt(v, d)})` : fmt(v, d) }))];
  const posRows = r.rows.map(x => ({ title: x.title, label: x.label, ...x.pos }));
  const posCols = [{ k: "title", label: "Book" }, ...(N.styleBy === "segment" ? [{ k: "label", label: "Segment" }] : []),
    ...Object.keys((r.rows[0] || {}).pos || {}).map(p => ({ k: p, label: p, num: true, fmt: v => fmt(v, 1) }))];
  const metric = STYLE_COLS.find(c => c[0] === N.styleMetric) || STYLE_COLS[2];
  const chart = N.styleBy === "segment"
    ? arcChart(r.rows.map(x => ({ book: x.book, title: x.title, label: x.label, words: x.words })), [{ name: metric[1], values: r.rows.map(x => x[metric[0]]) }])
    : hbarChart([{ name: metric[1], color: "#2e4a62", rows: r.rows.map(x => ({ item: x.title, n: x[metric[0]] })) }], { max: 60, dec: metric[2] });
  out.className = "";
  out.replaceChildren(
    h("div", { class: "controls" }, h("label", {}, "Chart", h("select", { onchange: e => { N.styleMetric = e.target.value; saveNar(); renderNarrative($("#main"), "style"); } },
      STYLE_COLS.map(([k, l]) => h("option", { value: k, selected: k === metric[0] }, l))))),
    chartBox(chart, `style-${metric[0]}`),
    table(cols, r.rows, { limit: 60, csvName: `style by ${N.styleBy}` }),
    h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Parts of speech, % of words"),
    table(posCols, posRows, { limit: 60, csvName: `pos profile by ${N.styleBy}` }),
    note("How these are calculated", S.lib.narrative_notes.style));
  body.append(h("section", { class: "panel" },
    h("div", { class: "controls" }, h("div", { class: "fld" }, "One row per", seg([["book", "Book"], ["segment", N.seg.mode === "chapters" ? "Chapter" : "Slice"]], N.styleBy, v => { N.styleBy = v; saveNar(); renderNarrative($("#main"), "style"); }))),
    out));
}

/** A cluster tree from the server's nested tree; leaves are labelled and coloured. */
function dendrogram(tree, texts, colorOf) {
  const leaves = [];
  const walk = t => { if (t.children) t.children.forEach(walk); else leaves.push(t.leaf); };
  walk(tree);
  const rowH = 18, top = 10, W = 900, labW = 300, H = top + leaves.length * rowH + 30, pw = W - labW - 20;
  const maxH = tree.height || 1;
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, "font-family": SVG_FONT, "font-size": 11.5, role: "img", "aria-label": "Cluster tree", style: "max-width:1000px" });
  const yLeaf = {};
  leaves.forEach((l, k) => (yLeaf[l] = top + k * rowH + rowH / 2));
  const xOf = hgt => 10 + pw * (1 - hgt / maxH);
  const draw = t => {
    if (!t.children) return [xOf(0), yLeaf[t.leaf]];
    const [a, b] = t.children.map(draw);
    const x = xOf(t.height);
    g.append(svg("path", { d: `M${a[0]},${a[1]} H${x} V${b[1]} H${b[0]}`, fill: "none", stroke: cssVar("--muted"), "stroke-width": 1.2 }));
    return [x, (a[1] + b[1]) / 2];
  };
  draw(tree);
  leaves.forEach(l => g.append(svg("text", { x: xOf(0) + 6, y: yLeaf[l] + 4, fill: colorOf(texts[l]) }, texts[l].label.length > 46 ? texts[l].label.slice(0, 45) + "…" : texts[l].label)));
  const y = top + leaves.length * rowH + 16;
  g.append(svg("line", { x1: xOf(maxH), x2: xOf(0), y1: y - 8, y2: y - 8, stroke: cssVar("--rule") }));
  g.append(svg("text", { x: xOf(maxH), y: y + 6, fill: cssVar("--faint"), "font-size": 10.5 }, fmt(maxH, 3)));
  g.append(svg("text", { x: xOf(0), y: y + 6, fill: cssVar("--faint"), "font-size": 10.5, "text-anchor": "end" }, "0 (identical)"));
  return g;
}
/** A scatter plot of texts on the first two principal components. */
function scatter(texts, colorOf, variance) {
  const W = 760, H = 500, M = 50;
  const xs = texts.map(t => t.x), ys = texts.map(t => t.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)];
  const X = v => M + (W - 2 * M) * (v - x0) / ((x1 - x0) || 1), Y = v => H - M - (H - 2 * M) * (v - y0) / ((y1 - y0) || 1);
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, "font-family": SVG_FONT, "font-size": 11, role: "img", "aria-label": "Stylometric map", style: "max-width:860px" });
  g.append(svg("rect", { x: M / 2, y: M / 2, width: W - M, height: H - M, fill: "none", stroke: cssVar("--rule-soft") }));
  g.append(svg("text", { x: W / 2, y: H - 8, "text-anchor": "middle", fill: cssVar("--faint") }, `Component 1 (${fmt(100 * variance[0], 1)}% of variance)`));
  g.append(svg("text", { x: 12, y: H / 2, fill: cssVar("--faint"), transform: `rotate(-90 12 ${H / 2})`, "text-anchor": "middle" }, `Component 2 (${fmt(100 * (variance[1] || 0), 1)}%)`));
  texts.forEach(t => {
    g.append(svg("circle", { cx: X(t.x), cy: Y(t.y), r: 5, fill: colorOf(t) }, svg("title", {}, t.label)));
    if (texts.length <= 40) g.append(svg("text", { x: X(t.x) + 7, y: Y(t.y) + 4, fill: cssVar("--ink"), stroke: cssVar("--panel"), "stroke-width": 3, "paint-order": "stroke" }, t.label.length > 30 ? t.label.slice(0, 29) + "…" : t.label));
  });
  return g;
}

/** Stylometry: cluster tree, principal-component map, nearest texts and distances. */
async function narStylo(body) {
  const N = S.nar, o = N.stylo;
  const out = h("div", {}, loading("Calculating…"));
  const run = async () => {
    saveNar();
    out.replaceChildren(loading("Calculating…"));
    const r = await api("/api/narrative/stylometry", withBooks({ seg: N.seg, ...o }));
    if (r.error) { out.replaceChildren(h("div", { class: "empty" }, r.error)); return; }
    const keyOf = t => o.color === "author" ? (t.author || "unknown author") : o.color === "series" ? (t.series || "no series") : t.book;
    const keys = [...new Set(r.texts.map(keyOf))];
    const colorOf = t => PALETTE[keys.indexOf(keyOf(t)) % PALETTE.length];
    const labels = r.texts.map(t => t.label);
    const mRows = r.matrix.map((row, i) => { const o2 = { label: labels[i] }; row.forEach((v, j) => (o2["d" + j] = v)); return o2; });
    out.replaceChildren(
      h("p", { class: "small muted" }, `${plural(r.texts.length, "text")}, ${r.mfw} most frequent words. Colours: ${keys.map(k => o.color === "book" ? bookTitle(k) : k).join(", ")}.`),
      h("h3", { class: "small muted" }, "Cluster tree"), chartBox(dendrogram(r.tree, r.texts, colorOf), "stylometry-tree"),
      h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Map (principal components)"), chartBox(scatter(r.texts, colorOf, r.variance), "stylometry-map"),
      h("div", { class: "cols2", style: { marginTop: "8px" } }, r.loadings.map((l, k) => h("div", { class: "small" }, h("b", {}, `Component ${k + 1}`),
        h("div", {}, "Towards +: ", l.pos.join(", ")), h("div", {}, "Towards −: ", l.neg.join(", "))))),
      h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Nearest texts"),
      table([{ k: "label", label: "Text" }, { k: "nearest", label: "Closest three (distance)", fmt: v => v.map(x => `${x.label} (${fmt(x.d, 3)})`).join("; "), csv: v => v.map(x => `${x.label} (${x.d})`).join("; ") }],
        r.nearest, { limit: 30, csvName: "stylometry nearest" }),
      h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Distances"),
      table([{ k: "label", label: "" }, ...labels.map((l, j) => ({ k: "d" + j, label: l.length > 18 ? l.slice(0, 17) + "…" : l, num: true, fmt: v => fmt(v, 3), title: l }))], mRows, { limit: 60, csvName: "stylometry distances" }),
      h("p", { class: "small muted" }, "Most frequent words used: " + r.words.join(", ") + (r.mfw > 50 ? "…" : "")),
      note("How this is calculated", S.lib.narrative_notes.stylo));
  };
  const num = (k, label, min, max) => h("label", {}, label, h("input", { type: "number", min, max, value: o[k], onchange: e => { o[k] = Math.min(max, Math.max(min, +e.target.value || min)); run(); } }));
  const sel = (k, label, opts) => h("label", {}, label, h("select", { onchange: e => { o[k] = e.target.value; run(); } }, opts.map(([v, l]) => h("option", { value: v, selected: o[k] === v }, l))));
  body.append(h("section", { class: "panel" },
    h("div", { class: "controls" },
      h("div", { class: "fld" }, "Texts", seg([["books", "Whole books"], ["segments", "Chapters or slices"]], o.units, v => { o.units = v; saveNar(); renderNarrative($("#main"), "stylometry"); })),
      num("mfw", "Most frequent words", 10, 2000), num("culling", "Culling % of texts", 0, 100),
      sel("measure", "Distance", [["cosine", "Cosine Delta"], ["classic", "Classic Delta"], ["euclidean", "Euclidean"]]),
      sel("linkage", "Tree", [["average", "Average linkage"], ["complete", "Complete linkage"], ["ward", "Ward"]]),
      sel("scope", "Text", [["all", "Everything"], ["narration", "Narration only"], ["dialogue", "Dialogue only"]]),
      sel("color", "Colour by", [["book", "Book"], ["author", "Author"], ["series", "Series"]]),
      h("label", { class: "inline" }, h("input", { type: "checkbox", checked: o.exclude_pronouns, onchange: e => { o.exclude_pronouns = e.target.checked; run(); } }), "Leave out pronouns")),
    out));
  run();
}

/** Sentiment (VADER) and emotion (a lexicon you load) across the books. */
async function narSentiment(body) {
  const N = S.nar, U = await units();
  const present = new Set(U.rows.map(r => r.id));
  N.sentIds = N.sentIds.filter(id => present.has(id));         // entities remembered from earlier may be gone since
  const lx = await api("/api/narrative/lexicons");
  const sOut = h("div"), eOut = h("div");
  const runS = async () => {
    if (!lx.vader) { sOut.replaceChildren(h("p", { class: "warn" }, "Sentiment needs one more package. In a terminal, with your environment active, run: pip install vaderSentiment. Then restart the analyser.")); return; }
    sOut.replaceChildren(loading("Scoring sentences… (the first time takes a little while per book)"));
    const r = await api("/api/narrative/sentiment", withBooks({ seg: N.seg, ids: N.sentIds }));
    sOut.replaceChildren(
      h("div", { class: "row", style: { marginBottom: "8px" } }, h("span", { class: "small muted" }, "Also around:"), entityChips(N.sentIds, v => { N.sentIds = v; saveNar(); runS(); }, U)),
      chartBox(arcChart(r.segments, r.series, { ylabel: "mean VADER compound score (−1 to +1)", continuous: S.nar.seg.scope === "corpus" }), "sentiment-arc"),
      table([{ k: "title", label: "Book" }, { k: "sentences", label: "Sentences", num: true, fmt: v => fmt(v) }, { k: "mean", label: "Mean score", num: true, fmt: v => fmt(v, 3) },
        { k: "positive", label: "% positive", num: true, fmt: v => fmt(v, 1) }, { k: "negative", label: "% negative", num: true, fmt: v => fmt(v, 1) }], r.books, { csvName: "sentiment by book" }),
      arcTable(r.segments, r.series, "sentiment arc", 3),
      note("How this is calculated", S.lib.narrative_notes.sentiment));
  };
  const upload = h("input", { type: "file", accept: ".txt,.tsv,.csv,text/plain", hidden: true, onchange: async e => {
    const f = e.target.files[0]; if (!f) return;
    const r = await api("/api/narrative/lexicons", { name: f.name.replace(/\.[^.]+$/, ""), text: await f.text() });
    toast(`Loaded ${r.emotion.name}: ${Object.keys(r.emotion.cats).length} categories.`); renderNarrative($("#main"), "sentiment"); } });
  const runE = async () => {
    if (!lx.emotion) {
      eOut.replaceChildren(h("p", { class: "small" }, "Load a word–emotion lexicon to plot emotions. The NRC Emotion Lexicon (Mohammad & Turney) is the usual choice. It's free for research, but can't be included here, so download the word-level file from ",
        h("a", { href: "https://saifmohammad.com/WebPages/NRC-Emotion-Lexicon.htm", target: "_blank", rel: "noopener" }, "its author's site"),
        " and load “NRC-Emotion-Lexicon-Wordlevel”. Any file with a word, a category and optionally 1/0 on each line works too."),
        h("button", { class: "btn", onclick: () => upload.click() }, "Load a lexicon…"), upload);
      return;
    }
    eOut.replaceChildren(loading("Counting…"));
    const all = Object.keys(lx.emotion.cats).sort();
    const chosen = N.emoCats && N.emoCats.length ? N.emoCats.filter(c => all.includes(c)) : all.filter(c => !["positive", "negative"].includes(c)).slice(0, 8);
    const r = await api("/api/narrative/emotion", withBooks({ seg: N.seg, cats: chosen }));
    eOut.replaceChildren(
      h("div", { class: "row", style: { marginBottom: "8px" } }, h("span", { class: "small muted" }, `${lx.emotion.name}:`),
        h("div", { class: "chips" }, all.map(c => h("button", { class: "chip" + (chosen.includes(c) ? " on" : ""), onclick: () => { N.emoCats = chosen.includes(c) ? chosen.filter(x => x !== c) : [...chosen, c]; saveNar(); runE(); } }, c, h("span", { class: "n" }, fmt(lx.emotion.cats[c]))))),
        h("button", { class: "btn small", onclick: () => upload.click() }, "Replace lexicon…"),
        h("button", { class: "btn small", onclick: async () => { await api("/api/narrative/lexicons/delete", {}); renderNarrative($("#main"), "sentiment"); } }, "Remove"), upload),
      chartBox(arcChart(r.segments, r.series, { ylabel: "words per 1,000", continuous: S.nar.seg.scope === "corpus" }), "emotion-arc"),
      arcTable(r.segments, r.series, "emotion arc"),
      note("How this is calculated", S.lib.narrative_notes.emotion));
  };
  body.append(h("section", { class: "panel" }, h("h2", {}, "Sentiment"), sOut), h("section", { class: "panel" }, h("h2", {}, "Emotion"), eOut));
  runS(); runE();
}
