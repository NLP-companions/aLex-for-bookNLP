"use strict";
/* ---------- Dialogue ---------- */
S.dlg = { sub: "speakers", minWords: 200, unit: "word", verbTarget: null, voiceTarget: null, voiceRef: { kind: "others" }, convTarget: null,
  // one sentence-type filter state ({type, weigh}) per place that shows the control, so none of them affects another
  sf: { quotes: { type: "", weigh: false }, verbs: { type: "", weigh: false }, verbsTarget: { type: "", weigh: false },
    style: { type: "", weigh: false }, voice: { type: "", weigh: false } },
  qf: { attributed: "", addr_method: "" },
  indMode: "search", indTarget: null, indRef: null };
/** Short names of the ways an addressee is found. */
const ADDR_SHORT = { named: "named in the quote", reply: "reply", continues: "continues", next: "next speaker", yours: "set by you", yours_all: "everyone present, set by you" };

/** Quote cards: speaker → addressee, the quote in its sentence, and a Correct link that opens the quote editor. */
function quoteCards(items, onChange) {
  return items.map(e => {
    const edit = h("div");
    return h("div", { class: "ev" },
      h("div", { class: "who" }, e.speaker ? h("b", {}, e.speaker) : h("span", { class: "muted" }, "Unattributed"),
        e.addressee ? [" → ", h("b", {}, e.addressee), h("span", { class: "meth" }, ` (${ADDR_SHORT[e.addr_method] || e.addr_method})`)] : null,
        e.verb ? h("span", { class: "meth" }, ` · ${e.verb}${e.adverbs ? " " + e.adverbs : ""}`) : null),
      h("div", { class: "src" }, `${e.title}, ${fmt(e.pos, 1)}% through · ${plural(e.words, "word")} · `, textLink(e.book, e.tok), " · ",
        h("a", { href: "#", onclick: ev => { ev.preventDefault(); if (edit.firstChild) edit.replaceChildren(); else edit.replaceChildren(quoteEditor(e.book, e.qi, onChange)); } }, "Correct")),
      markup(e.text), edit);
  });
}
/** Download a list of quotes as CSV. */
const quotesCsv = (name, items) => downloadCsv(slug(name), ["book", "position_percent", "speaker", "addressee", "addressee_method", "verb", "adverbs", "words", "quote"],
  items.map(e => [e.title, e.pos, e.speaker || "", e.addressee || "", e.addr_method || "", e.verb || "", e.adverbs, e.words, e.quote.replace(/[\x01][^\x02]*\x02|\x03/g, "")]));

/** Open the side drawer with the quotes matching a filter. */
async function openQuotes(title, subtitle, filter) {
  $("#drawerTitle").replaceChildren(h("h2", { style: { margin: 0 } }, title), subtitle ? h("div", { class: "muted small" }, subtitle) : null);
  $("#drawerBody").replaceChildren(loading("Finding quotes…"));
  $("#drawer").hidden = false;
  const r = await api("/api/dialogue/quotes", withBooks({ filter, limit: 300 }));
  $("#drawerBody").replaceChildren(
    h("div", { class: "tbl-foot" }, h("span", {}, r.total > r.shown ? `First ${fmt(r.shown)} of ${plural(r.total, "quote")}` : plural(r.total, "quote")),
      h("button", { class: "btn small", onclick: () => quotesCsv(title, r.items) }, "Download CSV")),
    r.items.length ? quoteCards(r.items, () => { S.units = null; }) : h("div", { class: "empty" }, "No quotes found."));
}

/** Dialogue share along a book (50 slices, lightly smoothed), one line per book. */
function timeChart(series) {
  const W = 760, left = 46, right = 170, top = 14, bottom = 34, H = 280, pw = W - left - right, ph = H - top - bottom;
  const smooth = v => v.map((_, i) => { const w = v.slice(Math.max(0, i - 1), i + 2); return w.reduce((a, b) => a + b, 0) / w.length; });
  const data = series.map(s => ({ ...s, values: smooth(s.values) }));
  const max = Math.max(1e-9, ...data.flatMap(s => s.values)) * 1.08;
  const x = i => left + pw * (i + 0.5) / 50, y = v => top + ph - ph * v / max;
  const g = svg("svg", { viewBox: `0 0 ${W} ${H}`, "font-family": SVG_FONT, "font-size": 11.5, role: "img", style: "max-width:900px" });
  const step = [5, 10, 20, 25].find(st => max / st <= 6) || 50;
  for (let v = 0; v <= max; v += step) {
    g.append(svg("line", { x1: left, x2: left + pw, y1: y(v), y2: y(v), stroke: cssVar("--rule-soft") }));
    g.append(svg("text", { x: left - 6, y: y(v) + 4, "text-anchor": "end", fill: cssVar("--faint") }, fmt(v, 0) + "%"));
  }
  g.append(svg("text", { x: left, y: H - 10, fill: cssVar("--faint"), "font-size": 10.5 }, "start of book"));
  g.append(svg("text", { x: left + pw, y: H - 10, fill: cssVar("--faint"), "font-size": 10.5, "text-anchor": "end" }, "end"));
  const ends = [];
  data.forEach(s => {
    g.append(svg("polyline", { points: s.values.map((v, i) => `${x(i)},${y(v)}`).join(" "), fill: "none", stroke: s.color, "stroke-width": data.length > MANY_LINES ? 1.2 : 1.8,
      "stroke-opacity": data.length > MANY_LINES ? 0.7 : 1 }, svg("title", {}, s.name)));
    ends.push([y(s.values[s.values.length - 1]), s]);
  });
  if (data.length > MANY_LINES) return g;           // too many lines to name at their ends: hovering a line gives its name
  ends.sort((a, b) => a[0] - b[0]);
  let last = -Infinity;
  for (const e of ends) { e[0] = Math.max(e[0], last + 13); last = e[0]; }
  for (const [ly, s] of ends) g.append(svg("text", { x: left + pw + 10, y: ly + 4, fill: s.color, "font-weight": 600 }, s.name.length > 22 ? s.name.slice(0, 21) + "…" : s.name));
  return g;
}

