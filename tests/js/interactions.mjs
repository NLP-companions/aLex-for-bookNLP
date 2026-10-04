// Drive the interface the way a person would (clicks, typing, selects) and check what happens.
// usage: node interactions.mjs http://127.0.0.1:8766
import { api, openPage, sleep, waitFor } from "./harness.mjs";

const base = process.argv[2];
const failures = [], passed = [];
const page = await openPage(base);
const w = page.window;
const ALL = ["alpha", "beta", "gamma"];

const $$ = s => page.$$(s);
const byText = (sel, re) => $$(sel).find(e => re.test(e.textContent.trim()));
const button = (re, within = "#main") => byText(`${within} button, ${within} .btn`, re);
const drawerText = () => (page.$("#drawerBody") || {}).textContent || "";
const drawerOpen = () => page.$("#drawer") && !page.$("#drawer").hidden;
async function until(fn, what, ms = 15000) { await waitFor(fn, what, ms); }       // generous: a busy computer must not fail a test
async function scenario(name, fn) {
  const before = page.errors.length;
  try {
    await fn();
    const errs = page.errors.slice(before);
    if (errs.length) throw new Error("script errors: " + errs.join(" | ").slice(0, 400));
    const bad = name.includes("bad query") ? [] : page.problems();
    if (bad.length) throw new Error(bad.join(" | "));
    passed.push(name);
  } catch (e) { failures.push(`${name}: ${e.message}`); }
  await page.settle("end of " + name).catch(() => {});
}
const fmtNum = n => page.eval(`fmt(${n})`);
function expect(cond, message) { if (!cond) throw new Error(message); }

// a fresh start for each scenario
const ORIGINAL_SOURCES = (await api(base, "/api/library")).sources;
async function reset() {
  for (const b of ALL) await api(base, "/api/books/" + b, { title: "", author: "", year: "", series: "", tags: [], pinned: null });
  page.$("#toast").hidden = true;
  for (const c of (await api(base, "/api/library")).collections) await api(base, "/api/collections/delete", { id: c.id });
  for (const g of (await api(base, "/api/library")).groups) await api(base, "/api/groups/delete", { id: g.id });
  for (const b of ALL) await api(base, "/api/annot/narrator", { book: b, narrator: null });
  for (const b of ALL) await api(base, "/api/narrative/chapters", { book: b, action: "reset" });
  for (const m of (await api(base, "/api/topics/models")).models) await api(base, "/api/topics/delete", { id: m.id });
  await api(base, "/api/settings", { sources: ORIGINAL_SOURCES, min: { PER: 2, LOC: 2, FAC: 2, GPE: 2, VEH: 2, ORG: 2, VAR: 2 }, count_mode: "per_book", conv_gap: 100 });
  w.localStorage.clear();
  await page.eval("S.sel = null; S.units = null; S.entMulti = false; S.entSel = []; S.entType = 'PER'; S.entQuery = ''; S.cmp = { a: null, b: null, rel: 'agent' }; loadLib()");
}

await scenario("books: edit a title, choose books, change minimum, add a bad folder", async () => {
  await reset();
  await page.go("#/books");
  const title = $$("input[type=text]").find(i => i.value === "alpha");
  expect(title, "title input for alpha");
  expect($$("#main button").some(b => /Original text/.test(b.textContent)), "download button for a book's original text");
  page.change(title, "Alpha Book");
  await until(() => page.eval("S.lib.books.find(b => b.id === 'alpha').title") === "Alpha Book", "title saved locally");
  expect((await api(base, "/api/library")).books.find(b => b.id === "alpha").title === "Alpha Book", "title saved on the server");
  const beta = $$("input[type=checkbox][aria-label^='Use']")[1];
  beta.checked = false; page.change(beta);
  expect(JSON.stringify(page.eval("S.sel")) === JSON.stringify(["alpha", "gamma"]), "selection is alpha and gamma");
  expect(/2 of 3 books/.test(page.$("#selBtn").textContent), "button says 2 of 3 books");
  const per = $$("input[aria-label^='Minimum for']")[0];
  page.change(per, "3");
  await until(() => page.eval("S.lib.settings.min.PER") === 3, "minimum saved");
  await page.settle();
  const src = page.$("input[placeholder='/path/to/folder/with/books']");
  src.value = "/no/such/folder";
  page.click(button(/Add folder/));
  await until(() => /Folder not found/.test(page.text()), "problem shown");
  const row = $$("#main .row").find(r => r.textContent.includes("/no/such/folder"));
  page.click([...row.querySelectorAll("button")].find(b => /Remove/.test(b.textContent)));
  await until(() => !/Folder not found/.test(page.text()), "problem gone");
});

await scenario("books: export the selected books as a zip", async () => {
  await reset();
  await page.go("#/books");
  const beta = $$("input[type=checkbox][aria-label^='Use']")[1];
  beta.checked = false; page.change(beta);                                  // alpha and gamma stay selected
  let blob = null, fileName = null;
  const realClick = w.HTMLAnchorElement.prototype.click;
  w.URL.createObjectURL = b => { blob = b; return "blob:test"; };           // catch what would be downloaded (jsdom can't follow the link)
  w.HTMLAnchorElement.prototype.click = function () { fileName = this.download; };
  const btn = button(/Export selected books/);
  expect(btn, "export button on the Library page");
  page.click(btn);
  await until(() => /Exported 2 books/.test(page.$("#toast").textContent), "export done");
  expect(blob && blob.type === "application/zip" && blob.size > 0, "a zip was downloaded");
  const bytes = new Uint8Array(await blob.arrayBuffer());
  expect(bytes[0] === 0x50 && bytes[1] === 0x4b, "it is a zip file");
  expect(/^analyser-export-\d{8}-\d{6}\.zip$/.test(fileName), "the file is named by the server: " + fileName);
  expect(!btn.disabled, "the button is usable again");
  w.URL.createObjectURL = () => "blob:test";
  w.HTMLAnchorElement.prototype.click = realClick;
});

await scenario("workspaces: make, rename, switch, remove, and delete one by typing its name", async () => {
  await reset();
  await page.go("#/books");
  const panelOf = () => $$("#main section.panel").find(p => /^Workspaces/.test(p.querySelector("h2").textContent));
  const rowOf = name => [...panelOf().querySelectorAll("tbody tr")].find(r => r.querySelector("strong").textContent === name);
  const rowButton = (name, re) => [...rowOf(name).querySelectorAll("button")].find(b => re.test(b.textContent));
  const listed = async () => (await api(base, "/api/workspaces")).workspaces;
  const pickerText = () => [...page.$("#wsSel").options].map(o => o.text).join();
  expect(panelOf() && rowOf("Default"), "a Workspaces section on the Library page lists the Default workspace");
  expect(!rowButton("Default", /Switch|Remove|Delete/), "the workspace in use has no switch, remove or delete button");
  expect(pickerText() === "Default", "the picker in the top bar lists it");

  const make = async name => {
    panelOf().querySelector("input[aria-label='Name of the new workspace']").value = name;
    page.click(button(/Make a workspace/));
    await until(() => rowOf(name), `${name} is listed`);
  };
  await make("Scratch");
  expect(pickerText() === "Default,Scratch", "the picker offers the new workspace");
  expect((await listed()).length === 2, "the server has it");

  page.click(rowButton("Scratch", /Rename/));
  page.input(panelOf().querySelector("input[aria-label='Rename']"), "Practice");
  page.click([...panelOf().querySelectorAll("button")].find(b => b.textContent === "OK"));
  await until(() => rowOf("Practice"), "renamed");

  // switching: the server opens the workspace and the page is told to reload (jsdom can't, so the call is replaced)
  page.eval("window.__reloads = 0; reloadPage = () => { window.__reloads++; }");
  const picker = page.$("#wsSel");
  page.change(picker, "scratch");                                       // renaming doesn't change the id
  await until(() => page.eval("window.__reloads") === 1, "the page reloads after switching with the picker");
  expect((await listed()).find(x => x.active).id === "scratch", "the server is in the other workspace");
  page.change(picker, "default");
  await until(() => page.eval("window.__reloads") === 2, "and after switching back");
  expect((await listed()).find(x => x.active).id === "default", "the server is back in Default");
  page.click(rowButton("Practice", /Switch to/));
  await until(() => page.eval("window.__reloads") === 3, "the row's button switches too");
  await api(base, "/api/workspaces/activate", { id: "default" });

  // removing from the list (asks first; the files stay)
  await make("Temp");
  page.click(rowButton("Temp", /Remove from list/));
  await until(() => !rowOf("Temp"), "Temp is gone from the list");

  // deleting needs the name typed out
  page.click(rowButton("Practice", /Delete/));
  const go = [...panelOf().querySelectorAll("button")].find(b => b.textContent === "Delete for good");
  const typed = panelOf().querySelector("input[aria-label^='Type']");
  expect(go.disabled, "Delete for good starts disabled");
  page.input(typed, "practice");
  expect(go.disabled, "a name that differs (even in case) keeps it disabled");
  page.input(typed, "Practice");
  expect(!go.disabled, "the exact name enables it");
  page.click(go);
  await until(() => !rowOf("Practice"), "Practice is deleted");
  expect((await listed()).map(x => x.id).join() === "default" && pickerText() === "Default", "only Default is left, on the server and in the picker");
  expect(!rowOf("Default").querySelector("button[title^='Delete']"), "Default can't be deleted");
});

