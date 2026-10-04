"use strict";
/* ---------- Links ---------- */
/** The Entity Links page: suggested matches between books, linking by hand, and the entities already linked. */
async function renderLinks(main) {
  const sugBox = h("div", {}, loading("Looking for matches…"));
  const groupsBox = h("div");
  const narratorLinksBox = h("div");
  const manual = h("div");
  const autoBox = h("div", { class: "row", style: { marginBottom: "12px" } });
  const changed = () => { S.units = null; loadSug(); loadGroups(); loadNarratorLinks(); };
  autoBox.append(
    h("button", { class: "btn", onclick: async () => {
      const r = await api("/api/links/auto", {});
      toast(r.linked.length ? `Linked ${plural(r.linked.length, "entity", "entities")}: ${r.linked.map(x => x.name).join(", ")}.` : "Nothing new to link.");
      changed();
    } }, "Auto-link exact matches"),
    h("span", { class: "small muted" }, "Links entities that share an exact name, type and (for people) BookNLP's pronouns, across the whole library, not only a series. Undo any of these below like any other link."));
  /** One candidate of a suggested pair, as a card: its name and type, the book appearances that would be joined, and,
      for a person with several names, which forms are used. */
  const sideView = s => h("div", { class: "link-card" },
    h("div", {}, typeChip(s.type), " ", h("span", { class: "nm" }, s.name), s.linked ? h("span", { class: "muted small" }, " (linked group)") : null),
    h("div", { class: "appear" }, s.members.map(m => h("div", {}, `${m.title}: ${m.name} (${fmt(m.mentions)})`))),
    s.forms && s.forms.length ? h("div", { class: "small" }, "Names used: ", s.forms.join(", ")) : null);
  let shown = 40;
  async function loadSug() {
    const r = await api("/api/links/suggestions");
    const rows = r.rows.slice(0, shown);
    sugBox.className = "";
    sugBox.replaceChildren(
      h("p", { class: "small muted" }, r.total ? `${plural(r.total, "possible match", "possible matches")}, best first. Linking treats them as one entity in every view; you can undo it below.` : "No suggestions. They are only made between books of the same series (set under Library); link anything else by hand below."),
      ...rows.map(s => h("div", { class: "sug" }, sideView(s.a), sideView(s.b),
        h("div", { class: "acts" },
          h("button", { class: "btn primary small", onclick: async () => { await api("/api/links/link", { a: s.a.id, b: s.b.id }); toast(`Linked ${s.a.name}.`); changed(); } }, "Link"),
          h("button", { class: "btn small", onclick: async () => { await api("/api/links/reject", { a: s.a.id, b: s.b.id }); changed(); } }, "Not the same"),
          h("span", { class: "score", title: "How strong the evidence is, 0 to 1" }, `score ${s.score}`)),
        h("div", { class: "why" }, s.reasons.join(". ") + "."))),
      r.total > shown ? h("button", { class: "btn small", style: { marginTop: "8px" }, onclick: () => { shown += 60; loadSug(); } }, "Show more") : null);
  }
  // batch unlink: tick whole cards (not their individual appearances), then dissolve them all at once
  const picked = new Set();
  const toolbar = h("div", { class: "row", style: { marginBottom: "10px" } });
  const drawToolbar = () => toolbar.replaceChildren(
    h("span", { class: "small muted" }, plural(picked.size, "entity", "entities") + " selected"),
    h("button", { class: "btn small", disabled: !picked.size, onclick: async () => {
      if (!confirm(`Unlink ${plural(picked.size, "entity", "entities")}? Each one's book appearances become separate entities again.`)) return;
      for (const id of picked) await api("/api/links/unlink_all", { id });
      picked.clear();
      toast("Unlinked.");
      changed();
    } }, "Unlink selected"));
  /** One linked character as a card: its type, name and tags on the left; "Open profile" and a checkbox to pick it for
      batch unlinking on the right; every book appearance linked into it below, each with its own Unlink (a card with
      one appearance left dissolves on its own). */
  const personCard = p => {
    const card = h("div", { class: "person-card" + (picked.has(p.id) ? " picked" : "") },
      h("div", { class: "head" },
        h("div", { class: "row", style: { gap: "6px" } }, typeChip(p.type),
          h("input", { type: "text", value: p.name, title: "Name used in every view", onchange: async e => { await api("/api/name", { id: p.id, name: e.target.value }); S.units = null; toast("Renamed."); } })),
        h("div", { class: "row", style: { gap: "8px" } },
          h("a", { class: "small", href: "#/entities/" + encodeURIComponent(p.id) }, "Open profile"),
          h("input", { type: "checkbox", title: "Select " + p.name + " for batch unlinking", checked: picked.has(p.id),
            onchange: e => { e.target.checked ? picked.add(p.id) : picked.delete(p.id); card.classList.toggle("picked", e.target.checked); drawToolbar(); } }))),
      tagEditor(p.id, p.tags, () => {}),
      h("div", { class: "small muted" }, plural(p.members.length, "appearance")),
      h("div", {}, p.members.map(m => h("div", { class: "appear-row" },
        h("span", { class: m.missing ? "warn" : "" }, `${m.title}: ${m.name}`, h("span", { class: "muted" }, m.missing ? "" : ` (${fmt(m.mentions)})`)),
        h("button", { class: "btn small", onclick: async () => { await api("/api/links/unlink", { id: p.id, book: m.book, coref: m.coref }); changed(); } }, "Unlink")))));
    return card;
  };
  async function loadGroups() {
    const r = await api("/api/links/persons");
    const ids = new Set(r.rows.map(p => p.id));
    for (const id of [...picked]) if (!ids.has(id)) picked.delete(id);      // drop picks that no longer exist
    drawToolbar();
    groupsBox.replaceChildren(r.rows.length ? h("div", { class: "people-grid" }, r.rows.map(personCard))
      : h("p", { class: "muted small" }, "Nothing linked yet."));
  }
  /** One linked narrator as a card: the same shape as `personCard`, but for narrator roles (see `links.narrator_links`) —
      no book appearances or tags (a role isn't an entity), each member its own possibly-anonymous role, with its own
      Unlink, and "Unlink all" to dissolve the whole link. Kept out of the person batch-unlink toolbar: a different
      kind of link, changed through `/api/narrators/*` rather than `/api/links/*`. */
  const narratorLinkCard = nl => h("div", { class: "person-card" },
    h("div", { class: "head" },
      h("div", { class: "row", style: { gap: "6px" } }, typeChip("NARR"),
        h("input", { type: "text", value: nl.name, title: "Name used in every view", onchange: async e => { await api("/api/name", { id: nl.id, name: e.target.value }); S.units = null; toast("Renamed."); } })),
      h("div", { class: "row", style: { gap: "8px" } },
        h("a", { class: "small", href: "#/entities/" + encodeURIComponent(nl.id) }, "Open profile"),
        h("button", { class: "btn small", onclick: async () => {
          if (!confirm("Unlink every narrator here? Each becomes its own narrator again.")) return;
          await api("/api/narrators/unlink_all", { id: nl.id }); toast("Unlinked."); changed();
        } }, "Unlink all"))),
    h("div", { class: "small muted" }, plural(nl.members.length, "narrator")),
    h("div", {}, nl.members.map(m => h("div", { class: "appear-row" },
      h("span", {}, m.name, h("span", { class: "muted" }, ` (${booksLabel(m.books)})`)),
      h("button", { class: "btn small", onclick: async () => { await api("/api/narrators/unlink", { id: nl.id, role: m.id }); toast("Unlinked."); changed(); } }, "Unlink")))));
  async function loadNarratorLinks() {
    const r = await api("/api/links/narrator_links");
    narratorLinksBox.replaceChildren(
      h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Linked narrators"),
      r.rows.length ? h("div", { class: "people-grid" }, r.rows.map(narratorLinkCard))
        : h("p", { class: "muted small" }, "No narrators linked yet — link them from a narrator's own page."));
  }
  // link by hand
  const chosen = [null, null];
  /** A search box for one side of a link. The list of entities opens when the box is focused and narrows as you type. */
  const finder = i => {
    const inp = h("input", { type: "search", placeholder: "Click to list entities, or type a name…", style: { width: "260px" } });
    const list = h("div", { class: "sugg", hidden: true });
    const label = h("div", { class: "small muted" }, "Nothing chosen");
    let timer, latest = 0;
    const show = async () => {
      const mine = ++latest;
      const r = await api("/api/links/search?q=" + encodeURIComponent(inp.value.trim()));
      if (mine !== latest) return;                  // a newer keystroke is already on its way
      const other = chosen[1 - i];                  // the entity picked in the other box can't be linked to itself
      list.replaceChildren(...r.rows.filter(x => !other || x.id !== other.id).map(x => h("div", { onmousedown: e => { e.preventDefault(); chosen[i] = x; list.hidden = true; inp.value = x.name;
        label.replaceChildren(typeChip(x.type), " ", x.members.map(m => `${m.title}: ${m.name} (${m.mentions})`).join("; ")); } },
        typeChip(x.type), " ", x.name, h("span", { class: "muted small" }, ` ${x.members.map(m => m.title).join(", ")} · ${fmt(x.mentions)}`))));
      list.hidden = !list.children.length;
    };
    inp.addEventListener("focus", show);
    inp.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(show, 200); });
    inp.addEventListener("blur", () => setTimeout(() => (list.hidden = true), 150));
    return h("div", { style: { display: "grid", gap: "4px" } }, h("div", { class: "picker" }, inp, list), label);
  };
  manual.append(h("div", { class: "controls" }, finder(0), finder(1),
    h("button", { class: "btn primary", onclick: async () => {
      if (!chosen[0] || !chosen[1]) return toast("Choose two entities first.", true);
      await api("/api/links/link", { a: chosen[0].id, b: chosen[1].id }); toast("Linked."); changed();
    } }, "Link these")),
    h("p", { class: "small muted" }, "Click a box to list the entities of every book (most mentioned first) and type to narrow the list; it includes entities below the minimum. Linking two entities from the same book is allowed, for groups the editor didn't merge."));
  main.replaceChildren(
    h("section", { class: "panel" }, h("h2", {}, "Auto-link"), autoBox),
    h("section", { class: "panel" }, h("h2", {}, "Suggested links"), sugBox,
      note("How suggestions are found", "Only entities with at least one proper name and two mentions are considered, in different books of the same series (set under Library) and of the same type. Books without a series get no suggestions; link their entities by hand. Titles like Mr., Dr. or Father are set aside before names are compared.",
        "Evidence, strongest first: the same full name; the same single name; for people, the same last name; spellings at least 85% alike; a shared word. For people, BookNLP's pronouns add a little when they agree and count strongly against a match when they differ.",
        "“Not the same” is remembered, so the pair won't be suggested again.")),
    h("section", { class: "panel" }, h("h2", {}, "Link by hand"), manual),
    h("section", { class: "panel" }, h("h2", {}, "Linked entities"), toolbar, groupsBox, narratorLinksBox));
  loadSug(); loadGroups(); loadNarratorLinks();
}