/** The Dialogue pages (speakers, verbs, voice, conversations, quotes) with the shared conversation-gap setting. */
async function renderDialogue(main, sub) {
  const D = S.dlg;
  D.sub = sub || D.sub;
  const tabs = [["speakers", "Who speaks"], ["verbs", "Speech verbs"], ["voice", "How they speak"], ["conversations", "Conversations"], ["quotes", "Quotes"],
    ["indepth", "In-Depth Who Speaks"]];
  const body = h("div", {}, loading("Loading…"));
  const gapInput = h("input", { type: "number", min: 0, value: S.lib.settings.conv_gap ?? 100, style: { width: "70px" },
    onchange: async e => { S.lib = await api("/api/settings", { conv_gap: Math.max(0, +e.target.value || 0) }); toast("Saved."); renderDialogue(main, D.sub); } });
  main.replaceChildren(
    h("section", { class: "panel" },
      h("div", { class: "row" },
        h("div", { class: "subtabs grow", style: { marginBottom: 0, borderBottom: 0 } }, tabs.map(([k, l]) => h("button", { class: k === D.sub ? "on" : "", onclick: () => (location.hash = "#/dialogue/" + k) }, l))),
        h("label", { class: "small muted row", style: { gap: "6px" }, title: "Used for conversations and addressees" }, "A conversation ends after", gapInput, "narration words without a quote"))),
    body);
  const f = { speakers: dlgSpeakers, verbs: dlgVerbs, voice: dlgVoice, conversations: dlgConversations, quotes: dlgQuotes, indepth: dlgIndepth }[D.sub] || dlgSpeakers;
  await f(body);
}

/** "Dialogue in each book" and "Speakers", for the whole selection: shared by "Who speaks" and, with nothing chosen,
    In-Depth Who Speaks' Search mode. */
async function wholeSpeakersPanels() {
  const O = await api("/api/dialogue/overview", withBooks({}));
  const N = S.lib.dialogue_notes;
  return [
    h("section", { class: "panel" }, h("h2", {}, "Dialogue in each book"),
      table([{ k: "title", label: "Book" }, { k: "words", label: "Words", num: true, fmt: v => fmt(v) }, { k: "dialogue", label: "In quotes", num: true, fmt: v => fmt(v) },
        { k: "share", label: "% dialogue", num: true, fmt: v => fmt(v, 1) }, { k: "quotes", label: "Quotes", num: true, fmt: v => fmt(v) },
        { k: "attributed", label: "% attributed", num: true, fmt: v => fmt(v, 1) }, { k: "addressed", label: "% with addressee", num: true, fmt: v => fmt(v, 1) },
        { k: "speakers", label: "Speakers", num: true, fmt: v => fmt(v) }, { k: "conversations", label: "Conversations", num: true, fmt: v => fmt(v) }],
        O.books, { csvName: "dialogue by book", limit: 100 }),
      h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Share of words in dialogue, from start to end of each book"),
      chartBox(timeChart(O.time.map((t, i) => ({ name: t.title, color: PALETTE[i % PALETTE.length], values: t.values }))), "dialogue-across-books"),
      note("How this is calculated", N.words, "The chart splits each book into 50 slices and shows the share of words inside quotes in each, averaged with its neighbours to smooth it.")),
    h("section", { class: "panel" }, h("h2", {}, "Speakers"),
      h("p", { class: "small muted", style: { marginTop: 0 } },
        `${fmt(O.dialogue_words)} words of dialogue. ` + (O.unattributed.quotes ? `${plural(O.unattributed.quotes, "quote")} (${fmt(O.unattributed.words)} words) have no speaker. ` : "") +
        (O.below_min ? `${plural(O.below_min, "quote")} come from speakers below the minimum and aren't listed. ` : "") + "Click a row for the quotes."),
      table([{ k: "name", label: "Speaker", fmt: (v, r) => h("span", {}, typeChip(r.type), " ", h("a", { href: "#/entities/" + encodeURIComponent(r.id), onclick: e => e.stopPropagation() }, v)), csv: v => v },
        { k: "books", label: "Books", num: true }, { k: "quotes", label: "Quotes", num: true, fmt: v => fmt(v) },
        { k: "words", label: "Words", num: true, fmt: barFmt(O.speakers[0] ? O.speakers[0].words : 1) },
        { k: "share", label: "% of dialogue", num: true, fmt: v => fmt(v, 1) }, { k: "per_quote", label: "Words per quote", num: true, fmt: v => fmt(v, 1) },
        { k: "addressed", label: "Addressed", num: true, fmt: v => fmt(v), title: "Quotes estimated to be addressed to them" },
        { k: "said", label: "% “said”", num: true, fmt: v => v == null ? "—" : fmt(v, 0), title: "Share of their quotes introduced with say" },
        { k: "top_verbs", label: "Most used speech verbs" }],
        O.speakers, { limit: 40, csvName: "speakers", onRow: r => openQuotes(`Quotes by ${r.name}`, null, { speaker: { kind: "unit", id: r.id } }), empty: "No attributed quotes." }),
      note("About these columns", N.words, "Addressed counts quotes estimated to be spoken to them; see Conversations for how.", N.verbs))
  ];
}

