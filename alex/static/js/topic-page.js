"use strict";
/* ---------- One topic's page ---------- */
S.top.lam = 0.6; S.top.entDir = "over"; S.top.entType = "ALL"; S.top.groupBy = "series";
/** A share (0…1) as a percentage. */
const pctFmt = (v, d = 1) => v == null ? "—" : fmt(100 * v, d) + "%";
/** A ratio as "× 2.5". */
const ratioFmt = v => v == null ? "—" : "× " + fmt(v, v >= 10 ? 0 : 1);
/** The p-value column of a group table. */
const pCol = { k: "p", label: "p", num: true, fmt: fmtP, title: "Mann–Whitney U, documents in the group against the rest" };
/** "more …" / "less …" when a group differs significantly (p < 0.05), else nothing. */
const versus = (r, what) => r.p == null || r.p >= 0.05 || r.ratio == null ? "" : r.ratio > 1 ? `more ${what}` : "less " + what;

/** A strip per book shaded by the topic's weight in each document; clicking a cell opens the text there. */
function topicStrip(strips, max, color, onOpen) {
  const W = 900, rowH = 26, top = 6, labW = 190, H = top + strips.length * rowH + 20;
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, "font-family": SVG_FONT, "font-size": 12, role: "img", "aria-label": "Share of the topic along each book" });
  strips.forEach((s, i) => {
    const y = top + i * rowH, pw = W - labW;
    g.append(svg("text", { x: labW - 10, y: y + 15, "text-anchor": "end", fill: cssVar("--muted") }, s.title.length > 28 ? s.title.slice(0, 27) + "…" : s.title));
    g.append(svg("rect", { x: labW, y: y + 3, width: pw, height: 18, fill: cssVar("--panel-2") }));
    s.docs.forEach(d => g.append(svg("rect", { x: labW + pw * d.a / 100, y: y + 3, width: Math.max(1.5, pw * (d.b - d.a) / 100 - 0.4), height: 18, fill: color, "fill-opacity": 0.06 + 0.94 * d.w / (max || 1),
      style: "cursor:pointer", onclick: () => onOpen(s.book, d.start) }, svg("title", {}, `${fmt(100 * d.w, 0)}% at ${fmt(d.a, 0)}–${fmt(d.b, 0)}% through. Click to open in the text.`))));
  });
  const y = top + strips.length * rowH + 12;
  g.append(svg("text", { x: labW, y, fill: cssVar("--faint"), "font-size": 10.5 }, "start of book"));
  g.append(svg("text", { x: W, y, fill: cssVar("--faint"), "font-size": 10.5, "text-anchor": "end" }, `end · darkest = ${fmt(100 * max, 0)}% of the document`));
  return g;
}

/** The columns of an entity or speaker table for a topic (count, share in topic text, rates, ratio, score). */
function assocCols(kind) {
  return [
    { k: "count", label: kind === "ent" ? "Mentions" : "Words", num: true, fmt: v => fmt(v) },
    { k: "share", label: "In topic text", num: true, title: "Share of the item that falls in text weighted by the topic", fmt: v => pctFmt(v, 0) },
    { k: "rate_in", label: "Per 1,000 in topic text", num: true, fmt: v => fmt(v, 1) },
    { k: "rate_out", label: "Per 1,000 elsewhere", num: true, fmt: v => fmt(v, 1) },
    { k: "ratio", label: "Ratio", num: true, fmt: ratioFmt, sortVal: r => r.ratio ?? 0, csv: v => v == null ? "" : fmt(v, 2) },
    { k: "ll", label: "Score", num: true, title: "Log-likelihood; a ranking, not a significance test", fmt: v => fmt(v, 1) }];
}

