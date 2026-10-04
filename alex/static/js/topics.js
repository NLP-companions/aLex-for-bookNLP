"use strict";
/* ---------- Topics ---------- */
S.top = loadState("analyser.top", { name: "", cfg: null, scanFrom: 4, scanTo: 14 });
/** Save the topic-form settings. */
const saveTop = () => saveState("analyser.top", { name: S.top.name, cfg: S.top.cfg, scanFrom: S.top.scanFrom, scanTo: S.top.scanTo });
/** Display names of the parts of speech a topic model can keep. */
const POS_NAMES = { NOUN: "Nouns", VERB: "Verbs", ADJ: "Adjectives", ADV: "Adverbs", PROPN: "Proper nouns" };
/** A topic's name: your label, else its three most distinctive words. */
const topicName = t => t.label || t.distinctive.slice(0, 3).map(w => w.w).join(" · ");

/** The Topics pages: the models list and fit form, a model's overview, a topic's page, or comparisons (chosen by the address). */
async function renderTopics(main, mid, tid, ...more) {
  if (!S.lib.topics_ready) {
    main.replaceChildren(h("section", { class: "panel" }, h("h2", {}, "Topics"),
      h("p", { class: "warn" }, "Topic modelling needs scikit-learn. Install it in your environment, then restart the analyser:"),
      h("pre", {}, "pip install scikit-learn")));
    return;
  }
  const T = S.top;
  T.cfg = Object.assign({}, S.lib.topic_defaults, T.cfg || {});
  const body = h("div");
  if (mid && tid === "compare") { main.replaceChildren(body); await topicCompare(body, decodeURIComponent(mid), more); return; }
  if (mid && tid != null && tid !== "") { main.replaceChildren(body); await topicPage(body, decodeURIComponent(mid), +tid); return; }
  main.replaceChildren(h("section", { class: "panel", "data-toc": "About topics" }, h("h2", { style: { marginTop: 0 } }, "Topics"),
    h("p", { class: "small muted", style: { margin: 0 } }, "Groups of words that occur together, found by a topic model over the books you've selected. ",
      "Fit a model, then explore its topics.")), body);
  if (mid) await topicOverview(body, decodeURIComponent(mid));
  else await topicHome(body);
}

