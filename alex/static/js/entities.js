"use strict";
/* ---------- Entities ---------- */
/** The Entities page: a filterable list on the left and, for the chosen entity, narrator or group, its profile on the right.
    `uid` is an entity id, a narrator role id (`nar:…`), "group" (the entities ticked in the list) or `g:<n>` (a saved group).
    "Select several" adds a checkbox to every row; ticked entities can be analysed together as a group (compound figures, one profile). */
async function renderEntities(main, uid) {
  const U = await units();
  const savedId = uid && uid.startsWith("g:") ? uid.slice(2) : null;
  const isGroup = uid === "group" || savedId !== null, isNarr = !!uid && (uid.startsWith("nar:") || uid.startsWith("nl:"));
  const isGender = !!uid && uid.startsWith("gender:"), isBook = !!uid && uid.startsWith("book:");
  if (isGroup) S.entMulti = true;
  if (isNarr) S.entType = "NARR";
  if (isGender) S.entType = "GENDER";
  let dirty = false;                    // a saved group whose ticked entities you have since changed
  const listItems = h("div", { class: "items" }), bar = h("div", { class: "multi-bar" });
  const counts = { ...U.type_counts, NARR: U.narrators.length, GENDER: U.genders.length };
  const total = Object.values(U.type_counts).reduce((a, b) => a + b, 0);
  const genderRows = () => U.genders.map(g => ({ id: "gender:" + g.pron, name: genderLabel(g.pron), type: "GENDER", mentions: g.mentions, entities: g.entities, books: [], tags: [] }));
  const ticking = () => S.entMulti && S.entType !== "NARR" && S.entType !== "GENDER";   // narrator roles and gender pools can't be grouped
  /** The rows that match the type chip and the filter box, in the chosen order. */
  const matching = () => {
    const q = S.entQuery.toLowerCase().trim();
    const rows = (S.entType === "NARR" ? U.narrators : S.entType === "GENDER" ? genderRows() : U.rows.filter(r => S.entType === "ALL" || r.type === S.entType))
      .filter(r => !q || r.name.toLowerCase().includes(q) || r.tags.some(t => t.toLowerCase().includes(q)));
    const rev = S.entSortRev ? -1 : 1;
    if (S.entSort === "name") rows.sort((a, b) => rev * a.name.localeCompare(b.name));
    else if (S.entSort === "books") rows.sort((a, b) => rev * ((b.books.length - a.books.length) || (b.mentions - a.mentions)));
    else rows.sort((a, b) => rev * (b.mentions - a.mentions));
    return rows;
  };
  const rowMeta = r => r.type === "NARR" ? `narrating · ${plural(r.paragraphs, "paragraph")} · ${r.books.length > 1 ? plural(r.books.length, "book") : bookTitle(r.books[0])}`
    : r.type === "GENDER" ? plural(r.entities, "entity", "entities")
    : (r.linked ? `linked · ${plural(r.books.length, "book")}` : bookTitle(r.books[0])) + (r.tags.length ? " · " + r.tags.join(", ") : "");
  const open = r => (location.hash = "#/entities/" + encodeURIComponent(r.id));
  /** Tick or untick one entity; a group page follows the ticks. */
  const toggle = id => { const s = new Set(S.entSel); s.has(id) ? s.delete(id) : s.add(id); ticked([...s]); };
  const ticked = ids => { S.entSel = ids; if (savedId) dirty = true; drawList(); drawBar(); if (isGroup) refreshGroup(); };
  const drawList = () => {
    const rows = matching(), shown = rows.slice(0, S.entLimit), picked = new Set(S.entSel), tick = ticking();
    listItems.replaceChildren(
      ...shown.map(r => h("div", { class: "ent-item" + (tick ? " multi" : "") + (tick ? (picked.has(r.id) ? " picked" : "") : (r.id === uid ? " on" : "")), role: "link", tabindex: 0,
        onclick: () => (tick ? toggle(r.id) : open(r)), onkeydown: e => { if (e.key === "Enter") (tick ? toggle(r.id) : open(r)); } },
        tick ? h("input", { type: "checkbox", checked: picked.has(r.id), tabindex: -1, "aria-label": "Select " + r.name, onclick: e => e.stopPropagation(), onchange: () => toggle(r.id) })
          : h("span", { class: "sw", style: { background: TC[r.type] } }),
        h("div", { style: { minWidth: 0 } }, h("div", { class: "nm" }, r.name), h("div", { class: "meta" }, rowMeta(r))),
        h("span", { class: "cnt", title: r.type === "NARR" ? "words narrated" : "mentions" }, fmt(r.mentions)))),
      rows.length > shown.length ? h("div", { style: { padding: "8px 12px" } }, h("button", { class: "btn small", onclick: () => { S.entLimit += 500; drawList(); } }, `Show more (${fmt(rows.length - shown.length)} left)`)) : null,
      !rows.length ? h("div", { class: "empty" }, S.entQuery.trim() ? "No names match." : S.entType === "NARR" ? "No narration in the selected books." : S.entType === "GENDER" ? "No people in the selected books." : "None in the selected books at this minimum.") : null);
  };
  /** The "select several" switch and, when it is on, what can be done with the ticks: select what is listed or a tag, clear, analyse together. */
  const drawBar = () => {
    const tick = ticking(), n = S.entSel.length;
    const byTag = tag => U.rows.filter(r => (S.entType === "ALL" || r.type === S.entType) && r.tags.includes(tag)).map(r => r.id);
    bar.replaceChildren(
      S.entType === "NARR" || S.entType === "GENDER" ? null : h("label", { class: "inline" }, h("input", { type: "checkbox", checked: S.entMulti,
        onchange: e => { S.entMulti = e.target.checked; if (!S.entMulti) { S.entSel = []; if (isGroup) { location.hash = "#/entities"; return; } } drawList(); drawBar(); } }), "Select several"),
      S.lib.groups.length ? h("select", { "aria-label": "Open a saved group", onchange: e => { if (e.target.value) location.hash = "#/entities/g:" + e.target.value; } },
        h("option", { value: "" }, "Saved groups…"), S.lib.groups.map(g => h("option", { value: g.id, selected: g.id === savedId }, g.name))) : null,
      tick ? h("div", { class: "row", style: { flexWrap: "wrap" } },
        h("b", { class: "small" }, `${plural(n, "entity", "entities")} selected`),
        h("button", { class: "btn small", title: "Tick everything that matches the type and filter above, not only what is listed so far", onclick: () => ticked([...new Set([...S.entSel, ...matching().map(r => r.id)])]) }, "Select shown"),
        S.lib.tags.length ? h("select", { "aria-label": "Select by tag", onchange: e => { if (e.target.value) ticked([...new Set([...S.entSel, ...byTag(e.target.value)])]); e.target.value = ""; } },
          h("option", { value: "" }, "Select by tag…"), S.lib.tags.map(t => h("option", { value: t }, t))) : null,
        n ? h("button", { class: "btn small", onclick: () => ticked([]) }, "Clear") : null,
        h("button", { class: "btn small primary", disabled: !n, title: "Profile of the ticked entities counted as one", onclick: () => (isGroup ? refreshGroup(0) : (location.hash = "#/entities/group")) }, "Analyse together →"),
        n >= 2 ? h("select", { "aria-label": "Make one of the ticked entities the plural group of the others", title: "Choose which ticked entity stands for the others together (“Holmes and Watson”)",
          onchange: async e => {
            const g = e.target.value; if (!g) return;
            await api("/api/plurals", { id: g, add: S.entSel.filter(x => x !== g) });
            S.units = null; S.entSel = []; S.entMulti = false; toast("Plural group saved.");
            location.hash = "#/entities/" + encodeURIComponent(g);
          } },
          h("option", { value: "" }, "Make plural group of the others…"),
          S.entSel.map(x => { const r = U.rows.find(y => y.id === x); return r ? h("option", { value: x }, r.name) : null; })) : null) : null);
  };
  const chips = h("div", { class: "chips" },
    [["ALL", "All", total], ...TYPES.map(t => [t, t, counts[t]]), ["NARR", "Narrators", counts.NARR], ["GENDER", "Gender", counts.GENDER]].map(([t, l, n]) =>
      h("button", { class: "chip" + (S.entType === t ? " on" : ""), title: TYPE_NAMES[t] || "All types",
        onclick: () => { S.entType = t; S.entLimit = 300; if ((isNarr && t !== "NARR") || (isGender && t !== "GENDER")) location.hash = "#/entities"; else render(); } }, l, h("span", { class: "n" }, fmt(n)))));
  const list = h("div", { class: "ent-list" },
    h("div", { class: "head" }, chips,
      h("div", { class: "row" },
        h("input", { type: "search", class: "grow", placeholder: "Filter by name or tag", value: S.entQuery, oninput: e => { S.entQuery = e.target.value; S.entLimit = 300; drawList(); } }),
        h("select", { onchange: e => { S.entSort = e.target.value; drawList(); } },
          [["mentions", "Most mentioned"], ["name", "Name"], ["books", "Most books"]].map(([v, l]) => h("option", { value: v, selected: S.entSort === v }, l))),
        reverseBtn(S.entSortRev, rev => rev ? `Reversed (${{ mentions: "least mentioned", name: "Z–A", books: "fewest books" }[S.entSort]} first): click for the normal order`
          : `Normal order (${{ mentions: "most mentioned", name: "A–Z", books: "most books" }[S.entSort]} first): click to reverse`,
          () => { S.entSortRev = !S.entSortRev; drawList(); })),
      bar, minLine()),
    listItems);
  drawList(); drawBar();
  const pane = h("div", {}, uid ? loading("Loading…") : h("div", { class: "panel empty" },
    U.rows.length ? "Choose an entity on the left to see its profile." : "Nothing meets the minimum in the selected books. Lower it under Library, or choose other books."));
  if (!uid && U.rows.length) pluralSuggestions().then(x => x && pane.append(x));
  main.replaceChildren(h("div", { class: "ent" }, list, pane));
  if (U.problems.length) pane.prepend(h("div", { class: "panel warn" }, U.problems.join(" ")));

  // ----- the pane: one entity, one narrator role, or the ticked group -----
  let paneTimer, paneRun = 0;
  /** Reload the group's profile shortly after the ticks change (at once with delay 0). */
  function refreshGroup(delay = 500) { clearTimeout(paneTimer); paneTimer = setTimeout(showPane, delay); }
  /** What the server is asked for: the saved group while it is untouched, else the ticked entities (null if none). */
  const groupRef = () => savedId && !dirty ? { group: savedId } : S.entSel.length ? { ids: [...S.entSel] } : null;
  async function showPane() {
    if (!uid) return;
    const run = ++paneRun;                                                    // a slower, older answer must not overwrite a newer one
    try {
      let view;
      if (isGroup) {
        const ref = groupRef();
        if (!ref) { pane.replaceChildren(h("div", { class: "panel empty" }, "Tick entities on the left, then choose Analyse together.")); return; }
        pane.replaceChildren(loading("Loading…"));
        const P = await api("/api/profile", withBooks(ref));
        if (run !== paneRun) return;
        if (savedId && !dirty) { S.entSel = P.group.units.map(u => u.id); drawList(); drawBar(); }      // opening a saved group ticks its entities
        P.unit.ref = { ...ref, name: P.unit.name };
        P.unit.target = { kind: "group", ...ref, name: P.unit.name, members: P.group.units.map(x => ({ id: x.id, name: x.name, type: x.type, books: x.books })) };   // members: what the Compare page's group picker shows
        P.unit.parts = P.group.units.map(x => x.id);
        S.profile = P;
        view = profileView(P, {
          saved: savedId ? S.lib.groups.find(g => g.id === savedId) : null, dirty,
          drop: id => toggle(id),
          save: async name => { const r = await api("/api/groups", { name, ids: P.group.units.map(u => u.id) }); S.lib.groups = r.groups; toast(`Saved “${name}”.`); location.hash = "#/entities/g:" + r.id; },
          update: async () => { const r = await api("/api/groups/" + savedId, { ids: S.entSel }); S.lib.groups = r.groups; dirty = false; toast("Saved."); showPane(); },
          rename: async name => { const r = await api("/api/groups/" + savedId, { name }); S.lib.groups = r.groups; toast("Renamed."); render(); },
          remove: async () => { const r = await api("/api/groups/delete", { id: savedId }); S.lib.groups = r.groups; S.entSel = []; location.hash = "#/entities"; },
          revert: () => { dirty = false; showPane(); },
        });
      } else if (isNarr) {
        const P = await api("/api/profile", withBooks({ id: uid }));
        if (run !== paneRun) return;
        view = narratorProfileView(P);
      } else if (isBook || isGender) {
        const P = await api("/api/profile", withBooks({ id: uid }));
        if (run !== paneRun) return;
        P.unit.target = isBook ? { kind: "book", book: uid.slice("book:".length), name: P.unit.name } : { kind: "gender", pron: uid.slice("gender:".length), name: P.unit.name };
        view = isBook ? bookProfileView(P) : genderProfileView(P);
      } else {
        const P = await api("/api/profile", withBooks({ id: uid }));
        if (run !== paneRun) return;
        P.unit.ref = { id: uid };
        P.unit.target = { kind: "unit", id: uid, name: P.unit.name };
        P.unit.parts = [uid];
        S.profile = P;
        view = profileView(P);
      }
      pane.replaceChildren(view);
    } catch (e) {
      if (run === paneRun) pane.replaceChildren(h("div", { class: "panel empty" }, e.message));
    }
  }
  showPane();
}

