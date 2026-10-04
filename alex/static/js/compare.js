"use strict";
/* ---------- Compare ---------- */
/** The Compare page: two entities or tag groups side by side (overview, kinds of action, distinctive words). */
async function renderCompare(main) {
  await units();
  const out = h("div");
  const c = S.cmp;
  const run = async () => {
    if (!c.a || !c.b) { out.replaceChildren(h("div", { class: "panel empty" }, "Choose two entities or tag groups to compare.")); return; }
    out.replaceChildren(loading("Comparing…"));
    const r = await api("/api/compare", withBooks({ a: c.a, b: c.b, ...S.stat }));
    const A = r.a, B = r.b, names = [specLabel(c.a), specLabel(c.b)];
    const ov = [
      ["Entities", A.units, B.units, 0], ["Mentions", A.mentions, B.mentions, 0], ["Books", A.books, B.books, 0],
      ["Mentions per 1,000 words", A.per1k, B.per1k, 2],
      ...["PROP", "NOM", "PRON"].map(k => [`${PROP_NAMES[k]} (% of mentions)`, 100 * A.by_prop[k] / (A.mentions || 1), 100 * B.by_prop[k] / (B.mentions || 1), 1]),
      ...S.lib.relations.map(rl => [`${rl.label} per 100 mentions`, 100 * A.relations[rl.id].total / (A.mentions || 1), 100 * B.relations[rl.id].total / (B.mentions || 1), 1]),
    ].map(([k, a, b, d]) => ({ k, a, b, d }));
    const relBox = h("div");
    const drawRel = () => {
      const rel = c.rel, D = r.distinctive[rel];
      relBox.replaceChildren(
        h("div", { class: "subtabs" }, S.lib.relations.map(rl => h("button", { class: rl.id === rel ? "on" : "", onclick: () => { c.rel = rl.id; drawRel(); } }, rl.label))),
        h("div", { class: "cols2" }, [A, B].map((G, i) => h("div", {}, h("h3", { class: "small muted" }, `Most frequent for ${names[i]}`),
          table([{ k: "item", label: "Word" }, { k: "n", label: "Count", num: true, fmt: v => fmt(v) }, { k: "pct", label: "%", num: true, fmt: v => fmt(v, 1) }],
            G.relations[rel].rows, { limit: 15, csvName: `${names[i]} ${rel}`, onRow: row => openEvidence(`${row.item}`, names[i], { target: i ? c.b : c.a, kind: rel, key: row.item }) })))),
        h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Distinctive in either direction"),
        D.summary.c === 0 || D.summary.d === 0 ? h("p", { class: "warn small" }, "One side has nothing in this list" + (D.summary.d === 0 && c.b.kind !== "unit" ? " once the overlap with the other side is removed." : ".")) : null,
        table(statCols(D.summary, true, names), D.rows, { limit: 40, csvName: `${names[0]} vs ${names[1]} ${rel}`, rowClass: row => row.sig ? "" : "dim",
          onRow: row => openEvidence(row.item, row.lr > 0 ? names[0] : names[1], { target: row.lr > 0 ? c.a : c.b, kind: rel, key: row.item }),
          empty: "No significant differences at these settings." }),
        statNote(D.summary));
    };
    drawRel();
    // comparing two whole books: also split them into characters, so "the book as a whole" doesn't hide who's in it
    const splitBox = c.a.kind === "book" && c.b.kind === "book" ? h("div") : null;
    if (splitBox) {
      const g = await api("/api/compare/books", withBooks({ a: c.a.book, b: c.b.book, top: 30 }));
      splitBox.append(h("section", { class: "panel" }, h("h2", {}, "Split into characters"),
        table([{ k: "name", label: "Character", fmt: (v, row) => h("a", { href: "#/entities/" + encodeURIComponent(row.id) }, v), csv: v => v },
          { k: "a", label: names[0], num: true, fmt: v => fmt(v) }, { k: "b", label: names[1], num: true, fmt: v => fmt(v) }],
          g.rows, { limit: 30, csvName: `${names[0]} vs ${names[1]} characters` }),
        note("What this shows", "Every character counted in either book, most mentions in either book first, with their mentions in each. A character linked across the two books gets one row; unlinked, each book's own entity is its own row (0 in the other), as everywhere else in the app.")));
    }
    out.replaceChildren(
      h("section", { class: "panel" }, h("h2", {}, "Overview"),
        table([{ k: "k", label: "" }, { k: "a", label: names[0], num: true, fmt: (v, row) => fmt(v, row.d) }, { k: "b", label: names[1], num: true, fmt: (v, row) => fmt(v, row.d) }],
          ov, { csvName: `${names[0]} vs ${names[1]} overview`, limit: 50 }),
        note("About the overview", "When a group and an entity overlap (for example a tag group that includes the entity), the entity is removed from the group so that the two sides don't share any mentions.")),
      splitBox,
      h("section", { class: "panel" }, h("h2", {}, "Kinds of action"),
        chartBox(hbarChart([{ name: names[0], color: "#2e4a62", rows: A.agent_ss }, { name: names[1], color: "#c0843a", rows: B.agent_ss }], { pct: true, max: 15 }),
          slug(`${names[0]} vs ${names[1]} supersenses`)),
        note("What this shows", "The share of each side's actions (verbs they are the subject of) in each WordNet supersense, as a percentage of all its actions that have a supersense.")),
      h("section", { class: "panel" }, h("h2", {}, "Words"), statControls(run, { both: true }), relBox));
  };
  main.replaceChildren(
    h("section", { class: "panel" }, h("h2", {}, "Compare two entities or groups"),
      h("div", { class: "controls" },
        h("div", { class: "fld" }, "First", picker(c.a, v => { c.a = v; run(); }, { books: true, group: true, book: true, gender: true })),
        h("div", { class: "fld" }, "Second", picker(c.b, v => { c.b = v; run(); }, { books: true, group: true, book: true, gender: true }))),
      h("p", { class: "small muted", style: { margin: 0 } }, "Compare one entity, a group you pick entity by entity (search, then remove any with its ×; or start from a saved group), or a tag group: every entity with a tag, optionally of one type. Add tags on an entity's page. ",
        "Limit either side to some books to compare the same entity or group across books.")),
    out);
  run();
}
