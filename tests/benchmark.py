"""Time every analysis the analyser offers over a whole library, to see how it copes with many books.

    python tests/benchmark.py                          # sixty generated books (nothing of yours is touched)
    python tests/benchmark.py --sources /path/to/your/books       # your own books, read-only
    python tests/benchmark.py --only network --only kwic              # just some of the requests (name contains…)

It loads every book, then asks for what each page of the browser asks for, with all books selected, and prints how long each answer
took and how large it was. Anything slower than `--slow` seconds is marked, and any request that fails makes the exit code 1.
Your own books are only read; the analyser's files for this run (the parsed-book cache, saved models) go into a temporary folder
unless you give `--data`, so a first run parses every book and later runs with the same `--data` start faster.
"""
from __future__ import annotations

import argparse
import resource
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import fixture  # noqa: E402


def megabytes_in_use():
    """The most memory this process has used so far, in MB (macOS counts bytes, Linux kilobytes)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / 1e6 if sys.platform == "darwin" else peak / 1e3


def requests_for(books, units):
    """The requests to time -> [(name, method, path, body)]: what the pages of the browser ask for, over all `books`.
    `units` is the entity list (`/api/units`), from which the most mentioned people stand in for "an entity"."""
    B = {"books": books}
    people = [r["id"] for r in units["rows"] if r["type"] == "PER"]
    top, second = (people + [None, None])[:2]
    one = {"kind": "unit", "id": top}
    seg = {"mode": "slices", "n": 10}
    out = [
        ("units", "POST", "/api/units", B),
        ("profile", "POST", "/api/profile", {**B, "id": top}),
        ("profile of a book", "POST", "/api/profile", {**B, "id": "book:" + books[0]}),
        ("distinctive words", "POST", "/api/distinctive", {**B, "target": one, "reference": {"kind": "others"}, "rel": "agent"}),
        ("compare two", "POST", "/api/compare", {**B, "a": one, "b": {"kind": "unit", "id": second}}),
        ("book by book", "POST", "/api/bybook", {**B, "target": one, "rel": "mod"}),
        ("evidence", "POST", "/api/evidence", {**B, "target": one, "kind": "agent", "key": "say"}),
        ("plural suggestions", "POST", "/api/plurals/suggestions", B),
        ("network, sentence", "POST", "/api/network", {**B, "kind": "sentence", "types": ["PER"], "min_weight": 1}),
        ("network, dialogue", "POST", "/api/network", {**B, "kind": "dialogue", "types": ["PER"], "min_weight": 1}),
        ("network, addressed", "POST", "/api/network", {**B, "kind": "addressed", "types": ["PER"], "min_weight": 1}),
        ("network, all types", "POST", "/api/network", {**B, "kind": "paragraph", "types": ["PER", "LOC", "FAC", "GPE", "ORG", "VEH", "VAR"], "min_weight": 1}),
        ("dialogue overview", "POST", "/api/dialogue/overview", B),
        ("dialogue verbs", "POST", "/api/dialogue/verbs", {**B, "target": one}),
        ("dialogue voice", "POST", "/api/dialogue/voice", {**B, "target": one, "reference": {"kind": "others"}}),
        ("dialogue style", "POST", "/api/dialogue/style", B),
        ("conversations", "POST", "/api/dialogue/conversations", B),
        ("quotes", "POST", "/api/dialogue/quotes", {**B, "filter": {}}),
        ("speech of an entity", "POST", "/api/dialogue/entity", {**B, "id": top}),
        ("narrators", "POST", "/api/dialogue/narrators", B),
        ("narrator suggestions", "POST", "/api/narrators/suggestions", B),
        ("kwic, a common word", "POST", "/api/corpus/kwic", {**B, "query": "the"}),
        ("kwic, in dialogue only", "POST", "/api/corpus/kwic", {**B, "query": "the", "scope": {"kind": "dialogue"}}),
        ("kwic, said # Holmes", "POST", "/api/corpus/kwic", {**B, "query": "said # Holmes"}),
        ("kwic, a pattern", "POST", "/api/corpus/kwic", {**B, "query": '[pos="ADJ"]* [pos="NOUN"]+', "mode": "pattern"}),
        ("kwic, many optional parts", "POST", "/api/corpus/kwic", {**B, "query": '[]? []? []? []? []? []? []? []? "zzz"', "mode": "pattern"}),
        ("kwic, near a word", "POST", "/api/corpus/kwic", {**B, "query": "said", "near": {"item": "holmes", "left": 5, "right": 5}}),
        ("kwic, with a context search", "POST", "/api/corpus/kwic", {**B, "query": "said", "ctx": {"query": "the", "left": 5, "right": 5}}),
        ("word-type options", "POST", "/api/corpus/filters", B),
        ("word list", "POST", "/api/corpus/wordlist", {**B, "unit": "word"}),
        ("word list, word+POS+lemma", "POST", "/api/corpus/wordlist", {**B, "unit": "word_pos_lemma"}),
        ("n-grams 2-3", "POST", "/api/corpus/ngrams", B),
        ("n-grams 2-5", "POST", "/api/corpus/ngrams", {**B, "n_min": 2, "n_max": 5}),
        ("collocates", "POST", "/api/corpus/collocates", {**B, "query": "said"}),
        ("keywords", "POST", "/api/corpus/keywords", {"books": books[len(books) // 2:], "reference": {"books": books[:len(books) // 2]}}),
        ("chapters", "POST", "/api/narrative/segments", {**B, "seg": {"mode": "chapters"}}),
        ("arc of entities", "POST", "/api/narrative/arcs", {**B, "kind": "entities", "ids": [i for i in (top, second) if i], "seg": seg}),
        ("arc of dialogue", "POST", "/api/narrative/arcs", {**B, "kind": "dialogue", "seg": seg}),
        ("arc of supersenses", "POST", "/api/narrative/arcs", {**B, "kind": "supersenses", "seg": seg}),
        ("style per book", "POST", "/api/narrative/style", {**B, "by": "book"}),
        ("style per slice", "POST", "/api/narrative/style", {**B, "by": "segment", "seg": seg}),
        ("stylometry of books", "POST", "/api/narrative/stylometry", {**B, "units": "books"}),
        ("stylometry of slices", "POST", "/api/narrative/stylometry", {**B, "units": "segments", "seg": {"mode": "slices", "n": 5}}),
        ("sentiment", "POST", "/api/narrative/sentiment", {**B, "ids": [top], "seg": seg}),
        ("text view", "POST", "/api/read", {**B, "book": books[0], "seg": {"mode": "chapters"}, "index": 1}),
        ("link suggestions", "GET", "/api/links/suggestions", None),
        ("link search", "GET", "/api/links/search?q=holmes", None),
        ("fit a topic model", "POST", "/api/topics/fit", {**B, "cfg": {"k": 10, "runs": 2, "min_df": 2, "pos": ["NOUN", "VERB", "ADJ"]}, "name": "benchmark"}),
    ]
    return out


def topic_requests(books, units, model_id):
    """The requests that need a fitted topic model."""
    B = {"books": books}
    top = next(r["id"] for r in units["rows"] if r["type"] == "PER")
    return [(f"topic page: {part}", "POST", "/api/topics/page", {**B, "id": model_id, "topic": 0, "part": part})
            for part in ("words", "where", "groups", "passages", "entities", "speech")] + [
        ("topic model", "POST", "/api/topics/model", {"id": model_id}),
        ("topic comparison: map", "POST", "/api/topics/compare", {"id": model_id, "part": "map"}),
        ("topic comparison: pair", "POST", "/api/topics/compare", {**B, "id": model_id, "part": "pair", "a": 0, "b": 1}),
        ("topics of an entity", "POST", "/api/topics/entity", {**B, "id": model_id, "unit": top})]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sources", nargs="*", help="folders with BookNLP exports (default: generate sixty small books)")
    parser.add_argument("--books", type=int, default=60, help="how many books to generate when no --sources are given")
    parser.add_argument("--data", help="a folder for the analyser's own files (default: a temporary one)")
    parser.add_argument("--only", action="append", default=[], help="run only requests whose name contains this (repeatable)")
    parser.add_argument("--slow", type=float, default=2.0, help="seconds after which a request is marked slow")
    args = parser.parse_args()

    from alex import app as app_module
    from alex.core.library import Library
    from fastapi.testclient import TestClient
    from fixture import LOCAL

    work = Path(tempfile.mkdtemp(prefix="analyser-benchmark-"))
    if args.sources:
        sources = [Path(s).expanduser() for s in args.sources]
    else:
        print(f"Generating {args.books} books …")
        fixture.build_many(work / "exports", args.books)
        sources = [work / "exports"]
    lib = Library(data_dir=Path(args.data).expanduser() if args.data else work / "data", sources=sources)
    books = sorted(lib.scan()[0])
    if not books:
        sys.exit("No books found.")
    started = time.time()
    broken = []
    for b in books:
        try:
            lib.book(b)
        except Exception as e:  # noqa: BLE001 - report it and go on with the others
            broken.append(f"{b}: {e}")
    print(f"{len(books)} books found; all loaded in {time.time() - started:.1f} s; {megabytes_in_use():.0f} MB in use")
    for line in broken:
        print("  could not be read:", line)
    books = [b for b in books if not any(x.startswith(b + ":") for x in broken)]

    client = TestClient(app_module.build_app(lib), base_url=LOCAL, raise_server_exceptions=False)
    failures, rows = [], []

    def run(name, method, path, body):
        if args.only and not any(o in name for o in args.only):
            return None
        peak_before, t = megabytes_in_use(), time.time()
        r = client.post(path, json=body) if method == "POST" else client.get(path)
        took = time.time() - t
        grew = megabytes_in_use() - peak_before
        rows.append((name, took, len(r.content) / 1024, r.status_code))
        too_little_text = name.startswith("fit a topic") and r.status_code == 400          # the generated books have too small a vocabulary
        print(f"{took:7.2f} s {len(r.content) / 1024:8.0f} KB  {name}" + ("   <-- slow" if took > args.slow else "") + (f"   (memory +{grew:.0f} MB)" if grew >= 50 else "")
              + ("" if r.status_code == 200 else f"   ({r.json()['detail'][:100]})" if too_little_text else f"   <-- {r.status_code}: {r.text[:150]}"), flush=True)
        if r.status_code != 200 and not too_little_text:
            failures.append(name)
        return r.json() if r.status_code == 200 else None

    units = client.post("/api/units", json={"books": books}).json()
    print(f"{len(units['rows'])} entities at your minimum mentions\n")
    for item in requests_for(books, units):
        run(*item)
    fitted = client.get("/api/topics/models").json().get("models") or []
    if fitted and (not args.only or any("topic" in o for o in args.only)):
        for item in topic_requests(books, units, fitted[0]["id"]):
            run(*item)
    total = sum(r[1] for r in rows)
    print(f"\n{len(rows)} requests in {total:.1f} s; slowest: " + ", ".join(f"{n} ({t:.1f} s)" for n, t, _, _ in sorted(rows, key=lambda r: -r[1])[:3]))
    print(f"Peak memory {megabytes_in_use():.0f} MB.")
    if failures:
        sys.exit("Failed: " + ", ".join(failures))


if __name__ == "__main__":
    main()