/** Tag chips with a box to add one; saves through /api/tags and calls onSaved(tags). */
function tagEditor(id, tags, onSaved) {
  const box = h("div", { class: "tag-edit" });
  const save = async next => {
    const r = await api("/api/tags", { id, tags: next });
    S.lib.tags = r.all; S.units = null;
    onSaved(r.tags); draw(r.tags);
  };
  const draw = cur => {
    const inp = h("input", { type: "text", placeholder: "Add tag", list: "tagOptions",
      onkeydown: e => { if (e.key === "Enter" && e.target.value.trim()) save([...cur, e.target.value.trim()]); } });
    box.replaceChildren(...cur.map(t => h("span", { class: "tag" }, t, h("button", { title: "Remove " + t, onclick: () => save(cur.filter(x => x !== t)) }, "×"))), inp,
      h("datalist", { id: "tagOptions" }, S.lib.tags.map(t => h("option", { value: t }))));
  };
  draw(tags);
  return box;
}

/** An entity's or linked person's name at the top of its profile: a "Rename" link swaps the heading for a text input
    (Enter to save, Escape to cancel); once you've set one, a "Reset" link clears it back to the name found in the books. */
function nameEditor(u) {
  const box = h("div", { class: "row", style: { alignItems: "baseline", gap: "10px", flexWrap: "wrap" } });
  const save = async name => {
    await api("/api/name", { id: u.id, name });
    S.units = null;
    toast(name ? "Renamed." : "Back to the name found in the books.");
    render();
  };
  const view = () => box.replaceChildren(
    h("h1", {}, u.name),
    h("button", { type: "button", class: "linkbtn", onclick: edit }, "Rename"),
    u.custom_name ? h("button", { type: "button", class: "linkbtn", title: "Go back to the name found in the books", onclick: () => save("") }, "Reset") : null);
  function edit() {
    const inp = h("input", { type: "text", value: u.name, style: { font: "500 28px var(--serif)", width: "min(420px, 100%)" },
      onkeydown: e => { if (e.key === "Enter") go(); if (e.key === "Escape") view(); } });
    const go = () => inp.value.trim() && save(inp.value.trim());
    box.replaceChildren(inp, h("button", { class: "btn small primary", onclick: go }, "Save"), h("button", { class: "btn small", onclick: view }, "Cancel"));
    inp.focus(); inp.select();
  }
  view();
  return box;
}