/** Who speaks: dialogue per book, then a table of speakers. */
async function dlgSpeakers(body) {
  narratorsPanel().then(p => body.append(p));
  body.replaceChildren(...await wholeSpeakersPanels());
}

/** The same three sections ("Dialogue in each book", "Speakers", "Narrators"), pooled for one scope (an entity, a
    group, a tag or a gender): "Dialogue in each book" becomes that scope's own per-book breakdown and dialogue-share
    chart, "Speakers" its own pooled figures, "Narrators" its own narrating figures, if any — everyone the scope
    matches, counted as one. Used by In-Depth Who Speaks' Search mode. */
async function scopedSpeakerPanels(spec) {
  const E = await api("/api/dialogue/scope", withBooks({ target: spec }));
  if (!E) return [h("p", { class: "muted small" }, "Nobody in the selected books matches that.")];
  const label = specLabel(spec);
  const fact = (lbl, v) => h("div", {}, h("b", {}, v), lbl);
  return [
    h("section", { class: "panel" }, h("h2", {}, "Dialogue in each book"),
      E.per_book.length ? table([{ k: "title", label: "Book" }, { k: "quotes", label: "Quotes", num: true },
        { k: "words", label: "Words", num: true, fmt: v => fmt(v) }, { k: "share", label: "% of the book's dialogue", num: true, fmt: v => fmt(v, 1) },
        { k: "per_quote", label: "Words per quote", num: true, fmt: v => fmt(v, 1) }, { k: "said", label: "% “said”", num: true, fmt: v => v == null ? "—" : fmt(v, 0) },
        { k: "top_verbs", label: "Most used speech verbs" }], E.per_book, { csvName: `${label} speech by book` })
        : h("p", { class: "muted small" }, "No quotes in the selected books."),
      E.time.length ? [h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Share of words in dialogue, from start to end of each book"),
        chartBox(timeChart(E.time.map((t, i) => ({ name: t.title, color: PALETTE[i % PALETTE.length], values: t.values }))), slug(label) + "-time")] : null),
    h("section", { class: "panel" }, h("h2", {}, "Speakers"),
      h("div", { class: "facts-inline" },
        fact("Quotes", fmt(E.style.quotes)), fact("Words spoken", fmt(E.style.words)), fact("Share of dialogue", fmt(E.share, 1) + "%"),
        fact("Words per quote", fmt(E.style.per_quote, 1)), fact("Questions per 100 quotes", fmt(E.style.questions, 1)),
        fact("MATTR", E.style.mattr == null ? "—" : fmt(E.style.mattr, 3)))),
    h("section", { class: "panel" }, h("h2", {}, "Narrators"),
      E.narrating ? h("p", { class: "small" }, `${plural(E.narrating.paragraphs, "paragraph")}, ${fmt(E.narrating.style.words)} words, in ${booksLabel(E.narrating.books)}.`)
        : h("p", { class: "muted small" }, "Nobody in this scope narrates in the selected books."))
  ];
}

/** One row of a Compare-mode comparison: a label, then two small filled bars scaled to whichever side is larger,
    target's colour above reference's — the "rows above and below each other" replacement for two side-by-side
    figures. */
function cmpRow(label, tv, rv, dec = 0) {
  const max = Math.max(tv, rv, 1e-9);
  const bar = (v, color) => h("div", { class: "bar-cell" }, h("i", { style: { width: Math.max(1, 130 * v / max) + "px", background: color, opacity: 1 } }), fmt(v, dec));
  return h("div", { style: { marginBottom: "10px" } }, h("div", { class: "small muted" }, label), bar(tv, PALETTE[0]), bar(rv, PALETTE[1]));
}

/** "Dialogue in each book", "Speakers" and "Narrators" for two scopes at once, target and reference stacked as rows
    rather than side by side — a paired bar per book (quotes), a `cmpRow` per Speakers figure, and a coloured line per
    side in one shared dialogue-share chart, target in `PALETTE[0]`, reference in `PALETTE[1]` throughout. Used by
    In-Depth Who Speaks' Compare mode. */
