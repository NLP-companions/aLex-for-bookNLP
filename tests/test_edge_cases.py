"""Awkward books: no quotes, no entities, almost no text, or a single sentence. Nothing may crash."""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient
from fixture import LOCAL

from alex import app as app_module
from alex.core.library import Library

HEADER = "COREF\tstart_token\tend_token\tprop\tcat\ttext\n"


@pytest.fixture
def odd(tmp_path, corpus):
    """A library with the usual gamma plus: 'bare' (tokens and entities only), 'noents' (no mentions at all),
    'tiny' (one sentence) and 'noquote' (mentions but the quotes file is header-only)."""
    src = next(corpus[0].glob("gamma-*"))
    root = tmp_path / "exports"
    shutil.copytree(src, root / "gamma-20260103-000000")
    bare = root / "bare-20260101-000000"
    bare.mkdir(parents=True)
    for ext in ("tokens", "entities"):
        shutil.copy(src / f"gamma.{ext}", bare / f"bare.{ext}")
    noents = root / "noents-20260101-000000"
    noents.mkdir()
    shutil.copy(src / "gamma.tokens", noents / "noents.tokens")
    (noents / "noents.entities").write_text(HEADER, encoding="utf-8")
    tiny = root / "tiny-20260101-000000"
    tiny.mkdir()
    lines = (src / "gamma.tokens").read_text().splitlines()
    (tiny / "tiny.tokens").write_text("\n".join(lines[:1] + lines[1:4]) + "\n", encoding="utf-8")
    (tiny / "tiny.entities").write_text(HEADER, encoding="utf-8")
    noq = root / "noquote-20260101-000000"
    noq.mkdir()
    for ext in ("tokens", "entities"):
        shutil.copy(src / f"gamma.{ext}", noq / f"noquote.{ext}")
    (noq / "noquote.quotes").write_text("quote_start\tquote_end\tmention_start\tmention_end\tmention_phrase\tchar_id\tquote\n", encoding="utf-8")
    return Library(data_dir=tmp_path / "data", sources=[root])


@pytest.fixture
def api(odd):
    return TestClient(app_module.build_app(odd), base_url=LOCAL, raise_server_exceptions=False)


BOOKS = ["bare", "noents", "tiny", "noquote"]


def ok(client, path, body, allowed=(200,)):
    r = client.post(path, json=body)
    assert r.status_code in allowed, (path, body, r.status_code, r.text[:300])
    return r.json() if r.headers["content-type"].startswith("application/json") else r.text


@pytest.mark.parametrize("book", BOOKS)
def test_every_analysis_copes_with_an_awkward_book(api, book):
    b = {"books": [book]}
    seg = {"mode": "slices", "n": 3}
    lib = api.get("/api/library").json()
    row = next(x for x in lib["books"] if x["id"] == book)
    assert "error" not in row and row["tokens"] > 0
    units = ok(api, "/api/units", b)
    ok(api, "/api/dialogue/overview", b)
    ok(api, "/api/dialogue/verbs", b)
    ok(api, "/api/dialogue/style", b)
    ok(api, "/api/dialogue/conversations", b)
    ok(api, "/api/dialogue/quotes", {**b, "filter": {}})
    ok(api, "/api/dialogue/narrators", b)
    ok(api, "/api/corpus/kwic", {**b, "query": "the"})
    ok(api, "/api/corpus/wordlist", b)
    ok(api, "/api/corpus/ngrams", b)
    ok(api, "/api/corpus/collocates", {**b, "query": "the"})
    for kind in ("entities", "events", "supersenses", "dialogue"):
        ok(api, "/api/narrative/arcs", {**b, "seg": seg, "kind": kind, "ids": []})
    ok(api, "/api/narrative/style", {**b, "seg": seg})
    ok(api, "/api/narrative/style", {**b, "seg": seg, "by": "segment"})
    ok(api, "/api/narrative/stylometry", {**b, "seg": seg}, allowed=(200,))
    ok(api, "/api/narrative/sentiment", {**b, "seg": seg})
    for kind in ("sentence", "paragraph", "dialogue", "addressed"):
        ok(api, "/api/network", {**b, "kind": kind, "types": ["PER", "LOC"], "keep_isolated": True})
        ok(api, "/api/network/export", {**b, "kind": kind}, allowed=(200,))
    ok(api, "/api/read", {**b, "book": book, "seg": seg, "index": 0, "layers": ["entities", "quotes", "narrators", "events", "supersenses"]})
    ok(api, "/api/read", {**b, "book": book, "seg": {"mode": "chapters"}, "tok": 1})
    ok(api, "/api/narrators/suggestions", b)
    for row in units["rows"][:2]:
        ok(api, "/api/profile", {**b, "id": row["id"]})
        ok(api, "/api/dialogue/entity", {**b, "id": row["id"]})
        ok(api, "/api/evidence", {**b, "target": {"kind": "unit", "id": row["id"]}, "kind": "agent", "key": "x"})
        ok(api, "/api/bybook", {**b, "target": {"kind": "unit", "id": row["id"]}})
    ok(api, "/api/distinctive", {**b, "target": {"kind": "type", "type": "PER"}, "reference": {"kind": "others"}})
    ok(api, "/api/compare", {**b, "a": {"kind": "type", "type": "PER"}, "b": {"kind": "type", "type": "LOC"}})
    assert api.get("/api/links/suggestions").status_code == 200