/** An entity's or linked person's short free-text description, editable in place next to its tags. */
function noteEditor(id, note) {
  const box = h("div", { class: "small muted", style: { marginTop: "4px" } });
  const save = async text => { await api("/api/note", { id, note: text }); toast("Saved."); render(); };
  const view = () => box.replaceChildren(
    note ? h("span", {}, note, " ") : null,
    h("button", { type: "button", class: "linkbtn", onclick: edit }, note ? "Edit description" : "+ Description"));
  function edit() {
    const inp = h("input", { type: "text", value: note, placeholder: "A short description or label", style: { width: "min(420px, 100%)" },
      onkeydown: e => { if (e.key === "Enter") save(inp.value.trim()); if (e.key === "Escape") view(); } });
    box.replaceChildren(inp, h("button", { class: "btn small primary", onclick: () => save(inp.value.trim()) }, "Save"), h("button", { class: "btn small", onclick: view }, "Cancel"));
    inp.focus();
  }
  view();
  return box;
}

/** The Entities page's "Possible plural groups": people named after two or more others (“Holmes and Watson”), with the members
    found, to accept or dismiss; null when there are none. */
async function pluralSuggestions() {
  const r = await api("/api/plurals/suggestions", withBooks({}));
  if (!r.items.length) return null;
  const box = h("section", { class: "panel" });
  const act = async (x, ok) => {
    await (ok ? api("/api/plurals", { id: x.id, add: x.members.map(m => m.id) }) : api("/api/plurals/reject", { id: x.id }));
    S.units = null; toast(ok ? `“${x.name}” is now a plural group.` : "Won't be suggested again.");
    render();
  };
  box.append(h("h2", {}, "Possible plural groups"),
    h("p", { class: "small muted", style: { marginTop: 0 } }, "Named after other people: their mentions (and the “they” linked to them) may mean those people together."),
    h("div", { class: "plural-sugs" }, r.items.map(x => h("div", { class: "row", style: { flexWrap: "wrap", gap: "8px" } },
      h("a", { href: "#/entities/" + encodeURIComponent(x.id) }, x.name), h("span", { class: "muted small" }, fmt(x.mentions)),
      h("span", {}, "→ plural group of ", x.members.map((m, i) => [i ? ", " : "", m.name])),
      x.unmatched.length ? h("span", { class: "muted small" }, `(no entity for ${x.unmatched.map(u => `“${u}”`).join(", ")})`) : null,
      h("button", { class: "btn small primary", onclick: () => act(x, true) }, "Make plural group"),
      h("button", { type: "button", class: "linkbtn", onclick: () => act(x, false) }, "Not plural")))),
    note("What a plural group does", "Declaring an entity a plural group lets its mentions, what it does, who it appears with, its quotes and the quotes addressed to it count for its members too, whenever a page's “Include plural-group mentions” is ticked (your default is under Library). It stays an entity of its own."));
  return box;
}

/** An entity's plural-group section, framed apart from the header above and the figures below: for a plural group its members
    as chips (× removes one) with a box to add more and "Not plural"; for a member the plural groups it belongs to; otherwise a box
    to make it one. It also holds the page's checkbox for counting plural groups' mentions for their members (`pluralBox`). A
    group of entities analysed together only gets the checkbox. */
/** The plural-group control on an entity's page: compact always, and just a small link (no box) for the common case
    of an entity that isn't part of any plural group, so it doesn't push everything else down. Sits beside the name
    and tags (`.phead-top`), not below them. */
function pluralSection(P) {
  const pl = P.plural, id = P.unit.id, members = pl.members.map(x => x.id);
  // changes are sent as additions and removals: the server keeps the members this page doesn't show (other books, below the minimum)
  const save = async change => {
    const r = await api("/api/plurals", { id, ...change });
    S.units = null;
    toast(r.members.length ? "Saved." : "No longer a plural group.");
    render();
  };
  /** An entity as a chip in its type's colour, linking to its page; `remove` adds a ×. */
  const chip = (x, remove) => h("span", { class: "tag" }, typeChip(x.type), " ",
    h("a", { href: "#/entities/" + encodeURIComponent(x.id) }, x.name),
    remove ? h("button", { title: `Remove ${x.name}`, "aria-label": `Remove ${x.name}`, onclick: remove }, "×") : null);
  const adder = placeholder => unitSearch({ exclude: () => [id, ...members], placeholder, onPick: r => save({ add: [r.id] }) });
  if (P.group)
    return h("div", { class: "plural-sec" }, h("span", { class: "plural-title" }, "Plural groups"), pluralBox(),
      h("div", { class: "plural-body" }, h("span", { class: "muted small" }, "Counted as each entity's figures are, with or without the mentions of plural groups they belong to.")));
  if (pl.members.length || pl.hidden)
    return h("div", { class: "plural-sec" }, h("span", { class: "plural-title" }, "Plural group of"), pluralBox(),
      h("div", { class: "plural-body" }, pl.members.map(x => chip(x, () => save({ remove: [x.id] }))),
        pl.hidden ? h("span", { class: "muted small" }, `${pl.members.length ? "and " : ""}${plural(pl.hidden, "member")} below the minimum mentions`) : null,
        adder("Add a member…"),
        h("button", { type: "button", class: "linkbtn", onclick: () => save({ members: [] }) }, "Not plural")));
  if (pl.member_of.length)
    return h("div", { class: "plural-sec" }, h("span", { class: "plural-title" }, "Also mentioned together as"), pluralBox(),
      h("div", { class: "plural-body" }, pl.member_of.map(x => chip(x))));
  // the common case: not part of any plural group — a small link, expanding in place, instead of an always-open box
  const box = h("span", { class: "plural-empty" });
  const collapse = () => box.replaceChildren(h("button", { type: "button", class: "linkbtn", onclick: expand }, "+ Plural group"));
  const expand = () => box.replaceChildren(
    h("span", { class: "muted small" }, "Member of a plural mention (“Holmes and Watson”, “they”)?"), adder("Add a member…"),
    h("button", { type: "button", class: "linkbtn", onclick: collapse }, "Cancel"));
  collapse();
  return box;
}

/** An entity's whole profile: header and facts, how it is referred to, what it does and what is done to it, book by book,
    speech, topics, kinds of action, who it appears with, and what is distinctive.
    The same page serves a group of entities counted as one (`P.group` is set; `ctl` holds what its header can do: see `groupHeader`).
    `P.unit.target` is the spec every request about it uses, `P.unit.ref` its `id` / `ids` / `group` for the routes that take those. */