async function compareSpeakerPanels(targetSpec, refSpec) {
  const [T, R] = await Promise.all([api("/api/dialogue/scope", withBooks({ target: targetSpec })), api("/api/dialogue/scope", withBooks({ target: refSpec }))]);
  const tName = specLabel(targetSpec), rName = specLabel(refSpec);
  if (!T || !R) return [h("p", { class: "muted small" }, `Nobody in the selected books matches ${!T ? tName : rName}.`)];
  const books = selected();
  const byBook = E => Object.fromEntries(E.per_book.map(pb => [pb.book, pb]));
  const tb = byBook(T), rb = byBook(R);
  const bars = hbarChart([{ name: tName, color: PALETTE[0], rows: books.map(b => ({ item: bookTitle(b), n: tb[b] ? tb[b].quotes : 0 })) },
    { name: rName, color: PALETTE[1], rows: books.map(b => ({ item: bookTitle(b), n: rb[b] ? rb[b].quotes : 0 })) }]);
  const time = [...T.time.map(t => ({ name: `${t.title} · ${tName}`, color: PALETTE[0], values: t.values })),
    ...R.time.map(t => ({ name: `${t.title} · ${rName}`, color: PALETTE[1], values: t.values }))];
  const narrLine = (E, name, color) => h("p", { class: "small", style: { borderLeft: `3px solid ${color}`, paddingLeft: "8px", margin: "4px 0" } },
    h("b", {}, name + ": "), E.narrating ? `${plural(E.narrating.paragraphs, "paragraph")}, ${fmt(E.narrating.style.words)} words, in ${booksLabel(E.narrating.books)}.` : "Doesn't narrate in the selected books.");
  return [
    h("section", { class: "panel" }, h("h2", {}, "Dialogue in each book"),
      h("p", { class: "small muted", style: { marginTop: 0 } }, "Quotes per book."), chartBox(bars, "compare-quotes-by-book"),
      time.length ? [h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Share of words in dialogue, from start to end of each book"),
        chartBox(timeChart(time), "compare-time")] : null),
    h("section", { class: "panel" }, h("h2", {}, "Speakers"),
      cmpRow("Quotes", T.style.quotes, R.style.quotes), cmpRow("Words spoken", T.style.words, R.style.words),
      cmpRow("Share of dialogue (%)", T.share, R.share, 1), cmpRow("Words per quote", T.style.per_quote, R.style.per_quote, 1),
      cmpRow("Questions per 100 quotes", T.style.questions, R.style.questions, 1),
      cmpRow("MATTR", T.style.mattr || 0, R.style.mattr || 0, 3)),
    h("section", { class: "panel" }, h("h2", {}, "Narrators"), narrLine(T, tName, PALETTE[0]), narrLine(R, rName, PALETTE[1]))
  ];
}

/** In-Depth Who Speaks: "Who speaks", "Dialogue in each book", "Speakers" and "Narrators" together, filterable and
    comparable by gender, tag, entity or group. Search mode scopes them to one pooled selection, or (nothing chosen)
    the same whole-selection totals as "Who speaks"; Compare mode stacks two scopes' figures as rows rather than side
    by side, target and reference each their own colour throughout (`compareSpeakerPanels`). */
async function dlgIndepth(body) {
  const D = S.dlg;
  const out = h("div"), controlsBox = h("div", { class: "controls" });
  const pickerOpts = { group: true, gender: true };
  const drawControls = () => controlsBox.replaceChildren(
    h("div", { class: "fld" }, "Mode", seg([["search", "Search"], ["compare", "Compare"]], D.indMode, v => { D.indMode = v; refresh(); })),
    h("div", { class: "fld" }, D.indMode === "compare" ? "Target" : "Scope", picker(D.indTarget, v => { D.indTarget = v; refresh(); }, pickerOpts)),
    D.indMode === "compare" ? h("div", { class: "fld" }, "Compared with", picker(D.indRef, v => { D.indRef = v; refresh(); }, pickerOpts)) : null);
  const draw = async () => {
    out.replaceChildren(loading("Loading…"));
    if (D.indMode === "compare") {
      if (!D.indTarget || !D.indRef) { out.replaceChildren(h("p", { class: "muted small" }, "Choose two things to compare.")); return; }
      out.replaceChildren(...await compareSpeakerPanels(D.indTarget, D.indRef));
    } else {
      out.replaceChildren(...(D.indTarget ? await scopedSpeakerPanels(D.indTarget) : await wholeSpeakersPanels()));
      if (!D.indTarget) narratorsPanel().then(p => out.append(p));
    }
  };
  const refresh = () => { drawControls(); draw(); };
  body.replaceChildren(h("section", { class: "panel" }, controlsBox), out);
  refresh();
}

