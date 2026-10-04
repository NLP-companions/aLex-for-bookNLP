// Unit tests of the browser's helper functions, run inside the loaded page.
// usage: node units.mjs http://127.0.0.1:8766
import { openPage } from "./harness.mjs";

const page = await openPage(process.argv[2]);
const w = page.window;
const failures = [], passed = [];
const ev = code => page.eval(code);
function test(name, fn) {
  try { fn(); passed.push(name); } catch (e) { failures.push(`${name}: ${e.message}`); }
}
function eq(actual, expected, what = "") {
  const a = JSON.stringify(actual), b = JSON.stringify(expected);
  if (a !== b) throw new Error(`${what} expected ${b} but got ${a}`);
}

test("fmt: thousands, decimals and missing values", () => {
  eq(ev("[fmt(1234567), fmt(1234.5678, 2), fmt(0), fmt(null), fmt(undefined), fmt(NaN), fmt(-3.5, 1)]"), ["1,234,567", "1,234.57", "0", "—", "—", "—", "-3.5"]);
});
test("fmtP and fmtSig", () => {
  eq(ev("[fmtP(null), fmtP(0.00001), fmtP(0.05), fmtSig(150.4), fmtSig(15.44), fmtSig(1.234)]"), ["—", "< 0.0001", "0.0500", "150", "15.4", "1.23"]);
});
test("plural", () => {
  eq(ev(`[plural(1, "book"), plural(2, "book"), plural(1, "entity", "entities"), plural(0, "entity", "entities"), plural(1234, "word")]`), ["1 book", "2 books", "1 entity", "0 entities", "1,234 words"]);
});
test("slug makes safe file names", () => {
  eq(ev(`[slug("Holmes & Watson: 3 books!"), slug("   "), slug("a".repeat(100)).length]`), ["holmes-watson-3-books", "export", 60]);
});
test("csvOf quotes fields that need it", () => {
  eq(ev(`csvOf(["a","b"], [[1, 'say "hi"'], ["x,y", null], ["line\\nbreak", 0]])`), 'a,b\r\n1,"say ""hi"""\r\n"x,y",\r\n"line\nbreak",0');
});
test("storageKey: remembered settings are kept per workspace, except the theme and the Default workspace's own", () => {
  eq(ev(`[storageKey("analyser.sel", "default"), storageKey("analyser.sel", "holmes"), storageKey("analyser.theme", "holmes"), storageKey("analyser.sel")]`),
    ["analyser.sel", "analyser.sel@holmes", "analyser.theme", "analyser.sel"]);          // the page under test is the Default workspace
  ev(`saveState("analyser.units-test", { a: 1 })`);
  eq(JSON.parse(w.localStorage.getItem("analyser.units-test")), { a: 1 }, "saved under the plain key");
  eq(ev(`loadState("analyser.units-test", { a: 0, b: 2 })`), { a: 1, b: 2 });
  w.localStorage.removeItem("analyser.units-test");
});
test("mergeState keeps saved values of the right kind and falls back otherwise", () => {
  eq(ev(`mergeState({a: 1, b: "x", c: [1], d: {e: true, f: null}, g: null}, {a: 2, b: 5, c: "no", d: {e: false, f: {z: 1}}, g: "any", extra: 1})`),
     { a: 2, b: "x", c: [1], d: { e: false, f: { z: 1 } }, g: "any", extra: 1 });
  eq(ev(`mergeState({a: 1}, null)`), { a: 1 });
  eq(ev(`mergeState({a: 1}, [1, 2])`), { a: 1 });
  eq(ev(`mergeState({a: {b: 1}}, {a: 5})`), { a: { b: 1 } });
});
test("loadState and loadJSON survive damaged storage", () => {
  w.localStorage.setItem("t.bad", "{ nope");
  w.localStorage.setItem("t.ok", JSON.stringify({ a: 5 }));
  eq(ev(`[loadJSON("t.bad", 7), loadJSON("t.missing", "d"), loadState("t.bad", {a: 1}), loadState("t.ok", {a: 1, b: 2})]`), [7, "d", { a: 1 }, { a: 5, b: 2 }]);
  ev(`saveState("t.round", {x: [1, 2]})`);
  eq(ev(`loadState("t.round", {x: []})`), { x: [1, 2] });
  w.localStorage.clear();
});
test("isObject", () => { eq(ev("[isObject({}), isObject([]), isObject(null), isObject('s')]"), [true, false, false, false]); });

