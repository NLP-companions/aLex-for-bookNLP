"use strict";
/* ---------- links into the text ---------- */
/** An "Open in the text" link to a position (and optional end) in a book. */
function textLink(book, tok, end) {
  if (tok == null) return null;
  return h("a", { href: `#/read/${encodeURIComponent(book)}/${tok}${end != null && end !== tok ? "-" + end : ""}`, onclick: () => ($("#drawer").hidden = true) }, "Open in the text");
}

/* ---------- correcting a quote: addressees and its conversation ---------- */
/** The panel for correcting a quote: addressees, and its conversation and participants. Saves through /api/annot/*. */
function quoteEditor(book, qi, onChange) {
  const box = h("div", { class: "qedit" }, loading("Loading…"));
  const books = selected();
  const post = async (path, body) => { await api(path, { books, book, ...body }); S.units = null; draw(); if (onChange) onChange(); };
  const chip = (u, onX, extra) => h("span", { class: "tag" }, u.name, extra || null, onX ? h("button", { title: "Remove " + u.name, onclick: onX }, "×") : null);
  async function draw() {
    const q = await api("/api/annot/quote", { books, book, qi });
    const ids = q.addressees.map(a => a.id);
    const setA = list => post("/api/annot/addressees", { qi, addressees: list });
    const meth = q.methods[q.method] || (q.addressees.length ? "" : "No addressee found");
    box.replaceChildren(
      h("div", { class: "small" }, h("b", {}, "Speaker: "), q.speaker ? q.speaker.name : "none", h("span", { class: "muted" }, " (speakers are corrected in the editor)")),
      h("div", { class: "qrow" }, h("b", { class: "small" }, "Addressed to: "),
        q.fixed && q.fixed[0] === "*" ? h("span", { class: "tag" }, "Everyone present", h("span", { class: "muted" }, ` (${q.addressees.map(a => a.name).join(", ") || "nobody else"})`),
          h("button", { title: "Remove", onclick: () => setA([]) }, "×"))
          : q.addressees.map(a => chip(a, () => setA(ids.filter(x => x !== a.id)))),
        picker(null, v => { if (v.kind === "unit" && !ids.includes(v.id)) setA([...(q.fixed && q.fixed[0] === "*" ? [] : ids), v.id]); }, { unitOnly: true })),
      h("div", { class: "qrow small" }, h("span", { class: "muted" }, q.fixed ? "Set by you." : `Estimated: ${meth.toLowerCase()}.`),
        h("button", { class: "btn small", onclick: () => setA(["*"]) }, "Everyone present"),
        q.fixed ? h("button", { class: "btn small", onclick: () => setA(null) }, "Back to the estimate") : null),
      h("div", { class: "qrow small", style: { marginTop: "8px" } }, h("b", {}, `Conversation (${plural(q.conv_quotes, "quote")}): `),
        q.participants.map(p => chip(p, () => post("/api/annot/participants", { first_qi: q.first_qi, id: p.id, action: "remove" }), p.speaker ? null : h("span", { class: "muted" }, " listening"))),
        q.removed.map(p => h("span", { class: "tag", style: { opacity: 0.6, textDecoration: "line-through" } }, p.name,
          h("button", { title: "Put back", onclick: () => post("/api/annot/participants", { first_qi: q.first_qi, id: p.id, action: "restore" }) }, "↺"))),
        h("span", { class: "muted" }, " Add a listener:"),
        picker(null, v => { if (v.kind === "unit") post("/api/annot/participants", { first_qi: q.first_qi, id: v.id, action: "add" }); }, { unitOnly: true })),
      h("div", { class: "qrow" },
        q.first ? h("button", { class: "btn small", onclick: () => post("/api/annot/conversation", { qi, action: "merge" }) }, "Join the previous conversation")
          : h("button", { class: "btn small", onclick: () => post("/api/annot/conversation", { qi, action: "split" }) }, "Start a new conversation here"),
        q.split || q.merged ? h("button", { class: "btn small", onclick: () => post("/api/annot/conversation", { qi: q.split ? qi : q.first_qi, action: "reset" }) }, q.split ? "Undo the split" : "Undo the join") : null));
  }
  draw();
  return box;
}

