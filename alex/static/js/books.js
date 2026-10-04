"use strict";
/* ---------- Library and settings ---------- */
/** Which collection the Library page shows ("all", "none" = in no collection, or a collection id) and how its table is grouped. */
S.libView = loadState("analyser.libview", { coll: "all", group: "none" });
const saveLibView = () => saveState("analyser.libview", S.libView);

/** The Library page: your library (collections, search and the book table), minimum mentions, and the source folders. */
async function renderBooks(main) {
  await loadLib();
  const L = S.lib, cur = new Set(selected()), V = S.libView;
  let query = "";
  const collById = () => Object.fromEntries(L.collections.map(c => [c.id, c]));
  if (!["all", "none"].includes(V.coll) && !collById()[V.coll]) V.coll = "all";        // the collection was deleted
  const saveBook = async (id, patch) => {
    await api("/api/books/" + encodeURIComponent(id), patch);
    Object.assign(L.books.find(b => b.id === id), patch);
    toast("Saved.");
  };
  const inp = (b, k, w) => h("input", { type: "text", value: k === "tags" ? (b.tags || []).join(", ") : (b[k] ?? ""), style: { width: w },
    onchange: e => saveBook(b.id, { [k]: k === "tags" ? e.target.value.split(",").map(t => t.trim()).filter(Boolean) : e.target.value }) });

  // ----- collections: a tree on the left; what it holds decides which books the table shows -----
  const treeBox = h("div", { class: "ctree" }), actionBox = h("div", { class: "row", style: { flexWrap: "wrap", marginTop: "8px" } });
  const pathOf = c => c.parent ? pathOf(collById()[c.parent]) + " / " + c.name : c.name;
  const depthOf = c => c.parent ? 1 + depthOf(collById()[c.parent]) : 0;
  /** Send a change to the collections, keep the server's list, and redraw. Returns the reply. */
  const changeColl = async (path, body) => {
    const r = await api(path, body);
    L.collections = r.collections;
    if (!["all", "none"].includes(V.coll) && !collById()[V.coll]) V.coll = "all";
    drawTree(); drawTable();
    return r;
  };
  const anyCollection = () => new Set(L.collections.flatMap(c => c.books));
  /** The books the table shows: those in the open collection (and the collections inside it) that match the search. */
  const shownBooks = () => {
    const open = V.coll === "all" || V.coll === "none" ? null : new Set(collById()[V.coll].deep), unfiled = V.coll === "none" ? anyCollection() : null;
    return L.books.filter(b => bookMatchesQuery(b, query) && (open ? open.has(b.id) : unfiled ? !unfiled.has(b.id) : true));
  };
  function drawTree() {
    const node = (id, label, n, depth, title) => h("div", { class: "node" + (V.coll === id ? " on" : ""), role: "button", tabindex: 0, title, style: { paddingLeft: 8 + 14 * depth + "px" },
      onclick: () => { V.coll = id; saveLibView(); drawTree(); drawTable(); },
      onkeydown: e => { if (e.key === "Enter") { V.coll = id; saveLibView(); drawTree(); drawTable(); } } }, h("span", {}, label), h("span", { class: "n" }, fmt(n)));
    treeBox.replaceChildren(node("all", "All books", L.books.length, 0), ...L.collections.map(c => node(c.id, c.name, c.deep.length, 1 + depthOf(c), pathOf(c))),
      node("none", "In no collection", L.books.length - anyCollection().size, 0));
    drawActions();
  }
  /** The buttons under the tree: make a collection, and (for the open one) rename, move, delete. Naming asks in place. */
  function drawActions() {
    const c = collById()[V.coll];
    const ask = (label, initial, ok) => {
      const box = h("input", { type: "text", value: initial, placeholder: "Name", "aria-label": label });
      const go = () => ok(box.value).then(drawActions, () => {});
      box.onkeydown = e => { if (e.key === "Enter") go(); if (e.key === "Escape") drawActions(); };
      actionBox.replaceChildren(box, h("button", { class: "btn small primary", onclick: go }, "OK"), h("button", { class: "btn small", onclick: drawActions }, "Cancel"));
      box.focus();
    };
    /** Ids of a collection and the collections nested in it (the ones it can't be moved into). */
    const descendantIds = id => new Set([id, ...L.collections.filter(x => x.parent === id).flatMap(x => [...descendantIds(x.id)])]);
    const moveTo = () => {
      const blocked = descendantIds(c.id);
      const pick = h("select", { "aria-label": "Move to" }, h("option", { value: "" }, "Top level"),
        L.collections.filter(x => !blocked.has(x.id)).map(x => h("option", { value: x.id, selected: x.id === c.parent }, "— ".repeat(depthOf(x)) + x.name)));
      actionBox.replaceChildren(pick, h("button", { class: "btn small primary", onclick: () => changeColl("/api/collections/" + c.id, { parent: pick.value || null }).then(drawActions, () => {}) }, "Move"),
        h("button", { class: "btn small", onclick: drawActions }, "Cancel"));
    };
    actionBox.replaceChildren(
      h("button", { class: "btn small", onclick: () => ask("New collection", "", name => changeColl("/api/collections", { name, parent: c ? c.id : null })) },
        c ? "New sub-collection" : "New collection"),
      c ? [h("button", { class: "btn small", onclick: () => ask("Rename", c.name, name => changeColl("/api/collections/" + c.id, { name })) }, "Rename"),
        h("button", { class: "btn small", onclick: moveTo }, "Move…"),
        h("button", { class: "btn small", onclick: () => { if (confirm(`Delete the collection “${c.name}”? Its books stay in the library.`)) changeColl("/api/collections/delete", { id: c.id }); } }, "Delete")] : null);
  }

  // ----- the book table -----
  const tableBox = h("div"), toolbar = h("div", { class: "controls" });
  /** Download the selected books and your work on them as one .zip (the server builds it, see core/export.py). */
  const exportZip = async button => {
    const ids = selected();
    button.disabled = true;
    try {
      const r = await api("/api/export", { books: ids }, true);
      download((/filename="(.+?)"/.exec(r.headers.get("content-disposition") || "") || [])[1] || "analyser-export.zip", await r.blob());
      toast(`Exported ${plural(ids.length, "book")}.`);
    } finally { button.disabled = false; }
  };
  const downloadText = async b => download(b.id + ".txt", await (await api("/api/books/" + encodeURIComponent(b.id) + "/text", undefined, true)).blob());
  const collChips = b => {
    const mine = L.collections.filter(c => c.books.includes(b.id)), others = L.collections.filter(c => !c.books.includes(b.id));
    return h("div", { class: "coll-cell" }, mine.map(c => h("span", { class: "tag", title: pathOf(c) }, c.name,
      h("button", { title: "Take out of " + c.name, onclick: () => changeColl("/api/collections/" + c.id, { remove: [b.id] }) }, "×"))),
      others.length ? h("select", { "aria-label": "Add " + b.title + " to a collection", onchange: e => { if (e.target.value) changeColl("/api/collections/" + e.target.value, { add: [b.id] }); } },
        h("option", { value: "" }, "＋"), others.map(c => h("option", { value: c.id }, pathOf(c)))) : null);
  };
  const bookRow = b => h("tr", {},
    h("td", {}, h("input", { type: "checkbox", checked: cur.has(b.id), "aria-label": "Use " + b.title,
      onchange: e => { e.target.checked ? cur.add(b.id) : cur.delete(b.id); if (!cur.size) { e.target.checked = true; cur.add(b.id); return toast("Keep at least one book.", true); } setSel(L.books.map(x => x.id).filter(x => cur.has(x))); } })),
    h("td", {}, inp(b, "title", "220px"), h("div", { class: "small muted" }, b.id),
      h("div", { class: "small" }, h("a", { href: "#/entities/" + encodeURIComponent("book:" + b.id) }, "Overview"))),
    h("td", {}, inp(b, "author", "150px")), h("td", {}, inp(b, "year", "64px")), h("td", {}, inp(b, "series", "130px")), h("td", {}, inp(b, "tags", "150px")),
    h("td", {}, collChips(b)),
    h("td", {}, narratorSelect(b.id)),
    h("td", {}, h("select", { onchange: e => saveBook(b.id, { pinned: e.target.value || null }).then(() => { S.units = null; renderBooks(main); }) },
      h("option", { value: "" }, `Newest (${b.versions[0].stamp})`),
      b.versions.map(v => h("option", { value: v.folder, selected: b.pinned === v.folder }, `${v.stamp}`))),
      h("div", { class: "small muted", title: b.folder }, b.folder.split(/[\\/]/).pop()),
      b.has_text ? h("button", { class: "btn small", style: { marginTop: "4px" }, title: "Download the original text this export was made from",
        onclick: () => downloadText(b) }, "Original text") : null),
    h("td", { class: "num" }, b.error ? h("span", { class: "warn" }, b.error) : fmt(b.words)),
    h("td", { class: "num" }, fmt(b.groups)), h("td", { class: "num" }, fmt(b.quotes)));
  const HEAD = ["Use", "Title", "Author", "Year", "Series", "Tags", "Collections", "Narrator", "Export used", "Words", "Entities", "Quotes"];
  /** Redraw the table (rows grouped by series or author if chosen) and the "Analyse the books shown" button. */
  function drawTable() {
    const books = shownBooks(), key = { series: b => b.series || "(no series)", author: b => b.author || "(no author)" }[V.group];
    const groups = key ? [...new Set(books.map(key))].sort((x, y) => x.localeCompare(y)) : [null];
    const rows = groups.flatMap(g => {
      const inGroup = key ? books.filter(b => key(b) === g) : books;
      return [key ? h("tr", { class: "grp" }, h("td", { colspan: HEAD.length }, g, h("span", { class: "n" }, fmt(inGroup.length)))) : null, ...inGroup.map(bookRow)];
    });
    tableBox.replaceChildren(books.length ? h("div", { class: "tbl-wrap" }, h("table", { class: "t2 books" },
      h("thead", {}, h("tr", {}, HEAD.map(x => h("th", {}, x)))), h("tbody", {}, rows)))
      : h("div", { class: "empty" }, !L.books.length ? "No books found yet. Add a folder of BookNLP output under “Where to find books” (a folder with a .tokens and an .entities file for each book)."
        : V.coll !== "all" && V.coll !== "none" && !query ? "No books in this collection yet. Open “All books” and add some with the ＋ in the Collections column, or search and use “Add the books shown to…”."
        : "No books match."));
    // what can be done with the books listed: analyse just those, or file them all in a collection
    const filtered = books.length < L.books.length, targets = L.collections.filter(c => books.some(b => !c.books.includes(b.id)));
    useBox.replaceChildren(
      filtered ? h("button", { class: "btn small", title: "Set the books to analyse (top right) to the books listed here", disabled: !books.length,
        onclick: () => { const ids = books.map(b => b.id); cur.clear(); ids.forEach(i => cur.add(i)); setSel(ids); toast(`Analysing ${plural(ids.length, "book")}.`); drawTable(); } },
        `Analyse the ${plural(books.length, "book")} shown`) : null,
      books.length && targets.length ? h("select", { "aria-label": "Add the books shown to a collection", onchange: e => { if (e.target.value) changeColl("/api/collections/" + e.target.value, { add: books.map(b => b.id) }); } },
        h("option", { value: "" }, `Add the ${plural(books.length, "book")} shown to…`), targets.map(c => h("option", { value: c.id }, pathOf(c)))) : null);
  }
  const groupBox = h("div", { class: "fld" }), useBox = h("div", { class: "row" });
  const drawGroup = () => groupBox.replaceChildren("Group by", seg([["none", "Nothing"], ["series", "Series"], ["author", "Author"]], V.group, v => { V.group = v; saveLibView(); drawGroup(); drawTable(); }));
  let searchTimer;
  toolbar.append(h("label", { style: { flex: "1 1 240px" } }, "Search", h("input", { type: "search", placeholder: "Title, author, series, tag, year or id",
    oninput: e => { query = e.target.value; clearTimeout(searchTimer); searchTimer = setTimeout(drawTable, 150); } })), groupBox, useBox,
    h("button", { class: "btn small", title: "Download the books ticked under Use (and the ones chosen at the top right) with your links, groups, collections and corrections as one .zip",
      onclick: e => exportZip(e.currentTarget) }, "Export selected books (.zip)"));
  drawGroup(); drawTree(); drawTable();
  const problems = [...L.problems, ...L.books.flatMap(b => (b.problems || []).map(p => `${b.title}: ${p}`))];
  // sources
  const srcBox = h("div", {}, L.sources.map((s, i) => h("div", { class: "row", style: { padding: "3px 0" } }, h("code", { class: "grow" }, s),
    h("button", { class: "btn small", onclick: async () => { S.lib = await api("/api/settings", { sources: L.sources.filter((_, j) => j !== i) }); S.units = null; renderBooks(main); } }, "Remove"))));
  const newSrc = h("input", { type: "text", placeholder: "/path/to/folder/with/books", style: { width: "380px" } });
  // settings
  const st = L.settings;
  const saveSettings = async patch => { S.lib = await api("/api/settings", patch); S.units = null; toast("Saved."); renderBooks(main); };
  const workspaces = await workspacePanel();
  // where books come from; while there are none it goes first, since it is the only thing to do
  const findPanel = h("section", { class: "panel" }, h("h2", {}, "Where to find books"),
    srcBox,
    h("div", { class: "row", style: { marginTop: "8px" } }, newSrc,
      h("button", { class: "btn", onclick: async () => { if (!newSrc.value.trim()) return; S.lib = await api("/api/settings", { sources: [...L.sources, newSrc.value.trim()] }); S.units = null; renderBooks(main); } }, "Add folder")),
    note("What counts as a folder of books", "A folder that holds BookNLP files directly (houn.tokens, houn.entities and so on), or a folder of exports with one subfolder per export (as the companion editor writes them). Each book needs at least .tokens and .entities; .quotes, .supersense and .book are used when present."));
  main.replaceChildren(
    L.books.length ? null : findPanel,
    h("section", { class: "panel" }, h("h2", {}, "Library"), toolbar,
      h("div", { class: "lib" }, h("div", {}, treeBox, actionBox), tableBox),
      problems.length ? h("div", { class: "warn small", style: { marginTop: "8px" } }, problems.map(p => h("div", {}, p))) : null,
      note("About this table", "Changes save as soon as you leave a field. Tags are separated by commas. The book selection at the top right uses these details.",
        "Collections work like folders that nest, except that a book can be in several at once: make one on the left, then add books to it with the ＋ in the Collections column. Click a collection to list its books (and those of the collections inside it). Deleting a collection never deletes books. Search looks in title, author, series, tags, year and id; “Analyse the books shown” sets the book selection to whatever the table lists.",
        "If you export from the companion editor, each export goes in its own dated folder. The newest is used unless you choose an earlier one under Export used. When you export again, the analyser picks it up next time you return to this window.")),
    h("section", { class: "panel" }, h("h2", {}, "Plural groups"),
      h("p", { class: "small muted", style: { marginTop: 0 } }, "Whether an entity's figures include the mentions of the plural groups it belongs to (“Holmes and Watson”, “they”). Declare plural groups on an entity's page, or accept the suggestions on the Entities page."),
      h("div", { class: "row" }, h("span", { class: "small" }, "By default count"),
        seg([["own", "Own mentions only"], ["all", "Include plural-group mentions"]], st.plural ? "all" : "own", v => saveSettings({ plural_default: v === "all" }))),
      note("What this means",
        "A plural group is an entity whose mentions mean several entities together: “Holmes and Watson”, and the “they” and “we” BookNLP linked to it. It is always an entity of its own.",
        "Own mentions only: each entity's figures come from its own mentions and quotes. Include plural-group mentions: a plural group's mentions, what it does, who it appears with, its quotes and the quotes addressed to it count for each of its members too; a member named inside a plural mention (“Holmes and Watson walked”) counts once, through its own mention.",
        "Every page that depends on it has its own checkbox (above the page, or in the “Plural group” box on an entity's page) to try the other way. A page keeps its choice until you set it back or choose other books.")),
    h("section", { class: "panel" }, h("h2", {}, "Minimum mentions"),
      h("p", { class: "small muted", style: { marginTop: 0 } }, "Entities with fewer mentions are left out of lists, profiles, comparisons and networks. BookNLP's .book uses 2 for people."),
      h("div", { class: "settings-grid" }, TYPES.map(t => h("label", { class: "row", style: { gap: "6px" } }, typeChip(t),
        h("input", { type: "number", min: 1, value: st.min[t], "aria-label": "Minimum for " + TYPE_NAMES[t], onchange: e => saveSettings({ min: { [t]: Math.max(1, +e.target.value || 1) } }) })))),
      h("div", { class: "row", style: { marginTop: "12px" } }, h("span", { class: "small" }, "Count mentions"),
        seg([["per_book", "In each book separately"], ["combined", "Across the selected books combined"]], st.count_mode, v => saveSettings({ count_mode: v }))),
      note("What the two ways of counting mean",
        "In each book separately: an entity counts in a book only if it reaches the minimum in that book. For a linked entity, books where it falls short are left out of its figures.",
        "Across the selected books combined: a linked entity counts if its mentions in all the selected books together reach the minimum, and then every book it appears in is included. Unlinked entities are the same either way.")),
    L.books.length ? findPanel : null,
    workspaces);
}
