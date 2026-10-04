"use strict";
/* ---------- router ---------- */
/* The address bar decides the page: #/<tab>/<sub>/<more…>. This is the last script to load, so every renderX exists. */

/** Show the page for the current address (below). */
async function renderPage() {
  const [, tab = "entities", arg] = location.hash.split("/");
  const shownTab = tab === "chapters" ? "narrative" : tab;              // the chapter editor is reached from Arcs and style
  document.querySelectorAll("#tabs a").forEach(a => a.classList.toggle("on", a.dataset.tab === shownTab));
  $("#drawer").hidden = true;
  const main = $("#main");
  if (!S.lib) await loadLib();
  if (!S.lib.books.length && tab !== "books") { location.hash = "#/books"; return; }
  // the page's plural-group checkbox; an entity profile shows its own beside "Plural group of" instead
  $("#pluralSlot").replaceChildren(PLURAL_TABS.has(tab) && !(tab === "entities" && arg) ? pluralBox() : "");
  // what's selected (book/collection/series) and a way back from a drill-down; the Library page shows this in its own table instead
  if (tab === "books") $("#viewSlot").replaceChildren(); else viewingBar();
  try {
    if (tab === "books") await renderBooks(main);
    else if (tab === "compare") await renderCompare(main);
    else if (tab === "network") await renderNetwork(main);
    else if (tab === "links") await renderLinks(main);
    else if (tab === "narrators") await renderNarrators(main);
    else if (tab === "dialogue") await renderDialogue(main, arg);
    else if (tab === "corpus") await renderCorpus(main, arg);
    else if (tab === "narrative") await renderNarrative(main, arg);
    else if (tab === "topics") await renderTopics(main, arg, ...location.hash.split("/").slice(3));
    else if (tab === "read") await renderRead(main, arg, location.hash.split("/")[3]);
    else if (tab === "chapters") await renderRead(main, arg, location.hash.split("/")[3], true);
    else await renderEntities(main, arg ? decodeURIComponent(arg) : null);
  } catch (e) {
    if (!e.handled) console.error(e);
    main.replaceChildren(h("div", { class: "panel warn" }, "Something went wrong: " + e.message));
  }
}

/** Re-draw the current page. Renders never overlap: if the address changes while one is still loading, the newest
    request waits for it and then runs, so a slow older page can't overwrite a newer one. */
const render = (() => {
  let running = false, again = false;
  return async function render() {
    if (running) { again = true; return; }
    running = true;
    try {
      do { again = false; await renderPage(); } while (again);
    } finally { running = false; }
  };
})();
window.addEventListener("hashchange", render);
render();