/* ---------- narrators ---------- */
/** A drop-down to set a book's narrator. */
function narratorSelect(book, onChange) {
  const sel = h("select", { "aria-label": "Narrator of " + bookTitle(book) }, h("option", { value: "" }, "Unnamed narrator"));
  api("/api/annot/narrator_options?book=" + encodeURIComponent(book)).then(r => {
    sel.append(...r.rows.map(x => h("option", { value: x.id, selected: x.id === r.current }, x.name + (x.type === "VAR" ? " (VAR)" : ""))));
    if (r.current && !r.rows.some(x => x.id === r.current)) sel.append(h("option", { value: r.current, selected: true }, r.current));
  });
  sel.onchange = async () => { await api("/api/annot/narrator", { book, narrator: sel.value || null }); S.units = null; toast("Narrator saved."); if (onChange) onChange(); };
  return sel;
}

/** The narrators table shown on the Dialogue page. */
async function narratorsPanel() {
  const box = h("section", { class: "panel" }, h("h2", {}, "Narrators"), loading("Loading…"));
  const r = await api("/api/dialogue/narrators", withBooks({}));
  box.replaceChildren(h("h2", {}, "Narrators"),
    h("p", { class: "small muted", style: { marginTop: 0 } }, `${fmt(r.narration_words)} words of narration (text outside quotes). Choose each book's narrator under Library or in the text view; paragraphs told by someone else can be set in the text view. Click a row to compare a narrator's voice with the same character's dialogue.`),
    table([{ k: "name", label: "Narrator" }, { k: "books", label: "Books", num: true }, { k: "paragraphs", label: "Paragraphs", num: true, fmt: v => fmt(v) },
      { k: "exceptions", label: "Set by paragraph", num: true, title: "Paragraphs you assigned to this narrator as exceptions" },
      { k: "words", label: "Words", num: true, fmt: v => fmt(v) }, { k: "share", label: "% of narration", num: true, fmt: v => fmt(v, 1) },
      { k: "per_para", label: "Words per paragraph", num: true, fmt: v => fmt(v, 1) }, { k: "questions", label: "Questions", num: true, fmt: v => fmt(v, 1), title: "Paragraphs with a question in the narration, per 100" },
      { k: "i", label: "I", num: true, fmt: v => fmt(v, 1) }, { k: "you", label: "You", num: true, fmt: v => fmt(v, 1) }, { k: "we", label: "We", num: true, fmt: v => fmt(v, 1) },
      { k: "mattr", label: "MATTR", num: true, fmt: (v, row) => v == null ? "—" : row.mattr_ok ? fmt(v, 3) : `(${fmt(v, 3)})` },
      { k: "spoken", label: "Words in dialogue", num: true, fmt: v => v == null ? "—" : fmt(v), title: "What the same character says in quotes" }],
      r.rows, { csvName: "narrators", onRow: x => { S.dlg.voiceTarget = { kind: "narration", id: x.id, name: x.name }; S.dlg.voiceRef = x.unit ? { kind: "unit", id: x.unit, name: x.name.replace(/, narrating$/, "") } : { kind: "others" }; location.hash = "#/dialogue/voice"; } }),
    note("How narration is counted", "Narration is every word outside quotes, paragraph by paragraph. It belongs to the book's narrator (a character you choose, or an unnamed narrator), except paragraphs you've assigned to someone else. A character who narrates appears twice: narrating (here) and in dialogue (under Speakers), so their narrating voice and their direct speech can be compared."));
  return box;
}

/* ---------- the text view ---------- */
S.read = loadState("analyser.read", { book: null, layers: { entities: true, quotes: true, narrators: true, events: false, supersenses: false, sentences: false, topics: false }, topicModel: null, topicFocus: "all", hidden: [] });
/** Save the text-view settings (book, layers, topic model and focus, entity types switched off). */
const saveRead = () => saveState("analyser.read", { book: S.read.book, layers: S.read.layers, topicModel: S.read.topicModel, topicFocus: S.read.topicFocus, hidden: S.read.hidden });

