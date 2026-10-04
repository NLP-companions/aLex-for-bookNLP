// The pages in a simulated browser over a library of many books (here: whatever the server has, all selected): nothing may break,
// and the charts and lists must stay a size a browser copes with.
// usage: node many.mjs http://127.0.0.1:8766
import { api, openPage } from "./harness.mjs";

const base = process.argv[2];
const failures = [], passed = [];
const page = await openPage(base);
const w = page.window;
const $$ = s => page.$$(s);

async function scenario(name, fn) {
  const before = page.errors.length;
  try {
    await fn();
    const errs = page.errors.slice(before);
    if (errs.length) throw new Error("script errors: " + errs.join(" | ").slice(0, 400));
    const bad = page.problems();
    if (bad.length) throw new Error(bad.join(" | "));
    passed.push(name);
  } catch (e) { failures.push(`${name}: ${e.message}`); }
}
function expect(cond, message) { if (!cond) throw new Error(message); }

const lib = await api(base, "/api/library");
const books = lib.books.map(b => b.id);
const model = (await api(base, "/api/topics/fit", { books, cfg: { chunk_words: 80, k: 4, min_df: 2, runs: 1, pos: ["NOUN", "VERB", "ADJ"] }, name: "Many" }).catch(() => ({}))).id;

await scenario(`${books.length} books are selected and the Library page lists them all`, async () => {
  await page.go("#/books");
  expect($$("#main table.books tbody tr").length >= books.length, "a row per book");
});
await scenario("the network is cut to the strongest entities and says so", async () => {
  w.eval(`S.net.min_weight = 1; S.net.max_nodes = 10; S.net.types = ["PER"]; S.net.kind = "sentence"`);
  await page.go("#/network");
  const circles = $$("#main .net-canvas svg circle").length;
  expect(circles > 0 && circles <= 10, `${circles} circles`);
  expect(/most strongly linked of/.test(page.text()), "a note says how many there were");
});
await api(base, "/api/links/auto", {});                              // from here on, every Holmes (and Watson) is one person across all the books
w.eval("S.units = null");
await scenario("the entity list opens a person linked across every book, whose charts stay readable", async () => {
  const units = (await api(base, "/api/units", { books })).rows;
  const holmes = units.find(u => u.name === "Holmes" && u.linked);
  expect(holmes && holmes.books.length === books.length, `Holmes is linked across all ${books.length} books`);
  await page.go("#/entities");
  await page.go("#/entities/" + encodeURIComponent(holmes.id));
  expect(/Book by book/.test(page.text()), "the book-by-book section");
  expect(new RegExp(`The 8 books with most actions of ${books.length}`).test(page.text()), "the kinds-of-action chart shows only the biggest books and says so");
  expect($$("#main svg").every(svg => svg.querySelectorAll("*").length < 5000), "no chart has thousands of elements");
});
await scenario("dialogue across all books", async () => {
  await page.go("#/dialogue/speakers");
  expect(/Dialogue in each book/.test(page.text()), "the per-book table");
  const chart = $$("#main svg").find(svg => svg.querySelectorAll("polyline").length >= books.length);
  expect(chart && chart.querySelectorAll("polyline title").length === books.length, "a line per book, each named by a tooltip");
});
await scenario("a concordance of a common word draws a bounded plot", async () => {
  w.eval(`S.corp.query = "the"; S.corp.mode = "simple"; S.corp.scope = { kind: "all" }; S.corp.near = null; S.corp.ctx.query = "";`);
  await page.go("#/corpus/kwic");
  const plot = $$("#main svg").find(svg => svg.getAttribute("aria-label") === "Concordance plot");
  expect(plot, "the plot");
  expect(plot.querySelectorAll("rect").length <= books.length * 201 + 5, "at most one shaded slice per 200th of each book");
  expect($$("#main .kwic .kl").length === 500, "the first page of lines");
});
await scenario("word lists, n-grams and keywords", async () => {
  await page.go("#/corpus/wordlist");
  await page.go("#/corpus/ngrams");
  await page.go("#/corpus/keywords");
});
await scenario("arcs, style and stylometry", async () => {
  await page.go("#/narrative/arcs");
  const chart = $$("#main svg").find(svg => svg.querySelectorAll("polyline").length);
  expect(chart, "an arc chart");
  await page.go("#/narrative/style");
  await page.go("#/narrative/stylometry");
  expect(/Cluster tree/.test(page.text()), "the cluster tree");
});
await scenario("link suggestions, narrators and the text view", async () => {
  await page.go("#/links");
  await page.go("#/narrators");
  await page.go("#/read/" + encodeURIComponent(books[0]));
});
if (model) await scenario("topics over all the books", async () => {
  await page.go("#/topics/" + encodeURIComponent(model));
  expect(/Most probable words/.test(page.text()), "the model overview");
  await page.go(`#/topics/${encodeURIComponent(model)}/0`);
});

console.log(JSON.stringify({ passed, failures, errorsAtEnd: page.errors }));
process.exit(0);