/** One topic's page: words (with the relevance slider), where it occurs, passages, entities, speech and book details, with a side menu. */
async function topicPage(body, mid, tid) {
  body.replaceChildren(loading("Loading…"));
  let M;
  try { M = await api("/api/topics/model", { id: mid }); } catch (e) { location.hash = "#/topics"; return; }
  const Tp = M.topics.find(x => x.id === tid);
  if (!Tp) { location.hash = "#/topics/" + encodeURIComponent(mid); return; }
  const order = M.topics.map(x => x.id), at = order.indexOf(tid);
  const link = i => i >= 0 && i < order.length ? "#/topics/" + encodeURIComponent(mid) + "/" + order[i] : null;
  const color = PALETTE[tid % PALETTE.length];
  const part = (name, extra) => api("/api/topics/page", { id: mid, topic: tid, part: name, ...extra });
  const N = S.lib.topic_notes;
  const lab = h("input", { type: "text", value: Tp.label, placeholder: topicName({ label: "", distinctive: Tp.distinctive }), style: { font: "600 20px var(--serif)", width: "min(460px, 100%)" },
    onchange: async e => { Tp.label = e.target.value.trim(); await api("/api/topics/rename", { id: mid, topic: tid, label: Tp.label }); toast("Saved."); } });
  const sections = {};
  const shell = (key, title, ...intro) => (sections[key] = h("section", { class: "panel", id: "sec-" + key }, h("h3", { style: { marginTop: 0 } }, title), ...intro, h("div", { class: "content" }, loading("Loading…"))));
  const fill = async (key, fn) => {
    const c = $(".content", sections[key]);
    try { c.replaceChildren(await fn()); } catch (e) { c.replaceChildren(h("p", { class: "warn small" }, e.message)); }
  };
  const nav = [["words", "Words"], ["where", "Where it occurs"], ["passages", "Passages"], ["entities", "Entities"], ["speech", "Speech"], ["groups", "Book details"]];

  const others = M.topics.filter(x => x.id !== tid);
  const toc = h("nav", { class: "tp-toc", "aria-label": "On this page" },
    nav.map(([k, l]) => h("a", { href: "#sec-" + k, "data-k": k, onclick: e => { e.preventDefault(); sections[k].scrollIntoView({ behavior: "smooth" }); } }, l)),
    h("div", { class: "tp-toc-sep" }, "Compare"),
    h("a", { href: `#/topics/${encodeURIComponent(mid)}/compare/map` }, "Map of all topics"),
    others.length ? h("label", { class: "tp-toc-pick" }, "With another topic",
      h("select", { onchange: e => { if (e.target.value !== "") location.hash = `#/topics/${encodeURIComponent(mid)}/compare/pair/${tid}/${e.target.value}`; } },
        h("option", { value: "" }, "Choose…"), others.map(x => h("option", { value: x.id }, topicName(x))))) : null,
    h("a", { href: `#/topics/${encodeURIComponent(mid)}/compare/grid` }, "Grids"));
  body.replaceChildren(
    h("section", { class: "panel" },
      h("div", { class: "row" }, lab, h("span", { class: "grow" }),
        h("a", { href: link(at - 1), class: "small", style: link(at - 1) ? null : { visibility: "hidden" } }, "← Larger topic"),
        h("a", { href: link(at + 1), class: "small", style: link(at + 1) ? null : { visibility: "hidden" } }, "Smaller topic →"),
        h("a", { href: "#/topics/" + encodeURIComponent(mid), class: "small" }, "All topics")),
      h("p", { class: "small muted", style: { margin: "6px 0 0" } },
        `${M.name} · topic ${tid + 1} of ${M.topics.length} · ${fmt(100 * Tp.share, 1)}% of the words · strongest in ${plural(Tp.top_docs, "document")} · coherence ${fmt(Tp.coherence, 3)}`,
        Tp.stability.of > 1 ? ` · recurs in ${Tp.stability.recurs} of ${Tp.stability.of} runs` : ""),
      Tp.stability.of > 1 && Tp.stability.recurs / Tp.stability.of < 0.6 ? h("p", { class: "warn small" }, "This topic came back in fewer than 60% of the re-runs, so it may not be a robust pattern.") : null,
      M.stale.length ? h("p", { class: "warn small" }, `${M.stale.join(", ")} changed since this model was fitted. Fit it again.`) : null),
    h("div", { class: "tp-layout" }, toc,
      h("div", { class: "tp-sections" }, shell("words", "Words"), shell("where", "Where it occurs"), shell("passages", "Passages"), shell("entities", "Entities"), shell("speech", "Speech"), shell("groups", "Book details"))));
  // highlight the last section whose top has passed under the header
  const links = Object.fromEntries([...toc.querySelectorAll("a[data-k]")].map(a => [a.dataset.k, a]));
  const spy = () => {
    if (!document.body.contains(toc)) { window.removeEventListener("scroll", spy); return; }
    let cur = nav[0][0];
    for (const [k] of nav) if (sections[k].getBoundingClientRect().top <= 110) cur = k;
    Object.entries(links).forEach(([k, a]) => a.classList.toggle("on", k === cur));
  };
  window.addEventListener("scroll", spy, { passive: true });
  spy();

  const fillers = [
    ["words", async () => {
      const W = await part("words"), out = h("div");
      const draw = () => {
        const lam = S.top.lam;
        const rows = W.words.map(x => ({ ...x, rel: lam * Math.log(x.p) + (1 - lam) * Math.log(x.p / x.pw) })).sort((a, b) => b.rel - a.rel).slice(0, 40);
        const maxP = Math.max(...rows.map(r => r.p));
        out.replaceChildren(
          table([{ k: "w", label: "Word", fmt: (v) => h("a", { href: "#", title: "Open in the concordance", onclick: e => { e.preventDefault(); goKwic(...itemQuery(v, W.form === "lemma" ? "lemma" : "word")); } }, v) },
            { k: "p", label: "Probability in topic (%)", num: true, fmt: v => barFmt(100 * maxP, 2)(100 * v), csv: v => fmt(100 * v, 3) },
            { k: "n", label: "Uses in the model", num: true, fmt: v => fmt(v) },
            { k: "excl", label: "Exclusive share", num: true, fmt: v => pctFmt(v, 0), csv: v => fmt(100 * v, 1), title: "Share of the word's weight in the model that belongs to this topic" },
            { k: "rel", label: "Relevance", num: true, fmt: v => fmt(v, 2) }], rows, { sort: "rel", limit: 40, csvName: slug(M.name) + "-topic-" + (tid + 1) + "-words" }));
      };
      draw();
      return [h("div", { class: "controls" }, h("label", {}, `Rank by: λ = ${fmt(S.top.lam, 2)}`,
        h("div", { class: "row", style: { gap: "8px" } }, h("span", { class: "small muted" }, "exclusive"),
          h("input", { type: "range", min: 0, max: 1, step: 0.05, value: S.top.lam, style: { width: "220px" }, oninput: e => { S.top.lam = +e.target.value; e.target.closest("label").firstChild.textContent = `Rank by: λ = ${fmt(S.top.lam, 2)}`; draw(); } }),
          h("span", { class: "small muted" }, "frequent")))), out, note("How this is calculated", N.page_words, "Click a word to search for it in the concordance.")];
    }],
    ["where", async () => {
      const box = h("div"), arcBox = h("div");
      const R = await part("where", { seg: S.nar.seg });
      const drawArc = async pre => {
        const r = pre || await part("where", { seg: S.nar.seg });
        const fb = Object.entries(r.info).filter(([b, i]) => i && i.fallback).map(([b]) => bookTitle(b));
        arcBox.replaceChildren(fb.length ? h("p", { class: "warn small" }, `No chapters found in ${fb.join(", ")}; slices are used there.`) : null,
          chartBox(arcChart(r.segments, [{ name: Tp.label || topicName({ label: "", distinctive: Tp.distinctive }), values: r.arc.values, counts: r.arc.counts, color }], { ylabel: "% of the words in each segment" }), `topic-${tid + 1}-arc`),
          table([{ k: "title", label: "Book" }, { k: "label", label: "Segment" }, { k: "words", label: "Words", num: true, fmt: v => fmt(v) },
            { k: "v", label: "Topic share %", num: true, fmt: v => v == null ? "—" : fmt(v, 1) }, { k: "c", label: "Documents", num: true }],
            r.segments.map((sg, k) => ({ ...sg, v: r.arc.values[k], c: r.arc.counts[k] })), { limit: 15, csvName: "topic-arc" }));
      };
      const bookCols = [{ k: "group", label: "Book" }, { k: "docs", label: "Documents", num: true }, { k: "share", label: "Share of the words", num: true, fmt: v => barFmt(100 * Math.max(...R.books.map(r => r.share)), 1)(100 * v), csv: v => fmt(100 * v, 2) },
        { k: "ratio", label: "Against all books", num: true, fmt: ratioFmt, csv: v => v == null ? "" : fmt(v, 2) }, pCol, { k: "p", label: "", fmt: (v, r) => versus(r, "than in the other books"), csv: () => "" }];
      box.append(chartBox(topicStrip(R.strips, R.max, color, (b, tok) => (location.hash = `#/read/${encodeURIComponent(b)}/${tok}`)), `topic-${tid + 1}-strip`),
        R.books.length > 1 ? table(bookCols, R.books, { sort: "share", csvName: "topic-books" }) : null,
        h("h4", { style: { margin: "14px 0 4px" } }, "Along the books"), segControl(drawArc), arcBox,
        note("How this is calculated", N.page_where));
      await drawArc(R);
      return box;
    }],
    ["passages", async () => {
      const st = S.top.passages || (S.top.passages = { n: 8, book: "" }), out = h("div");
      const load = async () => {
        out.replaceChildren(loading("Loading…"));
        const r = await part("passages", { n: st.n, book: st.book });
        out.replaceChildren(r.passages.map(p => h("div", { class: "ev", style: { padding: "8px 0" } },
          h("div", { class: "small muted" }, `${p.title} · ${fmt(p.pos, 1)}% through · topic share ${fmt(100 * p.weight, 0)}% · `, textLink(p.book, p.start, p.end)),
          markup(p.text))), h("p", { class: "small muted" }, "Highlighted: the topic's 30 most probable words."));
      };
      const ctl = h("div", { class: "controls" },
        h("label", {}, "Book", h("select", { onchange: e => { st.book = e.target.value; load(); } }, h("option", { value: "" }, "All books"), M.books.map(b => h("option", { value: b, selected: st.book === b }, M.titles[b])))),
        h("label", {}, "Passages", h("select", { onchange: e => { st.n = +e.target.value; load(); } }, [5, 8, 15, 30].map(n => h("option", { value: n, selected: st.n === n }, n)))));
      await load();
      return [ctl, out];
    }],
    ["entities", async () => {
      const r = await part("entities"), wrap = h("div"), st = S.top;
      const types = ["ALL", ...TYPES.filter(t => r.rows.some(x => x.type === t))];
      const draw = () => {
        const rows = r.rows.filter(x => (st.entType === "ALL" || x.type === st.entType) && (st.entDir === "over" ? x.ll > 0 : x.ll < 0))
          .sort((a, b) => st.entDir === "over" ? b.ll - a.ll : a.ll - b.ll).slice(0, 150);
        wrap.replaceChildren(
          h("p", { class: "small muted", style: { marginTop: 0 } }, `Entities with at least ${r.min} mentions in the model's documents, ranked by how much more (or less) often they are mentioned in text where this topic is strong.`),
          h("div", { class: "controls" }, h("div", { class: "fld" }, "Show", seg([["over", "Drawn to the topic"], ["under", "Avoiding the topic"]], st.entDir, v => { st.entDir = v; draw(); })),
            h("div", { class: "fld" }, "Type", seg(types.map(t => [t, t === "ALL" ? "All" : t]), st.entType, v => { st.entType = v; draw(); }))),
          table([{ k: "name", label: "Entity", fmt: (v, x) => h("a", { href: "#/entities/" + encodeURIComponent(x.id) }, v) }, { k: "type", label: "Type", fmt: v => typeChip(v) }, ...assocCols("ent")],
            rows, { sort: "ll", limit: 25, csvName: slug(M.name) + "-topic-" + (tid + 1) + "-entities", empty: "No entities with enough mentions." }),
          note("How this is calculated", N.page_entities));
      };
      draw();
      return wrap;
    }],
    ["speech", async () => {
      const r = await part("speech"), d = r.dialogue;
      const spkCols = [{ k: "name", label: "Speaker", fmt: (v, x) => x.linked ? h("a", { href: "#/entities/" + encodeURIComponent(x.id) }, v) : v }, ...assocCols("words")];
      const narCols = [{ k: "name", label: "Narrator", fmt: (v, x) => x.unit ? h("a", { href: "#/entities/" + encodeURIComponent(x.unit) }, v) : v }, ...assocCols("words")];
      const top = rows => rows.filter(x => x.ll > 0).slice(0, 25);
      return [h("p", { style: { marginTop: 0 } }, `Where this topic is strong, ${pctFmt(d.strong, 0)} of the words are in dialogue, against ${pctFmt(d.base, 0)} across the model. `,
          d.vocab_dialogue + d.vocab_narration ? `Its 30 most probable words occur ${fmt(d.vocab_dialogue)} times in dialogue and ${fmt(d.vocab_narration)} in narration (${pctFmt(d.vocab_share, 0)} in dialogue).` : ""),
        h("h4", { style: { margin: "12px 0 4px" } }, "Speakers whose quotes carry it"),
        table(spkCols, top(r.speakers), { sort: "ll", limit: 15, csvName: "topic-speakers", empty: "No speaker has enough words in this topic's text." }),
        h("h4", { style: { margin: "12px 0 4px" } }, "Narrators"),
        table(narCols, r.narrators.slice().sort((a, b) => b.ll - a.ll), { sort: "ll", limit: 15, csvName: "topic-narrators", empty: "No narrator has enough words." }),
        note("How this is calculated", N.page_speech, `Speakers and narrators need at least ${r.min} words in the model's documents.`)];
    }],
    ["groups", async () => {
      const r = await part("groups"), wrap = h("div"), st = S.top;
      const draw = () => {
        const rows = r.fields[st.groupBy];
        wrap.replaceChildren(
          h("div", { class: "controls" }, h("div", { class: "fld" }, "Group books by", seg([["series", "Series"], ["author", "Author"], ["year", "Year"], ["tag", "Tag"]], st.groupBy, v => { st.groupBy = v; draw(); }))),
          rows.length < 2 ? h("p", { class: "muted small" }, "All the model's books share the same value, so there is nothing to compare. Add details under Library.") : null,
          table([{ k: "group", label: { series: "Series", author: "Author", year: "Year", tag: "Tag" }[st.groupBy] },
            { k: "books", label: "Books", fmt: v => v.length > 3 ? plural(v.length, "book") : v.join(" + "), csv: v => v.join(" + "), sortVal: r2 => r2.books.length },
            { k: "docs", label: "Documents", num: true }, { k: "share", label: "Share of the words", num: true, fmt: v => barFmt(100 * Math.max(...rows.map(x => x.share)), 1)(100 * v), csv: v => fmt(100 * v, 2) },
            { k: "ratio", label: "Against all books", num: true, fmt: ratioFmt, csv: v => v == null ? "" : fmt(v, 2) }, pCol,
            { k: "p", label: "", fmt: (v, x) => versus(x, "than in the other groups"), csv: () => "" }], rows, { sort: "share", csvName: "topic-by-" + st.groupBy }),
          note("How this is calculated", N.page_groups));
      };
      draw();
      return wrap;
    }],
  ];
  (async () => { for (const [key, fn] of fillers) await fill(key, fn); })();
}