/** The text view: the whole book as one scroll, chapter (or slice) after chapter, loaded as you go. Numbers stand in the margin: each
    paragraph's number, and, if asked, each sentence's inside the text; every chapter has a heading with its number. A slim bar stays at
    the top with where you are and a jump menu. The chosen layers (entities, quotes, narrators, events, supersenses, sentence numbers,
    topics) are marked; a side panel opens for the clicked name, quote, narrator label or topic band.
    `edit` is the chapter editor (#/chapters/<book>): the same scroll without layers, where a paragraph can become the start of a chapter
    and a chapter start can be renamed or removed. `arg2` (with `arg`, the book) is a token to jump to, as "tok" or "tok-end". */
async function renderRead(main, arg, arg2, edit = false) {
  const R = S.read, books = selected();
  let tok = null, end = null;
  if (arg) { R.book = decodeURIComponent(arg); }
  if (arg2) { const [a, b] = arg2.split("-"); tok = +a; end = b != null ? +b : null; }
  if (!R.book || !S.lib.books.some(b => b.id === R.book)) R.book = books[0];
  const quiet = edit || R.quiet;                       // find the place without highlighting it (after an edit, or a reload)
  R.quiet = false;
  let index = tok == null && R.lastBook === R.book ? R.index : null;
  saveRead();
  if (renderRead.io) renderRead.io.disconnect();
  const cfg = edit ? { ...S.nar.seg, mode: "chapters" } : S.nar.seg;
  const layers = edit ? [] : Object.entries(R.layers).filter(([k, v]) => v).map(([k]) => k);
  const useTopics = !edit && R.layers.topics;
  let tmodels = [];
  if (useTopics) {
    try { tmodels = (await api("/api/topics/models")).models.filter(m => m.books.includes(R.book)); } catch (e) { tmodels = []; }
    if (!tmodels.some(m => m.id === R.topicModel)) { R.topicModel = tmodels.length ? tmodels[0].id : null; R.topicFocus = "all"; }
  }
  const ask = i => api("/api/read", withBooks({ book: R.book, seg: cfg, index: i, tok: i == null ? tok : null, end: i == null ? end : null, mark: !quiet, layers,
    topics: useTopics && R.topicModel ? { model: R.topicModel, focus: R.topicFocus } : null }));
  const first = await ask(index);
  const n = first.segments.length, segLabels = first.segments;
  R.lastBook = R.book; R.index = first.index;
  const TL = first.topic_layer && !first.topic_layer.error ? first.topic_layer : null;
  const tname = id => { const x = TL.topics.find(z => z.id === id); return x ? `${id + 1}. ${topicName(x)}` : `topic ${id + 1}`; };
  const Q = {}, PARA = new Map(), TDOCS = {};          // what the loaded chapters contain: quotes by number, paragraphs by id, topic documents
  const side = h("div", { class: "read-side" }, h("div", { class: "panel small muted" }, edit ? "" : "Click a name, a quote or a narrator label to see and correct it."));
  const text = h("div", { class: "read-text" + Object.entries(R.layers).map(([k, v]) => v && !edit ? " L-" + k : "").join("") + R.hidden.map(t => " hide-" + t).join("") + (edit ? " editing" : "") });
  const flow = h("div", { class: "flow" });
  let lo = first.index, hi = first.index, busy = false;
  const noun = first.mode === "chapters" ? "chapter" : "slice";

  /** Reload the page at the place being read, without highlighting it (after a correction that changes the text or its numbers). */
  const currentTok = () => (where.para ? where.para.tok : null);
  const reload = () => { R.quiet = true; const t = currentTok(); renderRead(main, encodeURIComponent(R.book), t == null ? null : String(t), edit); };
  const goTo = (pid, extra) => { R.quiet = true; const p = PARA.get(pid); renderRead(main, encodeURIComponent(R.book), p ? String(p.tok) : null, edit); };

  // ----- one paragraph, and one chapter -----
  /** The chapter (or slice) that starts at paragraph `pid`, if any: for the editor. */
  const headOf = pid => segLabels.findIndex(s => s.pid === pid);
  const editHead = (i, s) => {                          // heading of a chapter in the editor: its title, where it came from, and what can be done to it
    const label = h("span", { class: "grow" }, `${i + 1}. ${s.label}`);
    const box = h("div", { class: "seg-head edit" }, label, h("span", { class: "muted small" }, s.source === "yours" ? "started by you" : s.source === "auto" ? "found automatically" : ""), h("span", { class: "muted small" }, `${fmt(s.words)} words`));
    if (s.pid != null) {
      const act = (action, extra) => api("/api/narrative/chapters", { book: R.book, action, pid: s.pid, ...extra }).then(() => goTo(s.pid));
      box.append(h("button", { class: "btn small", onclick: () => {
          const inp = h("input", { type: "text", value: s.label, "aria-label": "Chapter title", style: { minWidth: "260px" } });
          const go = () => act("rename", { name: inp.value });
          inp.onkeydown = e => { if (e.key === "Enter") go(); if (e.key === "Escape") reload(); };
          label.replaceChildren(inp, h("button", { class: "btn small primary", onclick: go }, "OK"), h("button", { class: "btn small", onclick: reload }, "Cancel")); inp.focus(); } }, "Rename"),
        h("button", { class: "btn small", title: "The text of this chapter joins the one before it", onclick: () => act("remove") }, "Remove this chapter start"));
    }
    return box;
  };
  const paraDom = (p, r, seen) => {
    const el = markup(p.text);
    el.className = "para" + (p.exception ? " exc" : "") + (p.hit ? " hitp" : "");
    el.dataset.pid = p.pid;
    const wrap = h("div", { class: "pwrap", "data-pid": p.pid }, h("span", { class: "pno", title: `Paragraph ${p.no}` }, p.no));
    if (edit) {
      if (headOf(p.pid) < 0) wrap.append(h("button", { class: "cstart", title: "Start a new chapter at this paragraph", onclick: () => api("/api/narrative/chapters", { book: R.book, action: "add", pid: p.pid }).then(() => goTo(p.pid)) }, "＋ Start a chapter here"));
      wrap.append(el);
      return wrap;
    }
    if (TL) {
      el.querySelectorAll("mark.tw").forEach(m => { m.style.setProperty("--c", topicColor(+m.dataset.id)); m.title = "Topic " + tname(+m.dataset.id); });
      if (p.topic) {
        const col = topicColor(p.topic.dom);
        el.classList.add("tp"); el.style.setProperty("--c", col);
        if (TL.focus != null) el.style.background = `color-mix(in srgb, ${col} ${Math.round(32 * p.topic.w)}%, transparent)`;
      }
    }
    if (R.layers.quotes) el.querySelectorAll("mark.q").forEach(m => {                 // speaker labels at the start of each quote
      const q = r.quotes[m.dataset.id];
      if (!q || seen.has(m.dataset.id)) return;
      seen.add(m.dataset.id);
      m.prepend(h("span", { class: "ql" }, q.speaker || "?", q.addressees.length ? " → " + q.addressees.map(a => a.name).join(", ") : "", q.method && q.method.startsWith("yours") ? " ✓" : ""));
    });
    if (R.layers.narrators && p.narrator && (p.narrator !== r.prevNarr || p.exception)) wrap.append(h("button", { class: "pn" + (p.exception ? " exc" : ""), "data-pid": p.pid }, p.narrator));
    else if (R.layers.narrators && p.narrator) wrap.append(h("button", { class: "pn quiet", "data-pid": p.pid, title: p.narrator }, "¶"));
    if (p.narrator) r.prevNarr = p.narrator;
    if (TL && p.topic && p.topic.first) {
      const shares = TDOCS[p.topic.doc] || [];
      const parts = TL.focus != null ? [[TL.focus, p.topic.w]] : shares.slice(0, 3);
      wrap.append(h("button", { class: "tband", style: { "--c": topicColor(p.topic.dom) }, title: "Show every topic in this passage", onclick: () => topicPanel(p.topic.doc) },
        parts.map(([id, w], k) => h("span", { class: k ? "sec" : "main" }, `${tname(id)} ${fmt(100 * w, 0)}%`))));
    }
    wrap.append(el);
    return wrap;
  };
  const segmentEl = r => {
    Object.assign(Q, r.quotes);
    if (r.topic_layer && !r.topic_layer.error) Object.assign(TDOCS, r.topic_layer.docs);
    r.paragraphs.forEach(p => PARA.set(p.pid, p));
    const s = segLabels[r.index], seen = new Set();
    const head = edit ? editHead(r.index, s) : h("div", { class: "seg-head" }, h("span", { class: "grow" }, `${r.index + 1}. ${s.label}`), h("span", { class: "muted small" }, `${fmt(s.words)} words`));
    return h("section", { class: "chap", "data-index": r.index }, head, r.paragraphs.map(p => paraDom(p, r, seen)));
  };
  /** Load one more chapter (or slice) above or below what is shown. The scroll position stays with the text you were reading. */
  async function more(dir) {
    const i = dir < 0 ? lo - 1 : hi + 1;
    if (busy || i < 0 || i >= n) return;
    busy = true;
    try {
      const r = await ask(i);
      const el = segmentEl(r);
      if (dir < 0) { const h0 = document.documentElement.scrollHeight; flow.prepend(el); window.scrollBy(0, document.documentElement.scrollHeight - h0); lo = i; }
      else { flow.append(el); hi = i; }
      edges();
    } finally { busy = false; }
  }
  const topBtn = h("button", { class: "btn more", onclick: () => more(-1) }, `↑ Load the previous ${noun}`);
  const botBtn = h("button", { class: "btn more", onclick: () => more(1) }, `Load the next ${noun} ↓`);
  /** Show a "load more" button only where there is more to load, and look again in case the page is still too short to scroll. */
  function edges() {
    topBtn.hidden = lo <= 0; botBtn.hidden = hi >= n - 1;
    if (renderRead.io) for (const b of [topBtn, botBtn]) { renderRead.io.unobserve(b); renderRead.io.observe(b); }
  }
  flow.append(segmentEl(first));
  text.append(topBtn, flow, botBtn);
  if ("IntersectionObserver" in window) {
    renderRead.io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting && !e.target.hidden) more(e.target === topBtn ? -1 : 1); }), { rootMargin: "700px 0px" });
  }

  // ----- where you are, and jumping -----
  const where = { seg: first.index, para: null };
  const segSel = h("select", { "aria-label": "Jump to " + noun, onchange: e => jump(+e.target.value) }, segLabels.map((s, i) => h("option", { value: i, selected: i === first.index }, `${i + 1}. ${s.label}`)));
  const label = h("span", { class: "small muted", "aria-live": "polite" });
  const prev = h("button", { class: "btn small", onclick: () => jump(where.seg - 1) }, "← Previous");
  const next = h("button", { class: "btn small", onclick: () => jump(where.seg + 1) }, "Next →");
  /** Go to chapter i: scroll to it if it is loaded, else start the flow again from it. */
  async function jump(i) {
    if (i < 0 || i >= n) return;
    if (i < lo || i > hi) {
      if (i === hi + 1 || i === lo - 1) await more(i > hi ? 1 : -1);                 // the next one along: just add it
      if (i < lo || i > hi) { const r = await ask(i); flow.replaceChildren(segmentEl(r)); lo = hi = i; edges(); }
    }
    flow.querySelector(`.chap[data-index="${i}"]`).scrollIntoView({ block: "start" });
    updateWhere();
  }
  /** Work out which chapter and paragraph are at the top of the window, and show them. */
  function updateWhere() {
    const top = head.getBoundingClientRect().bottom + 4, segs = [...flow.children];       // just below the frozen menu
    const cur = segs.filter(s => s.getBoundingClientRect().top <= top).pop() || segs[0];
    if (!cur) return;
    const paras = [...cur.querySelectorAll(".pwrap")];
    const p = paras.find(x => x.getBoundingClientRect().bottom > top) || paras[paras.length - 1];
    where.seg = +cur.dataset.index; where.para = p ? PARA.get(+p.dataset.pid) : null;
    R.index = where.seg; segSel.value = where.seg;
    label.textContent = where.para ? `Paragraph ${where.para.no}` : "";
    prev.disabled = where.seg <= 0; next.disabled = where.seg >= n - 1;
  }
  let ticking = false;
  const onScroll = () => { if (ticking) return; ticking = true; requestAnimationFrame(() => { ticking = false; if (text.isConnected) updateWhere(); else window.removeEventListener("scroll", onScroll); }); };
  window.addEventListener("scroll", onScroll, { passive: true });

  // ----- the side panel -----
  function topicPanel(doc) {
    const rows = TDOCS[doc] || [], m = TL.model, base = "#/topics/" + encodeURIComponent(m.id);
    side.replaceChildren(h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Topics in this passage"),
      h("p", { class: "small muted" }, `From the model “${m.name}”, which reads the book in passages of similar length. Bars show each topic's share of the passage.`),
      rows.map(([id, w]) => h("div", { style: { margin: "6px 0" } }, h("div", { class: "row", style: { gap: "6px" } }, h("span", { class: "tdot", style: { background: topicColor(id) } }),
        h("a", { href: `${base}/${id}` }, tname(id)), h("span", { class: "grow" }), h("span", { class: "small" }, fmt(100 * w, 0) + "%")),
        h("div", { class: "tbar" }, h("i", { style: { width: 100 * w + "%", background: topicColor(id) } })))),
      h("p", { class: "small muted" }, "Highlighted words are each topic's most probable words, coloured by the topic they mostly belong to.")));
  }
  function quotePanel(qi) {
    side.replaceChildren(h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Quote"), quoteEditor(R.book, qi, reload)));
  }
  function entPanel(m) {
    const id = m.dataset.id, cls = m.className.split(" ");
    const type = cls.find(c => TYPES.includes(c)), counted = cls.includes("in");
    const text = m.textContent;
    const attributed = h("p", {}, h("span", { class: "muted small" }, "Looking up…"));
    side.replaceChildren(h("section", { class: "panel" }, h("div", {}, typeChip(type), " ", h("span", { class: "muted small" }, { PROP: "name", NOM: "description", PRON: "pronoun" }[cls.find(c => ["PROP", "NOM", "PRON"].includes(c))] || "")),
      h("h3", { style: { font: "500 20px var(--serif)", margin: "6px 0" } }, text),
      counted ? attributed : h("p", { class: "small muted" }, "Below the minimum number of mentions, so it has no profile."),
      h("p", { class: "small muted" }, "Mentions are corrected in the editor.")));
    if (!counted) return;
    units().then(U => {
      const name = (U.rows.find(r => r.id === id) || {}).name;
      if (name && name !== text) attributed.replaceChildren(h("span", { class: "muted small" }, "Attributed to "), h("a", { href: "#/entities/" + encodeURIComponent(id) }, name));
      else attributed.replaceChildren(h("a", { href: "#/entities/" + encodeURIComponent(id) }, "Open profile"));
    });
  }
  function narrPanel(pid) {
    const count = h("input", { type: "number", min: 0, value: 0, style: { width: "64px" } });
    const list = [...PARA.values()].sort((a, b) => a.pid - b.pid);
    const idx = list.findIndex(p => p.pid === pid), p = list[idx];
    const sel = h("select", {}, h("option", { value: "" }, `Book's narrator (${first.default_narrator_name})`), h("option", { value: "anon" }, "Unnamed narrator"));
    api("/api/annot/narrator_options?book=" + encodeURIComponent(R.book)).then(o => sel.append(...o.rows.map(x => h("option", { value: x.id }, x.name))));
    side.replaceChildren(h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Narrator"),
      h("p", { class: "small" }, "This paragraph: ", h("b", {}, p.narrator), p.exception ? " (set by you)" : " (the book's narrator)"),
      h("div", { class: "controls" }, h("label", {}, "Narrated by", sel), h("label", {}, "Also the next … paragraphs", count)),
      h("div", { class: "row" },
        h("button", { class: "btn primary", onclick: async () => {
          const pids = list.slice(idx, idx + 1 + Math.max(0, +count.value || 0)).map(x => x.pid);
          await api("/api/annot/paragraphs", { book: R.book, pids, narrator: sel.value || null }); S.units = null; toast("Saved."); reload(); } }, "Apply"),
        h("button", { class: "btn", title: "Assign every paragraph of this chapter, not just this one", onclick: async () => {
          await api("/api/annot/chapter_narrator", { book: R.book, pid, narrator: sel.value || null }); S.units = null; toast("Saved."); reload(); } }, "Apply to this whole chapter")),
      h("hr"), h("p", { class: "small" }, "The book's narrator: ", narratorSelect(R.book, reload))));
  }
  if (edit) {
    const yours = first.info.yours || 0;
    side.replaceChildren(h("section", { class: "panel" }, h("h3", { style: { marginTop: 0 } }, "Chapters"),
      h("p", { class: "small muted" }, first.info.mode === "chapters" ? `${plural(n, "chapter")}${first.info.edited ? `, ${yours} started by you` : ", found automatically"}.`
        : "No chapters were found automatically, so slices are shown. Start a chapter at any paragraph."),
      h("p", { class: "small" }, "Move the pointer over a paragraph and choose “Start a chapter here”. A chapter's title has buttons to rename it or remove its start; the text of a removed chapter joins the one before it. Your changes are used everywhere chapters are (Arcs and style, topics, the text view)."),
      h("div", { class: "row" }, h("button", { class: "btn small", disabled: !first.info.edited, onclick: async () => { if (confirm("Go back to the chapters found automatically for this book?")) { await api("/api/narrative/chapters", { book: R.book, action: "reset" }); reload(); } } }, "Back to the automatic chapters"),
        h("a", { class: "btn small", href: "#/read/" + encodeURIComponent(R.book) }, "Done")),
      h("h3", { class: "small muted" }, "In this book"),
      h("div", { class: "small" }, segLabels.map((s, i) => h("div", { class: "row", style: { justifyContent: "space-between", padding: "2px 0" } },
        h("a", { href: "#", onclick: e => { e.preventDefault(); jump(i); } }, `${i + 1}. ${s.label.length > 34 ? s.label.slice(0, 33) + "…" : s.label}`), h("span", { class: "muted" }, fmt(s.words)))))));
  }
  text.addEventListener("click", e => {
    if (edit) return;
    const q = e.target.closest("mark.q"), en = e.target.closest("mark.e"), pn = e.target.closest(".pn");
    if (pn) { narrPanel(+pn.dataset.pid); return; }
    if (en && !R.hidden.some(t => en.classList.contains(t)) && !(q && e.target.closest(".ql"))) { entPanel(en); if (!q) return; }
    if (q) quotePanel(+q.dataset.id);
  });

  // ----- the bars above the text -----
  const modelBar = useTopics ? h("div", { class: "controls", style: { margin: "8px 0 0" } },
    tmodels.length ? [h("label", {}, "Topic model", h("select", { onchange: e => { R.topicModel = e.target.value; R.topicFocus = "all"; saveRead(); reload(); } },
        tmodels.map(m => h("option", { value: m.id, selected: m.id === R.topicModel }, `${m.name} (${m.k} topics)`)))),
      TL ? h("label", {}, "Show", h("select", { onchange: e => { R.topicFocus = e.target.value; saveRead(); reload(); } }, h("option", { value: "all" }, "All topics"),
        TL.topics.slice().sort((a, b) => b.share - a.share).map(t => h("option", { value: t.id, selected: String(TL.focus) === String(t.id) }, `${t.id + 1}. ${topicName(t)}`)))) : null,
      first.topic_layer && first.topic_layer.error ? h("span", { class: "warn small" }, first.topic_layer.error) : null]
      : h("span", { class: "small muted" }, "No topic model includes this book. Fit one under ", h("a", { href: "#/topics" }, "Topics"), ".")) : null;
  const chapterNote = first.info.mode !== "chapters" && S.nar.seg.mode === "chapters" ? h("span", { class: "warn small" }, " No chapters were found in this book, so it is shown in slices.") : null;
  const head = h("div", { class: "read-head" });     // the menus that stay at the top: settings above, position below
  head.append(
    h("section", { class: "panel read-bar" },
      h("div", { class: "controls", style: { marginBottom: 0 } },
        h("label", {}, "Book", h("select", { onchange: e => { R.book = e.target.value; R.index = 0; saveRead(); location.hash = (edit ? "#/chapters/" : "#/read/") + encodeURIComponent(R.book); } },
          books.map(id => h("option", { value: id, selected: id === R.book }, bookTitle(id))))),
        edit ? h("div", { class: "fld" }, "Editing", h("b", {}, "chapters")) :
          h("div", { class: "fld" }, "Show", h("div", { class: "chips" }, [["entities", "Entities"], ["quotes", "Quotes and speakers"], ["narrators", "Narrators"], ["events", "Events"], ["supersenses", "Supersenses"], ["sentences", "Sentence numbers"], ["topics", "Topics"]].map(([k, l]) =>
            h("button", { class: "chip" + (R.layers[k] ? " on" : ""), onclick: () => { R.layers[k] = !R.layers[k]; saveRead(); reload(); } }, l)))),
        edit ? null : h("a", { class: "btn small", href: "#/chapters/" + encodeURIComponent(R.book), title: "Start, rename or remove chapters of this book" }, "Edit chapters")),
      modelBar,
      TL && TL.focus == null ? h("p", { class: "small", style: { margin: "6px 0 0", display: "flex", flexWrap: "wrap", gap: "2px 14px" } },
        TL.topics.slice().sort((a, b) => b.share - a.share).map(t => h("span", {}, h("span", { class: "tdot", style: { background: topicColor(t.id) } }), " ", `${t.id + 1}. ${shortName(t, 28)}`))) : null,
      h("p", { class: "small muted", style: { margin: "6px 0 0" } }, edit ? "Chapters found automatically, with your changes. " : "Chapters or slices follow the setting under Arcs and style. ", chapterNote,
        !edit && R.layers.entities ? h("span", { class: "legend", style: { display: "inline-flex" } }, TYPES.map(t => h("button", { class: R.hidden.includes(t) ? "off" : "", style: { "--c": TC[t] }, "aria-pressed": !R.hidden.includes(t),
          title: `${TYPE_NAMES[t]}: click to ${R.hidden.includes(t) ? "show" : "hide"} in the text`,
          onclick: e => { R.hidden = R.hidden.includes(t) ? R.hidden.filter(x => x !== t) : [...R.hidden, t]; text.classList.toggle("hide-" + t, R.hidden.includes(t)); e.currentTarget.classList.toggle("off", R.hidden.includes(t)); e.currentTarget.setAttribute("aria-pressed", !R.hidden.includes(t)); saveRead(); } }, t))) : null)),
    h("div", { class: "read-where" }, prev, next, h("label", { class: "row", style: { gap: "6px" } }, h("span", { class: "small muted" }, first.mode === "chapters" ? "Chapter" : "Slice"), segSel), label));
  main.replaceChildren(head, h("div", { class: "read" }, text, side));
  /** Tell the style sheet how tall the frozen menu is (it changes with the layers and topic controls), so that jumps and the side panel stay clear of it. */
  const sizeHead = () => document.documentElement.style.setProperty("--read-head", head.offsetHeight + "px");
  sizeHead();
  if ("ResizeObserver" in window) new ResizeObserver(sizeHead).observe(head);
  edges();
  updateWhere();
  const target = text.querySelector("mark.hit") || text.querySelector(".hitp") || (first.anchor != null && text.querySelector(`.pwrap[data-pid="${first.anchor}"]`));
  if (target) setTimeout(() => { target.scrollIntoView({ block: "center" }); updateWhere(); }, 50); else window.scrollTo(0, 0);
}