/** Speech verbs and adverbs overall, and for one speaker or group with what is distinctive. */
async function dlgVerbs(body) {
  const D = S.dlg;
  const out = h("div"), overall = h("div", {}, loading("Loading…"));
  const N = S.lib.dialogue_notes;
  const vt = (rows, label, key, name) => table([{ k: "item", label }, { k: "n", label: "Quotes", num: true, fmt: barFmt(rows[0] ? rows[0].n : 1) },
    ...(rows[0] && rows[0].pct != null ? [{ k: "pct", label: "% of quotes", num: true, fmt: v => fmt(v, 1) }] : []),
    ...(rows[0] && rows[0].speakers != null ? [{ k: "speakers", label: "Speakers", num: true }] : [])],
    rows, { limit: 20, csvName: name, onRow: r => openQuotes(`${label}: ${r.item}`, null, key(r)) });
  const loadOverall = async () => {
    const V = await api("/api/dialogue/verbs", withBooks({ ...typeArgs(D.sf.verbs) }));
    overall.replaceChildren(
      h("p", { class: "small muted", style: { marginTop: 0 } }, `${fmt(V.with_verb)} of ${plural(V.quotes, "quote")} have a speech verb: ${fmt(V.methods.subject || 0)} with the speaker as its subject, ${fmt(V.methods.near || 0)} from the nearest verb. Click a row for the quotes.`),
      h("div", { class: "cols3" },
        h("div", {}, h("h3", { class: "small muted" }, "Verbs"), vt(V.verbs, "Verb", x => ({ verb: x.item }), "speech verbs")),
        h("div", {}, h("h3", { class: "small muted" }, "Adverbs"), vt(V.adverbs, "Adverb", x => ({ adverb: x.item }), "speech adverbs")),
        h("div", {}, h("h3", { class: "small muted" }, "Verb and adverb"), vt(V.manner, "Verb and adverb", x => ({ verb: x.item.split(" ")[0], adverb: x.item.split(" ").slice(1).join(" ") }), "speech verb and adverb"))),
      note("How this is found", N.verbs));
  };
  const drawTarget = async () => {
    if (!D.verbTarget) { out.replaceChildren(h("p", { class: "muted small" }, "Choose a speaker or tag group to see their speech verbs and which are distinctive.")); return; }
    out.replaceChildren(loading("Loading…"));
    const r = await api("/api/dialogue/verbs", withBooks({ target: D.verbTarget, ...typeArgs(D.sf.verbsTarget), ...S.stat }));
    const T = r.target, name = specLabel(D.verbTarget);
    out.replaceChildren(
      h("p", { class: "small muted" }, `${name}: ${plural(T.total, "quote")} with a speech verb.`),
      h("div", { class: "cols2" },
        vt(T.verbs, "Verb", x => ({ speaker: D.verbTarget, verb: x.item }), `${name} speech verbs`),
        vt(T.adverbs, "Adverb", x => ({ speaker: D.verbTarget, adverb: x.item }), `${name} speech adverbs`)),
      h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Speech verbs distinctive of " + name + ", compared with all other speakers"),
      statControls(drawTarget),
      table(statCols(T.summary, false), T.distinctive, { limit: 30, csvName: `${name} distinctive speech verbs`, rowClass: row => row.sig ? "" : "dim",
        onRow: row => openQuotes(`${name}: ${row.item}`, null, { speaker: D.verbTarget, verb: row.item }), empty: "Nothing distinctive at these settings." }),
      statNote(T.summary));
  };
  body.replaceChildren(
    h("section", { class: "panel" }, h("h2", {}, "How speech is introduced"),
      sentenceTypeFilter(D.sf.verbs, loadOverall),
      overall),
    h("section", { class: "panel" }, h("h2", {}, "One speaker or group"),
      h("div", { class: "controls" },
        h("div", { class: "fld" }, "Speaker", picker(D.verbTarget, v => { D.verbTarget = v; drawTarget(); }, { books: true, book: true, gender: true })),
        sentenceTypeFilter(D.sf.verbsTarget, drawTarget)),
      out));
  loadOverall(); drawTarget();
}

/** The columns of a speaking-style table (see `dialogue.style`): quotes (or paragraphs, for narration), words, words per quote, questions, I/you/we, word length, MATTR. */
const SPEECH_STYLE_COLS = [{ k: "name", label: "Speaker", fmt: (v, r) => r.type ? h("span", {}, typeChip(r.type), " ", v) : h("b", {}, v), csv: v => v },
  { k: "quotes", label: "Quotes", num: true, fmt: v => fmt(v) }, { k: "words", label: "Words", num: true, fmt: v => fmt(v) },
  { k: "per_quote", label: "Words per quote", num: true, fmt: v => fmt(v, 1) }, { k: "questions", label: "Questions", num: true, fmt: v => fmt(v, 1), title: "Per 100 quotes" },
  { k: "exclaims", label: "Exclamations", num: true, fmt: v => fmt(v, 1), title: "Per 100 quotes" },
  { k: "i", label: "I", num: true, fmt: v => fmt(v, 1), title: "Per 1,000 words" }, { k: "you", label: "You", num: true, fmt: v => fmt(v, 1), title: "Per 1,000 words" },
  { k: "we", label: "We", num: true, fmt: v => fmt(v, 1), title: "Per 1,000 words" }, { k: "wordlen", label: "Word length", num: true, fmt: v => fmt(v, 2) },
  { k: "mattr", label: "MATTR", num: true, fmt: (v, r) => v == null ? "—" : r.mattr_ok ? fmt(v, 3) : `(${fmt(v, 3)})` }];

