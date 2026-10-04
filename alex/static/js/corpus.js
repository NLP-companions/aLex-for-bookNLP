"use strict";
/* ---------- Corpus tools ---------- */
const NO_FILTER = () => ({ pos: [], tag: [], ent: [] });             // a word-type filter that lets every word through
S.corp = loadState("analyser.corp", { sub: "kwic", query: "", mode: "simple", batch: false, showMatch: false, context: 10, near: null,
  sort: [{ pos: "R1", by: "word", desc: false }, { pos: "R2", by: "word", desc: false }, { pos: "R3", by: "word", desc: false }],   // concordance sort levels
  ctx: { query: "", mode: "simple", left: 5, right: 5, within_sentence: false, exclude: false },                                    // the context search
  settings: { match: "word", case: false, regex: false, wildcards: true, skip_punct: true }, scope: { kind: "all" },
  wl: { unit: "word", min_freq: 1, min_range: 1, filter: "", flt: NO_FILTER() },
  ng: { n_min: 2, n_max: 3, unit: "word", min_freq: 2, min_range: 1, contains: "", position: "any", within_sentence: true },
  col: { left: 5, right: 5, unit: "word", sort: "logdice", min_freq: 3, min_range: 1, within_sentence: false, flt: NO_FILTER() },
  kw: { unit: "word", refKind: "books", refBooks: null, refScope: "same", refFile: "", negative: false, min_range: 1 } });
// settings saved by an earlier version: sort levels were plain positions ("R1"), and there was no word-type filter
S.corp.sort = S.corp.sort.map(lv => typeof lv === "string" ? { pos: lv, by: "word", desc: false } : lv);
for (const o of [S.corp.wl, S.corp.col]) o.flt = { ...NO_FILTER(), ...(o.flt || {}) };
/** Save the corpus settings (the near-word filter is not kept). */
const saveCorp = () => saveState("analyser.corp", { ...S.corp, near: null });
/** Where a corpus search looks. */
const SCOPES = [["all", "Everywhere"], ["narration", "Narration only"], ["dialogue", "Dialogue only"], ["speech", "Speech of…"]];
/** A phrase for the scope, for result summaries. */
const scopeLabel = sc => ({ narration: "in narration", dialogue: "in dialogue", speech: `in the speech of ${specLabel(sc.speaker)}` }[sc.kind] || "across the whole text");

/** A scope selector: everywhere, narration, dialogue, or the speech of someone. */
function scopeControl(value, onChange, opts = {}) {
  const box = h("div", { class: "fld" });
  const draw = () => {
    const sel = h("select", { onchange: e => { const k = e.target.value; value = k === "speech" ? { kind: "speech", speaker: value.speaker || null } : k === "same" ? { kind: "same" } : { kind: k }; draw(); if (k !== "speech") onChange(value); } },
      (opts.same ? [["same", "Same as the target"]] : []).concat(SCOPES).map(([k, l]) => h("option", { value: k, selected: value.kind === k }, l)));
    box.replaceChildren(opts.label || "Search in", h("div", { class: "row" }, sel,
      value.kind === "speech" ? picker(value.speaker, v => { value = { kind: "speech", speaker: v }; onChange(value); }) : null));
  };
  draw();
  return box;
}

/** The collapsed "Search settings" (word forms or lemmas, case, regular expressions, ignore punctuation). */
function searchSettings(onChange) {
  const st = S.corp.settings;
  const set = (k, v) => { st[k] = v; saveCorp(); onChange(); };
  return h("div", { class: "controls", style: { marginTop: "8px" } },
    h("div", { class: "fld" }, "Simple searches match", seg([["word", "Word forms"], ["lemma", "Lemmas"]], st.match, v => set("match", v))),
    h("label", { class: "inline" }, h("input", { type: "checkbox", checked: st.case, onchange: e => set("case", e.target.checked) }), "Case sensitive"),
    h("label", { class: "inline" }, h("input", { type: "checkbox", checked: st.regex, onchange: e => set("regex", e.target.checked) }), "Regular expressions"),
    h("label", { class: "inline", title: "Off, * ? | and # are literal characters (in Simple and Pattern alike) — turn this off, and Ignore punctuation off too, to search for a mark like ? or * itself", disabled: st.regex },
      h("input", { type: "checkbox", checked: st.wildcards, disabled: st.regex, onchange: e => set("wildcards", e.target.checked) }), "Wildcards"),
    h("label", { class: "inline", title: "Match and count words only, so “said Holmes” also finds “said, Holmes”" }, h("input", { type: "checkbox", checked: st.skip_punct, onchange: e => set("skip_punct", e.target.checked) }), "Ignore punctuation"),
    h("span", { class: "small muted" }, st.regex ? "Regular expressions are on: each word or value is a full regular expression (Python syntax), e.g. s(ai|ay)d." :
      st.wildcards ? "Wildcards: * any letters, ? one letter, a|b either." : "Wildcards are off: *, ?, | and # are literal characters."));
}

/** The search box: simple/pattern mode, a single-line box or (Batch on) a list box of one term or pattern per line,
    and the syntax help. A batch is tried line by line and the hits merged into one search (`core.corpus.Matcher`). */