await scenario("theme: the button cycles auto/light/dark, applies it and remembers the choice", async () => {
  await reset();
  const btn = page.$("#themeBtn");
  const label = () => btn.textContent;
  const applied = () => w.document.documentElement.dataset.theme || "auto";
  const start = label();
  expect(["Theme: Auto", "Theme: Light", "Theme: Dark"].includes(start), "a known starting label: " + start);
  page.click(btn);
  expect(label() !== start, "the label changed");
  expect(label() === "Theme: " + applied()[0].toUpperCase() + applied().slice(1), "<html data-theme> matches the button");
  expect(JSON.parse(w.localStorage.getItem("analyser.theme")) === applied(), "the choice was saved");
  page.click(btn); page.click(btn);
  expect(label() === start, "three clicks return to the same theme");
});

await scenario("entities: filter by type and name, open a profile, tabs, evidence, tags", async () => {
  await reset();
  await page.go("#/entities");
  const names = () => $$("#main .ent-item .cnt").map(n => +n.textContent.replace(/,/g, ""));
  const normal = names();
  expect(normal.length > 1 && normal.every((n, i) => i === 0 || n <= normal[i - 1]), "most mentioned first by default");
  const dirBtn = page.$("#main .head button.btn.small");
  expect(dirBtn, "the sort-direction button");
  page.click(dirBtn);
  const reversed = names();
  expect(reversed.join() === normal.slice().reverse().join(), "the reverse button flips the order");
  page.click(dirBtn);
  expect(names().join() === normal.join(), "clicking again restores it");
  page.click(byText("#main .chip", /^LOC/));
  await until(() => $$("#main .ent-item").length > 0 && $$("#main .ent-item .nm").every(n => /Street|street/.test(n.textContent)), "only places listed");
  page.click(byText("#main .chip", /^PER/));
  await page.settle();
  const q = page.$("#main input[type=search]");
  page.input(q, "watson");
  await until(() => $$("#main .ent-item .nm").length > 0 && $$("#main .ent-item .nm").every(n => /Watson/.test(n.textContent)), "filtered by name");
  page.click($$("#main .ent-item")[0]);
  await until(() => /How they're referred to/.test(page.text()), "profile shown");
  expect(/Watson/.test(page.$("#main h1").textContent), "profile is Watson's");
  page.click(byText("#main .subtabs button", /Modifiers|Possessions/));
  page.click(byText("#main .subtabs button", /Actions/));
  const row = $$("#main table.t2 tbody tr.click")[0];
  page.click(row);
  await until(() => drawerOpen() && /sentence/.test(drawerText()) && $$("#drawerBody .ev").length > 0, "evidence sentences");
  page.window.document.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Escape" }));
  expect(!drawerOpen(), "Escape closes the drawer");
  const tag = page.$("#main .tag-edit input");
  tag.value = "narrator";
  tag.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => $$("#main .tag-edit .tag").some(t => /narrator/.test(t.textContent)), "tag added");
  expect((await api(base, "/api/library")).tags.includes("narrator"), "tag saved");

  const renameBtn = byText("#main .phead-id button", /^Rename$/);
  expect(renameBtn, "a Rename link next to the name");
  page.click(renameBtn);
  const nameInp = page.$("#main .phead-id input[type=text]");
  nameInp.value = "Doctor Watson";
  nameInp.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => (page.$("#main h1") || {}).textContent === "Doctor Watson", "renamed");
  const resetBtn = () => byText("#main .phead-id button", /^Reset$/);
  await until(resetBtn, "a Reset link appears once renamed");
  page.click(resetBtn());
  await until(() => (page.$("#main h1") || {}).textContent === "Watson", "Reset restores the name found in the books");

  const descBtn = byText("#main .phead-id button", /Description/);
  expect(descBtn, "a description link");
  page.click(descBtn);
  const descInp = page.$("#main .phead-id input[type=text]");
  descInp.value = "Loyal friend";
  descInp.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => /Loyal friend/.test(page.$("#main .phead-id").textContent), "description saved");
});

await scenario("book by book: several books sort by year, undated last, and the book name drills down to one", async () => {
  await reset();
  await api(base, "/api/books/alpha", { year: 1902 });
  await api(base, "/api/books/beta", { year: 1890 });     // gamma stays undated: it must sort last
  const p1 = await api(base, "/api/links/link", { a: "e:alpha:1", b: "e:beta:5" });
  await api(base, "/api/links/link", { a: p1.id, b: "e:gamma:3" });
  await page.eval("S.units = null; loadLib()");
  await page.go("#/entities/" + encodeURIComponent(p1.id));
  await until(() => /Book by book/.test(page.text()), "profile with a book-by-book section");
  const section = byText("#main h2", /^Book by book$/).closest("section");
  const rows = [...section.querySelectorAll("table.t2 tbody tr")].map(r => r.querySelector("td").textContent.trim());
  expect(rows[0] === "beta" && rows[1] === "alpha" && rows[2] === "gamma", "beta (1890), alpha (1902), then undated gamma: " + rows.join(","));
  const link = [...section.querySelectorAll("a")].find(a => a.title === "Show just this book" && a.textContent.trim() === "beta");
  expect(link, "beta's name is a drill-down link");
  page.click(link);
  await until(() => JSON.stringify(page.eval("S.sel")) === '["beta"]', "selection narrowed to beta alone");
  await until(() => /1 of 3 books/.test(page.$("#selBtn").textContent), "book-selection button updated");
  await until(() => /Viewing.*beta/.test(page.$("#viewSlot").textContent), "the viewing bar names the drilled-down book");
  const back = page.$("#viewSlot button");
  expect(back && /Back/.test(back.textContent), "a Back button appears once narrowed");
  page.click(back);
  await until(() => JSON.stringify(page.eval("S.sel")) === "null", "Back restores the wider selection");
  await until(() => !page.$("#viewSlot button"), "Back button gone once restored");
});