/** Speaking style per speaker, and the distinctive vocabulary of a speaker or narrator against others. */
async function dlgVoice(body) {
  const D = S.dlg, N = S.lib.dialogue_notes;
  const styleBox = h("div", {}, loading("Loading…"));
  const out = h("div");
  const styleCols = SPEECH_STYLE_COLS;
  const loadStyle = async () => {
    const r = await api("/api/dialogue/style", withBooks({ min_words: D.minWords, ...typeArgs(D.sf.style) }));
    styleBox.className = "";
    styleBox.replaceChildren(table(styleCols, [{ ...r.all, name: "All speakers", id: "" }, ...r.rows], { limit: 30, csvName: "speaking style",
      onRow: row => { if (row.id) { D.voiceTarget = { kind: "unit", id: row.id, name: row.name }; renderDialogue($("#main"), "voice"); } } }));
  };
  const draw = async () => {
    if (!D.voiceTarget) { out.replaceChildren(h("p", { class: "muted small" }, "Choose a speaker or tag group, or click a row above.")); return; }
    out.replaceChildren(loading("Comparing…"));
    const r = await api("/api/dialogue/voice", withBooks({ target: D.voiceTarget, reference: D.voiceRef, unit: D.unit, ...typeArgs(D.sf.voice), ...S.stat }));
    const s = r.summary;
    out.replaceChildren(
      table(styleCols.map(c => c.k === "name" ? { ...c, label: "", fmt: v => v } : c), [{ ...r.target, name: r.target.label }, { ...r.reference, name: r.reference.label }], { csvName: "style comparison" }),
      h("h3", { class: "small muted", style: { marginTop: "14px" } }, `Words distinctive of ${r.target.label}, compared with ${r.reference.label}`),
      r.summary.d === 0 ? h("p", { class: "warn small" }, "The comparison side has no speech in these books.") : null,
      table(statCols(s, false), r.rows, { limit: 40, csvName: `${r.target.label} distinctive words`, rowClass: row => row.sig ? "" : "dim",
        onRow: row => openQuotes(`“${row.item}”`, r.target.label, { speaker: D.voiceTarget, [D.unit === "lemma" ? "lemma" : "word"]: row.item }),
        empty: "Nothing distinctive at these settings." }),
      statNote(s));
  };
  body.replaceChildren(
    h("section", { class: "panel" }, h("h2", {}, "Speaking style"),
      h("div", { class: "controls" },
        h("label", {}, "Speakers with at least this many words", h("input", { type: "number", min: 0, value: D.minWords, onchange: e => { D.minWords = Math.max(0, +e.target.value || 0); loadStyle(); } })),
        sentenceTypeFilter(D.sf.style, loadStyle)),
      styleBox, note("What the columns mean", N.style)),
    h("section", { class: "panel" }, h("h2", {}, "Distinctive vocabulary"),
      h("div", { class: "controls" },
        h("div", { class: "fld" }, "Speaker or narrator", picker(D.voiceTarget, v => { D.voiceTarget = v; draw(); }, { books: true, narration: true, book: true, gender: true })),
        h("div", { class: "fld" }, "Compared with", picker(D.voiceRef, v => { D.voiceRef = v; draw(); }, { others: true, books: true, narration: true, book: true, gender: true })),
        h("div", { class: "fld" }, "Count", seg([["word", "Word forms"], ["lemma", "Lemmas"]], D.unit, v => { D.unit = v; renderDialogue($("#main"), "voice"); })),
        sentenceTypeFilter(D.sf.voice, draw)),
      statControls(draw), out));
  loadStyle(); draw();
}

/** Conversations: runs of quotes, optionally only those involving someone; click one to read it. */
async function dlgConversations(body) {
  const D = S.dlg, N = S.lib.dialogue_notes;
  const out = h("div", {}, loading("Loading…"));
  const load = async () => {
    const r = await api("/api/dialogue/conversations", withBooks({ target: D.convTarget }));
    out.className = "";
    out.replaceChildren(
      h("p", { class: "small muted" }, `${plural(r.total, "conversation")}. Click a row to read it.`),
      table([{ k: "title", label: "Book" }, { k: "pos", label: "% through", num: true, fmt: v => fmt(v, 1) }, { k: "quotes", label: "Quotes", num: true },
        { k: "words", label: "Words", num: true, fmt: v => fmt(v) }, { k: "speakers", label: "Speakers", num: true }, { k: "participants", label: "Who speaks" },
        { k: "opening", label: "Opening words" }], r.rows,
        { limit: 50, csvName: "conversations", rowClass: row => row.edited ? "edited" : "", onRow: row => openQuotes(`Conversation in ${row.title}`, `${fmt(row.pos, 1)}% through; ${row.participants}. Corrections apply when you reopen the list.`, { book: row.book, conv: row.conv }) }));
  };
  body.replaceChildren(h("section", { class: "panel" }, h("h2", {}, "Conversations"),
    h("div", { class: "controls" }, h("div", { class: "fld" }, "Only those involving", h("div", { class: "row" }, picker(D.convTarget, v => { D.convTarget = v; load(); }),
      D.convTarget ? h("button", { class: "btn small", onclick: () => { D.convTarget = null; renderDialogue($("#main"), "conversations"); } }, "Show all") : null))),
    out, note("How conversations and addressees are found", N.conversations, N.addressee)));
  load();
}