function queryBar(onSearch) {
  const c = S.corp;
  const search = raw => { c.query = raw.trim(); saveCorp(); onSearch(); };
  const inp = h("input", { type: "search", value: c.query, class: "grow", style: { font: "15px var(--serif)", padding: "7px 10px" },
    placeholder: c.mode === "simple" ? "e.g. said | look* at | the # of" : 'e.g. [lemma="say"] [pos="ADV"]  or  [char="Holmes"] [lemma="look"]',
    hidden: c.batch, onkeydown: e => { if (e.key === "Enter") search(inp.value); } });
  const area = h("textarea", { class: "grow", rows: 3, style: { font: "15px var(--serif)", padding: "7px 10px", resize: "vertical" }, value: c.query,
    placeholder: c.mode === "simple" ? "One word or phrase per line, e.g.\nsaid\nasked\nshouted" : 'One pattern per line, e.g.\n[lemma="say"]\n[lemma="ask"]',
    hidden: !c.batch, onkeydown: e => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) search(area.value); } });
  const attrs = S.lib.corpus_attrs;
  return h("div", {},
    h("div", { class: "row" }, seg([["simple", "Simple"], ["pattern", "Pattern"]], c.mode, v => { c.mode = v; saveCorp(); renderCorpus($("#main"), c.sub); }),
      inp, area,
      h("label", { class: "inline small", title: "Search several terms or patterns at once, one per line: every line is tried and the hits merged into one search" },
        h("input", { type: "checkbox", checked: c.batch, onchange: e => { c.batch = e.target.checked; saveCorp(); renderCorpus($("#main"), c.sub); } }), "Batch"),
      h("button", { class: "btn primary", onclick: () => search(c.batch ? area.value : inp.value) }, "Search")),
    c.batch ? h("p", { class: "small muted", style: { margin: "4px 0 0" } }, "Ctrl/Cmd+Enter to search (Enter alone starts a new line).") : null,
    c.mode === "pattern" ? note("Pattern syntax",
      "Each token is written in square brackets with one or more conditions joined by &: [lemma=\"say\" & tag=\"VBD\"]. Use != for “not”. [] matches any token. A bare word outside brackets matches that word form.",
      "After a token: ? optional, * up to 10, + one to 10, {2} exactly two, {1,3} one to three. For example [pos=\"ADJ\"]{2} [pos=\"NOUN\"].",
      "Attributes: " + Object.entries(attrs).map(([k, v]) => `${k} (${v})`).join("; ") + ".",
      "Values use wildcards (* ? |) unless regular expressions are turned on in Search settings, or Wildcards is turned off there (to search for a * ? | or # itself; turn off Ignore punctuation too, since those are usually punctuation). Word forms ignore case unless Case sensitive is on; other attributes always ignore case.",
      "Batch (several patterns at once): tick Batch above and list whole patterns, one per line — [lemma=\"say\"] and [lemma=\"ask\"] on separate lines finds either, tried in the order you list them and merged into one search. A “Matched” column (toggle it under the results) shows which line found each hit.") :
      note("Simple syntax", "Type one or more words: look at. Wildcards: * any letters (look*), ? one letter (s?ng), a|b either (said|cried), # any one word (the # of); turn Wildcards off under Search settings (and Ignore punctuation off too) to search for one of these characters itself, like a literal ?. Search settings choose between word forms and lemmas. Switch to Pattern to search BookNLP's tags, entities, supersenses, quotes and speakers.",
        "Batch (several words or phrases at once): tick Batch above and list them, one per line — quicker than typing said|asked|shouted by hand, and, unlike a|b, each line can be a whole phrase (look at|listen to won't work, but two lines will). Every line is tried and the hits merged into one search, with a “Matched” column (toggle it under the results) showing which line found each hit."));
}

/** One concordance line: left context, hit, right context, book and position, and (a batch search, with the
    "Matched" column on) which of the batch's lines found it. */
function kwicLine(h1, onOpen, showMatch) {
  return h("div", { class: "kl" + (showMatch ? " with-match" : ""), onclick: onOpen, role: "button", tabindex: 0, onkeydown: e => { if (e.key === "Enter") onOpen(); } },
    showMatch ? h("span", { class: "kl-m", title: "Matched: " + h1.matched }, h1.matched) : null,
    h("span", { class: "kl-l" }, h("span", {}, h1.left)), h("span", { class: "kl-k" }, h1.key), h("span", { class: "kl-r" }, h1.right),
    h("span", { class: "kl-s" }, `${h1.title} ${fmt(h1.pos, 0)}%`));
}

/** The concordance plot: a strip per book showing where the hits fall. `perBook[].bins` counts the hits in equal slices of the book
    (the server makes them, so a word with tens of thousands of hits costs the page no more than a rare one); darker = more. */
function plotChart(perBook) {
  const W = 900, rowH = 30, labW = 190, top = 6, H = top + perBook.length * rowH + 18;
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, "font-family": SVG_FONT, "font-size": 12, role: "img", "aria-label": "Concordance plot", style: "max-width:1000px" });
  perBook.forEach((p, i) => {
    const y = top + i * rowH, max = Math.max(...p.bins, 1), bw = (W - labW) / p.bins.length;
    g.append(svg("text", { x: labW - 10, y: y + 13, "text-anchor": "end", fill: cssVar("--ink") }, p.title.length > 26 ? p.title.slice(0, 25) + "…" : p.title));
    g.append(svg("text", { x: labW - 10, y: y + 25, "text-anchor": "end", fill: cssVar("--faint"), "font-size": 10.5 }, `${fmt(p.hits)} hits, ${fmt(p.per1k, 2)}/1k`));
    g.append(svg("rect", { x: labW, y: y + 3, width: W - labW, height: 22, fill: cssVar("--panel"), stroke: cssVar("--rule") }));
    p.bins.forEach((n, j) => {
      if (n) g.append(svg("rect", { x: labW + j * bw, y: y + 4, width: bw + 0.3, height: 20, fill: cssVar("--ink"), "fill-opacity": 0.2 + 0.8 * Math.sqrt(n / max) }));
    });
  });
  const y = top + perBook.length * rowH + 12;
  g.append(svg("text", { x: labW, y, fill: cssVar("--faint"), "font-size": 10.5 }, "start of book"));
  g.append(svg("text", { x: W, y, fill: cssVar("--faint"), "font-size": 10.5, "text-anchor": "end" }, "end"));
  return g;
}

