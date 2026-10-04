"use strict";
/* ---------- Narrators: suggestions from "I" in the narration ---------- */
S.narrs = loadState("analyser.narrs", { max_gap: 3, min_evidence: 2 });
/** The Narrators page: who narrates each book, suggested from the "I" in the narration, and stretches told by someone else. */
async function renderNarrators(main) {
  const o = S.narrs, save = () => saveState("analyser.narrs", o);
  const out = h("div", {}, loading("Looking at the narration…"));
  const reload = () => { S.units = null; load(); };
  const load = async () => {
    const r = await api("/api/narrators/suggestions", withBooks({ max_gap: o.max_gap, min_evidence: o.min_evidence }));
    out.className = "";
    out.replaceChildren(...r.books.map(bk => bookPanel(bk)), note("How suggestions are found", r.note));
  };
  const whoIsThis = (uid, label) => h("div", { class: "row", style: { gap: "6px" } }, h("span", { class: "small muted" }, "Who is this?"),
    picker(null, async v => {
      if (v.kind !== "unit" || v.id === uid) return;
      await api("/api/links/link", { a: v.id, b: uid, name: v.name });
      toast(`Linked ${label} to ${v.name}.`); reload();
    }, { unitOnly: true }));
  function bookPanel(bk) {
    const box = h("section", { class: "panel" }, h("h2", {}, bk.title));
    if (!bk.first_person) {
      box.append(h("p", { class: "small muted", style: { margin: "0 0 8px" } }, "No “I” in the narration: probably told in the third person. The narration belongs to an unnamed narrator unless you choose one."),
        h("div", { class: "row small" }, "Narrator: ", narratorSelect(bk.book, reload)));
      return box;
    }
    const cur = bk.current, sug = bk.suggested;
    const agree = cur && sug && cur.id === sug.id;
    box.append(
      h("div", { class: "row small", style: { marginBottom: "8px" } }, h("b", {}, "Narrator: "), narratorSelect(bk.book, reload),
        !cur ? h("span", { class: "muted" }, " Not chosen yet.") : agree ? h("span", { class: "muted" }, " ✓ matches the suggestion.") : null),
      cur && sug && !agree && sug.share > 50 ? h("p", { class: "warn small" }, `Most “I” in the narration (${fmt(sug.share, 0)}%) belongs to ${sug.name}, not ${cur.name}. ` +
        (sug.unnamed ? "If that group is the narrator, say who it is below." : "Check which is right.")) : null,
      h("h3", { class: "small muted" }, `Who the “I” in the narration belongs to (${plural(bk.first_person, "mention")})`),
      table([{ k: "name", label: "Character" }, { k: "n", label: "“I” mentions", num: true, fmt: v => fmt(v) }, { k: "share", label: "%", num: true, fmt: v => fmt(v, 1) },
        { k: "id", label: "", fmt: (v, row) => h("div", { class: "row", style: { gap: "6px", justifyContent: "flex-end" } },
          row.unnamed ? whoIsThis(v, row.name) : null,
          cur && cur.id === v ? h("span", { class: "muted small" }, "the book's narrator") :
            h("button", { class: "btn small", onclick: async e => { e.stopPropagation(); await api("/api/annot/narrator", { book: bk.book, narrator: v }); toast("Narrator saved."); reload(); } }, "Make the book's narrator")), csv: () => "" }],
        bk.candidates, { csv: false, limit: 6 }));
    const open = bk.runs.filter(x => !x.done), done = bk.runs.filter(x => x.done);
    box.append(h("h3", { class: "small muted", style: { marginTop: "14px" } },
      `Paragraphs told by someone else: ${plural(open.length, "suggestion")}` + (done.length ? `, ${fmt(done.length)} accepted` : "") + (cur ? "" : ` (compared with the suggested narrator, ${bk.narrator_name})`)));
    if (!open.length) box.append(h("p", { class: "small muted", style: { margin: 0 } }, bk.runs.length ? "All accepted." : "None: every paragraph with an “I” points to the book's narrator."));
    open.forEach(x => box.append(h("div", { class: "sug", style: { gridTemplateColumns: "1fr auto" } },
      h("div", {},
        h("div", {}, h("span", { class: "nm", style: { font: "16px var(--serif)" } }, x.name),
          h("span", { class: "muted small" }, ` · ${plural(x.paragraphs, "paragraph")}, ${fmt(x.from, 1)}–${fmt(x.to, 1)}% through, ${fmt(x.words)} words of narration`)),
        h("div", { class: "small muted" }, `Evidence: ${x.evidence} “I” for ${x.name}` + (x.against ? `, ${x.against} for others` : "") + ` · strength ${fmt(x.strength, 2)}`),
        x.samples.map(sm => h("div", { class: "ev", style: { padding: "4px 0", borderBottom: 0 } }, markup(sm.text))),
        x.unnamed ? whoIsThis(x.unit, x.name) : null),
      h("div", { class: "acts" },
        h("button", { class: "btn primary small", onclick: async () => { await api("/api/annot/paragraphs", { book: bk.book, pids: x.pids, narrator: x.unit }); toast(`${plural(x.paragraphs, "paragraph")} given to ${x.name}.`); reload(); } }, "Accept"),
        h("button", { class: "btn small", onclick: async () => { await api("/api/narrators/reject", { book: bk.book, key: x.key }); reload(); } }, "Not right"),
        h("a", { class: "small", href: `#/read/${encodeURIComponent(bk.book)}/${x.tok}` }, "Open in the text")))));
    if (done.length) box.append(h("details", { class: "note" }, h("summary", {}, `Accepted (${done.length})`),
      done.map(x => h("p", {}, `${x.name}: ${plural(x.paragraphs, "paragraph")}, ${fmt(x.from, 1)}–${fmt(x.to, 1)}% through. `,
        h("a", { href: `#/read/${encodeURIComponent(bk.book)}/${x.tok}` }, "Open in the text"), " · ",
        h("a", { href: "#", onclick: async e => { e.preventDefault(); await api("/api/annot/paragraphs", { book: bk.book, pids: x.pids, narrator: null }); reload(); } }, "Undo")))));
    return box;
  }
  const num = (k, label, min, max, title) => h("label", { title }, label, h("input", { type: "number", min, max, value: o[k], onchange: e => { o[k] = Math.min(max, Math.max(min, +e.target.value || min)); save(); load(); } }));
  main.replaceChildren(
    h("section", { class: "panel" }, h("h2", {}, "Narrators"),
      h("p", { class: "small muted", style: { marginTop: 0 } }, "Suggestions from the “I” in each book's narration (outside quotes): who narrates the book, and stretches told by someone else. Accept, reject or check each in the text. You can also set narrators by hand in the text view."),
      h("div", { class: "controls", style: { marginBottom: 0 } },
        num("max_gap", "Paragraphs without “I” allowed inside a run", 0, 50, "A run continues across up to this many paragraphs in a row that have no “I”"),
        num("min_evidence", "Minimum “I” per suggestion", 1, 100))),
    out);
  load();
}