/** Every quote, filtered by speaker, book, text, speech verb, attribution or how the addressee was found. */
async function dlgQuotes(body) {
  const D = S.dlg, f = D.qf;
  const out = h("div");
  let last = null;
  const load = async () => {
    out.replaceChildren(loading("Finding quotes…"));
    const filter = { ...f, ...typeArgs(D.sf.quotes) };
    for (const k of Object.keys(filter)) if (filter[k] === "" || filter[k] == null) delete filter[k];
    const r = await api("/api/dialogue/quotes", withBooks({ filter, limit: 400 }));
    last = r;
    out.replaceChildren(
      h("div", { class: "tbl-foot" }, h("span", {}, r.total > r.shown ? `First ${fmt(r.shown)} of ${plural(r.total, "quote")}; narrow the filters to see others` : plural(r.total, "quote")),
        h("button", { class: "btn small", onclick: () => quotesCsv("quotes", r.items) }, "Download CSV")),
      r.items.length ? quoteCards(r.items) : h("div", { class: "empty" }, "No quotes match."));
  };
  const txt = (k, ph) => h("input", { type: "search", placeholder: ph, value: f[k] || "", onchange: e => { f[k] = e.target.value.trim().toLowerCase(); load(); } });
  body.replaceChildren(h("section", { class: "panel" }, h("h2", {}, "Quotes"),
    h("div", { class: "controls" },
      h("div", { class: "fld" }, "Speaker", h("div", { class: "row" }, picker(f.speaker || null, v => { f.speaker = v; load(); }, { books: true }),
        f.speaker ? h("button", { class: "btn small", onclick: () => { f.speaker = null; renderDialogue($("#main"), "quotes"); } }, "Any speaker") : null))),
    h("div", { class: "filters-grid" },
      h("label", {}, "Book", h("select", { onchange: e => { f.book = e.target.value; load(); } }, h("option", { value: "" }, "Any selected book"), selected().map(id => h("option", { value: id, selected: f.book === id }, bookTitle(id))))),
      h("label", {}, "Containing", txt("q", "Text in the quote")),
      h("label", {}, "Speech verb (lemma)", txt("verb", "e.g. whisper")),
      h("label", {}, "Attributed", h("select", { onchange: e => { f.attributed = e.target.value; load(); } },
        [["", "All quotes"], ["yes", "With a speaker"], ["no", "Without a speaker"]].map(([v, l]) => h("option", { value: v, selected: f.attributed === v }, l)))),
      h("label", {}, "Addressee found by", h("select", { onchange: e => { f.addr_method = e.target.value; load(); } },
        h("option", { value: "" }, "Any way, or none"), Object.entries(S.lib.addr_methods).map(([v, l]) => h("option", { value: v, selected: f.addr_method === v }, l))))),
    sentenceTypeFilter(D.sf.quotes, load),
    out));
  load();
}

/* ---------- Speech section on an entity's page ---------- */
/** The request fields for one sentence-type filter's state `{type, weigh}`: `types` (null = every type) and `weigh_verb`. */
const typeArgs = st => ({ types: st.type ? [st.type] : null, weigh_verb: st.weigh });

/** A "Sentence type" select and a "weigh the speech verb" checkbox: question/exclaim/statement from a quote's own ?
    or !, or, with the checkbox on, a speech verb like asked or exclaimed decides it too when the punctuation alone
    doesn't already say so (`core.dialogue.sentence_type`). `st` is this one control's own state `{type, weigh}`
    (`S.dlg.sf` keeps one per place that shows it), which it reads and writes; `onChange()` runs after either
    changes. Every control has its own state, so changing one never changes what another shows. `compact` makes a
    small one-line version with a shorter checkbox label (an entity's Speech panel). */
function sentenceTypeFilter(st, onChange, compact = false) {
  return h("div", { class: "row" + (compact ? " small" : "") },
    h("label", {}, "Sentence type" + (compact ? " " : ""), h("select", { onchange: e => { st.type = e.target.value; onChange(); } },
      [["", "All"], ["question", "Questions"], ["exclaim", "Exclamations"], ["statement", "Statements"]]
        .map(([v, l]) => h("option", { value: v, selected: st.type === v }, l)))),
    h("label", { class: "inline", title: "A quote's own ? or ! decides its type; this also lets a speech verb like asked or exclaimed decide it when there's no such mark" },
      h("input", { type: "checkbox", checked: st.weigh, onchange: e => { st.weigh = e.target.checked; onChange(); } }), compact ? "Weigh the speech verb" : "Weigh the speech verb too"));
}

/** The Speech section of an entity's page: figures, where they speak, verbs, and whom they talk to. It has a compact
    sentence-type filter of its own (`sentenceTypeFilter`'s compact form), independent of every Dialogue tab's. */