test("h builds elements, skips empty children and never treats text as HTML", () => {
  const el = ev(`h("div", {class: "a", "data-x": 3, onclick: null, style: {color: "red"}}, "hi <b>x</b>", null, false, [h("span", {}, "s"), ["deep"]])`);
  eq(el.className, "a"); eq(el.getAttribute("data-x"), "3"); eq(el.style.color, "red");
  eq(el.innerHTML, "hi &lt;b&gt;x&lt;/b&gt;<span>s</span>deep");
  eq(ev(`h("svg:circle", {r: 3}).namespaceURI`), "http://www.w3.org/2000/svg");
  let clicked = 0;
  w.__cb = () => clicked++;
  ev(`window.__b = h("button", {onclick: window.__cb})`); w.__b.click();
  eq(clicked, 1);
});
test("append and replaceChildren accept nested arrays and skip null", () => {
  const d = ev(`(() => { const d = document.createElement("div"); d.append([["a", null], false, h("i", {})]); d.replaceChildren(["b", [h("b", {}), undefined]]); return d; })()`);
  eq(d.innerHTML, "b<b></b>");
});
test("loading() gives a placeholder and never a class on a container", () => {
  eq(ev(`loading("Wait").className`), "loading");
});

test("markup nests marks, reads data and ignores unbalanced closes", () => {
  const p = ev(`markup("a \\x01e PER PROP in|p:1\\x02Holmes\\x03 said \\x01q|4\\x02\\x01k\\x02hi\\x03\\x03 \\x03after")`);
  eq(p.tagName, "P");
  eq(p.textContent, "a Holmes said hi after");
  const e = p.querySelector("mark.e");
  eq([e.className, e.dataset.id], ["e PER PROP in", "p:1"]);
  eq(p.querySelector("mark.q mark.k").textContent, "hi");
});
test("markup never turns text into HTML", () => {
  const p = ev(`markup("<img src=x onerror=alert(1)> \\x01k\\x02<b>bold</b>\\x03")`);
  eq(p.querySelector("img"), null); eq(p.querySelector("b"), null); eq(p.textContent, "<img src=x onerror=alert(1)> <b>bold</b>");
});