/** The form for fitting a model (documents, words, method) with buttons to fit or to compare numbers of topics. */
function topicForm(onFit, onScan) {
  const T = S.top, c = T.cfg, N = S.lib.topic_notes;
  const ch = (fn) => e => { fn(e); saveTop(); };
  const num = (k, label, min, max, step, title, wide) => h("label", { title }, label,
    h("input", { type: "number", min, max, step: step || 1, value: c[k] ?? "", style: wide ? { width: "90px" } : { width: "70px" },
      onchange: ch(e => { c[k] = e.target.value === "" ? null : +e.target.value; }) }));
  const sel = (k, label, opts, title) => h("label", { title }, label,
    h("select", { onchange: ch(e => { c[k] = e.target.value; redraw(); }) }, opts.map(([v, l]) => h("option", { value: v, selected: c[k] === v }, l))));
  const box = h("div");
  function redraw() {
    box.replaceChildren(
      h("div", { class: "controls" },
        h("label", {}, "Name (optional)", h("input", { type: "text", value: T.name, placeholder: "e.g. Nouns, 300 words", style: { width: "200px" }, oninput: ch(e => { T.name = e.target.value; }) }))),
      h("h3", { style: { margin: "6px 0 4px" } }, "Documents"),
      h("div", { class: "controls" },
        sel("unit", "Cut the books into", [["chunk", "Chunks of about N words"], ["paras", "Groups of paragraphs"], ["segments", "Chapters or slices"], ["book", "Whole books"]]),
        c.unit === "chunk" ? num("chunk_words", "Words per chunk", 50, 5000, 50) : null,
        c.unit === "paras" ? num("paras", "Paragraphs per document", 1, 200) : null,
        c.unit === "segments" ? h("span", { class: "small muted", style: { alignSelf: "center" } }, "Uses the chapter or slice setting under Arcs and style.") : null,
        sel("text", "Text", [["all", "Narration and dialogue"], ["narration", "Narration only"], ["dialogue", "Dialogue only"]])),
      h("h3", { style: { margin: "6px 0 4px" } }, "Words"),
      h("div", { class: "controls" },
        h("div", { class: "fld" }, "Keep", h("div", { class: "row", style: { gap: "10px" } }, Object.entries(POS_NAMES).map(([p, l]) =>
          h("label", { class: "inline" }, h("input", { type: "checkbox", checked: c.pos.includes(p),
            onchange: ch(e => { c.pos = e.target.checked ? [...c.pos, p] : c.pos.filter(x => x !== p); }) }), l)))),
        sel("form", "Words as", [["lemma", "Lemmas"], ["word", "Word forms"]]),
        sel("drop", "Remove", [["names", "Names (proper-name mentions)"], ["people", "All mentions of people"], ["entities", "All entity mentions"], ["none", "Nothing"]],
          "Every token inside these BookNLP mentions is dropped")),
      h("div", { class: "controls" },
        num("min_df", "Minimum documents", 1, 1000, 1, "Words in fewer documents are removed"),
        h("label", { title: "Words in more than this share of documents are removed" }, "Maximum share of documents (%)",
          h("input", { type: "number", min: 5, max: 100, value: Math.round(100 * c.max_df), style: { width: "70px" }, onchange: ch(e => { c.max_df = Math.min(1, Math.max(0.05, (+e.target.value || 50) / 100)); }) })),
        num("min_len", "Minimum letters", 1, 10),
        h("label", { class: "inline", title: "Removes very general words such as thing, way, say, go" },
          h("input", { type: "checkbox", checked: c.generic, onchange: ch(e => { c.generic = e.target.checked; }) }), "Remove general words"),
        h("label", { title: "Separated by spaces or commas" }, "Also remove", h("input", { type: "text", value: c.extra_stop, style: { width: "220px" }, onchange: ch(e => { c.extra_stop = e.target.value; }) }))),
      h("h3", { style: { margin: "6px 0 4px" } }, "Model"),
      h("div", { class: "controls" },
        sel("method", "Method", [["nmf", "NMF (tf–idf)"], ["lda", "LDA"]], N.methods),
        num("k", "Number of topics", 2, 60),
        num("seed", "Seed", 0, 999999),
        num("runs", "Runs for stability", 1, 20, 1, "The model is re-fitted with other seeds; 1 skips the check"),
        c.method === "lda" ? num("alpha", "Alpha (blank = 1 ÷ topics)", 0.001, 10, 0.01, "Lower gives documents fewer topics", true) : null,
        c.method === "lda" ? num("beta", "Beta", 0.001, 1, 0.01, "Lower gives topics fewer words", true) : null),
      h("div", { class: "row", style: { marginTop: "6px" } },
        h("button", { class: "btn primary", onclick: () => onFit(c) }, "Fit model"),
        h("span", { class: "muted small" }, "or compare numbers of topics from"),
        h("input", { type: "number", min: 2, max: 60, value: T.scanFrom, style: { width: "60px" }, onchange: ch(e => { T.scanFrom = Math.max(2, +e.target.value || 2); }) }),
        h("span", { class: "muted small" }, "to"),
        h("input", { type: "number", min: 2, max: 60, value: T.scanTo, style: { width: "60px" }, onchange: ch(e => { T.scanTo = Math.min(60, Math.max(T.scanFrom, +e.target.value || T.scanFrom)); }) }),
        h("button", { class: "btn", onclick: () => onScan(c) }, "Compare")),
      note("What the settings do", N.model, N.documents, N.words, N.methods, N.metrics));
  }
  redraw();
  return box;
}