function profileView(P, ctl) {
  const u = P.unit, G = P.group, color = TC[u.type];
  const target = u.target;
  const ev = (kind, key, other, label) => openEvidence(label, u.name, { target, kind, key, other });
  const wrap = h("div");
  const excluded = P.members.filter(m => !m.included);
  const facts = [["Mentions", fmt(u.mentions)]];
  if (G) facts.push(["Entities", fmt(G.units.length)]);
  if (u.share != null) facts.push([`Share of ${TYPE_NAMES[u.type].toLowerCase()}`, fmt(u.share, 1) + "%"]);
  facts.push(["Per 1,000 words", fmt(P.per1k, 2)], ["Books", fmt(u.books.length)]);
  if (P.pronouns.length) facts.push(["Pronouns", P.pronouns.map(p => p.item).join(", ")]);
  const charQuery = (G ? G.units.map(x => x.name) : [u.name]).map(n => n.replace(/"/g, "")).join("|");
  wrap.append(h("section", { class: "phead" },
    G ? groupHeader(P, ctl) : h("div", { class: "phead-top" },
      h("div", { class: "phead-id" },
        h("div", { class: "row" }, typeChip(u.type), h("span", { class: "muted small" }, TYPE_NAMES[u.type], u.linked ? " · linked across books" : "")),
        nameEditor(u),
        tagEditor(u.id, u.tags, tags => (u.tags = tags)),
        noteEditor(u.id, u.note || "")),
      pluralSection(P)),
    h("div", { class: "small", style: { marginTop: "6px" } }, h("a", { href: "#/corpus/kwic", onclick: e => { e.preventDefault(); goKwic(`[char="${charQuery}"]+`, "pattern"); } }, "Every mention in the concordance"),
      G ? [" · ", h("a", { href: "#/compare", onclick: () => { S.cmp.a = target; } }, "Compare this group with…")] : null),
    G ? pluralSection(P) : null,
    h("div", { class: "facts" }, facts.map(([k, v]) => h("div", {}, h("b", {}, v), k))),
    chartBox(presenceChart(P.presence, color), slug(u.name) + "-presence"),
    h("details", { class: "members" }, h("summary", { class: "small" }, G ? `Where these come from: ${plural(P.members.length, "coreference group")}` : u.linked ? `In ${plural(P.members.length, "book")}` + (excluded.length ? `, ${excluded.length} below the minimum` : "") : "Where this comes from"),
      table([
        { k: "title", label: "Book" }, { k: "name", label: "Name in that book" }, { k: "coref", label: "Group ID", num: true },
        { k: "type", label: "Type" }, { k: "mentions", label: "Mentions", num: true, fmt: v => fmt(v) },
        { k: "included", label: "Counted", fmt: v => v ? "yes" : "below minimum" },
      ], P.members, { csvName: u.name + " books", csv: false })),
    note("About these figures",
      `Mentions count every reference BookNLP grouped with ${G ? "any of these entities, added together" : `this ${u.linked ? "linked entity" : "entity"}`} in the selected books: names, descriptions and pronouns.` +
      (P.count_mode === "per_book" ? " Books where it falls below the minimum are left out." : "") +
      (pluralMode() ? " Plural groups' mentions (“they”, “Holmes and Watson”) count for their members too, except where the member is named inside them." : ""),
      `Per 1,000 words divides mentions by the words (tokens other than punctuation) of the books it's counted in: ${fmt(P.words)} words.`,
      "The strip shows where mentions fall in each book, from start to end in 100 slices. Darker means more mentions.")));

  profileBody(wrap, u, P, color);
  return wrap;
}

/** The parts of a profile that only need a `target` spec and the figures already in `P` (an entity, a group, or a
    book's or gender's own pooled page): how it's referred to, what it does and what's done to it, book by book,
    kinds of action, who it appears with, and what is distinctive. `profileView` adds Speech and Topics itself,
    around this, since those need an `id` / `ids` / `group` ref that a book or gender pool doesn't have. */
function profileBody(wrap, u, P, color, opts = {}) {
  const G = P.group;
  const target = u.target;
  const ev = (kind, key, other, label) => openEvidence(label, u.name, { target, kind, key, other });

  // how they're referred to
  const formTable = k => table([{ k: "item", label: PROP_NAMES[k].replace(/s$/, "") }, { k: "n", label: "Mentions", num: true, fmt: barFmt(P.forms[k][0] ? P.forms[k][0].n : 1) }],
    P.forms[k], { limit: 10, csvName: `${u.name} ${PROP_NAMES[k]}`, onRow: r => ev("form", r.item, null, `“${r.item}”`), empty: "None." });
  wrap.append(h("section", { class: "panel" }, h("h2", {}, "How they're referred to"),
    chartBox(propChart(P.by_prop), slug(u.name) + "-references"),
    h("div", { class: "cols3", style: { marginTop: "10px" } }, ["PROP", "NOM", "PRON"].map(k => h("div", {}, h("h3", { class: "small muted" }, PROP_NAMES[k]), formTable(k)))),
    h("h3", { class: "small muted", style: { marginTop: "14px" } }, "Named or described in dialogue by"),
    table([{ k: "name", label: "Speaker" }, { k: "n", label: "Times", num: true, fmt: v => fmt(v) }], P.named_by,
      { limit: 10, csvName: `${u.name} named by`, onRow: r => ev("named", null, r.id, `Named by ${r.name}`), empty: "Nobody names or describes them inside a quote." }),
    note("How this is worked out", "Names, descriptions and pronouns follow BookNLP's own labels (PROP, NOM and PRON) for each mention.",
      "“Named or described in dialogue by” counts name and description mentions that fall inside a quote, grouped by the quote's speaker. Pronouns are left out, because inside dialogue they mostly refer to the speaker or listener. Click a row to see the sentences.")));

  // relations
  const relBox = h("div");
  const drawRel = () => {
    const rel = S.relTab, d = P.relations[rel];
    const max = d.rows[0] ? d.rows[0].n : 1;
    const cols = [{ k: "item", label: rel === "prep" ? "Attached to" : "Word (lemma)" }, { k: "n", label: "Count", num: true, fmt: barFmt(max) },
      { k: "per1k", label: "Per 1,000 words", num: true, fmt: v => fmt(v, 3) }, { k: "pct", label: "%", num: true, fmt: v => fmt(v, 1), title: "Share of this list" }];
    if (rel !== "poss" && rel !== "mod") cols.push({ k: "events", label: "Events", num: true, fmt: v => fmt(v), title: "How many BookNLP marks as actually happening (EVENT)" });
    if (rel === "agent" || rel === "patient") cols.push({ k: "supersense", label: "Supersense", fmt: v => (v || "").replace("verb.", "") });
    relBox.replaceChildren(
      h("div", { class: "subtabs" }, S.lib.relations.map(r => h("button", { class: r.id === rel ? "on" : "", onclick: () => { S.relTab = r.id; drawRel(); } },
        r.label, h("span", { class: "n" }, fmt(P.relations[r.id].total))))),
      h("div", { class: "muted small", style: { marginBottom: "6px" } }, `${plural(d.total, "occurrence")}, ${plural(d.distinct, "different word")}. Click a row for the sentences.`),
      table(cols, d.rows, { limit: 25, csvName: `${u.name} ${rel}`, onRow: r => ev(rel, r.item, null, `${S.lib.relations.find(x => x.id === rel).label}: ${r.item}`), empty: "None found." }));
  };
  drawRel();
  wrap.append(h("section", { class: "panel" }, h("h2", {}, "What they do and what's done to them"), relBox,
    note("How these are found",
      "These come from the dependency parse in the .tokens file, using BookNLP's rules. Actions: verbs the entity is the subject of, or the “by” agent of a passive. Done to them: verbs it is the object, indirect object or passive subject of. Possessions: nouns it possesses (“his pipe”). Modifiers: adjectives attached to it, nouns in apposition (“Brown, the priest”), and complements of “to be” (“Brown was small”).",
      "Three additions to BookNLP's rules: a mention joined by “and” shares the role of the first (“Holmes and Watson went”); a subject also counts for verbs joined to its verb (“He rose and lit his pipe” gives rise and light); and Prepositions and settings records every “verb/noun + preposition” the entity is attached to (“went to London”), for every type. Because of these additions, counts can be higher than in the exported .book.",
      "Events uses the event column of .tokens. Supersense is the most common WordNet supersense BookNLP gave to that verb for this entity.")));

  // book by book, and (for an entity or a hand-picked group, which have an id/ids/group ref) speech and topics
  wrap.append(byBookPanel(u, P));
  if (!opts.noSpeechTopics) { wrap.append(speechPanel(u)); wrap.append(entityTopicsPanel(u)); }

  // supersenses
  const ssBox = h("div");
  const drawSs = () => {
    const rows = P.supersenses[S.ssRel], none = P.supersenses[S.ssRel + "_none"];
    ssBox.replaceChildren(
      h("div", { class: "row", style: { marginBottom: "8px" } }, seg([["agent", "Actions"], ["patient", "Done to them"]], S.ssRel, v => { S.ssRel = v; drawSs(); })),
      rows.length ? chartBox(hbarChart([{ name: u.name, color, rows }]), `${slug(u.name)}-supersenses-${S.ssRel}`) : h("div", { class: "muted small" }, "No supersenses on these verbs."),
      none ? h("div", { class: "muted small" }, `${plural(none, "verb")} had no supersense and ${none === 1 ? "is" : "are"} not shown.`) : null);
  };
  drawSs();
  wrap.append(h("section", { class: "panel" }, h("h2", {}, "Kinds of action"), ssBox,
    note("What this shows", "Each verb in Actions or Done to them is grouped by the WordNet supersense BookNLP assigned to it in the .supersense file: communication, cognition, perception, motion and so on.")));

  // co-occurrence (the small network is drawn around one entity, so a group gets the table only; a book or gender
  // pool is left out entirely, since it pools almost every entity that could "appear with" it, leaving nobody else)
  if (!opts.noCooccur) {
    const ego = G ? null : h("div", {}, loading("Drawing network…"));
    wrap.append(h("section", { class: "panel" }, h("h2", {}, "Appears with"),
      h("div", { class: G ? "" : "cols2" },
        table([{ k: "name", label: "Entity", fmt: (v, r) => h("span", {}, typeChip(r.type), " ", v) , csv: v => v}, { k: "type", label: "Type" },
          { k: "n", label: "Shared sentences", num: true, fmt: barFmt(P.cooccurring[0] ? P.cooccurring[0].n : 1) }],
          P.cooccurring, { limit: 12, csvName: `${u.name} appears with`, onRow: r => ev("cooc", null, r.id, `With ${r.name}`), empty: "Never mentioned in the same sentence as another counted entity." }),
        ego),
      note("How this is counted", G ? "The number of sentences in which at least one of the group's entities and the other entity are both mentioned, across the selected books; a sentence counts once however many of the group's entities it holds. Entities of the group itself are left out. Click a row for the sentences."
        : "The number of sentences in which both are mentioned, across the selected books. Click a row for the sentences. The network shows this entity with its 15 most frequent companions and the links among them; open it in Network for more control.")));
    if (!G) api("/api/network", withBooks({ kind: "sentence", types: TYPES, min_weight: 1, focus: u.id, focus_top: 15 })).then(N => {
      if (!N.nodes.length) { ego.replaceChildren(h("div", { class: "muted small" }, "No network to draw.")); return; }
      const el = networkSvg(N, { color: "type", size: "strength", labels: 16, height: 760, focus: u.id, font: 22, radius: 1.8 });
      ego.className = "";
      ego.replaceChildren(chartBox(el, slug(u.name) + "-network"));
    });
  }

  // distinctive
  wrap.append(distinctivePanel(u));
}

/** The entities a book's or a gender's page pools, as a plain table: no ticking or editing, since that belongs to a
    hand-picked group, not an automatic pool. Clicking a row opens that entity's own profile. */
function poolTable(units, name) {
  return table([
    { k: "name", label: "Entity", fmt: (v, r) => h("span", {}, typeChip(r.type), " ", v), csv: v => v },
    { k: "mentions", label: "Mentions", num: true, fmt: v => fmt(v) },
    { k: "pct", label: "% of this pool", num: true, fmt: v => fmt(v, 1) },
    { k: "per1k", label: "Per 1,000 words", num: true, fmt: v => fmt(v, 2) },
  ], units, { limit: 100, csvName: name + " entities", onRow: r => (location.hash = "#/entities/" + encodeURIComponent(r.id)) });
}

/** A book's own page (`book:<id>`): title, author, year, series, word and quote counts, then every entity counted in
    it pooled as one group — the same shape `profileBody` gives an entity or a hand-picked group, so it reads as
    "how does this book look": who's in it, what they do, how they speak, who appears with whom, what's distinctive.
    Book by book and topics are left out (a book profile is already one book; see `profileBody`'s `noSpeechTopics`). */
function bookProfileView(P) {
  const u = P.unit, B = P.book, wrap = h("div"), color = TC[u.type];
  const facts = [["Entities", fmt(P.group.units.length)], ["Mentions", fmt(u.mentions)], ["Words", fmt(B.words)],
    ["Quotes", fmt(B.quotes)], ["Per 1,000 words", fmt(P.per1k, 2)]];
  if (B.author) facts.push(["Author", B.author]);
  if (B.year) facts.push(["Year", String(B.year)]);
  if (B.series) facts.push(["Series", B.series]);
  wrap.append(h("section", { class: "phead" },
    h("div", { class: "row" }, h("span", { class: "muted small" }, "Book overview")),
    h("h1", {}, B.title),
    h("div", { class: "small" }, h("a", { href: "#/read/" + encodeURIComponent(B.id) }, "Read this book")),
    h("div", { class: "facts" }, facts.map(([k, v]) => h("div", {}, h("b", {}, v), k))),
    chartBox(presenceChart(P.presence, color), slug(B.title) + "-presence")),
    h("section", { class: "panel" }, h("h2", {}, "Entities in this book"), poolTable(P.group.units, B.title)));
  profileBody(wrap, u, P, color, { noSpeechTopics: true, noCooccur: true });
  return wrap;
}

/** A gender's own page (`gender:<pron>`): every PER entity of that gender across the
    selection, pooled as one group — "how do men, women… talk, act, appear", the same profile shape as a book's page. */
function genderProfileView(P) {
  const u = P.unit, wrap = h("div"), color = TC[u.type];
  const facts = [["Entities", fmt(P.group.units.length)], ["Mentions", fmt(u.mentions)], ["Books", fmt(u.books.length)], ["Per 1,000 words", fmt(P.per1k, 2)]];
  wrap.append(h("section", { class: "phead" },
    h("div", { class: "row" }, typeChip("PER"), h("span", { class: "muted small" }, "Gender overview")),
    h("h1", {}, u.name),
    h("div", { class: "facts" }, facts.map(([k, v]) => h("div", {}, h("b", {}, v), k))),
    chartBox(presenceChart(P.presence, color), slug(u.name) + "-presence")),
    h("section", { class: "panel" }, h("h2", {}, "Entities of this gender"), poolTable(P.group.units, u.name)));
  profileBody(wrap, u, P, color, { noSpeechTopics: true, noCooccur: true });
  return wrap;
}

/** The top of a group's page: its name and the entities it consists of as removable tags (× drops one from the ticks), a table of
    each entity's share of the group, and what can be done with the group. `ctl`: saved (the saved group or null), dirty (ticks differ from it),
    drop(id), save(name), update(), rename(name), remove(), revert(). */
function groupHeader(P, ctl) {
  const u = P.unit, G = P.group, saved = ctl.saved;
  const ask = (label, initial, ok) => {
    const inp = h("input", { type: "text", value: initial, placeholder: "Group name", "aria-label": label });
    const go = () => { if (inp.value.trim()) ok(inp.value.trim()); };
    inp.onkeydown = e => { if (e.key === "Enter") go(); if (e.key === "Escape") actions(); };
    acts.replaceChildren(inp, h("button", { class: "btn small primary", onclick: go }, "OK"), h("button", { class: "btn small", onclick: actions }, "Cancel"));
    inp.focus();
  };
  const acts = h("div", { class: "row", style: { flexWrap: "wrap", margin: "8px 0" } });
  const actions = () => acts.replaceChildren(
    saved && !ctl.dirty ? [h("button", { class: "btn small", onclick: () => ask("Rename group", saved.name, ctl.rename) }, "Rename"),
      h("button", { class: "btn small", onclick: () => { if (confirm(`Delete the group “${saved.name}”? The entities stay.`)) ctl.remove(); } }, "Delete group")]
      : [h("button", { class: "btn small primary", onclick: () => ask("Save as group", saved ? saved.name + " (2)" : "", ctl.save) }, "Save as a group…"),
        saved ? h("button", { class: "btn small", title: "Replace the saved group's entities with these", onclick: ctl.update }, `Update “${saved.name}”`) : null,
        saved ? h("button", { class: "btn small", onclick: ctl.revert }, "Back to the saved group") : null]);
  actions();
  return [
    h("div", { class: "row" }, typeChip(u.type), h("span", { class: "muted small" }, saved ? (ctl.dirty ? `Saved group “${saved.name}”, changed` : "Saved group") : "Group",
      ` · ${plural(G.units.length, "entity", "entities")}`, Object.keys(G.types).length > 1 ? " of several types (" + Object.entries(G.types).map(([t, n]) => `${t} ${n}`).join(", ") + ")" : "")),
    h("h1", {}, saved && !ctl.dirty ? saved.name : u.name),
    h("div", { class: "gbox", "aria-label": "The entities in this group" }, G.units.map(x => gtag(x, () => ctl.drop(x.id), true))),
    G.missing.length ? h("p", { class: "warn small", style: { margin: "6px 0 0" } }, `${plural(G.missing.length, "entity", "entities")} of this group ${G.missing.length === 1 ? "isn't" : "aren't"} in the selected books or below the minimum, so ${G.missing.length === 1 ? "it isn't" : "they aren't"} counted.`) : null,
    acts,
    table([{ k: "name", label: "Entity", fmt: (v, r) => h("span", {}, typeChip(r.type), " ", h("a", { href: "#/entities/" + encodeURIComponent(r.id) }, v)), csv: v => v },
      { k: "mentions", label: "Mentions", num: true, fmt: barFmt(G.units[0] ? G.units[0].mentions : 1) }, { k: "pct", label: "% of the group", num: true, fmt: v => fmt(v, 1) },
      { k: "per1k", label: "Per 1,000 words", num: true, fmt: v => fmt(v, 2), title: "Its own mentions per 1,000 words of the books it appears in" },
      { k: "books", label: "Books", fmt: v => booksLabel(v), csv: v => v.join("; "), sortVal: r => r.books.length }], G.units, { csvName: u.name + " members", limit: 30 }),
    note("About a group", "A group counts several entities as one: its mentions, relations, speech and topics are those of all its entities added together, each sentence or quote counted once. Everything below works on that pooled material; the table above shows how much each entity contributes.",
      "Save a group to come back to it or to use it on the Compare page. A saved group stores only which entities are in it, so it follows your minimum-mentions setting, the books selected and any links you make.")];
}

/** "Book by book": the entity's figures per book and how its words change across books (chi-squared per word). */
function byBookPanel(u, P) {
  const box = h("section", { class: "panel" }, h("h2", {}, "Book by book"));
  if (u.books.length < 2) {
    const below = P.members.filter(m => !m.included).length;
    box.append(h("p", { class: "muted small", style: { margin: 0 } },
      below ? `Counted in one book; ${plural(below, "other book")} fall below the minimum. ` : "Appears in one of the selected books. ",
      u.linked || P.group ? "" : "If the same entity appears in other books, link them on the ", u.linked || P.group ? "" : h("a", { href: "#/links" }, "Entity Links"), u.linked || P.group ? "" : " page to compare them book by book."));
    return box;
  }
  const target = u.target;
  const out = h("div", {}, loading("Loading…"));
  S.bbRel = S.bbRel || "mod";
  S.bbChart = S.bbChart || "changed";
  const run = async () => {
    const r = await api("/api/bybook", withBooks({ target, rel: S.bbRel, ...S.stat }));
    const titles = r.books.map(b => b.title);
    const colors = r.books.map((_, i) => PALETTE[i % PALETTE.length]);
    const actions = x => x.rows.reduce((a, b) => a + b.n, 0);
    const biggest = r.supersenses.map((_, i) => i).sort((a, b) => actions(r.supersenses[b]) - actions(r.supersenses[a])).slice(0, 8).sort((a, b) => a - b);      // book numbers, in book order
    // overview
    const ovCols = [{ k: "title", label: "Book", fmt: (v, row) => bookLink(row.book, v) }, { k: "mentions", label: "Mentions", num: true, fmt: v => fmt(v) },
      { k: "per1k", label: "Per 1,000 words", num: true, fmt: v => fmt(v, 2) }];
    if (r.overview[0] && r.overview[0].share != null) ovCols.push({ k: "share", label: `% of ${TYPE_NAMES[u.type].toLowerCase()}`, num: true, fmt: v => fmt(v, 1) });
    ovCols.push({ k: "names", label: "Names %", num: true, fmt: v => fmt(v, 1) }, { k: "descriptions", label: "Descriptions %", num: true, fmt: v => fmt(v, 1) },
      { k: "pronouns", label: "Pronouns %", num: true, fmt: v => fmt(v, 1) },
      ...S.lib.relations.map(rl => ({ k: "rel_" + rl.id, label: rl.label, num: true, fmt: v => fmt(v, 1), title: `${rl.label} per 100 mentions` })),
      { k: "names_used", label: "Names used" });
    // matrix
    const rows = r.rows.map(x => { const o = { ...x }; x.counts.forEach((c, i) => { o["b" + i] = c; o["p" + i] = x.pcts[i]; o["r" + i] = x.resid[i]; }); return o; });
    const cell = i => (v, row) => h("span", { class: row["r" + i] == null ? "" : row["r" + i] >= 1.96 ? "rp" : row["r" + i] <= -1.96 ? "rn" : "",
      title: row["r" + i] == null ? "" : `adjusted residual ${fmt(row["r" + i], 2)}` }, v ? `${fmt(v)} (${fmt(row["p" + i], 1)}%)` : "·");
    const mCols = [{ k: "item", label: "Word" },
      ...titles.map((t, i) => ({ k: "b" + i, label: t, num: true, fmt: cell(i), csv: (v, row) => v, sortVal: row => row["p" + i] })),
      { k: "total", label: "Total", num: true, fmt: v => fmt(v) },
      { k: "chi2", label: "χ²", num: true, fmt: v => v == null ? "—" : fmtSig(v) },
      { k: "p", label: "p", num: true, fmt: fmtP, sortVal: row => row.p == null ? -2 : -row.p },
      { k: "v", label: "Cramér's V", num: true, fmt: v => v == null ? "—" : fmt(v, 3) }];
    // chart: most changed or most frequent
    const tested = rows.filter(x => x.tested);
    const pickRows = S.bbChart === "changed" ? [...tested].sort((a, b) => a.p - b.p).slice(0, 8) : rows.slice(0, 8);
    const chart = pickRows.length ? chartBox(lineChart(titles, pickRows.map((x, i) => ({ name: x.item, color: PALETTE[i % PALETTE.length], values: x.pcts }))),
      `${slug(u.name)}-${r.rel}-by-book`) : h("p", { class: "muted small" }, "Nothing to chart at this minimum frequency.");
    const relLabel = S.lib.relations.find(x => x.id === r.rel).label;
    out.className = "";
    out.replaceChildren(
      table(ovCols, r.overview, { csvName: `${u.name} by book`, limit: 50 }),
      h("h3", { style: { marginTop: "16px" } }, "Words, book by book"),
      h("div", { class: "subtabs" }, S.lib.relations.map(rl => h("button", { class: rl.id === r.rel ? "on" : "", onclick: () => { S.bbRel = rl.id; run(); } }, rl.label))),
      h("div", { class: "controls" },
        h("label", {}, "Minimum frequency for the test", h("input", { type: "number", min: 1, value: S.stat.min_freq, onchange: e => { S.stat.min_freq = Math.max(1, +e.target.value || 1); saveStat(run); run(); } })),
        h("label", {}, "Significance level", h("select", { onchange: e => { S.stat.alpha = +e.target.value; saveStat(run); run(); } },
          [0.05, 0.01, 0.001, 0.0001].map(a => h("option", { value: a, selected: S.stat.alpha === a }, "p < " + a)))),
        h("label", { class: "inline" }, h("input", { type: "checkbox", checked: S.stat.bonferroni, onchange: e => { S.stat.bonferroni = e.target.checked; saveStat(run); run(); } }), "Bonferroni correction"),
        h("button", { class: "btn small", onclick: () => { S.cmp = { a: { ...target, books: [r.books[0].id] }, b: { ...target, books: [r.books[1].id] }, rel: r.rel }; location.hash = "#/compare"; } }, "Compare two books in detail")),
      h("p", { class: "small muted" }, `${relLabel} per book: ${r.books.map((b, i) => `${b.title} ${fmt(r.totals[i])}`).join(", ")}. ` +
        `${plural(r.distinct, "different word")}; ${plural(r.summary.tested, "word")} with at least ${r.summary.min_freq} occurrences tested, ${fmt(r.summary.significant)} changing significantly.`),
      h("div", { class: "row", style: { margin: "4px 0 6px" } }, h("span", { class: "small" }, "Chart"),
        seg([["changed", "Most changed"], ["frequent", "Most frequent"]], S.bbChart, v => { S.bbChart = v; run(); })),
      chart,
      table(mCols, rows, { limit: 30, csvName: `${u.name} ${r.rel} by book`, rowClass: row => row.tested && !row.sig ? "" : "",
        onRow: row => openEvidence(`${relLabel}: ${row.item}`, `${u.name}, all books`, { target, kind: r.rel, key: row.item }) }),
      h("h3", { style: { marginTop: "16px" } }, "Kinds of action, book by book"),
      chartBox(hbarChart(biggest.map(i => ({ name: r.supersenses[i].title, color: colors[i], rows: r.supersenses[i].rows })), { pct: true, max: 12 }), `${slug(u.name)}-supersenses-by-book`),
      biggest.length < r.supersenses.length ? h("p", { class: "small muted" }, `The ${biggest.length} books with most actions of ${r.supersenses.length}: more bars than that would be unreadable.`) : null,
      note("How this is calculated",
        "The overview gives each book's figures on their own: mentions per 1,000 words of that book, the share of mentions that are names, descriptions and pronouns, and each list per 100 mentions.",
        "In the word table, each book's cell shows the count and its share of that book's list. " + S.lib.across_note,
        "Words below the minimum frequency are listed without a test. For two books, the χ² here is the same as the Compare page's χ². Compare two books in detail opens them side by side with every statistic.",
        "The kinds-of-action chart shows each book's actions by supersense, as a percentage of that book's actions with a supersense."));
  };
  box.append(h("p", { class: "small muted", style: { marginTop: 0 } }, "How this entity's figures and words change from one selected book to the next, in the order of the book list."), out);
  syncStat(box, run);                 // its test settings are the shared ones: follow a change made in "What's distinctive" below
  run();
  return box;
}

/** "What's distinctive": words markedly more typical of this entity than of a comparison group. */
function distinctivePanel(u) {
  const box = h("section", { class: "panel" });
  const out = h("div");
  const target = u.target;
  const run = async () => {
    out.replaceChildren(loading("Comparing…"));
    const ref = S.distRef.kind === "unit" && S.distRef.id === u.id ? { kind: "others" } : S.distRef;
    const r = await api("/api/distinctive", withBooks({ target, reference: ref, rel: S.distRel, ...S.stat }));
    const s = r.summary;
    out.replaceChildren(
      h("p", { class: "small muted" }, `${u.name}: ${plural(s.c, "item")}. Compared with ${s.reference}` + (s.reference_units ? ` (${plural(s.reference_units, "entity", "entities")})` : "") + `: ${plural(s.d, "item")}.`),
      s.d === 0 ? h("p", { class: "warn small" }, "The comparison group has nothing in this list, so there is nothing to compare with.") : null,
      table(statCols(s, false), r.rows, { limit: 30, csvName: `${u.name} distinctive ${s.rel}`,
        rowClass: row => row.sig ? "" : "dim",
        onRow: row => openEvidence(`${s.rel_label}: ${row.item}`, u.name, { target, kind: s.rel, key: row.item }),
        empty: `Nothing is significantly more typical of ${u.name} at these settings.` }),
      statNote(s));
  };
  const relSel = h("label", {}, "List", h("select", { onchange: e => { S.distRel = e.target.value; run(); } },
    S.lib.relations.map(r => h("option", { value: r.id, selected: r.id === S.distRel }, r.label))));
  const refPick = h("div", { class: "fld" }, "Compared with", picker(S.distRef, v => { S.distRef = v; if (v.kind !== "tag" || v.tag) run(); }, { others: true, book: true, gender: true }));
  const ctl = h("div");
  const drawCtl = () => ctl.replaceChildren(statControls(run, { pre: [relSel, refPick] }));
  drawCtl();
  box.append(h("h2", {}, "What's distinctive"),
    h("p", { class: "small muted", style: { marginTop: 0 } }, "Words markedly more typical of this entity than of the comparison group."),
    ctl, out);
  syncStat(box, run, () => { drawCtl(); run(); });      // its test settings are the shared ones: follow a change made in "Book by book" above
  run();
  return box;
}

/* ---------- Narrators as entities ---------- */
S.narrRef = "narration";                 // what a narrator's vocabulary is compared with: narration, dialogue or their own dialogue
/** Linking narrator roles into one narrator (Watson-as-narrator of one book and Watson-as-narrator of another, told
    as if by the same voice; or two anonymous narrators, or a mix): the current members with an unlink for each
    and "Unlink all", and always a picker to add another narrator role — including one already linked, which joins
    the two links into one. Unlike linking entities, this only pools narration; nothing else about them merges. */
function narratorLinkBox(R) {
  const box = h("div", { class: "small", style: { margin: "4px 0" } });
  // Linking or unlinking can change which id this role lives at (a fresh "nl:…", or, once a link of two dissolves,
  // a member's own original id): navigate there, or just re-render if it's the id we're already on (a same-value
  // hash assignment fires no hashchange).
  const goTo = id => { S.units = null; if (id === R.id) render(); else location.hash = "#/entities/" + encodeURIComponent(id); };
  const sel = h("select", {}, h("option", { value: "" }, "Loading…"));
  api("/api/dialogue/narrators", withBooks({})).then(r => {
    const opts = r.rows.filter(x => x.id !== R.id);
    sel.replaceChildren(h("option", { value: "" }, "Choose a narrator…"), opts.map(x => h("option", { value: x.id }, x.name)));
  });
  const link = async () => {
    if (!sel.value) return;
    const r = await api("/api/narrators/link", { a: R.id, b: sel.value });
    toast("Linked."); goTo(r.id);
  };
  const unlink = async m => {
    await api("/api/narrators/unlink", { id: R.id, role: m.id });
    toast("Unlinked.");
    const rest = R.members.filter(x => x.id !== m.id);
    goTo(rest.length > 1 ? R.id : rest[0].id);          // down to one member: the link dissolved, so follow the one left
  };
  const unlinkAll = async () => {
    if (!confirm("Unlink every narrator here? Each becomes its own narrator again.")) return;
    await api("/api/narrators/unlink_all", { id: R.id });
    toast("Unlinked."); goTo(R.members[0].id);
  };
  box.append(R.linked
    ? h("div", { class: "row", style: { flexWrap: "wrap", gap: "4px" } }, h("span", { class: "muted" }, "Linked narrators: "),
        R.members.map((m, i) => h("span", {}, i ? ", " : "",
          m.unit ? h("a", { href: "#/entities/" + encodeURIComponent(m.unit), title: "Their own profile (mentions, relations and dialogue)" }, m.name) : m.name,
          h("button", { type: "button", class: "linkbtn", title: "Unlink " + m.name, onclick: () => unlink(m) }, "×"))),
        h("button", { type: "button", class: "linkbtn", onclick: unlinkAll }, "Unlink all"))
    : h("span", { class: "muted" }, "Narrated alone so far."));
  box.append(h("div", { class: "row", style: { marginTop: "4px" } }, "Link with another narrator:", sel, h("button", { class: "btn small", onclick: link }, "Link")));
  return box;
}

/** A narrator role's page (`nar:<entity>`, `nar:anon:<book>`, or `nl:<n>` once linked): how much they narrate and where,
    their voice against all narration and against the same character's dialogue, a row per book, who they are linked
    with, and the words that are distinctive of their narration. */
function narratorProfileView(P) {
  const R = P.role, wrap = h("div"), st = P.style;
  wrap.append(h("section", { class: "phead" },
    h("div", { class: "row" }, typeChip("NARR"), h("span", { class: "muted small" }, R.linked ? "Linked narrators" : R.anonymous ? "Unnamed narrator" : "A character who narrates")),
    R.linked ? nameEditor({ id: R.id, name: R.name, custom_name: true }) : h("h1", {}, R.name),
    R.unit ? h("div", { class: "small" }, h("a", { href: "#/entities/" + encodeURIComponent(R.unit) }, `${R.unit_name}'s own profile`), " (mentions, relations and dialogue)") : null,
    narratorLinkBox(R),
    h("div", { class: "facts" }, [["Words narrated", fmt(P.words)], ["Paragraphs", fmt(P.paragraphs)], ["Share of all narration", fmt(P.share, 1) + "%"],
      ["Per 1,000 words", fmt(P.per1k, 1)], ["Books", fmt(R.books.length)], P.exceptions ? ["Set by paragraph", fmt(P.exceptions)] : null].filter(Boolean)
      .map(([k, v]) => h("div", {}, h("b", {}, v), k))),
    chartBox(presenceChart(P.presence, TC.NARR, "Where they narrate"), slug(R.name) + "-narration"),
    note("About these figures", "Narration is every word outside quotes, paragraph by paragraph. A paragraph belongs to the book's narrator (chosen under Library or in the text view) unless you gave it to someone else. " +
      "Per 1,000 words divides the words narrated by all words of the books they narrate in. The strip counts the paragraphs they narrate in each 1% of the book.")));
  const rows = [{ ...st, name: R.name, type: "NARR" }, { ...P.all_style, name: "All narration" }, P.spoken ? { ...P.spoken, name: `${R.unit_name}, in dialogue` } : null].filter(Boolean);
  const cols = SPEECH_STYLE_COLS.map(c => c.k === "name" ? { ...c, label: "" } : c.k === "quotes" ? { ...c, label: "Paragraphs / quotes" } : c.k === "per_quote" ? { ...c, label: "Words per paragraph / quote" } : c);
  wrap.append(h("section", { class: "panel" }, h("h2", {}, "Voice"),
    h("p", { class: "small muted", style: { marginTop: 0 } }, R.unit ? "Their narrating voice next to all narration and to what the same character says in quotes." : "Their narration next to all narration."),
    table(cols, rows, { csvName: `${R.name} voice` }),
    note("What the columns mean", S.lib.dialogue_notes.style, "For narration, a “quote” is a paragraph: questions and exclamations are the share of paragraphs that contain one.")));
  wrap.append(h("section", { class: "panel" }, h("h2", {}, "Book by book"),
    table([{ k: "title", label: "Book" }, { k: "paragraphs", label: "Paragraphs", num: true, fmt: v => fmt(v) }, { k: "words", label: "Words", num: true, fmt: v => fmt(v) },
      { k: "share", label: "% of the book's narration", num: true, fmt: v => fmt(v, 1) }, { k: "per_para", label: "Words per paragraph", num: true, fmt: v => fmt(v, 1) },
      { k: "exceptions", label: "Set by paragraph", num: true, title: "Paragraphs you gave to this narrator as exceptions" }],
      P.per_book, { csvName: `${R.name} by book` })));
  wrap.append(narratorVoicePanel(P));
  return wrap;
}

/** "What's distinctive" for a narrator: words markedly more typical of their narration than of the chosen comparison. */
function narratorVoicePanel(P) {
  const R = P.role, box = h("section", { class: "panel" }, h("h2", {}, "What's distinctive"));
  const out = h("div");
  const target = { kind: "narration", id: R.id, name: R.name };
  const refs = { narration: { kind: "narration", id: "all", name: "all other narration" }, others: { kind: "others" },
    ...(R.unit ? { own: { kind: "unit", id: R.unit, name: R.unit_name } } : {}) };
  const labels = { narration: "Other narration", others: "Everyone's dialogue", own: "Their own dialogue" };
  if (!refs[S.narrRef]) S.narrRef = "narration";
  const run = async () => {
    out.replaceChildren(loading("Comparing…"));
    const r = await api("/api/dialogue/voice", withBooks({ target, reference: refs[S.narrRef], unit: "word", ...S.stat }));
    const s = r.summary;
    out.replaceChildren(
      h("p", { class: "small muted" }, `${R.name}: ${plural(s.c, "word")}. Compared with ${s.reference}: ${plural(s.d, "word")}.`),
      s.d === 0 ? h("p", { class: "warn small" }, "The comparison side has no words in these books, so there is nothing to compare with.") : null,
      table(statCols(s, false), r.rows, { limit: 40, csvName: `${R.name} distinctive words`, rowClass: row => row.sig ? "" : "dim",
        onRow: row => { S.corp.scope = { kind: "narration" }; saveCorp(); goKwic(...itemQuery(row.item, "word")); }, empty: "Nothing distinctive at these settings." }),
      statNote(s));
  };
  box.append(h("p", { class: "small muted", style: { marginTop: 0 } }, "Words markedly more typical of this narration than of the comparison. Click a word for its concordance in narration."),
    statControls(run, { pre: [h("div", { class: "fld" }, "Compared with", seg(Object.keys(refs).map(k => [k, labels[k]]), S.narrRef, v => { S.narrRef = v; box.replaceWith(narratorVoicePanel(P)); }))] }), out);
  run();
  return box;
}