test("table sorts (descending first for numbers), limits and offers CSV", () => {
  ev(`window.__t = table([{k: "n", label: "Name"}, {k: "v", label: "Value", num: true}, {k: "s", label: "Side", sortVal: r => r.v}], [{n: "b", v: 2, s: "x"}, {n: "a", v: 10, s: "y"}, {n: "c", v: 5, s: "z"}], {sort: "v", limit: 2, csvName: "t"})`);
  const names = () => [...w.__t.querySelectorAll("tbody tr td:first-child")].map(td => td.textContent);
  eq(names(), ["a", "c"]);
  eq(w.__t.querySelector(".tbl-foot span").textContent.trim().replace(/\s+/g, " "), "2 of 3 rows Show all");
  [...w.__t.querySelectorAll("th")][1].click();                      // same column again: reverse
  eq(names(), ["b", "c"]);
  [...w.__t.querySelectorAll("th")][0].click();                      // text column: ascending first
  eq(names(), ["a", "b"]);
  [...w.__t.querySelectorAll("button")].find(b => b.textContent === "Show all").click();
  eq(names().length, 3);
  ev(`window.__e = table([{k: "a", label: "A"}], [], {empty: "None here."})`);
  eq(w.__e.textContent, "None here.");
});
test("a table sorted by a column that doesn't exist still draws", () => {
  eq(ev(`table([{k: "a", label: "A"}], [{a: 1}, {a: 2}], {sort: "missing"}).querySelectorAll("tbody tr").length`), 2);
});
test("barFmt scales bars", () => {
  const w1 = ev(`barFmt(10)(5).querySelector("i").style.width`);
  const w2 = ev(`barFmt(0)(5).querySelector("i").style.width`);
  eq(w1, "30px"); eq(typeof w2, "string");
});
test("seg marks the chosen option and reports clicks", () => {
  ev(`window.__got = null; window.__s = seg([["a", "A"], ["b", "B"]], "b", v => window.__got = v)`);
  eq([...w.__s.querySelectorAll("button")].map(b => b.className), ["", "on"]);
  w.__s.querySelector("button").click();
  eq(w.__got, "a");
});
test("note builds a details box and drops empty paragraphs", () => {
  eq(ev(`note("How", "one", null, "two").querySelectorAll("p").length`), 2);
});
test("typeChip, selected and bookTitle use the library", () => {
  eq(ev(`typeChip("PER").className`), "t PER");
  eq(ev(`selected()`), ["alpha", "beta", "gamma"]);
  eq(ev(`bookTitle("alpha")`), "alpha"); eq(ev(`bookTitle("nope")`), "nope");
});
test("withBooks adds the selection", () => { eq(ev(`withBooks({q: 1})`), { books: ["alpha", "beta", "gamma"], q: 1 }); });

test("chart builders return SVG with the data in it", () => {
  const s = ev(`arcChart([{book: "a", title: "A", label: "1", words: 9}, {book: "a", title: "A", label: "2", words: 9}], [{name: "x", values: [1, null], counts: [1, 0]}], {})`);
  eq(s.tagName, "svg"); eq(s.querySelectorAll("circle").length, 1);
  eq(ev(`presenceChart([{title: "T", bins: [0, 3, 1]}], "#000").querySelectorAll("rect").length`), 1 + 2);
  eq(ev(`hbarChart([{name: "n", color: "#000", rows: [{item: "a", n: 2}, {item: "b", n: 1}]}]).querySelectorAll("rect").length`), 2);
  eq(ev(`propChart({PROP: 1, NOM: 1, PRON: 2}).querySelectorAll("rect").length`), 3 + 3);
  eq(ev(`lineChart(["a", "b"], [{name: "s", color: "#000", values: [1, 2]}]).querySelectorAll("circle").length`), 2);
  eq(ev(`scatter([{x: 0, y: 0, label: "a"}, {x: 1, y: 1, label: "b"}], () => "#000", [0.5, 0.3]).querySelectorAll("circle").length`), 2);
  eq(ev(`dendrogram({children: [{leaf: 0, size: 1, height: 0}, {leaf: 1, size: 1, height: 0}], size: 2, height: 1}, [{label: "a"}, {label: "b"}], () => "#000").querySelectorAll("path").length`), 1);
});
test("charts cope with empty data", () => {
  eq(ev(`presenceChart([], "#000").tagName`), "svg");
  eq(ev(`hbarChart([{name: "n", color: "#000", rows: []}]).tagName`), "svg");
  eq(ev(`arcChart([], [], {}).tagName`), "svg");
});
test("SVG export prepares a standalone copy with a white background", () => {
  const c = ev(`prepSvg(propChart({PROP: 1, NOM: 1, PRON: 1}))`);
  eq(c.getAttribute("xmlns"), "http://www.w3.org/2000/svg"); eq(c.firstChild.getAttribute("fill"), "#ffffff");
});

