// Visit every page of the analyser in a simulated browser and report what went wrong (JSON on the last line).
// usage: node smoke.mjs http://127.0.0.1:8766
import { api, openPage } from "./harness.mjs";

const base = process.argv[2];
const results = { visited: [], problems: [] };
const note = (where, what) => results.problems.push(`${where}: ${what}`);

const page = await openPage(base);
const ALL = ["alpha", "beta", "gamma"];
const lib = await api(base, "/api/library");
const units = (await api(base, "/api/units", { books: ALL })).rows;
const holmes = units.find(u => u.name === "Holmes" && u.books[0] === "alpha").id;
const model = (await api(base, "/api/topics/fit", { books: ALL, cfg: { chunk_words: 60, k: 4, min_df: 2, runs: 2 }, name: "Smoke" })).id;
const mid = encodeURIComponent(model);

const routes = [
  ["#/books", /Minimum mentions/], ["#/entities", /Choose an entity/], [`#/entities/${encodeURIComponent(holmes)}`, /How they're referred to/],
  ["#/dialogue/speakers", /Dialogue in each book/], ["#/dialogue/verbs", /How speech is introduced/], ["#/dialogue/voice", /Speaking style/],
  ["#/dialogue/conversations", /Conversations/], ["#/dialogue/quotes", /Quotes/],
  ["#/corpus/kwic", /Search for a word/], ["#/corpus/wordlist", /tokens/], ["#/corpus/ngrams", /different n-grams/], ["#/corpus/collocates", /Search for a word/], ["#/corpus/keywords", /Target/],
  ["#/narrative/arcs", /Plot/], ["#/narrative/style", /Sentence length/], ["#/narrative/stylometry", /Cluster tree/], ["#/narrative/sentiment", /Sentiment/],
  ["#/compare", /Compare two entities/], ["#/network", /Building network|links/i], ["#/links", /Suggested links/], ["#/narrators", /Narrators/],
  ["#/read/alpha", /CHAPTER|Holmes/], [`#/read/alpha/300`, /Holmes|CHAPTER/],
  ["#/topics", /Fit a new model/], [`#/topics/${mid}`, /Most probable words/], [`#/topics/${mid}/0`, /Words/], [`#/topics/${mid}/compare/map`, /Cluster tree/],
  [`#/topics/${mid}/compare/pair`, /Words/], [`#/topics/${mid}/compare/grid`, /Topic/],
];
for (const [hash, expect] of routes) {
  try {
    const errs = await page.go(hash);
    results.visited.push(hash);
    errs.forEach(e => note(hash, e));
    page.problems().forEach(p => note(hash, p));
    if (!expect.test(page.text())) note(hash, `page text doesn't match ${expect}: “${page.text().slice(0, 120).replace(/\s+/g, " ")}…”`);
  } catch (e) { note(hash, e.message); }
}
results.errorsAtEnd = page.errors.slice();
console.log(JSON.stringify(results));
process.exit(0);