function speechPanel(u) {
  const box = h("section", { class: "panel" }, h("h2", {}, "Speech"), loading("Loading…"));
  const spec = u.target, group = spec.kind === "group";      // for a group, the quotes of all its entities together
  const filt = { type: "", weigh: false };
  const load = () => api("/api/dialogue/entity", withBooks({ ...u.ref, ...typeArgs(filt) })).then(draw);
  const draw = E => {
    const stSel = sentenceTypeFilter(filt, load, true);
    const st = E.style, all = E.all_style;
    const narr = E.narrating ? h("div", { class: "small", style: { margin: "4px 0 10px" } }, h("b", {}, "Narrates: "),
      `${plural(E.narrating.paragraphs, "paragraph")}, ${fmt(E.narrating.style.words)} words in ${booksLabel(E.narrating.books)}. `,
      group ? null : [h("a", { href: "#/entities/" + encodeURIComponent("nar:" + u.id) }, "Narrator profile"), " · ",
        h("a", { href: "#/dialogue/voice", onclick: () => { S.dlg.voiceTarget = { kind: "narration", id: u.id, name: u.name + ", narrating" }; S.dlg.voiceRef = { kind: "unit", id: u.id, name: u.name }; } }, "Compare their narrating voice with their dialogue")]) : null;
    if (!st.quotes) { box.replaceChildren(h("h2", {}, "Speech"), stSel, narr, h("p", { class: "muted small", style: { margin: 0 } }, "No quotes are attributed to them in the selected books" + (filt.type ? " at this sentence type." : ".")),
      E.addressed_by.length ? h("p", { class: "small" }, `Addressed in ${plural(E.addressed_by.reduce((a, b) => a + b.n, 0), "quote")}, most by ${E.addressed_by[0].name}.`) : null); return; }
    const fact = (label, v, ref) => h("div", {}, h("b", {}, v), label, ref != null ? h("span", { class: "muted" }, ` (all: ${ref})`) : null);
    const small = (rows, cols, name, onRow) => table(cols, rows, { limit: 10, csvName: `${u.name} ${name}`, onRow, empty: "None." });
    box.replaceChildren(h("h2", {}, "Speech"), stSel, narr,
      h("div", { class: "facts-inline" },
        fact("Quotes", fmt(st.quotes)), fact("Words spoken", fmt(st.words)), fact("Share of dialogue", fmt(E.share, 1) + "%"),
        fact("Words per quote", fmt(st.per_quote, 1), fmt(all.per_quote, 1)), fact("Questions per 100 quotes", fmt(st.questions, 1), fmt(all.questions, 1)),
        fact("MATTR", st.mattr == null ? "—" : fmt(st.mattr, 3), all.mattr == null ? null : fmt(all.mattr, 3)),
        E.within != null ? fact("Quotes between members", fmt(E.within)) : null),
      E.presence.length ? chartBox(presenceChart(E.presence, "#b5473c", "Where they speak"), slug(u.name) + "-speech") : null,
      E.per_book.length > 1 ? h("div", { style: { marginTop: "10px" } }, table([{ k: "title", label: "Book" }, { k: "quotes", label: "Quotes", num: true },
        { k: "words", label: "Words", num: true, fmt: v => fmt(v) }, { k: "share", label: "% of the book's dialogue", num: true, fmt: v => fmt(v, 1) },
        { k: "per_quote", label: "Words per quote", num: true, fmt: v => fmt(v, 1) }, { k: "said", label: "% “said”", num: true, fmt: v => v == null ? "—" : fmt(v, 0) },
        { k: "top_verbs", label: "Most used speech verbs" }], E.per_book, { csvName: `${u.name} speech by book` })) : null,
      h("div", { class: "cols2", style: { marginTop: "12px" } },
        h("div", {}, h("h3", { class: "small muted" }, "Speech verbs"),
          small(E.verbs, [{ k: "item", label: "Verb" }, { k: "n", label: "Quotes", num: true }, { k: "pct", label: "%", num: true, fmt: v => fmt(v, 1) }], "speech verbs",
            r => openQuotes(`${u.name}: ${r.item}`, null, { speaker: spec, verb: r.item }))),
        h("div", {}, h("h3", { class: "small muted" }, "Adverbs"),
          small(E.adverbs, [{ k: "item", label: "Adverb" }, { k: "n", label: "Quotes", num: true }], "speech adverbs",
            r => openQuotes(`${u.name}: ${r.item}`, null, { speaker: spec, adverb: r.item })))),
      h("div", { class: "cols2", style: { marginTop: "12px" } },
        h("div", {}, h("h3", { class: "small muted" }, "Talks to (estimated)"),
          small(E.talks_to, [{ k: "name", label: "Addressee" }, { k: "n", label: "Quotes", num: true },
            { k: "methods", label: "Found by", fmt: v => Object.entries(v).map(([m, n]) => `${ADDR_SHORT[m]} ${n}`).join(", "), csv: v => JSON.stringify(v) }], "talks to",
            r => openQuotes(`${u.name} to ${r.name}`, null, { speaker: spec, addressee: r.id }))),
        h("div", {}, h("h3", { class: "small muted" }, "Spoken to by (estimated)"),
          small(E.addressed_by, [{ k: "name", label: "Speaker" }, { k: "n", label: "Quotes", num: true }], "spoken to by",
            r => openQuotes(`${r.name} to ${u.name}`, null, { speaker: { kind: "unit", id: r.id }, addressee: u.parts })))),
      h("p", { class: "small" }, h("a", { href: "#/dialogue/voice", onclick: () => { S.dlg.voiceTarget = spec; } }, "Distinctive vocabulary and speaking style"), " · ",
        h("a", { href: "#/dialogue/verbs", onclick: () => { S.dlg.verbTarget = spec; } }, "Distinctive speech verbs")),
      note("How this is worked out", S.lib.dialogue_notes.words, S.lib.dialogue_notes.verbs, S.lib.dialogue_notes.addressee));
  };
  load();
  return box;
}