test("topic helpers", () => {
  eq(ev(`topicName({label: "", distinctive: [{w: "a"}, {w: "b"}, {w: "c"}, {w: "d"}]})`), "a · b · c");
  eq(ev(`topicName({label: "Mine", distinctive: []})`), "Mine");
  eq(ev(`shortName({label: "x".repeat(50), distinctive: []}, 10)`), "xxxxxxxxx…");
  eq(ev(`[topicColor(0), topicColor(12)]`), [ev("PALETTE[0]"), ev("PALETTE[0]")]);
  eq(ev(`[pctFmt(0.256), pctFmt(null), ratioFmt(2.55), ratioFmt(25), ratioFmt(null)]`), ["25.6%", "—", "× 2.6", "× 25", "—"]);
  eq(ev(`[versus({p: 0.01, ratio: 2}, "here"), versus({p: 0.01, ratio: 0.5}, "here"), versus({p: 0.5, ratio: 2}, "here"), versus({p: null, ratio: 2}, "here")]`), ["more here", "less here", "", ""]);
  eq(ev(`heatBg(1, 1)`), "rgba(46,74,98,0.85)"); eq(ev(`heatBg(1, 1, true)`), "rgba(181,71,60,0.85)");
  eq(ev(`heatBg(0, 0)`), "rgba(46,74,98,0)");
});
test("itemQuery builds concordance queries", () => {
  eq(ev(`itemQuery("say", "lemma")`), ['[lemma="say"]', "pattern"]);
  eq(ev(`itemQuery("said_VERB", "word_pos")`), ['[word="said" & pos="VERB"]', "pattern"]);
  eq(ev(`itemQuery("VERB", "pos")`), ['[pos="VERB"]', "pattern"]);
  eq(ev(`itemQuery("a*b", "word")`), ["a*b", "simple"]);
});
test("label helpers", () => {
  eq(ev(`booksLabel(["alpha"])`), "alpha"); eq(ev(`booksLabel(["alpha", "beta"])`), "alpha + beta");
  eq(ev(`specLabel({kind: "unit", name: "Holmes"})`), "Holmes"); eq(ev(`specLabel({kind: "tag", tag: "x", type: "PER"})`), "tag “x” (PER)");
  eq(ev(`specLabel({kind: "others"})`), "everyone else"); eq(ev(`specLabel(null)`), "?");
  eq(ev(`scopeLabel({kind: "dialogue"})`), "in dialogue"); eq(ev(`scopeLabel({kind: "all"})`), "across the whole text");
});
test("statCols follows the chosen measure", () => {
  const cols = ev(`statCols({measure: "lr", test: "ll", bonferroni: false}, false, [])`).map(c => c.k);
  eq(cols.slice(0, 5), ["item", "a", "pa", "b", "pb"]); eq(cols.includes("lr") && cols.includes("ll") && cols.includes("p"), true);
  eq(ev(`statCols({measure: "ll", test: "ll"}, true, ["A", "B"])`).some(c => c.label === "More typical of"), true);
});

