"use strict";
/* ---------- Workspaces ---------- */
/* A workspace is a separate library (its own books folders, links, groups, collections, corrections, topic models; see
   core/workspaces.py). The picker in the top bar switches between them; the Library page's "Workspaces" section makes, imports,
   renames, removes and deletes them. Switching reloads the page, so everything on screen belongs to one workspace. */

/** The workspaces, from /api/workspaces: [{id, name, path, active, missing, own_books, owned}]. */
S.ws = [];

/** Redraw the picker in the top bar from `S.ws`. */
function drawWorkspacePicker() {
  $("#wsSel").replaceChildren(...S.ws.map(w => h("option", { value: w.id, selected: w.active, disabled: w.missing }, w.missing ? w.name + " (folder missing)" : w.name)));
}

/** Fetch the workspaces and redraw the picker. */
async function loadWorkspaces() {
  S.ws = (await api("/api/workspaces")).workspaces;
  drawWorkspacePicker();
}

/** Open another workspace on the server, then reload the page so that nothing from the old one stays on screen. */
async function switchWorkspace(id) {
  try {
    await api("/api/workspaces/activate", { id });
    reloadPage();
  } catch (e) {
    drawWorkspacePicker();                               // it didn't open (the error is shown): the picker goes back to the one in use
    throw e;
  }
}
$("#wsSel").onchange = e => switchWorkspace(e.target.value);