/** The Corpus pages (concordance, word list, n-grams, collocates, keywords) with shared scope and settings. */
async function renderCorpus(main, sub) {
  const c = S.corp;
  c.sub = sub || c.sub;
  const tabs = [["kwic", "Concordance"], ["wordlist", "Word list"], ["ngrams", "N-grams"], ["collocates", "Collocates"], ["keywords", "Keywords"]];
  const body = h("div");
  // the tool tabs are their own element, a direct child of main (not nested in the settings panel below), so they
  // stay sticky across the whole page — settings and results both — not just while their own short panel is in view
  main.replaceChildren(
    h("div", { class: "subtabs corp-tabs" }, tabs.map(([k, l]) => h("button", { class: k === c.sub ? "on" : "", onclick: () => (location.hash = "#/corpus/" + k) }, l))),
    h("section", { class: "panel" },
      h("div", { class: "controls", style: { marginBottom: 0 } },
        c.sub !== "keywords" ? scopeControl(c.scope, v => { c.scope = v; saveCorp(); renderCorpus(main, c.sub); }) : null),
      searchSettings(() => renderCorpus(main, c.sub))),
    body);
  await ({ kwic: corpKwic, wordlist: corpWordlist, ngrams: corpNgrams, collocates: corpCollocates, keywords: corpKeywords }[c.sub] || corpKwic)(body);
}
/** Jump to the concordance with a query (from a word list row, a profile link…). */
const goKwic = (query, mode, near) => { S.corp.query = query; S.corp.mode = mode || "simple"; S.corp.near = near || null; saveCorp(); if (location.hash === "#/corpus/kwic") render(); else location.hash = "#/corpus/kwic"; };
/** The concordance query, and its mode, that finds an item of a list (a word, lemma, word+POS, word+POS+lemma or POS).
    `row` is the list row, which a word+POS+lemma item needs (it has the three parts separately). */
