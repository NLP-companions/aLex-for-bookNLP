// Visit every page of a library with no books at all (what a fresh install shows) and report anything that breaks (JSON on the last line).
// usage: node empty.mjs http://127.0.0.1:8766
import { openPage } from "./harness.mjs";

const base = process.argv[2];
const results = { visited: [], problems: [] };
const page = await openPage(base);

const routes = ["#/books", "#/entities", "#/dialogue/speakers", "#/dialogue/verbs", "#/dialogue/voice", "#/dialogue/conversations", "#/dialogue/quotes",
  "#/corpus/kwic", "#/corpus/wordlist", "#/corpus/ngrams", "#/corpus/collocates", "#/corpus/keywords",
  "#/narrative/arcs", "#/narrative/style", "#/narrative/stylometry", "#/narrative/sentiment",
  "#/compare", "#/network", "#/links", "#/narrators", "#/topics"];
for (const hash of routes) {
  try {
    const errs = await page.go(hash);
    results.visited.push(hash);
    errs.concat(page.problems()).forEach(e => results.problems.push(`${hash}: ${e}`));
  } catch (e) { results.problems.push(`${hash}: ${e.message}`); }
}
await page.go("#/books");
if (!/Where to find books/.test(page.text()) || !/No books found yet/.test(page.text())) results.problems.push("#/books: the first-run guidance is missing");
const first = page.$("#main h2");
if (!first || first.textContent !== "Where to find books") results.problems.push("#/books: “Where to find books” should come first while there are no books");
results.errorsAtEnd = page.errors.slice();
console.log(JSON.stringify(results));
process.exit(0);