def test_a_book_without_mentions_has_an_empty_entity_list(api):
    assert ok(api, "/api/units", {"books": ["noents"]})["rows"] == []
    assert ok(api, "/api/network", {"books": ["noents"], "kind": "sentence"})["nodes"] == []
    assert ok(api, "/api/dialogue/overview", {"books": ["noents"]})["speakers"] == []


def test_a_book_without_quotes_has_no_dialogue(api):
    for book in ("bare", "noquote"):
        o = ok(api, "/api/dialogue/overview", {"books": [book]})
        assert o["dialogue_words"] == 0 and o["books"][0]["quotes"] == 0 and o["books"][0]["share"] == 0
        assert ok(api, "/api/corpus/kwic", {"books": [book], "query": "the", "scope": {"kind": "dialogue"}})["total"] == 0
        assert ok(api, "/api/narrative/arcs", {"books": [book], "seg": {"mode": "slices", "n": 3}, "kind": "dialogue"})["series"][0]["values"] == [0, 0, 0]


def test_mixed_selections_work(api):
    everything = ok(api, "/api/units", {"books": BOOKS + ["gamma"]})
    assert len(everything["rows"]) == len(ok(api, "/api/units", {"books": ["gamma"]})["rows"]) + len(ok(api, "/api/units", {"books": ["bare"]})["rows"]) + len(ok(api, "/api/units", {"books": ["noquote"]})["rows"])
    ok(api, "/api/narrative/stylometry", {"books": BOOKS + ["gamma"], "seg": {"mode": "slices", "n": 3}})
    ok(api, "/api/corpus/keywords", {"books": ["gamma"], "reference": {"kind": "books", "books": ["tiny"]}})


def test_topics_refuse_tiny_books_with_a_message(api):
    r = api.post("/api/topics/fit", json={"books": ["tiny"], "cfg": {}})
    assert r.status_code == 400 and "Only" in r.json()["detail"]
    r = api.post("/api/topics/scan", json={"books": ["tiny"], "cfg": {}, "ks": [3]})
    assert r.status_code == 400


def test_the_reader_handles_positions_at_the_edges(api):
    b = {"books": ["tiny"], "book": "tiny", "seg": {"mode": "slices", "n": 5}}
    assert ok(api, "/api/read", {**b, "index": 4})["paragraphs"] is not None
    assert ok(api, "/api/read", {**b, "tok": 2, "end": 99999})["paragraphs"]
    assert api.post("/api/corpus/context", json={"books": ["tiny"], "book": "tiny", "tok": 0}).status_code == 200


def test_a_sentence_without_words_after_filtering_does_not_divide_by_zero(odd):
    from alex.core import narrative
    from alex.core.view import View
    v = View(odd, ["tiny"])
    assert narrative.style(v, {"mode": "slices", "n": 4})["rows"]
    assert narrative.stylometry(v, {"mode": "slices", "n": 4})["error"]