const itemQuery = (item, unit, row) => unit === "lemma" ? [`[lemma="${item}"]`, "pattern"]
  : unit === "word_pos" ? [`[word="${item.replace(/_[^_]*$/, "")}" & pos="${item.split("_").pop()}"]`, "pattern"]
  : unit === "word_pos_lemma" ? [`[word="${row.word}" & pos="${row.pos}" & lemma="${row.lemma}"]`, "pattern"]
  : unit === "pos" ? [`[pos="${item}"]`, "pattern"] : [item.replace(/[*?|#]/g, m => (S.corp.settings.regex ? "\\" + m : m)), "simple"];

/** A word-type filter for lists: choose word classes (POS), entity types and fine tags, several of each. `flt` is `{pos, tag, ent}`
    (arrays of chosen values, kept by the caller); `onChange()` is called after each change. A word passes if it matches one choice in
    every group where something is chosen. */
function typeFilter(flt, onChange) {
  const box = h("details", { class: "note tfilter", style: { marginTop: 0 } });
  const summary = h("summary", {});
  const body = h("div", { style: { marginTop: "8px" } }, loading("Loading…"));
  const chosen = () => flt.pos.length + flt.tag.length + flt.ent.length;
  const label = () => {
    summary.textContent = chosen() ? "Word types: " + [...flt.pos, ...flt.ent, ...flt.tag].join(", ") : "Word types: all words (click to choose word classes, entity types or fine tags)";
    box.classList.toggle("active", chosen() > 0);
  };
  const group = (title, key, list, hint) => h("div", { style: { margin: "6px 0" } }, title ? h("div", { class: "small muted" }, title, hint ? h("span", {}, " · ", hint) : null) : null,
    h("div", { class: "chips", style: { marginTop: "4px" } }, list.map(o => h("button", { class: "chip" + (flt[key].includes(o.value) ? " on" : ""), type: "button", "aria-pressed": String(flt[key].includes(o.value)),
      title: `${o.label || o.value}: ${fmt(o.n)} words`,
      onclick: e => { flt[key] = flt[key].includes(o.value) ? flt[key].filter(v => v !== o.value) : [...flt[key], o.value]; e.currentTarget.classList.toggle("on", flt[key].includes(o.value)); label(); saveCorp(); onChange(); } },
      o.value, o.label && key !== "tag" ? h("span", { class: "n" }, o.label) : null))));
  label();
  box.append(summary, body);
  box.open = chosen() > 0;
  filterOptions().then(O => body.replaceChildren(
    group("Word class (POS)", "pos", O.pos, "BookNLP's universal tags"),
    group("Entity type", "ent", O.ent, "words that are part of a mention of this kind"),
    h("details", {}, h("summary", { class: "small" }, "Fine POS tags"), group(null, "tag", O.tag)),
    h("div", { class: "row" }, h("button", { class: "btn small", disabled: !chosen(), onclick: () => { flt.pos = []; flt.tag = []; flt.ent = []; saveCorp(); onChange(); box.replaceWith(typeFilter(flt, onChange)); } }, "Clear the filter"),
      h("span", { class: "small muted" }, "Several choices in one group mean any of them; choices in different groups must all hold."))));
  return box;
}
/** The word classes, fine tags and entity types of the selected books (fetched once per selection). */
async function filterOptions() {
  const key = selected().join();
  if (S.filterOpts && S.filterOptsKey === key) return S.filterOpts;
  S.filterOpts = await api("/api/corpus/filters", withBooks({}));
  S.filterOptsKey = key;
  return S.filterOpts;
}
/** "nouns and verbs that are part of a PER mention" for a filter in a result summary; "" if it lets everything through. */
const filterLabel = flt => [flt.pos.length ? flt.pos.join("/") : "", flt.tag.length ? flt.tag.join("/") : "", flt.ent.length ? "in " + flt.ent.join("/") + " mentions" : ""].filter(Boolean).join(" ");

/** The context search: keep hits that have (or don't have) something in the words around them. It takes a query like the main
    search (simple or pattern), and how far to look on each side. `onChange()` runs the search again. */
function ctxControl(onChange) {
  const x = S.corp.ctx;
  const label = () => x.query.trim() ? `Context search: hits ${x.exclude ? "without" : "with"} “${x.query.trim()}” within ${x.left} words left and ${x.right} right` : "Search in the context of the hits";
  const summary = h("summary", {}, label());
  const set = (k, v) => { x[k] = v; summary.textContent = label(); saveCorp(); onChange(); };
  const num = (k, label) => h("label", {}, label, h("input", { type: "number", min: 0, max: 60, value: x[k], onchange: e => set(k, Math.min(60, Math.max(0, +e.target.value || 0))) }));
  return h("details", { class: "note", open: !!x.query.trim(), style: { marginTop: "8px" } },
    summary,
    h("div", { class: "controls", style: { marginTop: "8px" } },
      h("label", {}, "Keep hits", h("select", { onchange: e => set("exclude", e.target.value === "no") },
        [["yes", "that have this in their context"], ["no", "that do not have this in their context"]].map(([v, l]) => h("option", { value: v, selected: (v === "no") === x.exclude }, l)))),
      h("label", {}, "Mode", h("select", { onchange: e => set("mode", e.target.value) }, [["simple", "Simple"], ["pattern", "Pattern"]].map(([v, l]) => h("option", { value: v, selected: x.mode === v }, l)))),
      h("label", { style: { flex: "1 1 220px" } }, "Context search", h("input", { type: "search", value: x.query, placeholder: x.mode === "simple" ? "e.g. not | never | Watson" : 'e.g. [pos="ADV"]  or  [char="Watson"]',
        onchange: e => set("query", e.target.value) })),
      num("left", "Words to the left"), num("right", "Words to the right"),
      h("label", { class: "inline" }, h("input", { type: "checkbox", checked: x.within_sentence, onchange: e => set("within_sentence", e.target.checked) }), "Stay within the sentence"),
      h("button", { class: "btn small", onclick: e => { x.query = ""; e.currentTarget.closest("details").querySelector("input[type=search]").value = ""; summary.textContent = label(); saveCorp(); onChange(); } }, "Clear")),
    h("p", { class: "small" }, "The hits are kept when a match of this second search lies wholly inside their window (not counting the hit itself). It uses the same syntax and Search settings as the search above, and the window stops at the edge of the search scope."));
}

/** The concordance: hits with sortable context, plot, per-book figures and paging. */
async function corpKwic(body) {
  const c = S.corp;
  const out = h("div");
  const opts = ["key", "L1", "L2", "L3", "L4", "L5", "R1", "R2", "R3", "R4", "R5", "book"];
  const optLabel = k => k === "key" ? "Search term" : k === "book" ? "Book and position" : k;
  /** One sort level: the position (the hit, a word left or right of it, or the book), what to compare there, and the direction. */
  const levelControl = k => {
    const lv = c.sort[k], change = (key, v) => { lv[key] = v; saveCorp(); run(); };
    return h("div", { class: "fld" }, `Sort ${k + 1}`, h("div", { class: "row", style: { gap: "4px", flexWrap: "nowrap" } },
      h("select", { "aria-label": `Sort ${k + 1}: position`, onchange: e => change("pos", e.target.value) }, opts.map(o => h("option", { value: o, selected: lv.pos === o }, optLabel(o)))),
      lv.pos === "book" ? null : h("select", { "aria-label": `Sort ${k + 1}: by`, onchange: e => change("by", e.target.value) },
        Object.entries(S.lib.sort_by).map(([v, l]) => h("option", { value: v, selected: lv.by === v }, l))),
      h("button", { class: "btn small", type: "button", "aria-pressed": String(lv.desc), title: lv.desc ? "Reversed (Z–A, least frequent first, last in the text first): click for the normal order" : "Normal order (A–Z, most frequent first): click to reverse",
        onclick: () => change("desc", !lv.desc) }, lv.desc ? "↑" : "↓")));
  };
  let latest = 0;                       // searches can overlap when settings change quickly: only the newest one may fill the page
  const run = async () => {
    const mine = ++latest;
    if (!c.query) { out.replaceChildren(h("div", { class: "empty" }, "Search for a word, phrase or pattern.")); return; }
    out.replaceChildren(loading("Searching…"));
    const req = withBooks({ query: c.query, mode: c.mode, settings: c.settings, scope: c.scope, context: c.context, sort: c.sort, near: c.near, ctx: c.ctx.query.trim() ? c.ctx : null, limit: 500 });
    const r = await api("/api/corpus/kwic", req);
    if (mine !== latest) return;
    const showMatch = () => r.batch && c.showMatch;
    const lines = h("div", { class: "kwic" }, r.hits.map(x => kwicLine(x, () => openContext(x), showMatch())));
    let offset = r.hits.length;
    const more = h("button", { class: "btn small", onclick: async () => {
      const r2 = await api("/api/corpus/kwic", { ...req, offset });
      lines.append(...r2.hits.map(x => kwicLine(x, () => openContext(x), showMatch()))); offset += r2.hits.length;
      if (offset >= r.total) more.remove(); } }, "Show more");
    const allHits = async () => { const r2 = await api("/api/corpus/kwic", { ...req, limit: 100000 }); return r2.hits; };
    out.replaceChildren(
      h("p", { class: "small muted" }, `${plural(r.total, "hit")}${r.capped ? " (stopped at the limit)" : ""}, ${fmt(r.per1k, 2)} per 1,000 words, ${scopeLabel(c.scope)}.`,
        c.ctx.query.trim() ? ` Only hits ${c.ctx.exclude ? "without" : "with"} “${c.ctx.query.trim()}” in their context.` : "",
        c.near ? [` Only hits with “${c.near.item}” within ${c.near.left} words left or ${c.near.right} right. `, h("button", { class: "btn small", onclick: () => { c.near = null; run(); } }, "Show all hits")] : null),
      r.total ? chartBox(plotChart(r.per_book), `plot-${slug(c.query)}`) : null,
      r.total ? h("div", { class: "cols2", style: { marginTop: "8px" } },
        table([{ k: "title", label: "Book" }, { k: "hits", label: "Hits", num: true }, { k: "per1k", label: "Per 1,000 words", num: true, fmt: v => fmt(v, 2) },
          { k: "d", label: "Dispersion (D)", num: true, fmt: v => v == null ? "—" : fmt(v, 2), title: "Juilland's D over ten equal parts of the book: 1 is perfectly even" }],
          r.per_book, { csvName: `hits by book ${c.query}`, csv: true }),
        table([{ k: "name", label: "Said by" }, { k: "n", label: "Hits", num: true }], r.speakers, { limit: 8, csvName: `hits by speaker ${c.query}` })) : null,
      r.total ? h("div", { class: "controls", style: { marginTop: "12px" } },
        [0, 1, 2].map(levelControl),
        h("label", {}, "Context", h("select", { onchange: e => { c.context = +e.target.value; saveCorp(); run(); } },
          [5, 10, 15, 25].map(n => h("option", { value: n, selected: c.context === n }, `${n} tokens`)))),
        r.batch ? h("label", { class: "inline", title: "Show which batch line found each hit" },
          h("input", { type: "checkbox", checked: c.showMatch, onchange: e => { c.showMatch = e.target.checked; saveCorp(); run(); } }), "Matched") : null,
        h("div", { class: "row grow", style: { justifyContent: "flex-end" } },
          h("button", { class: "btn small", onclick: async () => downloadCsv(`kwic-${slug(c.query)}`, r.batch ? ["book", "position_percent", "left", "hit", "right", "matched"] : ["book", "position_percent", "left", "hit", "right"],
            (await allHits()).map(x => r.batch ? [x.title, x.pos, x.left, x.key, x.right, x.matched] : [x.title, x.pos, x.left, x.key, x.right])) }, "Download CSV"))) : null,
      lines, r.total > offset ? more : null,
      note("How hits are counted", "Hits must lie wholly inside the chosen scope. Per 1,000 words divides hits by the words in scope. The plot shades each slice of a book by how many hits fall in it.",
        "Dispersion is Juilland's D over ten equal parts of each book: near 1, the term is spread evenly; near 0, it's concentrated in a few places. Click a line to read its paragraph.",
        "Sorting has up to three levels. Each looks at one place (the hit itself, one of the five words to its left or right, or the book) and compares its word, its lemma, its word class (POS), its fine tag, or how often that word occurs at that place among the hits (most frequent first). The arrow reverses a level. Hits that tie on every level stay in the order of the text."));
  };
  body.append(h("section", { class: "panel" }, queryBar(run), ctxControl(run), out));
  run();
}
/** Open the drawer with the paragraph around a concordance hit. */
async function openContext(x) {
  $("#drawerTitle").replaceChildren(h("h2", { style: { margin: 0 } }, x.key), h("div", { class: "muted small" }, `${x.title}, ${fmt(x.pos, 1)}% through`));
  $("#drawerBody").replaceChildren(loading("Loading…"));
  $("#drawer").hidden = false;
  const r = await api("/api/corpus/context", withBooks({ book: x.book, tok: x.tok, end: x.end }));
  $("#drawerBody").replaceChildren(h("div", { class: "ev" }, h("div", { class: "src" }, textLink(x.book, x.tok, x.end)), markup(r.text)));
}

/** A frequency list with range and dispersion, of words, lemmas, word + POS, word + POS + lemma or POS, optionally only of some word types. */
async function corpWordlist(body) {
  const c = S.corp, w = c.wl;
  const out = h("div", {}, loading("Counting…"));
  let latest = 0;                       // only the newest request may fill the page (see corpKwic)
  const run = async () => {
    const mine = ++latest;
    out.replaceChildren(loading("Counting…"));
    const r = await api("/api/corpus/wordlist", withBooks({ unit: w.unit, scope: c.scope, settings: c.settings, min_freq: w.min_freq, min_range: w.min_range, filter: w.flt }));
    if (mine !== latest) return;
    const f = w.filter.toLowerCase();
    const rows = f ? r.rows.filter(x => x.item.toLowerCase().includes(f)) : r.rows;
    const flt = filterLabel(w.flt);
    const first = w.unit === "word_pos_lemma" ? [{ k: "word", label: "Word" }, { k: "pos", label: "POS" }, { k: "lemma", label: "Lemma" }]
      : [{ k: "item", label: { word: "Word", lemma: "Lemma", word_pos: "Word_POS", pos: "POS" }[w.unit] }];
    out.className = "";
    out.replaceChildren(
      h("p", { class: "small muted" }, `${fmt(r.tokens)} tokens, ${fmt(r.types)} types (type/token ratio ${fmt(r.types / Math.max(1, r.kept), 3)}), ${scopeLabel(c.scope)}. ` +
        (flt ? `Only ${flt}: ${fmt(r.kept)} of the tokens (${fmt(100 * r.kept / Math.max(1, r.tokens), 1)}%); rates are still per 1,000 words of the whole text. ` : "") +
        (r.listed > r.rows.length ? `Showing the ${fmt(r.rows.length)} most frequent of ${fmt(r.listed)}. ` : "") + "Click a row for its concordance."),
      table([{ k: "rank", label: "Rank", num: true }, ...first,
        { k: "n", label: "Frequency", num: true, fmt: v => fmt(v) }, { k: "per1k", label: "Per 1,000", num: true, fmt: v => fmt(v, 2) },
        { k: "range", label: "Range", num: true, title: "Number of books it occurs in" }, { k: "d", label: "Dispersion (D)", num: true, fmt: v => v == null ? "—" : fmt(v, 2) }],
        rows, { limit: 100, csvName: `word list ${w.unit}`, onRow: x => goKwic(...itemQuery(x.item, w.unit, x)) }),
      note("How this is counted", "Tokens are words in scope, leaving out punctuation and quotation marks. Word forms are lowercased unless Case sensitive is on. Range is the number of selected books an item occurs in.",
        "Dispersion is Juilland's D over ten equal parts of the selected text, taken in book order.",
        "Word + POS + lemma lists each combination of a word form, its word class and its lemma, so the same word used as a noun and as a verb, or with two lemmas, is counted separately.",
        "The word-type filter counts only tokens of the chosen word classes, fine tags and entity types (a token is in an entity type when a mention of that kind covers it). The type/token ratio then compares the types of those tokens with their number; per-1,000 rates and dispersion still refer to all words of the text, so “nouns per 1,000 words” is what you read."));
  };
  body.append(h("section", { class: "panel" },
    h("div", { class: "controls" },
      h("div", { class: "fld" }, "List", seg([["word", "Words"], ["lemma", "Lemmas"], ["word_pos", "Word + POS"], ["word_pos_lemma", "Word + POS + lemma"], ["pos", "POS"]], w.unit, v => { w.unit = v; saveCorp(); renderCorpus($("#main"), "wordlist"); })),
      h("label", {}, "Minimum frequency", h("input", { type: "number", min: 1, value: w.min_freq, onchange: e => { w.min_freq = Math.max(1, +e.target.value || 1); saveCorp(); run(); } })),
      h("label", {}, "Minimum range", h("input", { type: "number", min: 1, value: w.min_range, onchange: e => { w.min_range = Math.max(1, +e.target.value || 1); saveCorp(); run(); } })),
      h("label", {}, "Filter", h("input", { type: "search", value: w.filter, placeholder: "Show items containing…", oninput: e => { w.filter = e.target.value; clearTimeout(corpWordlist.tm); corpWordlist.tm = setTimeout(run, 300); } }))),
    typeFilter(w.flt, run),
    out));
  run();
}

/** N-grams, optionally containing a word first, last or anywhere. */
async function corpNgrams(body) {
  const c = S.corp, g = c.ng;
  const out = h("div", {}, loading("Counting…"));
  const run = async () => {
    out.replaceChildren(loading("Counting…"));
    const r = await api("/api/corpus/ngrams", withBooks({ ...g, scope: c.scope, settings: c.settings }));
    out.className = "";
    out.replaceChildren(
      h("p", { class: "small muted" }, `${fmt(r.types)} different n-grams, ${fmt(r.listed)} at these minimums, ${scopeLabel(c.scope)}. Click a row for its concordance.`),
      table([{ k: "rank", label: "Rank", num: true }, { k: "item", label: "N-gram" }, { k: "size", label: "Size", num: true },
        { k: "n", label: "Frequency", num: true, fmt: v => fmt(v) }, { k: "per1k", label: "Per 1,000", num: true, fmt: v => fmt(v, 3) },
        { k: "range", label: "Range", num: true }], r.rows,
        { limit: 100, csvName: `ngrams ${g.n_min}-${g.n_max}`, onRow: x => g.unit === "lemma" ? goKwic(x.item.split(" ").map(t => `[lemma="${t}"]`).join(" "), "pattern") : goKwic(x.item, "simple") }),
      note("How n-grams are counted", "An n-gram is a run of n consecutive words in scope. Punctuation is skipped when Ignore punctuation is on. Runs stop at the edge of the scope (a quote, say), and at the end of a sentence if chosen.",
        "Containing keeps only n-grams with a word matching the term (wildcards allowed): anywhere, as the first word (on the left) or as the last word (on the right), like AntConc's clusters."));
  };
  const num = (k, label, min, max) => h("label", {}, label, h("input", { type: "number", min, max, value: g[k], onchange: e => { g[k] = Math.min(max, Math.max(min, +e.target.value || min)); if (g.n_max < g.n_min) g.n_max = g.n_min; saveCorp(); run(); } }));
  body.append(h("section", { class: "panel" },
    h("div", { class: "controls" }, num("n_min", "Shortest", 2, 8), num("n_max", "Longest", 2, 8),
      h("div", { class: "fld" }, "Count", seg([["word", "Words"], ["lemma", "Lemmas"]], g.unit, v => { g.unit = v; saveCorp(); renderCorpus($("#main"), "ngrams"); })),
      num("min_freq", "Minimum frequency", 1, 100000), num("min_range", "Minimum range", 1, 1000),
      h("label", {}, "Containing", h("input", { type: "search", value: g.contains, placeholder: "any word", onchange: e => { g.contains = e.target.value.trim(); saveCorp(); run(); } })),
      h("label", {}, "Where", h("select", { onchange: e => { g.position = e.target.value; saveCorp(); run(); } },
        [["any", "Anywhere"], ["left", "First word"], ["right", "Last word"]].map(([v, l]) => h("option", { value: v, selected: g.position === v }, l)))),
      h("label", { class: "inline" }, h("input", { type: "checkbox", checked: g.within_sentence, onchange: e => { g.within_sentence = e.target.checked; saveCorp(); run(); } }), "Within sentences")),
    out));
  run();
}

/** Collocates of the search term, ranked by a chosen association measure. */
async function corpCollocates(body) {
  const c = S.corp, o = c.col;
  const out = h("div");
  let latest = 0;                       // only the newest request may fill the page (see corpKwic)
  const run = async () => {
    const mine = ++latest;
    if (!c.query) { out.replaceChildren(h("div", { class: "empty" }, "Search for a word or pattern to find its collocates.")); return; }
    out.replaceChildren(loading("Counting…"));
    const r = await api("/api/corpus/collocates", withBooks({ query: c.query, mode: c.mode, settings: c.settings, scope: c.scope, ...o, filter: o.flt }));
    if (mine !== latest) return;
    const m = S.lib.coll_measures, flt = filterLabel(o.flt);
    out.replaceChildren(
      h("p", { class: "small muted" }, `${plural(r.hits, "hit")} for the search term; ${fmt(r.window_tokens)} words in their windows; ${fmt(r.listed)} collocates${flt ? ` (only ${flt})` : ""} at these minimums, ${scopeLabel(c.scope)}. Click a row for the concordance lines with both.`),
      table([{ k: "rank", label: "Rank", num: true }, { k: "item", label: "Collocate" },
        { k: "n", label: "Freq (O)", num: true, fmt: v => fmt(v) }, { k: "left", label: "L", num: true }, { k: "right", label: "R", num: true },
        { k: "freq", label: "Corpus freq", num: true, fmt: v => fmt(v) }, { k: "range", label: "Range", num: true },
        ...["mi", "t", "logdice", "mi3", "ll"].map(k => ({ k, label: m[k], num: true, fmt: v => v == null ? "—" : fmt(v, 2) })),
        { k: "p", label: "p (LL)", num: true, fmt: fmtP }],
        r.rows, { sort: o.sort, limit: 100, csvName: `collocates ${c.query}`,
          onRow: x => goKwic(c.query, c.mode, { item: x.item, unit: o.unit, left: o.left, right: o.right, within_sentence: o.within_sentence }) }),
      note("How collocates are measured", S.lib.coll_note,
        "The word-type filter only decides which collocates are listed: the windows and the hit count don't change. A collocate's corpus frequency then counts only its tokens of the chosen types, so a word is compared with its own uses as that word class."));
  };
  const num = (k, label, min, max) => h("label", {}, label, h("input", { type: "number", min, max, value: o[k], onchange: e => { o[k] = Math.min(max, Math.max(min, +e.target.value || min)); saveCorp(); run(); } }));
  body.append(h("section", { class: "panel" }, queryBar(run),
    h("div", { class: "controls", style: { marginTop: "10px" } }, num("left", "Words to the left", 0, 20), num("right", "Words to the right", 0, 20),
      h("div", { class: "fld" }, "Count", seg([["word", "Words"], ["lemma", "Lemmas"]], o.unit, v => { o.unit = v; saveCorp(); renderCorpus($("#main"), "collocates"); })),
      h("label", {}, "Rank by", h("select", { onchange: e => { o.sort = e.target.value; saveCorp(); run(); } }, Object.entries(S.lib.coll_measures).map(([k, l]) => h("option", { value: k, selected: o.sort === k }, l)))),
      num("min_freq", "Minimum frequency", 1, 100000), num("min_range", "Minimum range", 1, 1000),
      h("label", { class: "inline" }, h("input", { type: "checkbox", checked: o.within_sentence, onchange: e => { o.within_sentence = e.target.checked; saveCorp(); run(); } }), "Keep windows within a sentence")),
    typeFilter(o.flt, run),
    out));
  run();
}

/** Keywords of the selected books against other books or your own reference files. */
async function corpKeywords(body) {
  const c = S.corp, k = c.kw;
  const refs = (await api("/api/refs")).rows;
  const out = h("div");
  const target = selected();
  if (!k.refBooks) k.refBooks = S.lib.books.map(b => b.id).filter(id => !target.includes(id));
  const refChooser = () => {
    const cur = new Set(k.refBooks);
    return h("div", { class: "books-menu", style: { position: "static", boxShadow: "none", minWidth: 0 } },
      S.lib.books.map(b => h("label", { class: "book" }, h("input", { type: "checkbox", checked: cur.has(b.id), onchange: e => { e.target.checked ? cur.add(b.id) : cur.delete(b.id); k.refBooks = S.lib.books.map(x => x.id).filter(id => cur.has(id)); saveCorp(); run(); } }),
        b.title, target.includes(b.id) ? h("span", { class: "muted small" }, " (also in the target)") : null)));
  };
  const upload = h("input", { type: "file", multiple: true, accept: ".txt,.tsv,.csv,text/plain", hidden: true, onchange: async e => {
    const files = await Promise.all([...e.target.files].map(async f => ({ name: f.name, text: await f.text() })));
    if (!files.length) return;
    const name = files.length === 1 ? files[0].name.replace(/\.[^.]+$/, "") : `${files[0].name.replace(/\.[^.]+$/, "")} and ${files.length - 1} more`;
    const r = await api("/api/refs", { name, files });
    k.refFile = r.id; k.refKind = "file"; saveCorp();
    toast(`Loaded ${r.name}: ${fmt(r.tokens)} tokens (${Object.entries(r.kinds).map(([a, b]) => `${b} ${a}${b > 1 ? "s" : ""}`).join(", ")}).`);
    renderCorpus($("#main"), "keywords");
  } });
  const run = async () => {
    out.replaceChildren(loading("Comparing…"));
    const reference = k.refKind === "file" ? { kind: "file", id: k.refFile } : { kind: "books", books: k.refBooks, scope: k.refScope === "same" ? null : k.refScopeValue || { kind: k.refScope } };
    if (k.refKind === "file" && !k.refFile) { out.replaceChildren(h("div", { class: "empty" }, "Load a reference file, or use books as the reference.")); return; }
    if (k.refKind === "books" && !k.refBooks.length) { out.replaceChildren(h("div", { class: "empty" }, "Tick one or more reference books. They can be the same books as the target if you compare different parts, such as dialogue against narration.")); return; }
    let r;
    try { r = await api("/api/corpus/keywords", withBooks({ scope: c.scope, unit: k.unit, settings: c.settings, reference, negative: k.negative, min_range: k.min_range, ...S.stat })); }
    catch (e) { out.replaceChildren(h("div", { class: "empty" }, e.message)); return; }
    const s = r.summary;
    const refName = k.refKind === "file" ? (refs.find(x => x.id === k.refFile) || {}).name : booksLabel(k.refBooks);
    const cols = statCols(s, k.negative, ["Target", "Reference"]).map(col => col.k === "lr" && col.label === "More typical of" ? { ...col, label: "Keyness", fmt: v => v > 0 ? "positive" : "negative", csv: v => v > 0 ? "positive" : "negative" } : col);
    cols.splice(1, 0, { k: "range", label: "Range", num: true, title: "Target books it occurs in" });
    out.replaceChildren(
      h("p", { class: "small muted" }, `Target: ${booksLabel(target)}, ${scopeLabel(c.scope)}: ${fmt(s.target_tokens)} tokens. Reference: ${refName}: ${fmt(s.reference_tokens)} tokens. ` +
        `${plural(r.rows.length, "keyword")}${k.negative ? ", positive and negative" : ""}. Click a row for its concordance in the target.`),
      table(cols, r.rows, { limit: 100, csvName: `keywords ${k.unit}`, rowClass: row => (row.sig ? "" : "dim"), onRow: x => goKwic(...itemQuery(x.item, k.unit)) }),
      statNote(s),
      note("About the reference", "As in AntConc, the reference can be other books or your own files. Files can be word lists (AntConc's exported word lists, or any list of words with frequencies, tab- or comma-separated) or plain texts, which are split into words here: lowercased, with n't, 's, 'll and so on split off to match BookNLP's tokens. Reference files only have word forms, so they're always compared lowercased.",
        "Positive keywords are more frequent in the target than the reference; negative ones (if shown) are less frequent."));
  };
  body.append(h("section", { class: "panel" },
    h("div", { class: "cols2" },
      h("div", {}, h("h3", { class: "small muted" }, "Target"),
        h("p", { class: "small", style: { margin: "0 0 6px" } }, `The selected books (${booksLabel(target)}), ${scopeLabel(c.scope)}. Change the books at the top right.`),
        h("div", { class: "controls" }, scopeControl(c.scope, v => { c.scope = v; saveCorp(); run(); }, { label: "Target text" }))),
      h("div", {}, h("h3", { class: "small muted" }, "Reference"),
        seg([["books", "Books"], ["file", "Reference file"]], k.refKind, v => { k.refKind = v; saveCorp(); renderCorpus($("#main"), "keywords"); }),
        k.refKind === "books" ? h("div", { style: { marginTop: "8px" } }, refChooser(),
          h("div", { class: "controls", style: { marginTop: "8px" } }, scopeControl(k.refScope === "same" ? { kind: "same" } : (k.refScopeValue || { kind: k.refScope }), v => { k.refScope = v.kind; k.refScopeValue = v.kind === "speech" ? v : null; saveCorp(); run(); }, { same: true, label: "Reference text" })))
          : h("div", { style: { marginTop: "8px" } },
            refs.length ? h("div", {}, refs.map(x => h("label", { class: "book", style: { display: "flex", gap: "6px", alignItems: "center" } },
              h("input", { type: "radio", name: "reffile", checked: k.refFile === x.id, onchange: () => { k.refFile = x.id; saveCorp(); run(); } }),
              x.name, h("span", { class: "muted small" }, ` ${fmt(x.tokens)} tokens, ${fmt(x.types)} types`),
              h("button", { class: "btn small", onclick: async ev => { ev.preventDefault(); await api("/api/refs/delete", { id: x.id }); if (k.refFile === x.id) k.refFile = ""; saveCorp(); renderCorpus($("#main"), "keywords"); } }, "Remove")))) : h("p", { class: "small muted" }, "No reference files yet."),
            h("button", { class: "btn small", style: { marginTop: "6px" }, onclick: () => upload.click() }, "Load reference files…"), upload))),
    h("div", { class: "controls", style: { marginTop: "12px" } },
      h("div", { class: "fld" }, "Count", seg([["word", "Word forms"], ["lemma", "Lemmas"]], k.unit, v => { k.unit = v; saveCorp(); renderCorpus($("#main"), "keywords"); })),
      h("label", {}, "Minimum range", h("input", { type: "number", min: 1, value: k.min_range, onchange: e => { k.min_range = Math.max(1, +e.target.value || 1); saveCorp(); run(); } })),
      h("label", { class: "inline" }, h("input", { type: "checkbox", checked: k.negative, onchange: e => { k.negative = e.target.checked; saveCorp(); run(); } }), "Show negative keywords")),
    statControls(run), out));
  run();
}