/** The models table, the fit form and the results of comparing numbers of topics. */
async function topicHome(body) {
  const T = S.top;
  const list = h("div"), scanOut = h("div");
  const withSeg = cfg => cfg.unit === "segments" && S.nar ? { ...cfg, seg: S.nar.seg } : cfg;
  const fitBtn = async cfg => {
    body.append(h("div", { class: "loading", id: "fitting" }, "Fitting the model and re-running it for stability. This can take a minute…"));
    try {
      const r = await api("/api/topics/fit", withBooks({ cfg: withSeg(cfg), name: T.name }));
      location.hash = "#/topics/" + encodeURIComponent(r.id);
    } catch (e) { const f = $("#fitting"); if (f) f.remove(); }
  };
  const scanBtn = async cfg => {
    scanOut.replaceChildren(loading("Fitting one model for each number of topics…"));
    const ks = []; for (let k = T.scanFrom; k <= T.scanTo && ks.length < 20; k++) ks.push(k);
    try {
      const r = await api("/api/topics/scan", withBooks({ cfg: withSeg(cfg), ks }));
      const best = Math.max(...r.rows.map(x => x.coherence));
      scanOut.replaceChildren(h("h3", { style: { marginBottom: "4px" } }, "Number of topics"),
        h("p", { class: "small muted", style: { marginTop: 0 } }, `${fmt(r.docs)} documents, ${fmt(r.vocab)} words, ${fmt(r.words)} word tokens. Higher coherence, diversity and stability are better; the highest coherence is marked. Click a row to use that number.`),
        table([{ k: "k", label: "Topics", num: true }, { k: "coherence", label: "Coherence (NPMI)", num: true, fmt: (v, r2) => fmt(v, 3) + (v === best ? " ★" : "") },
          { k: "diversity", label: "Diversity", num: true, fmt: v => fmt(v, 2) }, { k: "stability", label: "Stability", num: true, fmt: v => v == null ? "—" : fmt(100 * v, 0) + "%" }],
          r.rows, { limit: 40, csvName: "topic-scan", onRow: row => { T.cfg.k = row.k; saveTop(); renderTopics($("#main")); } }));
    } catch (e) { scanOut.replaceChildren(); }
  };
  const models = (await api("/api/topics/models")).models;
  const del = async m => { if (!confirm(`Delete the model “${m.name}”?`)) return; await api("/api/topics/delete", { id: m.id }); renderTopics($("#main")); };
  list.append(models.length ? table([
    { k: "name", label: "Model", fmt: (v, r) => h("a", { href: "#/topics/" + encodeURIComponent(r.id) }, v) },
    { k: "titles", label: "Books", fmt: v => v.length > 3 ? `${v.length} books` : v.join(" + "), csv: v => v.join(" + ") },
    { k: "method", label: "Method", fmt: v => v.toUpperCase() }, { k: "k", label: "Topics", num: true }, { k: "docs", label: "Documents", num: true, fmt: v => fmt(v) },
    { k: "coherence", label: "Coherence", num: true, fmt: v => fmt(v, 3) }, { k: "diversity", label: "Diversity", num: true, fmt: v => fmt(v, 2) },
    { k: "stable", label: "Stable topics", num: true, title: "Topics that came back in at least 60% of the runs", fmt: (v, r) => v == null ? "—" : `${v} of ${r.k}` },
    { k: "created", label: "Created" }, { k: "id", label: "", fmt: (v, r) => h("button", { class: "btn small", onclick: () => del(r) }, "Delete"), csv: () => "" }],
    models, { sort: "created", csvName: "topic-models", limit: 50 }) : h("p", { class: "muted small" }, "No models yet. Fit one below."));
  const book = selected();
  body.append(h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Models"), list),
    h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Fit a new model"),
      h("p", { class: "small muted", style: { marginTop: 0 } }, `Uses the ${plural(book.length, "selected book")}: ${book.map(bookTitle).slice(0, 4).join(", ")}${book.length > 4 ? "…" : ""}. Change the selection at the top right.`),
      book.length < 3 ? h("p", { class: "small warn" }, "With so little text the topics will be exploratory. Small documents, few topics and NMF work best.") : null,
      topicForm(fitBtn, scanBtn), scanOut));
}