test("pageKey: a key per page, one for all entity profiles", () => {
  const key = h => { w.location.hash = h; return ev("pageKey()"); };
  eq([key("#/dialogue/verbs"), key("#/entities/e:alpha:1"), key("#/entities"), key("#/compare"), key("#/corpus/kwic")],
     ["dialogue/verbs", "entity", "entities", "compare", "corpus/kwic"]);
});
test("pluralMode: the page's own choice, else the default", () => {
  ev(`S.lib.settings.plural = false; S.pluralPages = {compare: true}`);
  w.location.hash = "#/compare"; eq(ev("pluralMode()"), true);
  w.location.hash = "#/network"; eq(ev("pluralMode()"), false);
  ev(`S.lib.settings.plural = true`); eq(ev("pluralMode()"), true);
  ev(`S.lib.settings.plural = false; S.pluralPages = {}`);
});
test("pluralBox shows the page's state and offers a reset only when it differs from the default", () => {
  w.location.hash = "#/compare";
  let b = ev("pluralBox()");
  eq([b.querySelector("input").checked, !!b.querySelector("button")], [false, false]);
  ev(`S.pluralPages = {compare: true}`);
  b = ev("pluralBox()");
  eq([b.querySelector("input").checked, !!b.querySelector("button")], [true, true]);
  b.querySelector("button").click();                                   // back to the default: the page forgets its choice
  eq([ev("S.pluralPages"), JSON.parse(w.localStorage.getItem("analyser.plural"))], [{}, {}]);
  b = ev("pluralBox()");
  const box = b.querySelector("input");                                // ticking it remembers the page's choice
  box.checked = true; box.dispatchEvent(new w.Event("change"));
  eq(ev("S.pluralPages"), { compare: true });
  ev(`S.pluralPages = {}; saveState("analyser.plural", {})`);
});
test("choosing other books puts every page's plural-group choice back to the default", () => {
  const all = ev("S.lib.books.map(b => b.id)");
  ev(`S.pluralPages = {compare: true}; setSel(${JSON.stringify(all)})`);         // the same books: kept
  eq(ev("S.pluralPages"), { compare: true });
  ev(`setSel(${JSON.stringify(all.slice(0, 1))})`);                             // other books: reset
  eq([ev("S.pluralPages"), JSON.parse(w.localStorage.getItem("analyser.plural"))], [{}, {}]);
  ev(`setSel(${JSON.stringify(all)})`);
});
test("every post carries the page's plural-group choice unless it sets one", () => {
  const orig = w.fetch, sent = [];
  w.fetch = (p, o) => { sent.push(o && o.body ? JSON.parse(o.body) : null); return new Promise(() => {}); };
  try {
    ev(`S.pluralPages = {compare: true}`); w.location.hash = "#/compare";
    ev(`api("/api/x", {a: 1}); api("/api/y", {plural: false}); api("/api/z")`);
    eq(sent, [{ a: 1, plural: true }, { plural: false }, null]);
  } finally { w.fetch = orig; ev(`S.pluralPages = {}`); w.location.hash = "#/entities"; }
});

test("plotChart draws one shaded slice per non-empty bin, so a frequent word costs no more than a rare one", () => {
  const bins = n => Array.from({ length: 200 }, (_, i) => (i % 2 ? n : 0));
  const g = ev(`plotChart([{ title: "A", hits: 5000, per1k: 3, bins: ${JSON.stringify(bins(50))} }, { title: "B", hits: 0, per1k: 0, bins: ${JSON.stringify(bins(0))} }])`);
  eq(g.querySelectorAll("rect").length, 2 /* one frame per book */ + 100 /* the non-empty slices of the first */);
  eq(g.querySelectorAll("line").length, 0);
});
test("the sentence-type control is one function with a compact form", () => {
  const full = ev(`sentenceTypeFilter({ type: "", weigh: false }, () => {})`), small = ev(`sentenceTypeFilter({ type: "", weigh: false }, () => {}, true)`);
  eq([full.classList.contains("small"), small.classList.contains("small")], [false, true]);
  eq([full.querySelectorAll("option").length, small.querySelectorAll("option").length], [4, 4]);
});

test("charts with many lines name them by tooltip instead of piling labels at the right", () => {
  const lines = n => JSON.stringify(Array.from({ length: n }, (_, i) => ({ name: "Book " + i, color: "#336", values: Array.from({ length: 50 }, (_, j) => (i + j) % 40) })));
  const few = ev(`timeChart(${lines(5)})`), many = ev(`timeChart(${lines(60)})`);
  eq([few.querySelectorAll("polyline").length, few.querySelectorAll("text").length > many.querySelectorAll("text").length], [5, true]);
  eq([many.querySelectorAll("polyline").length, [...many.querySelectorAll("polyline title")].map(t => t.textContent).slice(0, 2)], [60, ["Book 0", "Book 1"]]);
  const labels = n => ev(`lineChart(${JSON.stringify(Array.from({ length: n }, (_, i) => "Book " + i))}, [{ name: "x", color: "#336", values: ${JSON.stringify(Array(n).fill(3))} }])`)
    .querySelectorAll("text[transform]").length;
  eq([labels(8), labels(60) <= 16], [8, true]);
});

console.log(JSON.stringify({ passed, failures, errorsAtEnd: page.errors }));
process.exit(0);