/** The "Workspaces" section of the Library page: the list with what can be done to each, and forms to make and import one. */
async function workspacePanel() {
  await loadWorkspaces();
  const listBox = h("div"), askBox = h("div", { class: "row", style: { flexWrap: "wrap", marginTop: "8px" } });
  /** Send a change, keep the list the server answers with, redraw everything that shows it. Returns the reply. */
  const change = async (path, body, message) => {
    const r = await api(path, body);
    S.ws = r.workspaces;
    drawWorkspacePicker(); draw(); askBox.replaceChildren();
    if (message) toast(message);
    return r;
  };
  /** An inline question in the box under the list: one text field, OK and Cancel. */
  const ask = (label, initial, ok) => {
    const box = h("input", { type: "text", value: initial, placeholder: "Name", "aria-label": label });
    const go = () => ok(box.value).catch(() => {});
    box.onkeydown = e => { if (e.key === "Enter") go(); if (e.key === "Escape") askBox.replaceChildren(); };
    askBox.replaceChildren(box, h("button", { class: "btn small primary", onclick: go }, "OK"), h("button", { class: "btn small", onclick: () => askBox.replaceChildren() }, "Cancel"));
    box.focus();
  };
  /** Deleting asks for the workspace's name, typed out, before the button works (the server checks it too). */
  const askDelete = w => {
    const box = h("input", { type: "text", placeholder: w.name, "aria-label": `Type “${w.name}” to delete it`, autocomplete: "off" });
    const go = h("button", { class: "btn small primary", disabled: true,
      onclick: () => change("/api/workspaces/delete", { id: w.id, name: box.value }, `Deleted “${w.name}”.`).catch(() => {}) }, "Delete for good");
    box.oninput = () => { go.disabled = box.value !== w.name; };
    askBox.replaceChildren(
      h("div", { class: "warn small", style: { flex: "1 1 100%" } }, `This deletes “${w.name}” and everything in its folder (${w.path}): its copied books, links, groups, corrections and topic models. It can't be undone. Type its name to confirm:`),
      box, go, h("button", { class: "btn small", onclick: () => askBox.replaceChildren() }, "Cancel"));
    box.focus();
  };
  const row = w => h("tr", {},
    h("td", {}, h("strong", {}, w.name), w.active ? h("span", { class: "tag", style: { marginLeft: "8px" } }, "In use") : null,
      w.own_books ? h("div", { class: "small muted" }, "Holds its own copy of its books") : null,
      w.missing ? h("div", { class: "warn small" }, "Its folder is missing") : null),
    h("td", {}, h("code", { class: "small" }, w.path)),
    h("td", {}, h("div", { class: "row", style: { flexWrap: "wrap", gap: "4px" } },
      !w.active && !w.missing ? h("button", { class: "btn small primary", onclick: () => switchWorkspace(w.id).catch(() => {}) }, "Switch to") : null,
      h("button", { class: "btn small", onclick: () => ask("Rename", w.name, name => change("/api/workspaces/" + encodeURIComponent(w.id), { name }, "Renamed.")) }, "Rename"),
      w.id !== "default" && !w.active ? h("button", { class: "btn small", title: "Take it off the list; its files stay where they are",
        onclick: () => { if (confirm(`Remove “${w.name}” from the list? Its files stay where they are.`)) change("/api/workspaces/forget", { id: w.id }, "Removed from the list.").catch(() => {}); } }, "Remove from list") : null,
      w.owned && !w.active ? h("button", { class: "btn small", title: "Delete its folder and everything in it", onclick: () => askDelete(w) }, "Delete…") : null)));
  function draw() {
    listBox.replaceChildren(h("div", { class: "tbl-wrap" }, h("table", { class: "t2" },
      h("thead", {}, h("tr", {}, ["Workspace", "Folder", ""].map(x => h("th", {}, x)))), h("tbody", {}, S.ws.map(row)))));
  }

  // ----- make an empty one, or import an export zip -----
  const newName = h("input", { type: "text", placeholder: "Name", "aria-label": "Name of the new workspace", style: { width: "180px" } });
  const newFolder = h("input", { type: "text", placeholder: "Folder with books (optional)", "aria-label": "Folder with books", style: { width: "340px" } });
  const create = async () => {
    const folder = newFolder.value.trim(), r = await change("/api/workspaces", { name: newName.value, sources: folder ? [folder] : null }, "Workspace made. Use “Switch to” to open it.");
    newName.value = newFolder.value = "";
    return r;
  };
  const zipFile = h("input", { type: "file", accept: ".zip,application/zip", "aria-label": "Export zip to import" });
  const zipName = h("input", { type: "text", placeholder: "Name (optional)", "aria-label": "Name for the imported workspace", style: { width: "180px" } });
  const importBtn = h("button", { class: "btn", onclick: async () => {
    const file = zipFile.files[0];
    if (!file) return toast("Choose an export zip first.", true);
    importBtn.disabled = true;
    toast("Importing… this can take a while for a large corpus.");
    try {
      const name = zipName.value.trim(), r = await api("/api/workspaces/import?name=" + encodeURIComponent(name), file);
      S.ws = r.workspaces; drawWorkspacePicker(); draw();
      zipFile.value = zipName.value = "";
      toast(`Imported “${S.ws.find(w => w.id === r.id).name}”. Use “Switch to” to open it.`);
    } catch (e) { /* shown as a message by api() */ } finally { importBtn.disabled = false; }
  } }, "Import");

  draw();
  return h("section", { class: "panel" }, h("h2", {}, "Workspaces"),
    h("p", { class: "small muted", style: { marginTop: 0 } }, "A workspace is a separate library: its own folders of books, links between entities, groups, collections, corrections, topic models and settings. Switch to work on another corpus; nothing is shared or merged between workspaces."),
    listBox, askBox,
    h("div", { class: "row", style: { marginTop: "12px", flexWrap: "wrap" } }, newName, newFolder,
      h("button", { class: "btn", onclick: () => create().catch(() => {}) }, "Make a workspace")),
    h("div", { class: "row", style: { marginTop: "8px", flexWrap: "wrap" } }, zipFile, zipName, importBtn),
    note("About workspaces",
      "The Default workspace is the analyser's own data folder and reads books from the folders listed under “Where to find books”. A workspace you make reads books from the folder you give it (add more under “Where to find books” once you have switched to it).",
      "Import makes a workspace from a zip made with “Export selected books (.zip)”: the books are copied into the workspace together with your links, groups, collections, corrections, topic models and reference files, so the zip works on any computer. Importing never changes another workspace.",
      "Remove from list only forgets a workspace; its files stay. Delete removes the folder of a workspace the analyser made (an imported one, or one made here) with everything in it, after you type its name. The Default workspace and the one in use can be neither removed nor deleted, and books in folders a workspace merely points at are never touched."));
}

loadWorkspaces().catch(() => {});                          // fill the picker (a failure is shown as a message)