/** A model's overview: its settings and quality, a table of topics, and a card per topic. */
async function topicOverview(body, mid) {
  body.replaceChildren(loading("Loading…"));
  let M;
  try { M = await api("/api/topics/model", { id: mid }); } catch (e) { location.hash = "#/topics"; return; }
  const c = M.cfg, me = M.metrics;
  const unitText = { chunk: `chunks of about ${c.chunk_words} words`, paras: `groups of ${c.paras} paragraphs`, segments: "chapters or slices", book: "whole books" }[c.unit];
  const dropText = { none: "no names removed", names: "names removed", people: "people removed", entities: "entities removed" }[c.drop];
  const nameIn = h("input", { type: "text", value: M.name, style: { font: "600 18px var(--serif)", width: "min(520px, 100%)" },
    onchange: async e => { await api("/api/topics/rename", { id: M.id, name: e.target.value }); toast("Saved."); } });
  const maxShare = Math.max(...M.topics.map(t => t.share));
  const bookShare = Math.max(1e-9, ...M.topics.flatMap(t => Object.values(t.by_book)));
  const cols = [
    { k: "label", label: "Topic", sortVal: r => topicName(r), fmt: (v, r) => h("a", { href: `#/topics/${encodeURIComponent(M.id)}/${r.id}` }, topicName(r)), csv: (v, r) => topicName(r) },
    { k: "words", label: "Top words", sortVal: () => 0, fmt: v => v.slice(0, 8).map(w => w.w).join(", "), csv: v => v.slice(0, 8).map(w => w.w).join(" ") },
    { k: "share", label: "Share %", num: true, fmt: v => barFmt(100 * maxShare, 1)(100 * v), csv: v => fmt(100 * v, 2), sortVal: r => r.share },
    { k: "coherence", label: "Coherence", num: true, fmt: v => fmt(v, 3) },
    { k: "stability", label: "Recurs", num: true, sortVal: r => r.stability.recurs / r.stability.of, title: "In how many of the runs a similar topic came back",
      fmt: v => v.of > 1 ? `${v.recurs} of ${v.of}` : "—", csv: v => v.of > 1 ? `${v.recurs}/${v.of}` : "" },
    ...M.books.map(b => ({ k: "b:" + b, label: M.titles[b], num: true, fmt: v => fmt(100 * v, 1) + "%", csv: v => fmt(100 * v, 2) }))];
  const rows = M.topics.map(t => ({ ...t, ...Object.fromEntries(M.books.map(b => ["b:" + b, t.by_book[b]])) }));
  const cards = M.topics.map(t => {
    const lab = h("input", { type: "text", value: t.label, placeholder: t.distinctive.slice(0, 3).map(w => w.w).join(" · "), style: { font: "600 16px var(--serif)", width: "min(420px, 100%)" },
      onchange: async e => { t.label = e.target.value.trim(); await api("/api/topics/rename", { id: M.id, topic: t.id, label: t.label }); toast("Saved."); } });
    const unstable = t.stability.of > 1 && t.stability.recurs / t.stability.of < 0.6;
    const maxP = Math.max(...t.words.map(w => w.p));
    return h("section", { class: "panel", id: "topic-" + t.id, "data-toc": `${t.id + 1}. ${topicName(t)}` },
      h("div", { class: "row", "data-cx-head": "" }, lab, h("a", { class: "small", href: `#/topics/${encodeURIComponent(M.id)}/${t.id}` }, "Open topic page →"), h("span", { class: "muted small" }, `Topic ${t.id + 1} · ${fmt(100 * t.share, 1)}% of the words · strongest in ${plural(t.top_docs, "document")}`),
        t.stability.of > 1 ? h("span", { class: unstable ? "warn small" : "muted small", title: "In how many of the runs a similar topic came back" }, `recurs in ${t.stability.recurs} of ${t.stability.of} runs`) : null),
      h("div", { class: "cols2", style: { marginTop: "8px" } },
        h("div", {}, h("div", { class: "small muted" }, "Most probable words"),
          h("div", { class: "chips", style: { margin: "4px 0 10px" } }, t.words.slice(0, 20).map(w => h("span", { class: "chip", style: { cursor: "default", opacity: 0.45 + 0.55 * w.p / maxP } }, w.w))),
          h("div", { class: "small muted" }, "Most distinctive words"),
          h("div", { class: "chips", style: { margin: "4px 0" } }, t.distinctive.slice(0, 20).map(w => h("span", { class: "chip", style: { cursor: "default" }, title: `${fmt(w.n)} uses in the model` }, w.w)))),
        h("div", {}, h("div", { class: "small muted" }, "Share in each book"),
          M.books.map(b => h("div", { class: "row", style: { gap: "8px", margin: "3px 0" } },
            h("span", { class: "small", style: { width: "180px", flex: "none", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }, title: M.titles[b] }, M.titles[b]),
            h("div", { class: "bar-cell" }, h("i", { style: { width: Math.max(1, 120 * t.by_book[b] / bookShare) + "px" } }), fmt(100 * t.by_book[b], 1) + "%"))))),
      h("div", { class: "small muted", style: { margin: "10px 0 4px" } }, "Strongest passages"),
      t.passages.map(p => h("div", { class: "ev", style: { padding: "5px 0" } },
        h("div", { class: "small muted" }, `${p.title} · ${fmt(p.pos, 1)}% through · topic weight ${fmt(100 * p.weight, 0)}% · `,
          h("a", { href: `#/read/${encodeURIComponent(p.book)}/${p.start}` }, "Open in the text")),
        p.text ? h("div", {}, p.text) : null)));
  });
  body.replaceChildren(
    h("section", { class: "panel" },
      h("div", { class: "row" }, nameIn, h("a", { href: `#/topics/${encodeURIComponent(M.id)}/compare/map`, class: "small" }, "Compare topics →"), h("a", { href: "#/topics", class: "small" }, "← All models")),
      h("p", { class: "small muted", style: { margin: "6px 0 0" } },
        `${c.method.toUpperCase()}, ${plural(M.topics.length, "topic")}, seed ${c.seed} · ${plural(M.docs, "document")} (${unitText}) · ${fmt(M.words)} word tokens, ${fmt(M.vocab)} distinct words · ${dropText} · ${c.pos.map(p => POS_NAMES[p].toLowerCase()).join(", ")} as ${c.form === "lemma" ? "lemmas" : "word forms"} · `,
        `mean coherence ${fmt(me.mean_coherence, 3)}, diversity ${fmt(me.diversity, 2)} · fitted ${M.created}`),
      M.stale.length ? h("p", { class: "warn small" }, `${M.stale.join(", ")} changed since this model was fitted, so passages may not match. Fit it again.`) : null,
      M.docs < 150 ? h("p", { class: "warn small" }, `Only ${M.docs} documents: treat these topics as exploratory and check how often they recur.`) : null),
    h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Topics"), table(cols, rows, { sort: "share", limit: 80, csvName: slug(M.name) + "-topics" }),
      note("How this is calculated", S.lib.topic_notes.model, S.lib.topic_notes.metrics, S.lib.topic_notes.prevalence,
        "Distinctive words are ranked by relevance (Sievert & Shirley 2014, with λ = 0.6): a word scores higher when it is probable in the topic and much more probable there than in the model overall.")),
    cards);
}