await scenario("entity page: Book by book and What's distinctive share the significance settings, and both follow a change made in either", async () => {
  await reset();
  const p1 = await api(base, "/api/links/link", { a: "e:alpha:1", b: "e:beta:5" });
  await page.eval("S.units = null; loadLib()");
  try {
    await page.go("#/entities/" + encodeURIComponent(p1.id));
    await until(() => byText("#main h2", /^Book by book$/) && byText("#main h2", /What's distinctive/), "both panels on one profile");
    const minFreq = h2 => { const sec = byText("#main h2", h2).closest("section"); return [...sec.querySelectorAll("label")].find(l => /^Minimum frequency/.test(l.textContent.trim())).querySelector("input"); };
    const setMin = (h2, v) => { const i = minFreq(h2); i.value = String(v); i.dispatchEvent(new w.Event("change", { bubbles: true })); };
    const startVal = minFreq(/^Book by book$/).value;
    expect(minFreq(/What's distinctive/).value === startVal, "both start on the same minimum frequency");
    setMin(/^Book by book$/, 6);
    await until(() => minFreq(/What's distinctive/).value === "6", "What's distinctive follows a change made in Book by book");
    setMin(/What's distinctive/, 9);
    await until(() => minFreq(/^Book by book$/).value === "9", "and Book by book follows one made in What's distinctive");
  } finally {
    await page.eval("S.stat.min_freq = 3");
    await api(base, "/api/links/unlink_all", { id: p1.id }).catch(() => {});
    await page.eval("S.units = null");
  }
});

await scenario("viewing bar: names a single book, a whole collection or series, or several unrelated books", async () => {
  await reset();
  await page.go("#/corpus");
  const label = () => page.$("#viewSlot .view-label").textContent;
  await api(base, "/api/books/alpha", { year: 1902 });
  const coll = await api(base, "/api/collections", { name: "Casebook" });
  await api(base, "/api/collections/" + coll.id, { add: ["alpha", "beta"] });
  await page.eval("S.lib = null; loadLib()");
  await page.eval("setSel(['alpha','beta']); render()");
  await until(() => label() === "Casebook", "the whole collection is named: " + label());
  await page.eval("setSel(['alpha']); render()");
  await until(() => label() === "alpha", "a single book's own title (falls back to its id, untitled here): " + label());
  await page.eval("setSel(['alpha','beta','gamma']); render()");
  await until(() => label() === "Various", "unrelated books together: " + label());
});

await scenario("dialogue: quotes drawer and the quote editor", async () => {
  await reset();
  await page.go("#/dialogue/speakers");
  page.click($$("#main table.t2 tbody tr.click")[0]);
  await until(() => drawerOpen() && $$("#drawerBody .ev").length > 0, "quotes in the drawer");
  page.click(byText("#drawerBody a", /^Correct$/));
  await until(() => page.$("#drawerBody .qedit .qrow"), "quote editor");
  page.click(byText("#drawerBody .qedit button", /Everyone present/));
  await until(() => /Set by you/.test(page.$("#drawerBody .qedit").textContent), "correction saved");
  page.click(byText("#drawerBody .qedit button", /Back to the estimate/));
  await until(() => /Estimated/.test(page.$("#drawerBody .qedit").textContent), "back to the estimate");
  await page.go("#/dialogue/conversations");
  expect(/conversation/.test(page.text()), "conversations listed");
  await page.go("#/dialogue/quotes");
  const verb = $$("#main input[type=search]").find(i => /whisper/.test(i.placeholder));
  page.change(verb, "say");
  await until(() => /quote/.test(page.text()) && $$("#main .ev").length > 0, "filtered quotes");
});

await scenario("dialogue: sentence-type filter (questions/exclamations/statements) in quotes, style and speaking style; Speech verbs' two filters stay independent; a compact select on an entity's own speech panel", async () => {
  await reset();
  await page.go("#/dialogue/speakers");          // in case the previous scenario already left the hash on #/dialogue/quotes: force a real navigation, not a no-op
  await page.go("#/dialogue/quotes");
  const count = () => +(/^([\d,]+) quote/.exec(page.$("#main .tbl-foot span").textContent) || [0, "0"])[1].replace(",", "");
  await until(() => count() > 0, "quotes loaded");
  const all = count();
  const typeSel = () => [...$$("#main select")].find(s => [...s.options].some(o => o.textContent === "Statements"));
  page.change(typeSel(), "question");
  await until(() => count() === 0, "the fixture never writes a literal ? or !, so no quote is a question");
  page.change(typeSel(), "statement");
  await until(() => count() === all, "every quote is a statement by punctuation, so this is back to all of them");
  page.change(typeSel(), "");
  await until(() => count() === all, "back to no filter");

  await page.go("#/dialogue/voice");
  await until(() => byText("#main label", /Sentence type/), "the same filter appears under Speaking style");
  expect(byText("#main label.inline", /Weigh the speech verb too/), "and the classification-rule checkbox");
  // Speaking style and Distinctive vocabulary each have their own filter, and so does the Quotes page: none changes another
  const voiceSels = () => [...$$("#main select")].filter(s => [...s.options].some(o => o.textContent === "Statements"));
  expect(voiceSels().length === 2, "Speaking style and Distinctive vocabulary each have a Sentence type select");
  page.change(voiceSels()[0], "question");
  await until(() => voiceSels()[0].value === "question", "Speaking style filtered to questions");
  expect(voiceSels()[1].value === "", "Distinctive vocabulary's own filter is unaffected");
  page.change(voiceSels()[1], "exclaim");
  await until(() => voiceSels()[1].value === "exclaim", "Distinctive vocabulary filtered to exclamations");
  expect(voiceSels()[0].value === "question", "and Speaking style's stays on questions");
  await page.go("#/dialogue/quotes");
  await until(() => count() > 0, "Quotes reloaded");
  expect(typeSel().value === "" && count() === all, "Quotes has its own filter: unaffected by How they speak's");
  await page.go("#/dialogue/voice");
  await until(() => voiceSels().length === 2, "How they speak again");
  expect(voiceSels()[0].value === "question" && voiceSels()[1].value === "exclaim", "How they speak remembers each filter separately");
  page.change(voiceSels()[0], "");
  page.change(voiceSels()[1], "");

  await page.go("#/dialogue/verbs");
  await until(() => /How speech is introduced/.test(page.text()) && byText("#main label", /Sentence type/), "and under How speech is introduced");
  const verbsSel = () => [...$$("#main select")].find(s => [...s.options].some(o => o.textContent === "Statements"));
  const verbQuotes = () => +((/of ([\d,]+) quote/.exec(page.text()) || [0, "0"])[1] || "0").toString().replace(/,/g, "");
  const before = verbQuotes();
  page.change(verbsSel(), "question");
  await until(() => /0 of 0 quote/.test(page.text()), "no questions overall either");
  page.change(verbsSel(), "");
  await until(() => verbQuotes() === before, "back to no filter");

  const holmes = (await api(base, "/api/units", { books: ALL })).rows.find(r => r.name === "Holmes" && r.books[0] === "alpha").id;
  const targetSection = byText("#main h2", /One speaker or group/).closest(".panel");
  const speakerBox = targetSection.querySelector("input[type=search]");
  speakerBox.focus();
  page.input(speakerBox, "Holmes");
  await until(() => targetSection.querySelectorAll(".sugg div").length > 0, "suggestions for a speaker");
  targetSection.querySelectorAll(".sugg div")[0].dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  await until(() => /quotes with a speech verb/.test(targetSection.textContent), "verbs for Holmes, in “One speaker or group”");
  expect([...targetSection.querySelectorAll("label")].find(l => /Sentence type/.test(l.textContent)), "which has its own Sentence type filter too");
  const targetText = () => targetSection.textContent.match(/Holmes:[^.]+\./)?.[0];
  const targetBefore = targetText();
  const targetSel = () => [...targetSection.querySelectorAll("select")].find(s => [...s.options].some(o => o.textContent === "Statements"));

  // the two filters must be independent: changing "How speech is introduced" leaves "One speaker or group" alone, and back
  page.change(verbsSel(), "question");
  await until(() => /0 of 0 quote/.test(page.text()), "How speech is introduced filters down to nothing");
  expect(targetText() === targetBefore, "but One speaker or group, filtered separately, is untouched by it");
  page.change(verbsSel(), "");
  await until(() => verbQuotes() === before, "How speech is introduced back to no filter");

  page.change(targetSel(), "question");
  await until(() => /: 0 quotes with a speech verb/.test(targetSection.textContent), "no questions for Holmes either");
  expect(verbQuotes() === before, "and How speech is introduced, filtered separately, is untouched by that in turn");
  page.change(targetSel(), "");
  await until(() => /quotes with a speech verb/.test(targetSection.textContent) && !/: 0 quotes with a speech verb/.test(targetSection.textContent), "back to no filter for the target too");

  await page.go("#/entities/" + encodeURIComponent(holmes));
  await until(() => byText("#main label", /Sentence type/), "the entity's own Speech panel has a compact sentence-type select");
  expect(byText("#main label.inline", /^Weigh the speech verb$/) && !byText("#main label.inline", /Weigh the speech verb too/), "with its own compact checkbox, separate from every Dialogue tab's");
  const quotesFact = () => +((/^[\d,]+/.exec(($$("#main .facts-inline div")[0] || {}).textContent || "") || ["0"])[0].replace(/,/g, ""));
  await until(() => quotesFact() > 0, "Holmes has quotes");
  const entSel = () => [...$$("#main select")].find(s => [...s.options].some(o => o.textContent === "Statements"));
  page.change(entSel(), "question");
  await until(() => /No quotes are attributed/.test(page.text()), "no questions for Holmes either, filtered right on the entity page");
  page.change(entSel(), "");
  await until(() => quotesFact() > 0, "back to no filter");
  const verbsHead = byText("#main h3", /Speech verbs/);
  expect(verbsHead, "the Speech verbs section shows too");
  expect(verbsHead.parentElement.textContent.includes("say"), "with a row for “say”, reflecting the earlier fix where this table used to ignore the filter");
});

await scenario("dialogue: verbs for one speaker through the picker", async () => {
  await reset();
  await page.go("#/dialogue/verbs");
  const box = page.$("#main .picker input[type=search]");
  box.focus();
  page.input(box, "Holmes");
  await until(() => $$("#main .picker .sugg div").length > 0, "suggestions");
  $$("#main .picker .sugg div")[0].dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  await until(() => /with a speech verb/.test(page.text()), "verbs for the speaker");
});

await scenario("dialogue: In-Depth Who Speaks scopes and compares by gender, tag, entity or group", async () => {
  await reset();
  await page.go("#/dialogue/indepth");
  await until(() => byText("#main h2", /Dialogue in each book/), "the default view matches Who speaks");
  expect($$("#main table").length && !$$("#main .facts-inline").length, "nothing chosen yet: the whole-selection tables, not pooled facts");

  const seg = txt => [...$$("#main .seg button")].find(b => b.textContent === txt);
  page.click(seg("Gender"));
  await until(() => $$("#main .facts-inline").length > 0, "a pooled Speakers card appears for the gender scope");
  const colQuotes = root => +((/^[\d,]+/.exec((root.querySelector(".facts-inline div") || {}).textContent || "") || ["0"])[0].replace(/,/g, ""));
  const genderQuotes = colQuotes(page.$("#main"));
  expect(genderQuotes > 0, "the gender scope has quotes");

  page.click(seg("Compare"));
  await until(() => /Choose two things to compare/.test(page.text()), "compare mode needs a second side");

  const refFld = byText("#main .fld", /Compared with/);
  const refBox = refFld.querySelector("input[type=search]");
  refBox.focus();
  page.input(refBox, "Holmes");
  await until(() => refFld.querySelectorAll(".sugg div").length > 0, "suggestions for the reference");
  refFld.querySelector(".sugg div").dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  await until(() => $$("#main .bar-cell").length > 0, "the compare layout (rows of paired bars, not side-by-side columns) appears");
  expect(!$$("#main .cols2").length, "no more side-by-side columns in Compare mode");
  const quotesLabel = [...$$("#main .small.muted")].find(d => d.textContent.trim() === "Quotes");
  expect(quotesLabel, "a Quotes comparison row");
  const barValue = el => +el.textContent.replace(/[^\d.]/g, "");
  const bars = [...quotesLabel.parentElement.querySelectorAll(".bar-cell")].map(barValue);
  expect(bars.length === 2, "two bars, target above reference");
  expect(bars[0] === genderQuotes, "the target bar still shows the gender scope's figures");
  expect(bars[1] > 0 && bars[1] <= genderQuotes, "the reference bar (Holmes alone) has fewer or equal quotes than the whole gender pool he's part of");
  expect(byText("#main h3", /Share of words in dialogue/), "the dialogue-share chart appears in Compare mode too, one shared graphic");
  expect($$("#main svg").length >= 2, "the paired per-book bar chart and the shared dialogue-share chart both render");
});

await scenario("corpus: concordance search, sorting, context, word list, n-grams", async () => {
  await reset();
  await page.go("#/corpus/kwic");
  const q = page.$("#main input[type=search]");
  q.value = "said";
  q.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await until(() => $$("#main .kwic .kl").length > 0 && /hits?/.test(page.text()), "hits");
  const total = +(/([\d,]+) hits?/.exec(page.text()) || [])[1].replace(",", "");
  expect(total === 185, `185 hits for "said", got ${total}`);
  const sort = $$("#main select").find(s => [...s.options].some(o => /Search term/.test(o.textContent)));
  page.change(sort, "key");
  await page.settle();
  page.click($$("#main .kwic .kl")[0]);
  await until(() => drawerOpen() && /Open in the text/.test(drawerText()), "context drawer");
  await page.go("#/corpus/wordlist");
  page.click($$("#main table.t2 tbody tr.click")[0]);
  await until(() => /#\/corpus\/kwic/.test(w.location.hash) && $$("#main .kwic .kl").length > 0, "word list row opens its concordance");
  await page.go("#/corpus/ngrams");
  const contains = $$("#main input[type=search]").find(i => /any word/.test(i.placeholder));
  page.change(contains, "said");
  await until(() => $$("#main table.t2 tbody tr").every(r => /said/.test(r.textContent)), "n-grams contain the word");
  await page.go("#/corpus/collocates");
  await until(() => /hit for the search term|hits for the search term/.test(page.text()), "collocates of the last search");
});

await scenario("corpus: sort levels, the context search, word-type filters and the word + POS + lemma list", async () => {
  await reset();
  await page.go("#/corpus/kwic");
  const enter = el => el.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  const hits = () => +(/([\d,]+) hits?/.exec(page.text()) || [0, "0"])[1].replace(",", "");
  page.$("#main input[type=search]").value = "look";
  enter(page.$("#main input[type=search]"));
  await until(() => $$("#main .kwic .kl").length > 0, "hits for look");
  const all = hits();
  // the context search: keep hits with Watson in the three words before them, or without
  const ctx = byText("#main details.note", /Search in the context/);
  ctx.open = true;
  const ctxInput = ctx.querySelector("input[type=search]");
  const numbers = [...ctx.querySelectorAll("input[type=number]")];
  numbers[0].value = "3"; page.change(numbers[0]); numbers[1].value = "0"; page.change(numbers[1]);
  const within = ctx.querySelector("input[type=checkbox]"); within.checked = true; page.change(within);
  ctxInput.value = "watson"; page.change(ctxInput);
  await until(() => hits() > 0 && hits() < all && /with .watson. in their context/.test(page.text()), "hits narrowed by the context search");
  const kept = hits();
  const keep = ctx.querySelector("select");
  page.change(keep, "no");
  await until(() => hits() === all - kept, "the other hits when the search is inverted");
  page.change(keep, "yes");
  await until(() => hits() === kept, "back to the matching hits");
  ctx.querySelector("button").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
  await until(() => hits() === all, "clearing the context search brings every hit back");
  // sort levels: by lemma, reversed
  const by = $$("#main select").find(s => s.getAttribute("aria-label") === "Sort 1: by");
  page.change(by, "lemma");
  const arrow = () => $$("#main .controls button").find(b => /Reversed|Normal order/.test(b.title));
  await until(() => arrow() && hits() === all, "the concordance is redrawn with the lemma sort");
  page.click(arrow());
  await until(() => arrow().getAttribute("aria-pressed") === "true" && hits() === all, "a reversed lemma sort keeps all hits");
  expect(JSON.parse(w.localStorage.getItem("analyser.corp")).sort[0].by === "lemma", "the sort level is remembered");
  // the word list: three columns, and a word-class filter
  await page.go("#/corpus/wordlist");
  page.click(byText("#main .seg button", /Word \+ POS \+ lemma/));
  await until(() => $$("#main table.t2 thead th").some(t => /^POS/.test(t.textContent)) && $$("#main table.t2 thead th").some(t => /^Lemma/.test(t.textContent)), "three columns");
  const total = $$("#main table.t2 tbody tr").length;
  const filter = page.$("#main details.tfilter");
  filter.open = true;
  await until(() => byText("#main .tfilter .chip", /^VERB/), "the word classes are listed");
  page.click(byText("#main .tfilter .chip", /^VERB/));
  await until(() => /Only VERB/.test(page.text()) && $$("#main table.t2 tbody tr").length > 0 && $$("#main table.t2 tbody tr").every(r => r.children[2].textContent === "VERB"), "only verbs");
  page.click(byText("#main .tfilter .chip", /^NOUN/));
  await until(() => $$("#main table.t2 tbody tr").some(r => r.children[2].textContent === "NOUN") && $$("#main table.t2 tbody tr").every(r => ["NOUN", "VERB"].includes(r.children[2].textContent)), "verbs or nouns: several choices in one group");
  page.click(byText("#main .tfilter button", /Clear the filter/));
  await until(() => !/Only /.test(page.text()) && $$("#main table.t2 tbody tr").length === total, "the filter is cleared");
  // collocates take the same filter
  await page.go("#/corpus/collocates");
  await until(() => /for the search term/.test(page.text()), "collocates");
  const tf = page.$("#main details.tfilter");
  tf.open = true;
  await until(() => byText("#main .tfilter .chip", /^PROPN/), "word classes for collocates");
  page.click(byText("#main .tfilter .chip", /^PROPN/));
  await until(() => /only PROPN/.test(page.text()), "collocates limited to proper nouns");
});

await scenario("corpus: a batch search merges several lines into one, with a toggleable Matched column", async () => {
  await reset();
  await page.go("#/corpus/kwic");
  const hits = () => +(/([\d,]+) hits?/.exec(page.text()) || [0, "0"])[1].replace(",", "");
  const search = q => { const inp = page.$("#main input[type=search]"); inp.value = q; inp.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); };
  search("said");
  await until(() => hits() > 0, "hits for said");
  const said = hits();
  search("watched");
  await until(() => hits() > 0 && hits() !== said, "hits for watched");
  const watched = hits();
  expect(!byText("#main label.inline", /Matched/), "no Matched toggle for a single-line search");
  page.click(byText("#main label.inline", /^Batch/));
  await until(() => page.$("#main textarea"), "the batch list box appears");
  page.change(page.$("#main textarea"), "said\nwatched");
  page.click(byText("#main button", /^Search$/));
  await until(() => hits() === said + watched, "the batch merges both searches into one");
  await until(() => byText("#main label.inline", /^Matched/), "a Matched toggle appears now it's a batch");
  expect($$("#main .kl-m").length === 0, "the Matched column is hidden until switched on");
  page.click(byText("#main label.inline", /^Matched/).querySelector("input"));
  await until(() => $$("#main .kl-m").length > 0, "the Matched column appears");
  expect($$("#main .kl-m").every(el => el.textContent === "said" || el.textContent === "watched"), "each hit shows which line matched it");
});

await scenario("corpus: wildcards can be turned off to search punctuation literally", async () => {
  await reset();
  await page.go("#/corpus/kwic");
  const hits = () => +(/([\d,]+) hits?/.exec(page.text()) || [0, "0"])[1].replace(",", "");
  const search = q => { const inp = page.$("#main input[type=search]"); inp.value = q; inp.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true })); };
  page.click(byText("#main label.inline", /Ignore punctuation/).querySelector("input"));   // include punctuation in the search
  search("?");
  await until(() => hits() > 0, "“?” is the any-one-letter wildcard by default: matches one-letter words");
  page.click(byText("#main label.inline", /^Wildcards/).querySelector("input"));
  await until(() => hits() === 0, "with wildcards off, “?” is a literal character the fixture never writes");
});

await scenario("corpus: a bad query shows a message, not a crash", async () => {
  await reset();
  await page.go("#/corpus/kwic");
  page.click(byText("#main .seg button", /Pattern/));
  await page.settle();
  const q = page.$("#main input[type=search]");
  q.value = '[lemma="say"';
  q.dispatchEvent(new w.KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
  await sleep(600);
  expect(/no matching/.test(page.$("#toast").textContent) && !page.$("#toast").hidden, "error toast shown");
  expect(/no matching/.test(page.$("#main .warn").textContent) && !page.$("#main .loading"), "the message replaces the Searching… line");
  page.$("#toast").hidden = true;
  q.value = ""; page.eval("S.corp.query = ''; S.corp.mode = 'simple'; saveCorp()");
});

await scenario("arcs, style and stylometry controls", async () => {
  await reset();
  await page.go("#/narrative/arcs");
  page.click(byText("#main .seg button", /Dialogue/));
  await until(() => page.$("#main svg[role=img]"), "dialogue arc");
  const corpusBtn = byText("#main .seg button", /Whole corpus/);
  expect(corpusBtn, "the Timeline scope toggle shows with several books selected");
  page.click(corpusBtn);
  await until(() => page.eval("S.nar.seg.scope") === "corpus", "scope switched to corpus");
  await page.settle();
  expect(page.$("#main svg[role=img] polyline"), "a line is drawn across the whole corpus");
  page.click(byText("#main .seg button", /Book by book/));
  await until(() => page.eval("S.nar.seg.scope") === "book", "scope back to book by book");
  page.click(byText("#main .seg button", /Chapters/));
  await page.settle();
  page.click(byText("#main .seg button", /Characters and places/));
  await until(() => $$("#main .tag").length > 0, "chosen entities");
  await page.go("#/narrative/style");
  page.click(byText("#main .seg button", /^Slice$|^Chapter$/));
  await until(() => /Segment/.test(page.text()), "style per segment");
  await page.go("#/narrative/stylometry");
  const measure = $$("#main select").find(s => [...s.options].some(o => /Euclidean/.test(o.textContent)));
  page.change(measure, "euclidean");
  await until(() => /Cluster tree/.test(page.text()), "stylometry redrawn");
});

await scenario("the text view: layers, paging, side panels", async () => {
  await reset();
  await page.go("#/read/alpha");
  await until(() => $$("#main .para").length > 0, "paragraphs");
  page.click($$("#main .read-text mark.q")[0]);
  await until(() => /Quote/.test(page.$(".read-side").textContent) && page.$(".read-side .qedit"), "quote panel");
  page.click($$("#main .read-text mark.e.in")[0]);
  await until(() => page.$(".read-side a[href^='#/entities/']"), "entity panel, linking into a profile");
  const pron = $$("#main .read-text mark.e.in.PRON").find(m => m.textContent === "He");
  expect(pron, "a pronoun mention of Holmes to click");
  page.click(pron);
  await until(() => /Attributed to/.test(page.$(".read-side").textContent) && byText("#main .read-side a", /^Holmes$/), "the pronoun's own entity, not just its literal text");
  page.click(byText("#main .chips .chip", /Events/));
  await until(() => $$("#main .read-text mark.ev").length > 0, "events layer");
  page.click(byText("#main .chips .chip", /Events/));
  await page.settle();
  const before = page.eval("S.read.index");
  page.click(button(/Next/));
  await until(() => page.eval("S.read.index") === before + 1 || /#\/read\//.test(w.location.hash), "next segment");
  page.click(byText("#main .chips .chip", /^Topics$/));
  await until(() => /No topic model includes this book/.test(page.text()), "message when there is no model");
  page.click(byText("#main .chips .chip", /^Topics$/));
  await page.settle();
});

await scenario("topics: fit a model, open a topic, the relevance slider, comparing", async () => {
  await reset();
  for (const m of (await api(base, "/api/topics/models")).models) await api(base, "/api/topics/delete", { id: m.id });
  await page.go("#/topics");
  page.eval("S.top.cfg = Object.assign({}, S.lib.topic_defaults, {chunk_words: 60, k: 4, min_df: 2, runs: 2}); saveTop(); render()");
  await page.settle();
  page.click(button(/^Compare$/));
  await until(() => /Coherence/.test(page.text()) && $$("#main table.t2").length > 0, "numbers of topics compared");
  page.click(button(/Fit model/));
  await until(() => /#\/topics\/[a-z0-9-]+$/.test(w.location.hash), "opened the fitted model", 60000);
  await page.settle();
  expect($$("#main section.panel[id^=topic-]").length === 4, "four topic cards");
  page.click($$("#main table.t2 tbody a")[0]);
  await until(() => /#\/topics\/[a-z0-9-]+\/\d+$/.test(w.location.hash) && page.$("#sec-entities .content table"), "topic page filled", 30000);
  const slider = page.$("#sec-words input[type=range]");
  const first = () => page.$("#sec-words tbody tr td").textContent;
  const before = first();
  page.input(slider, "0");
  page.input(slider, "1");
  expect(first().length > 0 && before.length > 0, "words listed at both ends of the slider");
  await until(() => page.$(".tp-toc a.on"), "side menu highlights a section");
  page.click(page.$("#sec-words .cx"));
  expect(page.$("#sec-words").classList.contains("collapsed"), "section collapsed");
  page.click(page.$("#sec-words .cx"));
  const pick = page.$(".tp-toc select");
  page.change(pick, pick.options[1].value);
  await until(() => /compare\/pair\//.test(w.location.hash) && /Only in/.test(page.text()), "pair comparison", 30000);
  await page.go(w.location.hash.replace(/compare\/pair.*/, "compare/grid"));
  page.click(byText("#main .seg button", /Topic × character/));
  await until(() => $$("#main .heat tbody tr").length > 0, "character grid");
  for (const m of (await api(base, "/api/topics/models")).models) await api(base, "/api/topics/delete", { id: m.id });
});

await scenario("collapsing sections and the side menu on an entity page", async () => {
  await reset();
  const holmes = (await api(base, "/api/units", { books: ALL })).rows.find(u => u.name === "Holmes" && u.books[0] === "alpha").id;
  await page.go("#/entities/" + encodeURIComponent(holmes));
  await until(() => page.$(".page-toc") && page.$$ && $$("#main .cx").length >= 5, "menu and arrows", 15000);
  const panel = byText("#main section.panel > h2", /Book by book|Speech/).parentElement;
  page.click(panel.querySelector(".cx"));
  expect(panel.classList.contains("collapsed") && JSON.stringify(w.localStorage.getItem("analyser.collapsed")).length > 4, "collapsed and remembered");
  const link = $$(".page-toc a").find(a => a.dataset.target === panel.id);
  expect(link.classList.contains("collapsed"), "menu entry marked");
  page.click(byText(".page-toc-tools button", /Expand all/));
  expect(!panel.classList.contains("collapsed"), "expand all");
  page.click(byText(".page-toc-tools button", /Collapse all/));
  expect($$("#main section.panel.cx-panel").every(p => p.classList.contains("collapsed")), "collapse all");
  page.click(byText(".page-toc-tools button", /Expand all/));
});

await scenario("books: collections nest and hold books, search narrows the table, the pop-up filters by collection", async () => {
  await reset();
  await page.go("#/books");
  const rowsShown = () => $$("#main table.books tbody tr:not(.grp)").length;
  const node = re => byText("#main .ctree .node", re);
  const nameIt = name => { const box = page.$("#main .lib input[type=text]"); box.value = name; page.click(byText("#main .lib button", /^OK$/)); };
  expect(rowsShown() === 3 && node(/All books/) && node(/In no collection/), "all three books, and the two fixed tree entries");
  // make a collection, then a sub-collection inside it
  page.click(button(/^New collection$/)); nameIt("Holmes");
  await until(() => page.eval("S.lib.collections.length") === 1, "collection made");
  page.click(node(/^Holmes/));
  page.click(button(/^New sub-collection$/)); nameIt("Novels");
  await until(() => page.eval("S.lib.collections.length") === 2, "sub-collection made");
  expect((await api(base, "/api/library")).collections[1].parent === (await api(base, "/api/library")).collections[0].id, "the second collection is inside the first");
  // put a book in Novels (a sub-collection), through the row's ＋ menu (in the list of all books: an empty collection lists nothing)
  page.click(node(/All books/));
  const novels = page.eval("S.lib.collections.find(c => c.name === 'Novels').id");
  const add = $$("#main table.books select").find(s => s.getAttribute("aria-label") === "Add alpha to a collection");
  expect(add, "a ＋ menu on the first book");
  page.change(add, novels);
  await until(() => page.eval("S.lib.collections.find(c => c.name === 'Novels').books.length") === 1, "book added");
  // the parent lists it too, the fixed entry no longer does
  page.click(node(/^Holmes/));
  expect(rowsShown() === 1, "the parent collection lists the book of its sub-collection");
  page.click(node(/In no collection/));
  expect(rowsShown() === 2, "the other two books are in no collection");
  // search
  page.click(node(/All books/));
  const search = page.$("#main .controls input[type=search]");
  page.input(search, "hound");
  await sleep(300);
  expect(rowsShown() === 0, "a search that matches nothing lists nothing");
  page.input(search, "alpha");
  await until(() => rowsShown() === 1, "search by id finds one book");
  // the analysis selection follows the table
  page.click(button(/Analyse the 1 book shown/));
  expect(JSON.stringify(page.eval("S.sel")) === JSON.stringify(["alpha"]), "selection is the shown book");
  // the pop-up filters by collection
  page.click(page.$("#selBtn"));
  const popColl = $$("#selPop select").find(s => [...s.options].some(o => o.textContent === "Novels"));
  expect(popColl, "the pop-up has a collection filter");
  page.change(popColl, novels);
  expect($$("#selPop label.book").length === 1, "only the book in that collection is listed");
  page.click(byText("#selPop button", /^Cancel$/));
  // deleting a collection keeps the books and moves the sub-collection up
  page.click(node(/^Holmes/));
  page.click(button(/^Delete$/));
  await until(() => page.eval("S.lib.collections.length") === 1, "collection deleted");
  expect((await api(base, "/api/library")).collections[0].parent === null && page.eval("S.lib.books.length") === 3, "the child moved up and no book was lost");
});

await scenario("selecting books from the pop-up", async () => {
  await reset();
  await page.go("#/entities");
  page.click(page.$("#selBtn"));
  expect(!page.$("#selPop").hidden, "pop-up open");
  const boxes = $$("#selPop input[type=checkbox]");
  boxes.forEach(b => { b.checked = false; page.change(b); });
  boxes[0].checked = true; page.change(boxes[0]);
  page.click(byText("#selPop button", /Use these books/));
  await until(() => JSON.stringify(page.eval("S.sel")) === JSON.stringify(["alpha"]), "selection changed");
  await page.settle();
  expect(/1 of 3 books/.test(page.$("#selBtn").textContent), "button label");
  expect(JSON.parse(w.localStorage.getItem("analyser.sel")).length === 1, "selection remembered");
});

await scenario("network: a click pins the focus, empty space releases it, and a hidden name shows while hovered or pinned", async () => {
  await reset();
  w.localStorage.setItem("analyser.net", JSON.stringify({ kind: "sentence", types: ["PER"], min_weight: 1, keep_isolated: false, color: "type", size: "strength", labels: "0" }));
  await page.eval("S.net = loadState('analyser.net', {})");
  await page.go("#/network");
  await until(() => $$(".net-canvas svg circle").length > 2, "network drawn");
  const circle = i => $$(".net-canvas svg circle")[i];
  const label = i => $$(".net-canvas svg text")[i].getAttribute("visibility");
  const mouse = (el, type) => el.dispatchEvent(new w.MouseEvent(type, { bubbles: false }));
  expect(label(0) === "hidden", "with labels off, names are hidden");
  mouse(circle(0), "mouseenter");
  expect(label(0) === "visible", "hovering shows the name");
  mouse(circle(0), "mouseleave");
  expect(label(0) === "hidden", "the name hides again");
  page.click(circle(0));
  mouse(circle(0), "mouseleave");
  expect(label(0) === "visible" && circle(0).getAttribute("stroke") === "#1d2a2e", "a click pins the focus: the name and outline stay");
  expect(/Linked to/.test(page.$(".net-side").textContent), "the side panel shows the pinned entity");
  page.click(page.$(".net-canvas svg"));
  expect(label(0) === "hidden" && circle(0).getAttribute("stroke") === "#ffffff", "clicking empty space releases the focus");
  expect(/release it/.test(page.$(".net-side").textContent), "the side panel goes back to its hint");
});

await scenario("text view: the entity legend switches a type's underlines off and on", async () => {
  await reset();
  await page.go("#/read/alpha");
  const legend = t => $$("#main .legend button").find(b => b.textContent === t);
  const text = () => page.$("#main .read-text");
  expect(legend("PER") && legend("LOC"), "the legend has a button per type");
  page.click(legend("PER"));
  expect(text().classList.contains("hide-PER") && legend("PER").classList.contains("off"), "PER is hidden");
  expect(JSON.parse(w.localStorage.getItem("analyser.read")).hidden.includes("PER"), "the choice is remembered");
  await page.go("#/read/alpha");
  expect(text().classList.contains("hide-PER"), "still hidden after the page is drawn again");
  page.click(legend("PER"));
  expect(!text().classList.contains("hide-PER"), "PER is back");
});

await scenario("entities: narrators have profiles; entities can be ticked, analysed together, saved as a group and reopened", async () => {
  await reset();
  const rows = (await api(base, "/api/units", { books: ALL })).rows;
  const watson = rows.find(r => r.name === "Watson" && r.books[0] === "alpha").id;
  await api(base, "/api/annot/narrator", { book: "alpha", narrator: watson });
  await page.eval("S.units = null");
  await page.go("#/entities");
  // narrators
  page.click(byText("#main .chip", /^Narrators/));
  await until(() => $$("#main .ent-item .nm").some(n => /Watson, narrating/.test(n.textContent)), "the narrating Watson is listed");
  expect($$("#main .ent-item .nm").some(n => /Narrator of/.test(n.textContent)), "unnamed narrators are listed too");
  expect(!page.$("#main .multi-bar input[type=checkbox]"), "narrator roles can't be grouped, so there is no select-several switch");
  page.click($$("#main .ent-item").find(e => /Watson, narrating/.test(e.textContent)));
  await until(() => /Where they narrate/.test(page.text()) && /What's distinctive/.test(page.text()) && $$("#main table.t2 tbody tr").length > 3, "narrator profile");
  expect(/Watson, narrating/.test(page.$("#main h1").textContent) && byText("#main a", /Watson's own profile/), "title and a link to the character");
  // select several
  page.click(byText("#main .chip", /^PER/));
  await until(() => w.location.hash === "#/entities" && page.$("#main .multi-bar input[type=checkbox]"), "back to the list of people");
  const multi = page.$("#main .multi-bar input[type=checkbox]");
  multi.checked = true; page.change(multi);
  await until(() => $$("#main .ent-item.multi").length > 2, "rows get checkboxes");
  page.click($$("#main .ent-item")[0]); page.click($$("#main .ent-item")[1]);
  await until(() => /2 entities selected/.test(page.$("#main .multi-bar").textContent), "two ticked");
  const [a, b] = page.eval("S.entSel").map(id => rows.find(r => r.id === id));
  page.click(byText("#main .multi-bar button", /Analyse together/));
  await until(() => /#\/entities\/group/.test(w.location.hash) && $$("#main .phead .gtag").length === 2 && /Where these come from/.test(page.text()), "group profile", 15000);
  const fact = label => (byText("#main .phead .facts div", new RegExp(label)) || {}).textContent || "";
  expect(fact("Mentions").startsWith(fmtNum(a.mentions + b.mentions)) && /^2/.test(fact("Entities")), "the group's mentions are the two entities' added together");
  expect($$("#main .phead .gtag").every(t => /^(PER)/.test(t.textContent)), "members are shown as tags with their type");
  // remove one with its ×, and tick it again
  page.click($$("#main .phead .gtag button")[0]);
  await until(() => $$("#main .phead .gtag").length === 1 && page.eval("S.entSel.length") === 1, "one member taken out");
  page.click($$("#main .ent-item").find(e => e.textContent.includes(a.name) || e.textContent.includes(b.name)) || $$("#main .ent-item")[0]);
  await until(() => $$("#main .phead .gtag").length === 2, "and ticked again");
  // save, reopen, change, update, delete
  page.click(byText("#main .phead button", /Save as a group/));
  page.$("#main .phead input[type=text]").value = "Duo";
  page.click(byText("#main .phead button", /^OK$/));
  await until(() => /#\/entities\/g:/.test(w.location.hash) && /Duo/.test(page.$("#main h1").textContent), "saved group opened");
  expect((await api(base, "/api/library")).groups.length === 1 && byText("#main .multi-bar option", /Duo/), "the group is saved and listed");
  page.click($$("#main .phead .gtag button")[0]);
  await until(() => /Update “Duo”/.test(page.text()) && $$("#main .phead .gtag").length === 1, "changed ticks are offered as an update");
  page.click(byText("#main .phead button", /Update “Duo”/));
  await until(() => page.eval("S.lib.groups[0].ids.length") === 1, "saved group updated");
  await until(() => byText("#main .phead button", /Delete group/), "back to a plain saved group");
  page.click(byText("#main .phead button", /Delete group/));
  await until(() => page.eval("S.lib.groups.length") === 0 && !/g:/.test(w.location.hash), "group deleted");
});

await scenario("entities: linking narrator roles pools their narration, and unlinking splits them apart", async () => {
  await reset();
  await page.go("#/entities");
  page.click(byText("#main .chip", /^Narrators/));
  const items = () => $$("#main .ent-item");
  await until(() => items().some(e => /narrating/.test(e.textContent)), "narrator rows shown, not still the people list");
  const before = items().length;
  const find = re => items().find(e => re.test(e.textContent));
  expect(find(/Narrator of beta/) && find(/Narrator of gamma/), "beta and gamma each have an anonymous narrator by default");
  page.click(find(/Narrator of beta/));
  await until(() => /Narrated alone so far/.test(page.text()), "not linked yet");
  const linkRow = () => byText("#main .row", /Link with another narrator/);
  await until(() => linkRow().querySelector("select").options.length > 1, "narrator options loaded");
  const sel = linkRow().querySelector("select");
  const gammaOpt = [...sel.options].find(o => /Narrator of gamma/.test(o.textContent));
  expect(gammaOpt, "gamma's narrator is offered to link with");
  page.change(sel, gammaOpt.value);
  page.click(linkRow().querySelector("button"));
  await until(() => /nl%3A/.test(w.location.hash), "the page follows the fresh linked id");
  await until(() => /Linked narrators/.test(page.text()), "linked narrators page");
  expect(/Narrator of beta/.test(page.text()) && /Narrator of gamma/.test(page.text()), "both members shown, each with their own share");
  await until(() => items().length === before - 1, "the list has one fewer row: the two merged into one");
  // unlink one: a link of just two dissolves, and the page follows the member that's left
  const unlinkBeta = page.$('#main button.linkbtn[title="Unlink Narrator of beta"]');
  expect(unlinkBeta, "an unlink button for beta");
  page.click(unlinkBeta);
  await until(() => /Narrator of gamma/.test((page.$("#main h1") || {}).textContent || ""), "back to gamma's own narrator page");
  expect(/Narrated alone so far/.test(page.text()), "no longer linked");
  await until(() => items().length === before, "the list is back to its original count");
});

await scenario("compare: a group is picked by search, shown as removable tags outside the list, and compared", async () => {
  await reset();
  const rows = (await api(base, "/api/units", { books: ALL })).rows;
  const place = rows.find(r => r.type === "LOC");
  await page.go("#/compare");
  const pick = async (box, text) => {
    const inp = box.querySelector("input[type=search]");
    page.input(inp, text);
    await until(() => box.querySelector(".sugg div"), "suggestions for " + text);
    box.querySelector(".sugg div").dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  };
  const first = () => $$("#main .picker")[0], second = () => $$("#main .picker")[1];
  page.click([...first().querySelectorAll(".seg button")].find(b => /^Group$/.test(b.textContent)));
  await pick(first().querySelector(".gpick"), "holmes");
  await pick(first().querySelector(".gpick"), "watson");
  await until(() => first().querySelectorAll(".gbox .gtag").length === 2, "two entities shown as tags");
  await pick(second(), place.name.toLowerCase().slice(0, 5));
  await until(() => /Overview/.test(page.text()) && byText("#main table.t2 tbody tr", /^Entities/), "comparison drawn");
  const entitiesRow = () => byText("#main table.t2 tbody tr", /^Entities/).textContent;
  expect(/^Entities2/.test(entitiesRow()), "the group has two entities");
  page.click(first().querySelector(".gbox .gtag button"));
  await until(() => first().querySelectorAll(".gbox .gtag").length === 1 && /^Entities1/.test(entitiesRow()), "removing a tag updates the comparison");
});

await scenario("compare: two books split into characters, only while both sides are books", async () => {
  await reset();
  await page.go("#/compare");
  const first = () => $$("#main .picker")[0], second = () => $$("#main .picker")[1];
  const setMode = (box, label) => page.click([...box.querySelectorAll(".seg button")].find(b => new RegExp(`^${label}$`).test(b.textContent)));
  setMode(first(), "Book");
  await until(() => first().querySelector("select"), "a book select appears");
  page.change(first().querySelector("select"), "alpha");
  setMode(second(), "Book");
  await until(() => second().querySelector("select"), "the second book select appears");
  page.change(second().querySelector("select"), "beta");
  await until(() => byText("#main h2", /Split into characters/), "the split grid appears for two books");
  const grid = byText("#main h2", /Split into characters/).parentElement;
  const heads = [...grid.querySelectorAll("th")].map(th => th.textContent);
  expect(heads.some(t => /alpha/.test(t)) && heads.some(t => /beta/.test(t)), "one column per book");
  expect([...grid.querySelectorAll("td a")].find(a => /Holmes/.test(a.textContent)), "a character links to its own profile");
  setMode(second(), "Gender");                          // switching one side away from a book: the split grid goes
  await until(() => !byText("#main h2", /Split into characters/), "no split grid once a side isn't a book");
});

await scenario("entities: a book's and a gender's own overview pages pool every entity in them", async () => {
  await reset();
  await page.go("#/books");
  const overview = byText("#main a", /^Overview$/);
  expect(overview, "a book row offers its own overview");
  page.click(overview);
  await until(() => /#\/entities\/book/.test(w.location.hash) && /Book overview/.test(page.text()), "the book's overview page");
  const heads = () => [...$$("#main h2")].map(h => h.textContent);
  expect(heads().includes("Entities in this book") && heads().includes("What they do and what's done to them"), "the pooled profile sections");
  expect(!heads().includes("Speech") && !heads().includes("Topics"), "speech and topics are left out (they need an id/ids ref a pool doesn't have)");

  await page.go("#/entities");
  page.click(byText("#main .chip", /^Gender/));
  await until(() => $$("#main .ent-item").some(e => /he\/him\/his/.test(e.textContent)), "gender buckets listed");
  page.click($$("#main .ent-item").find(e => /he\/him\/his/.test(e.textContent)));
  await until(() => /Gender overview/.test(page.text()) && heads().includes("Entities of this gender"), "the gender's overview page");
});

await scenario("text view: the book scrolls chapter after chapter with numbers in the margin; sentence numbers; jumping", async () => {
  await reset();
  await page.eval("S.nar.seg = { mode: 'chapters', n: 10, rules: { numbered: true, caps: true, short: false }, min_words: 50 }");
  await page.go("#/read/alpha");
  await until(() => $$("#main .chap").length === 1 && $$("#main .pwrap .pno").length > 2, "the first chapter and its paragraph numbers");
  const nums = () => $$("#main .pno").map(e => +e.textContent);
  const firstNums = nums();
  expect(firstNums[0] === 1 && firstNums.every((n, i) => i === 0 || n === firstNums[i - 1] + 1), "paragraphs are numbered from 1, one after another");
  expect(/^1\. /.test(page.$("#main .seg-head").textContent) && page.$("#main .read-where select"), "a heading per chapter and a jump menu");
  const more = () => byText("#main button.more", /Load the next/);
  page.click(more());
  await until(() => $$("#main .chap").length === 2, "the next chapter is added below");
  const both = nums();
  expect(both[firstNums.length] === firstNums[firstNums.length - 1] + 1, "the numbers carry on into the next chapter");
  expect(/^2\. /.test($$("#main .seg-head")[1].textContent), "with its own heading");
  // sentence numbers are a layer
  page.click(byText("#main .chips .chip", /Sentence numbers/));
  await until(() => $$("#main .read-text mark.sn").length > 3 && page.$("#main .read-text").classList.contains("L-sentences"), "sentence numbers marked");
  const ids = $$("#main .read-text mark.sn").map(m => +m.dataset.id);
  expect(ids.every((n, i) => i === 0 || n === ids[i - 1] + 1), "sentences are numbered one after another");
  page.click(byText("#main .chips .chip", /Sentence numbers/));
  await until(() => $$("#main .read-text mark.sn").length === 0, "and go away again");
  // jumping to the last chapter starts the flow there
  const menu = page.$("#main .read-where select");
  const last = menu.options.length - 1;
  page.change(menu, String(last));
  await until(() => $$("#main .chap").length === 1 && page.$("#main .chap").dataset.index === String(last), "jump to the last chapter");
  expect(byText("#main button.more", /previous/) && !byText("#main button.more", /previous/).hidden, "earlier chapters can still be loaded");
  await page.eval("S.nar.seg = { mode: 'slices', n: 10, rules: { numbered: true, caps: true, short: false }, min_words: 500 }");
});

await scenario("chapter editor: start, rename and remove chapters in the text, and go back to the automatic ones", async () => {
  await reset();
  await page.eval("S.nar.seg = { mode: 'chapters', n: 10, rules: { numbered: true, caps: true, short: false }, min_words: 50 }");
  const cfg = { mode: "chapters", n: 10, rules: { numbered: true, caps: true, short: false }, min_words: 50 };
  const chapters = async () => (await api(base, "/api/read", { books: ALL, book: "alpha", seg: cfg, layers: [] })).segments;
  const auto = (await chapters()).length;
  await page.go("#/chapters/alpha");
  await until(() => $$("#main .seg-head.edit").length === 1 && $$("#main .cstart").length > 1, "the editor shows the first chapter and a start button on its paragraphs");
  expect(/found automatically/.test(page.text()) && byText("#main .seg-head.edit button", /Remove this chapter start/), "chapter titles have their buttons");
  expect(/Back to the automatic chapters/.test(page.text()) && byText("#main button", /Back to the automatic/).disabled, "nothing to undo yet");
  // start a chapter at a paragraph of the first chapter
  page.click($$("#main .cstart")[2]);
  await until(async () => (await chapters()).length === auto + 1, "the new chapter start is saved");
  await until(() => $$("#main .seg-head.edit").some(x => /started by you/.test(x.textContent)), "the editor shows it, at the place it was made");
  expect(!byText("#main button", /Back to the automatic/).disabled, "and offers to go back");
  // rename it
  const mine = $$("#main .seg-head.edit").find(x => /started by you/.test(x.textContent));
  page.click([...mine.querySelectorAll("button")].find(b => /Rename/.test(b.textContent)));
  const title = mine.querySelector("input[type=text]");
  title.value = "My chapter";
  page.click([...mine.querySelectorAll("button")].find(b => /^OK$/.test(b.textContent)));
  await until(async () => (await chapters()).some(s => s.label === "My chapter"), "the title is saved");
  await until(() => $$("#main .seg-head.edit").some(x => /My chapter/.test(x.textContent)), "and shown");
  // the same chapters are used elsewhere
  await api(base, "/api/narrative/segments", { books: ALL, seg: cfg }).then(r => expect(r.segments.some(s => s.label === "My chapter" && s.source === "yours"), "Arcs and style see it too"));
  // remove it again, and an automatic one, then reset
  const start = $$("#main .seg-head.edit").find(x => /My chapter/.test(x.textContent));
  page.click([...start.querySelectorAll("button")].find(b => /Remove this chapter start/.test(b.textContent)));
  await until(async () => (await chapters()).length === auto, "removing your own chapter start gives back the automatic chapters");
  await until(() => !$$("#main .seg-head.edit").some(x => /My chapter/.test(x.textContent)) && byText("#main button", /Back to the automatic/).disabled, "and the editor follows");
  await page.eval("S.nar.seg = { mode: 'slices', n: 10, rules: { numbered: true, caps: true, short: false }, min_words: 500 }");
});

await scenario("the text view: assign a narrator to a whole chapter at once", async () => {
  await reset();
  await page.eval("S.nar.seg = { mode: 'chapters' }; S.read.index = 0;");   // alpha has real chapters at the default settings;
  const cfg = { mode: "chapters" };                                        // force index 0, in case an earlier scenario left the reader on alpha's last chapter
  const watson = (await api(base, "/api/units", { books: ALL })).rows.find(r => r.name === "Watson" && r.books[0] === "alpha").id;
  const read = index => api(base, "/api/read", { books: ALL, book: "alpha", seg: cfg, index, layers: ["narrators"] });
  const first = await read(0);
  expect(first.segments.length > 1 && first.paragraphs.length > 1, "the first chapter has more than one paragraph, and there's a second");
  await page.go("#/read/alpha");
  await until(() => page.eval("S.read.index") === 0 && $$("#main .pn").length > 0, "the first chapter, with a narrator label to click");
  page.click($$("#main .pn")[0]);
  const applyChapter = () => byText("#main .read-side button", /Apply to this whole chapter/);
  await until(() => applyChapter(), "the whole-chapter button");
  const sel = page.$(".read-side select");
  await until(() => [...sel.options].some(o => o.value === watson), "Watson offered as a narrator");
  page.change(sel, watson);
  page.click(applyChapter());
  await until(async () => (await read(0)).paragraphs.every(p => p.exception && p.narrator_id === "nar:" + watson), "every paragraph of the first chapter now belongs to Watson");
  expect((await read(1)).paragraphs.every(p => !p.exception), "the next chapter is unaffected");
  await until(() => $$("#main .pn.exc").length > 0, "the text view shows the exception");
  // clear it again through the same control
  page.click($$("#main .pn")[0]);
  await until(() => page.$(".read-side select"), "the panel reopens");
  page.change(page.$(".read-side select"), "");
  page.click(applyChapter());
  await until(async () => (await read(0)).paragraphs.every(p => !p.exception), "cleared again");
  await page.eval("S.nar.seg = { mode: 'slices', n: 10, rules: { numbered: true, caps: true, short: false }, min_words: 500 }");
});

await scenario("links: auto-link exact name, type and pronoun matches", async () => {
  await reset();
  await page.go("#/links");
  await until(() => byText("#main h2", /Auto-link/), "the Auto-link panel");
  page.click(byText("#main button", /Auto-link exact matches/));
  // a later scenario is not guaranteed to start unlinked (reset() doesn't undo links), so check the end state via the
  // API rather than the toast wording, which differs between "linked just now" and "already linked"
  await until(async () => (await api(base, "/api/links/persons")).rows.some(p => p.name === "Holmes" && p.members.length === 3),
    "Holmes across all three books becomes one linked person");
  await until(() => $$("#main .person-card").length >= 2, "one card per linked character");
  const holmesCard = $$("#main .person-card").find(c => c.querySelector("input[type=text]").value === "Holmes");
  expect(holmesCard, "a card for Holmes");
  expect(holmesCard.querySelectorAll(".appear-row").length === 3, "its three book appearances are listed inside the card");

  // batch unlink: tick the whole card (not one of its appearances), leaving the still-linked Watson card untouched
  page.click(holmesCard.querySelector('input[type="checkbox"]'));
  expect(holmesCard.classList.contains("picked"), "the ticked card is highlighted");
  await until(() => /1 entity selected/.test(page.text()), "the toolbar counts the selection");
  page.click(byText("#main button", /Unlink selected/));
  await until(async () => !(await api(base, "/api/links/persons")).rows.some(p => p.name === "Holmes"), "Holmes was unlinked");
  expect((await api(base, "/api/links/persons")).rows.some(p => p.name === "Watson"), "Watson, not ticked, is still linked");
});

await scenario("links: linked narrators get their own card in Linked entities, with their own Unlink", async () => {
  await reset();
  const lid = (await api(base, "/api/narrators/link", { a: "nar:anon:alpha", b: "nar:anon:beta", name: "The Chronicler" })).id;
  try {
    await page.go("#/entities");          // in case a previous scenario already left the hash on #/links: force a real navigation, not a no-op
    await page.go("#/links");
    await until(() => byText("#main h3", /Linked narrators/), "the Linked narrators heading");
    const card = () => $$("#main .person-card").find(c => (c.querySelector("input[type=text]") || {}).value === "The Chronicler");
    await until(() => card(), "a card for the linked narrator");
    expect(card().querySelectorAll(".appear-row").length === 2, "its two narrator roles are listed");
    expect(card().querySelector(`a[href="#/entities/${encodeURIComponent(lid)}"]`), "links to the narrator link's own profile");
    // unlink one role: a link of two dissolves, so the card disappears entirely
    page.click([...card().querySelectorAll(".appear-row")].find(r => /beta/.test(r.textContent)).querySelector("button"));
    await until(() => !card(), "the dissolved link's card is gone");
    expect(/No narrators linked yet/.test(page.text()), "back to the empty state");
  } finally {
    await api(base, "/api/narrators/unlink_all", { id: lid }).catch(() => {});   // in case the scenario failed before unlinking
  }
});

await scenario("links: the search boxes list entities when clicked and narrow as you type; the read menus are frozen together", async () => {
  await reset();
  await page.go("#/links");
  const box = () => $$("#main .picker input[type=search]")[0];
  const items = () => $$("#main .picker .sugg div").length;
  box().dispatchEvent(new w.Event("focus"));
  await until(() => items() > 2, "entities listed before anything is typed");
  const all = items();
  page.input(box(), "watson");
  await until(() => items() > 0 && items() < all && $$("#main .picker .sugg div").every(d => /Watson/.test(d.textContent)), "the list narrows to the name");
  const narrowed = items();
  $$("#main .picker .sugg div")[0].dispatchEvent(new w.MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  expect(/Watson/.test(box().value), "choosing an entry fills the box");
  // the entity chosen in the first box no longer appears in the second box's list
  const second = $$("#main .picker input[type=search]")[1];
  page.input(second, "watson");
  await until(() => $$("#main .picker")[1].querySelectorAll(".sugg div").length === narrowed - 1, "the chosen entity is hidden from the other list");
  await page.go("#/read/alpha");
  const head = page.$("#main .read-head");
  expect(head && head.children[0].classList.contains("read-bar") && head.children[1].classList.contains("read-where"), "the settings bar sits above the position bar in one frozen block");
  expect(page.$("#main .read-head select") && page.window.document.documentElement.style.getPropertyValue("--read-head") !== "", "the block's height is published for the layout");
});

await scenario("damaged remembered settings don't break the page", async () => {
  w.localStorage.setItem("analyser.corp", "{ nope");
  w.localStorage.setItem("analyser.nar", JSON.stringify({ seg: "not an object", stylo: 5, arcKind: 7 }));
  w.localStorage.setItem("analyser.read", "[]");
  w.localStorage.setItem("analyser.collapsed", "42");
  await page.eval("S.sel = null");
  const state = page.eval(`(() => ({ corp: loadState("analyser.corp", {a: {b: 1}}), nar: loadState("analyser.nar", {seg: {mode: "slices"}, stylo: {x: 1}, arcKind: "entities"}) }))()`);
  expect(state.corp.a.b === 1 && state.nar.seg.mode === "slices" && state.nar.stylo.x === 1 && state.nar.arcKind === "entities", "damaged values fall back to defaults");
  await page.go("#/corpus/kwic");
  await page.go("#/narrative/arcs");
  await page.go("#/read/alpha");
  w.localStorage.clear();
});

console.log(JSON.stringify({ passed, failures, errorsAtEnd: page.errors }));
process.exit(0);