/* ---------- Topics section on an entity's page ---------- */
S.top.entKind = "mentions";
/** The Topics section of an entity's page: which topics its mentions or speech fall in. */
function entityTopicsPanel(u) {
  const box = h("section", { class: "panel" }, h("h2", {}, "Topics"), loading("Loading…"));
  const st = S.top;
  const load = async () => {
    let models;
    try { models = (await api("/api/topics/models")).models; } catch (e) { box.replaceChildren(h("h2", {}, "Topics"), h("p", { class: "warn small" }, e.message)); return; }
    if (!models.length) { box.replaceChildren(h("h2", {}, "Topics"), h("p", { class: "muted small", style: { margin: 0 } }, "Fit a topic model under ", h("a", { href: "#/topics" }, "Topics"), " to see which topics this one belongs to.")); return; }
    const sel = models.filter(m => m.books.some(b => u.books.includes(b)));
    if (!sel.length) { box.replaceChildren(h("h2", {}, "Topics"), h("p", { class: "muted small", style: { margin: 0 } }, "None of the saved topic models covers the books this appears in.")); return; }
    if (!sel.some(m => m.id === st.entModel)) st.entModel = sel[0].id;
    const body = h("div");
    const draw = async () => {
      body.replaceChildren(loading("Loading…"));
      let R;
      try { R = await api("/api/topics/entity", withBooks({ id: st.entModel, unit: u.ref.id, ids: u.ref.ids, group: u.ref.group, name: u.ref.name, kind: st.entKind })); } catch (e) { body.replaceChildren(h("p", { class: "warn small" }, e.message)); return; }
      if (!R.count) { body.replaceChildren(h("p", { class: "muted small" }, st.entKind === "speech" ? "No quotes are attributed to them in the model's books." : "Not mentioned in the model's documents.")); return; }
      const base = "#/topics/" + encodeURIComponent(st.entModel), maxShare = Math.max(...R.rows.map(r => r.share));
      body.replaceChildren(
        h("p", { class: "small muted", style: { marginTop: 0 } }, st.entKind === "speech"
          ? `${fmt(R.count)} words spoken in the model's books, divided among the topics of the passages they fall in.`
          : `${plural(R.count, "mention")} in the model's books, divided among the topics of the passages they fall in.`),
        table([{ k: "id", label: "Topic", fmt: (v, r) => h("a", { href: `${base}/${v}` }, `${v + 1}. ${topicName(r)}`), sortVal: r => r.share, csv: (v, r) => topicName(r) },
          { k: "words", label: "Top words", fmt: v => v.slice(0, 6).join(", "), sortVal: () => 0, csv: v => v.join(" ") },
          { k: "share", label: "Share of theirs", num: true, fmt: v => barFmt(100 * maxShare, 0)(100 * v), csv: v => fmt(100 * v, 2) },
          { k: "lift", label: "Against topic average", num: true, fmt: v => v == null ? "—" : "× " + fmt(v, 1), csv: v => v == null ? "" : fmt(v, 2), title: "Their share in the topic's text divided by the topic's share of the whole model" },
          { k: "ll", label: "Score", num: true, fmt: v => fmt(v, 1), title: "Log-likelihood; a ranking, not a significance test" }],
          R.rows, { sort: "ll", limit: 8, csvName: `${u.name} topics`, onRow: r => (location.hash = `${base}/${r.id}`) }),
        note("How this is calculated", S.lib.topic_notes.cmp_grid_items, "The score compares the rate per 1,000 words (or 1,000 dialogue words, for speech) in text weighted by the topic with the rate elsewhere, and ranks topics; it is not a significance test."));
    };
    box.replaceChildren(h("h2", {}, "Topics"),
      h("div", { class: "controls" },
        h("label", {}, "Topic model", h("select", { onchange: e => { st.entModel = e.target.value; draw(); } }, sel.map(m => h("option", { value: m.id, selected: m.id === st.entModel }, `${m.name} (${m.k} topics)`)))),
        h("div", { class: "fld" }, "Topics of their", seg([["mentions", "Mentions"], ["speech", "Speech"]], st.entKind, v => { st.entKind = v; load(); }))),
      body);
    draw();
  };
  load();
  return box;
}
