"""The web API: every route, its errors, your corrections end to end, and concurrent use."""
from __future__ import annotations

import json
import tempfile
import threading
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from fixture import LOCAL

from alex import app as app_module

ALL = ["alpha", "beta", "gamma"]


def post(client, path, body=None, status=200, **extra):
    r = client.post(path, json={"books": ALL, **(body or {}), **extra})
    assert r.status_code == status, (path, r.status_code, r.text[:300])
    return r.json()


def detail(client, path, body=None, status=400, **extra):
    r = client.post(path, json={"books": ALL, **(body or {}), **extra})
    assert r.status_code == status, (path, r.status_code, r.text[:300])
    assert r.headers["content-type"].startswith("application/json")
    return r.json()["detail"]


@pytest.fixture
def unit(client):
    """unit id of a book's entity by name."""
    rows = post(client, "/api/units")["rows"]
    return lambda name, book: next(r["id"] for r in rows if r["name"] == name and r["books"] == [book])


# ---------- pages, static files, library ----------
def test_index_and_static_files_are_never_cached(client):
    r = client.get("/")
    assert r.status_code == 200 and "aLex" in r.text and r.headers["cache-control"] == "no-cache"
    for path in ("/static/app.css", "/static/index.html"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
    assert client.get("/static/nothing.js").status_code == 404


def test_library(client):
    lib = client.get("/api/library").json()
    assert [b["id"] for b in lib["books"]] == ["alpha", "beta", "gamma"] or {b["id"] for b in lib["books"]} == set(ALL)
    a = next(b for b in lib["books"] if b["id"] == "alpha")
    assert a["words"] > 1000 and a["quotes"] == 85 and a["problems"] == [] and len(a["signature"]) == 12 and a["versions"][0]["exported"]
    assert lib["settings"]["min"]["PER"] == 2 and lib["topics_ready"] is True and "page_words" in lib["topic_notes"] and "cmp_pair" in lib["topic_notes"]
    assert {"types", "relations", "measures", "network_kinds", "dialogue_notes", "corpus_attrs", "narrative_notes", "stat_notes"} <= set(lib)
    assert client.get("/api/library").json()["books"][0]["signature"] == lib["books"][0]["signature"]      # stable between calls


def test_book_details_and_validation(client):
    r = client.post("/api/books/alpha", json={"title": "T", "year": "1890", "tags": [" a ", "b", "a", ""]})
    assert r.status_code == 200 and r.json()["year"] == 1890 and r.json()["tags"] == ["a", "b"] and r.json()["title"] == "T"
    assert client.post("/api/books/alpha", json={"year": "abc"}).json()["detail"] == "Year must be a number"
    assert client.post("/api/books/nope", json={"title": "x"}).status_code == 404
    assert client.post("/api/books/alpha", json={"year": ""}).status_code == 200


def test_original_text_download(client):
    lib = client.get("/api/library").json()
    assert next(b for b in lib["books"] if b["id"] == "alpha")["has_text"] is True
    r = client.get("/api/books/alpha/text")
    assert r.status_code == 200 and r.text.strip() and r.headers["content-disposition"] == 'attachment; filename="alpha.txt"'
    assert client.get("/api/books/nope/text").status_code == 404


def test_export_download(client, tmp_path):
    r = client.post("/api/export", json={"books": ["beta", "nope", "beta"]})        # unknown ids and repeats are ignored
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    assert r.headers["content-disposition"].startswith('attachment; filename="analyser-export-')
    (tmp_path / "got.zip").write_bytes(r.content)
    with zipfile.ZipFile(tmp_path / "got.zip") as z:
        assert {n.split("/")[1] for n in z.namelist() if n.startswith("books/")} == {"beta"}
        assert json.loads(z.read("manifest.json"))["books"].keys() == {"beta"}
    assert not [p for p in Path(tempfile.gettempdir()).glob("tmp*.zip") if p.stat().st_mtime > time.time() - 5]    # no temporary file is left behind
    for bad in ({}, {"books": []}, {"books": ["nope"]}, {"books": "alpha"}):
        assert client.post("/api/export", json=bad).status_code == 400


def test_settings(client):
    s = client.post("/api/settings", json={"min": {"PER": "5", "BOGUS": 1}, "conv_gap": 30, "count_mode": "combined"}).json()["settings"]
    assert s["min"]["PER"] == 5 and "BOGUS" not in s["min"] and s["conv_gap"] == 30 and s["count_mode"] == "combined"
    assert client.post("/api/settings", json={"count_mode": "nonsense"}).json()["settings"]["count_mode"] == "combined"
    assert client.post("/api/settings", json={"min": {"PER": "many"}}).status_code == 400
    lib = client.post("/api/settings", json={"sources": ["/no/such/folder", "/no/such/folder"]}).json()
    assert lib["books"] == [] and any("not found" in p for p in lib["problems"]) and lib["sources"] == ["/no/such/folder"]


def test_units_and_tags(client, unit):
    rows = post(client, "/api/units", type="LOC")
    assert {r["type"] for r in rows["rows"]} == {"LOC"} and rows["type_counts"]["LOC"] == 3 and rows["words"] == 2949
    h = unit("Holmes", "alpha")
    r = client.post("/api/tags", json={"id": h, "tags": ["b", "a"]}).json()
    assert r["tags"] == ["a", "b"] and r["all"] == ["a", "b"]
    assert client.post("/api/tags", json={"id": "p:99", "tags": ["x"]}).status_code == 404
    assert client.post("/api/tags", json={"tags": ["x"]}).status_code == 400


# ---------- entities ----------
def test_profile_and_friends(client, unit):
    h = unit("Holmes", "alpha")
    p = post(client, "/api/profile", id=h)
    assert p["unit"]["name"] == "Holmes" and p["relations"]["agent"]["total"] > 0
    assert client.post("/api/profile", json={"books": ["alpha"], "id": "e:alpha:999"}).status_code == 404
    d = post(client, "/api/distinctive", target={"kind": "unit", "id": h}, rel="agent", min_freq=1, show_all=True)
    assert d["summary"]["rel"] == "agent" and d["rows"]
    c = post(client, "/api/compare", a={"kind": "unit", "id": h}, b={"kind": "unit", "id": unit("Watson", "alpha")})
    assert set(c["distinctive"]) == {"agent", "patient", "poss", "mod", "prep"} and c["a"]["units"] == 1
    b = post(client, "/api/bybook", target={"kind": "type", "type": "PER"}, rel="agent")
    assert len(b["books"]) == 3 and b["rows"]
    e = post(client, "/api/evidence", target={"kind": "unit", "id": h}, kind="agent", key="say")
    assert e["total"] == e["shown"] > 0 and "\x01" in e["items"][0]["text"]
    assert detail(client, "/api/distinctive", {}) == "“target” is missing."


def test_book_and_gender_profiles(client, unit):
    """A book or a gender is a pool of entities, addressed by id prefix like narrator roles (nar:/nl:), with the
    same profile shape plus, for a book, its own facts."""
    u = post(client, "/api/units")
    genders = {row["pron"]: row for row in u["genders"]}
    assert genders["he/him/his"]["entities"] >= 3

    p = post(client, "/api/profile", id="book:alpha")
    assert p["book"]["title"] == "alpha" and p["book"]["words"] > 0
    assert {row["name"] for row in p["group"]["units"]} >= {"Holmes", "Watson"}
    assert client.post("/api/profile", json={"books": ALL, "id": "book:nope"}).status_code == 404

    g = post(client, "/api/profile", id="gender:he/him/his")
    assert "book" not in g and {row["name"] for row in g["group"]["units"]} >= {"Holmes", "Watson"}
    assert client.post("/api/profile", json={"books": ALL, "id": "gender:she/her"}).status_code == 404

    # a book or a gender works as a compare/bybook/evidence/dialogue target too, through the same resolve() path
    c = post(client, "/api/compare", a={"kind": "book", "book": "alpha"}, b={"kind": "book", "book": "beta"})
    assert c["a"]["books"] == 1 and c["b"]["books"] == 1
    v = post(client, "/api/dialogue/voice", target={"kind": "gender", "pron": "he/him/his"}, reference={"kind": "others"})
    assert v["target"]["label"] == "he/him/his"

    # comparing two books split into characters
    g = post(client, "/api/compare/books", a="alpha", b="beta")
    assert g["rows"] and all("a" in r and "b" in r for r in g["rows"])


def test_network_routes(client):
    n = post(client, "/api/network", kind="sentence", types=["PER", "LOC"])
    assert n["nodes"] and n["edges"] and n["directed"] is False and {"x", "y", "community"} <= set(n["nodes"][0])
    assert post(client, "/api/network", kind="dialogue")["directed"] is True
    assert detail(client, "/api/network", {"kind": "nonsense"}) == "Unknown network kind"
    assert detail(client, "/api/network", {"min_weight": "lots"}) == "“min_weight” should be a whole number."
    for fmt, marker in (("graphml", b"graphml"), ("gexf", b"gexf")):
        r = client.post("/api/network/export", json={"books": ALL, "kind": "sentence", "format": fmt})
        assert r.status_code == 200 and marker in r.content and f"network-sentence.{fmt}" in r.headers["content-disposition"]


# ---------- dialogue and your corrections ----------
def test_dialogue_views(client, unit):
    h = unit("Holmes", "alpha")
    assert len(post(client, "/api/dialogue/overview")["speakers"]) >= 3
    assert post(client, "/api/dialogue/verbs")["verbs"][0]["item"] == "say"
    assert post(client, "/api/dialogue/verbs", target={"kind": "unit", "id": h})["target"]["total"] > 0
    v = post(client, "/api/dialogue/voice", target={"kind": "unit", "id": h}, reference={"kind": "others"})
    assert v["summary"]["reference"] == "all other speakers"
    assert post(client, "/api/dialogue/style", min_words=0)["rows"]
    assert post(client, "/api/dialogue/conversations")["total"] >= 3
    q = post(client, "/api/dialogue/quotes", filter={"speaker": {"kind": "unit", "id": h}}, limit=3)
    assert q["shown"] == 3 and q["total"] == 67
    assert post(client, "/api/dialogue/entity", id=h)["style"]["quotes"] == 67
    assert client.post("/api/dialogue/entity", json={"books": ["alpha"], "id": "e:alpha:999"}).status_code == 404
    scoped = post(client, "/api/dialogue/scope", target={"kind": "unit", "id": h})
    assert scoped["style"]["quotes"] == 67 and scoped["time"][0]["book"] == "alpha" and len(scoped["time"][0]["values"]) == 50
    assert post(client, "/api/dialogue/scope", target={"kind": "gender", "pron": "he/him/his"})["style"]["quotes"] > 67
    assert post(client, "/api/dialogue/scope", target={"kind": "gender", "pron": "she/her"}) is None
    assert post(client, "/api/dialogue/narrators")["rows"]
    assert detail(client, "/api/dialogue/quotes", {"limit": "x"}) == "“limit” should be a whole number."


def test_correcting_a_quote_end_to_end(client, unit):
    h, w = unit("Holmes", "alpha"), unit("Watson", "alpha")
    q = post(client, "/api/annot/quote", book="alpha", qi=0)
    assert q["speaker"]["name"] in ("Holmes", "Watson") and q["fixed"] is None and q["first"] is True and q["participants"]
    other = w if q["speaker"]["id"] == h else h
    post(client, "/api/annot/addressees", book="alpha", qi=0, addressees=[other])
    fixed = post(client, "/api/annot/quote", book="alpha", qi=0)
    assert fixed["method"] == "yours" and [a["id"] for a in fixed["addressees"]] == [other]
    post(client, "/api/annot/addressees", book="alpha", qi=0, addressees=["*"])
    assert post(client, "/api/annot/quote", book="alpha", qi=0)["method"] == "yours_all"
    post(client, "/api/annot/addressees", book="alpha", qi=0, addressees=None)
    assert post(client, "/api/annot/quote", book="alpha", qi=0)["fixed"] is None
    # conversations and participants
    post(client, "/api/annot/participants", book="alpha", first_qi=0, id="e:alpha:10", action="add")
    assert any(p["id"] == "e:alpha:10" for p in post(client, "/api/annot/quote", book="alpha", qi=0)["participants"])
    post(client, "/api/annot/participants", book="alpha", first_qi=0, id="e:alpha:10", action="restore")
    assert not any(p["id"] == "e:alpha:10" for p in post(client, "/api/annot/quote", book="alpha", qi=0)["participants"])
    before = post(client, "/api/dialogue/conversations")["total"]
    post(client, "/api/annot/conversation", book="alpha", qi=3, action="split")
    assert post(client, "/api/dialogue/conversations")["total"] >= before
    post(client, "/api/annot/conversation", book="alpha", qi=3, action="reset")
    assert post(client, "/api/dialogue/conversations")["total"] == before
    assert client.post("/api/annot/quote", json={"books": ALL, "book": "alpha", "qi": 9999}).status_code == 404
    assert client.post("/api/annot/addressees", json={"book": "alpha", "qi": 9999, "addressees": []}).status_code == 404


def test_narrator_workflow(client, unit):
    w = unit("Watson", "alpha")
    opts = client.get("/api/annot/narrator_options", params={"book": "alpha"}).json()
    assert any(r["id"] == w for r in opts["rows"]) and opts["current"] is None
    post(client, "/api/annot/narrator", book="alpha", narrator=w)
    assert client.get("/api/annot/narrator_options", params={"book": "alpha"}).json()["current"] == w
    s = post(client, "/api/narrators/suggestions")
    alpha = next(b for b in s["books"] if b["book"] == "alpha")
    assert alpha["current"]["id"] == w and alpha["suggested"]["id"] == w
    post(client, "/api/annot/paragraphs", book="alpha", pids=[4, 5, 999999], narrator="anon")
    rows = post(client, "/api/dialogue/narrators")["rows"]
    assert any(r["exceptions"] == 2 for r in rows)
    post(client, "/api/annot/paragraphs", book="alpha", pids=[4, 5], narrator=None)
    assert all(r["exceptions"] == 0 for r in post(client, "/api/dialogue/narrators")["rows"])
    post(client, "/api/narrators/reject", book="alpha", key="k")
    post(client, "/api/narrators/reject", book="alpha", key="k")
    assert client.post("/api/annot/paragraphs", json={"book": "nowhere", "pids": [1]}).status_code == 404


def test_chapter_narrator_workflow(client, lib, unit):
    from alex.core import narrative as nar
    from alex.core.view import View
    v = View(lib, ["alpha"])
    segs, info = nar.book_segments(v, "alpha", {"mode": "chapters"})
    assert not info["fallback"] and len(segs) >= 2
    ch2_start = v.bd["alpha"].para[segs[1]["head"]]
    w = unit("Watson", "alpha")
    assert post(client, "/api/annot/chapter_narrator", book="alpha", pid=ch2_start, narrator=w) == {"ok": True}
    rows = post(client, "/api/dialogue/narrators")["rows"]
    assert any(r["exceptions"] >= 1 for r in rows)
    assert post(client, "/api/annot/chapter_narrator", book="alpha", pid=ch2_start, narrator=None) == {"ok": True}
    assert all(r["exceptions"] == 0 for r in post(client, "/api/dialogue/narrators")["rows"])
    assert client.post("/api/annot/chapter_narrator", json={"book": "nowhere", "pid": 0, "narrator": w}).status_code == 404


def test_narrator_linking_workflow(client):
    r = client.post("/api/narrators/link", json={"a": "nar:anon:alpha", "b": "nar:anon:beta", "name": "Chronicle"})
    assert r.status_code == 200
    lid = r.json()["id"]
    assert lid == "nl:1"
    rows = post(client, "/api/dialogue/narrators")["rows"]
    assert any(row["id"] == lid and row["name"] == "Chronicle" for row in rows)
    linkrows = client.get("/api/links/narrator_links").json()["rows"]
    assert linkrows == [{"id": lid, "name": "Chronicle", "custom_name": True,
                         "members": [{"id": "nar:anon:alpha", "name": "Narrator of alpha", "unit": None, "books": ["alpha"]},
                                     {"id": "nar:anon:beta", "name": "Narrator of beta", "unit": None, "books": ["beta"]}]}]
    assert client.post("/api/narrators/link", json={"a": "nar:anon:gamma", "b": "nar:anon:gamma"}).json()["detail"] == "Choose two different narrators"
    assert client.post("/api/narrators/link", json={"a": "nl:404", "b": "nar:anon:gamma"}).status_code == 404
    assert client.post("/api/narrators/unlink", json={"id": lid, "role": "nar:anon:beta"}).status_code == 200
    assert client.post("/api/narrators/unlink", json={"id": "nl:404", "role": "x"}).status_code == 404
    lid2 = client.post("/api/narrators/link", json={"a": "nar:anon:alpha", "b": "nar:anon:gamma"}).json()["id"]
    assert client.post("/api/narrators/unlink_all", json={"id": lid2}).status_code == 200
    assert client.post("/api/narrators/unlink_all", json={"id": lid2}).status_code == 404


def test_corrections_reach_the_files_and_survive_a_restart(client, lib, unit):
    post(client, "/api/annot/narrator", book="alpha", narrator=unit("Watson", "alpha"))
    from alex.core.library import Library
    again = Library(data_dir=lib.data_dir, sources=lib.state["sources"])
    assert again.ann["books"]["alpha"]["narrator"] == unit("Watson", "alpha")


# ---------- corpus ----------
def test_concordance_and_paging(client):
    r = post(client, "/api/corpus/kwic", query="the", limit=10)
    assert len(r["hits"]) == 10 and r["total"] > 10 and r["per_book"] and r["offset"] == 0
    second = post(client, "/api/corpus/kwic", query="the", limit=10, offset=10)
    assert "per_book" not in second and second["offset"] == 10 and second["hits"] != r["hits"]
    everything = post(client, "/api/corpus/kwic", query="the", limit=100000)
    assert everything["hits"][:10] == r["hits"] and everything["hits"][10:20] == second["hits"]
    assert post(client, "/api/corpus/kwic", query='[lemma="say"] [char="Holmes"]', mode="pattern")["total"] > 0
    c = post(client, "/api/corpus/context", book="alpha", tok=100, end=101)
    assert "\x01k\x02" in c["text"]


def test_batch_query_over_the_route(client):
    """A multi-line query (see core.corpus.Matcher) needs no route changes: the string just carries newlines."""
    said, watched = post(client, "/api/corpus/kwic", query="said")["total"], post(client, "/api/corpus/kwic", query="watched")["total"]
    r = post(client, "/api/corpus/kwic", query="said\nwatched")
    assert r["total"] == said + watched and r["batch"] is True
    assert {h["matched"] for h in r["hits"]} == {"said", "watched"}


def test_corpus_routes_take_filters_sort_levels_and_context(client):
    o = post(client, "/api/corpus/filters")
    assert {"NOUN", "VERB"} <= {x["value"] for x in o["pos"]} and {"PER", "LOC"} <= {x["value"] for x in o["ent"]} and o["tag"]
    plain = post(client, "/api/corpus/wordlist")
    verbs = post(client, "/api/corpus/wordlist", filter={"pos": ["VERB"]})
    assert 0 < verbs["kept"] < plain["tokens"] == verbs["tokens"] and all(x["n"] > 0 for x in verbs["rows"])
    triple = post(client, "/api/corpus/wordlist", unit="word_pos_lemma", filter={"pos": ["VERB"], "ent": []})
    assert {x["pos"] for x in triple["rows"]} == {"VERB"} and {"word", "pos", "lemma"} <= set(triple["rows"][0])
    coll = post(client, "/api/corpus/collocates", query="said", left=2, right=2, min_freq=1, filter={"pos": ["PROPN"]})
    assert coll["rows"] and {x["item"] for x in coll["rows"]} <= {x["item"] for x in post(client, "/api/corpus/collocates", query="said", left=2, right=2, min_freq=1)["rows"]}
    base = post(client, "/api/corpus/kwic", query="look")["total"]
    ctx = {"query": "watson", "left": 3, "right": 0, "within_sentence": True}
    kept = post(client, "/api/corpus/kwic", query="look", ctx=ctx)["total"]
    assert 0 < kept < base and post(client, "/api/corpus/kwic", query="look", ctx={**ctx, "exclude": True})["total"] == base - kept
    lines = post(client, "/api/corpus/kwic", query="the", sort=[{"pos": "R1", "by": "lemma", "desc": True}, {"pos": "book"}], limit=20)
    assert len(lines["hits"]) == 20 and lines["total"] > 20
    assert client.get("/api/library").json()["sort_by"]["freq"] == "Frequency"


@pytest.mark.parametrize("path,body,message", [
    ("/api/corpus/kwic", {"query": '[lemma="say"', "mode": "pattern"}, "no matching"),
    ("/api/corpus/kwic", {"query": "  "}, "Type something"),
    ("/api/corpus/kwic", {"query": "(", "settings": {"regex": True}}, "regular expression"),
    ("/api/corpus/kwic", {"query": "said", "sort": ["ZZ"]}, "Can't sort"),
    ("/api/corpus/kwic", {"query": "said", "sort": [{"pos": "R1", "by": "colour"}]}, "Can't sort"),
    ("/api/corpus/kwic", {"query": "said", "ctx": {"query": "[lemma=", "mode": "pattern"}}, "no matching"),
    ("/api/corpus/kwic", {"query": "said", "near": {"left": 2}}, "needs a word"),
    ("/api/corpus/kwic", {"query": "said", "context": "wide"}, "whole number"),
    ("/api/corpus/context", {"book": "alpha", "tok": 10 ** 9}, "outside the book"),
    ("/api/corpus/collocates", {"query": '[word="a"]{20}', "mode": "pattern"}, "isn't allowed"),
    ("/api/corpus/keywords", {"reference": {}}, "at least one reference book"),
])
def test_corpus_errors_are_messages(client, path, body, message):
    assert message in detail(client, path, body)


def test_lists_and_keywords(client):
    assert post(client, "/api/corpus/wordlist", unit="lemma", min_freq=5)["rows"][0]["rank"] == 1
    assert post(client, "/api/corpus/ngrams", n_min=2, n_max=2, contains="said", position="left")["rows"]
    assert post(client, "/api/corpus/collocates", query="said", left=1, right=1, min_freq=1)["hits"] > 0
    kw = post(client, "/api/corpus/keywords", scope={"kind": "dialogue"}, reference={"kind": "books", "books": ALL, "scope": {"kind": "narration"}}, min_freq=3)
    assert kw["rows"] and kw["summary"]["target_tokens"] > 0


def test_reference_files(client):
    r = client.post("/api/refs", json={"name": "Word list", "files": [{"name": "w.tsv", "text": "the\t500\nof\t300\nand\t200\nto\t150\n"}, {"name": "empty.txt", "text": ""}]}).json()
    assert r["kinds"] == {"word list": 1} and r["tokens"] == 1150
    again = client.post("/api/refs", json={"name": "Word list", "files": [{"name": "w.tsv", "text": "a\t3\n"}]}).json()
    assert again["id"] != r["id"] and sorted(x["id"] for x in client.get("/api/refs").json()["rows"]) == sorted([r["id"], again["id"]])
    kw = post(client, "/api/corpus/keywords", reference={"kind": "file", "id": r["id"]}, min_freq=3)
    assert kw["summary"]["reference_tokens"] == 1150
    assert "word forms" in detail(client, "/api/corpus/keywords", {"reference": {"kind": "file", "id": r["id"]}, "unit": "lemma"})
    assert detail(client, "/api/corpus/keywords", {"reference": {"kind": "file", "id": "gone"}}, status=404) == "That reference file is no longer available."
    assert client.post("/api/refs/delete", json={"id": r["id"]}).json() == {"ok": True}
    assert client.post("/api/refs/delete", json={"id": "../../etc/passwd"}).json() == {"ok": True}
    assert client.post("/api/refs", json={"files": []}).json()["detail"] == "Choose one or more text files."
    assert client.post("/api/refs", json={"files": [{"name": "n", "text": "!!! ???"}]}).json()["detail"] == "No words found in those files."


def test_a_damaged_reference_file_does_not_hide_the_others(client, lib):
    client.post("/api/refs", json={"name": "ok", "files": [{"name": "a.txt", "text": "the quick brown fox"}]})
    (lib.data_dir / "references" / "broken.json").write_text("{ nope")
    assert [x["name"] for x in client.get("/api/refs").json()["rows"]] == ["ok"]


# ---------- narrative and the text view ----------
def test_narrative_routes(client, unit):
    seg = {"mode": "slices", "n": 5}
    assert len(post(client, "/api/narrative/segments", seg=seg)["segments"]) == 15
    for kind in ("entities", "events", "supersenses", "dialogue"):
        assert post(client, "/api/narrative/arcs", seg=seg, kind=kind, ids=[unit("Holmes", "alpha")])["series"]
    assert post(client, "/api/narrative/style", seg=seg)["rows"] and post(client, "/api/narrative/style", seg=seg, by="segment")["rows"]
    st = post(client, "/api/narrative/stylometry", seg=seg, mfw=20, culling=10)
    assert len(st["texts"]) == 3
    assert "at least three" in post(client, "/api/narrative/stylometry", books=["alpha", "beta"], seg=seg)["error"]
    assert detail(client, "/api/narrative/stylometry", {"seg": seg, "mfw": "many"}) == "“mfw” should be a whole number."
    s = post(client, "/api/narrative/sentiment", seg=seg, ids=[unit("Holmes", "alpha")])
    assert len(s["series"]) == 2 and s["books"]


def test_emotion_lexicon_workflow(client):
    assert client.get("/api/narrative/lexicons").json() == {"vader": True, "emotion": None}
    assert "Load an emotion lexicon" in detail(client, "/api/narrative/emotion", {"seg": {"mode": "slices", "n": 5}})
    assert "No word–category pairs" in client.post("/api/narrative/lexicons", json={"text": "nothing useful here"}).json()["detail"]
    r = client.post("/api/narrative/lexicons", json={"name": "Tiny", "text": "moor\tnature\t1\nhound\tfear\t1\nhill\tnature\t1\n"}).json()
    assert r["emotion"] == {"name": "Tiny", "cats": {"nature": 2, "fear": 1}}
    e = post(client, "/api/narrative/emotion", seg={"mode": "slices", "n": 5}, cats=["nature"])
    assert [s["name"] for s in e["series"]] == ["nature"] and sum(e["series"][0]["counts"]) > 0
    assert client.post("/api/narrative/lexicons/delete").json()["emotion"] is None


def test_the_text_view(client, unit):
    seg = {"mode": "chapters", "min_words": 50, "rules": {}}
    r = post(client, "/api/read", book="alpha", seg=seg, index=1, layers=["entities", "quotes", "narrators"])
    assert r["index"] == 1 and len(r["segments"]) == 4 and r["paragraphs"] and r["quotes"] and r["topic_layer"] is None
    assert any("\x01e PER PROP in|" in p["text"] for p in r["paragraphs"]) and r["paragraphs"][0]["narrator"]
    jump = post(client, "/api/read", book="beta", seg=seg, tok=300, layers=["events", "supersenses"])
    assert any("\x01hit|" in p["text"] for p in jump["paragraphs"]) and any("\x01ev|event" in p["text"] for p in jump["paragraphs"])
    outside = client.post("/api/read", json={"books": ["alpha"], "book": "gamma", "seg": seg}).json()     # a book outside the selection
    assert outside["book"] == "gamma" and outside["paragraphs"]
    assert client.post("/api/read", json={"books": ALL, "book": "nowhere"}).status_code == 404
    assert client.post("/api/read", json={"books": ALL}).json()["detail"] == "“book” is missing."


# ---------- topics ----------
def test_topic_workflow(client, unit):
    cfg = {"chunk_words": 60, "k": 4, "min_df": 2, "runs": 2}
    assert client.get("/api/topics/models").json() == {"models": []}
    scan = post(client, "/api/topics/scan", cfg=cfg, ks=[2, 3, 99, 3])
    assert len(scan["rows"]) == 3 and [x["k"] for x in scan["rows"]][:2] == [2, 3]          # 99 is held to what the documents allow
    assert detail(client, "/api/topics/scan", {"cfg": cfg, "ks": []}) == "Choose at least one number of topics."
    mid = post(client, "/api/topics/fit", cfg=cfg, name="  Themes ")["id"]
    assert mid.startswith("themes-") and post(client, "/api/topics/fit", cfg=cfg)["id"] != mid
    models = client.get("/api/topics/models").json()["models"]
    assert {m["name"] for m in models} >= {"Themes"} and any(m["name"].startswith("NMF, 4 topics") for m in models)
    o = post(client, "/api/topics/model", id=mid)
    assert len(o["topics"]) == 4 and o["stale"] == []
    t = o["topics"][0]["id"]
    for part, key in (("words", "words"), ("where", "strips"), ("groups", "fields"), ("passages", "passages"), ("entities", "rows"), ("speech", "speakers")):
        r = post(client, "/api/topics/page", id=mid, topic=t, part=part, seg={"mode": "slices", "n": 4})
        assert key in r, part
    assert detail(client, "/api/topics/page", {"id": mid, "topic": t, "part": "nonsense"}) == "Unknown part."
    assert "Unknown topic" in detail(client, "/api/topics/page", {"id": mid, "topic": 99, "part": "words"})
    for part, key in (("map", "bases"), ("groups", "columns")):
        assert key in post(client, "/api/topics/compare", id=mid, part=part, by="book")
    assert {"shared", "a", "b"} == set(post(client, "/api/topics/compare", id=mid, part="pair", a=0, b=1, seg={"mode": "slices", "n": 4})["words"])
    assert post(client, "/api/topics/compare", id=mid, part="items", kind="mentions", types=["PER"], min=10, limit=5)["rows"]
    assert "different" in detail(client, "/api/topics/compare", {"id": mid, "part": "pair", "a": 1, "b": 1})
    e = post(client, "/api/topics/entity", id=mid, unit=unit("Holmes", "alpha"), kind="speech")
    assert e["count"] > 0 and len(e["rows"]) == 4
    arcs = post(client, "/api/narrative/arcs", kind="topics", model=mid, ids=[t], seg={"mode": "slices", "n": 4})
    assert [s["id"] for s in arcs["series"]] == [t] and arcs["info"]["model"]["name"] == "Themes"
    post(client, "/api/topics/rename", id=mid, name="Renamed", topic=0, label="First")
    assert post(client, "/api/topics/model", id=mid)["name"] == "Renamed"
    r = post(client, "/api/read", book="alpha", seg={"mode": "slices", "n": 4}, index=0, layers=["topics"], topics={"model": mid, "focus": "all"})
    assert r["topic_layer"]["error"] is None and any("\x01tw|" in p["text"] for p in r["paragraphs"]) and r["paragraphs"][0]["topic"]
    post(client, "/api/topics/delete", id=mid)
    assert "no longer exists" in detail(client, "/api/topics/model", {"id": mid})
    gone = post(client, "/api/read", book="alpha", seg={"mode": "slices", "n": 4}, index=0, layers=["topics"], topics={"model": mid})
    assert gone["topic_layer"]["error"] and gone["paragraphs"]


def test_topic_errors(client):
    for bad in ("../x", "no such", None):
        assert client.post("/api/topics/model", json={"id": bad}).status_code == 400
    assert "Only 3 documents" in detail(client, "/api/topics/fit", {"cfg": {"unit": "book"}})        # whole books: one document each
    assert detail(client, "/api/topics/fit", {"cfg": {"k": "x"}}) == "“k” should be a number."
    assert client.post("/api/topics/fit", json={"cfg": {}}).json()["detail"] == "No books selected"


def test_topics_can_be_switched_off(lib):
    c = TestClient(app_module.build_app(lib, topics_module=None), base_url=LOCAL, raise_server_exceptions=False)
    assert c.get("/api/library").json()["topics_ready"] is False
    for r in (c.get("/api/topics/models"), c.post("/api/topics/fit", json={"books": ALL}), c.post("/api/narrative/arcs", json={"books": ALL, "kind": "topics"})):
        assert r.status_code == 400 and "scikit-learn" in r.json()["detail"]
    assert c.post("/api/units", json={"books": ALL}).status_code == 200


# ---------- links ----------
def test_links_workflow(client, unit):
    a, b = unit("Holmes", "alpha"), unit("Holmes", "beta")
    assert client.get("/api/links/suggestions").json() == {"rows": [], "total": 0}      # no series yet
    for book in ("alpha", "beta", "gamma"):
        client.post(f"/api/books/{book}", json={"series": "Baker Street"})
    sug = client.get("/api/links/suggestions").json()
    assert sug["total"] > 0 and any({s["a"]["id"], s["b"]["id"]} == {a, b} for s in sug["rows"])
    assert any(x["id"] == a for x in client.get("/api/links/search", params={"q": "holmes"}).json()["rows"])
    everyone = client.get("/api/links/search", params={"q": "  "}).json()["rows"]                # no name: the most mentioned first
    assert len(everyone) > 1 and [x["mentions"] for x in everyone] == sorted((x["mentions"] for x in everyone), reverse=True)
    pid = client.post("/api/links/link", json={"a": a, "b": b, "name": "Sherlock"}).json()["id"]
    persons = client.get("/api/links/persons").json()["rows"]
    assert persons[0]["id"] == pid and persons[0]["name"] == "Sherlock" and len(persons[0]["members"]) == 2
    assert client.post("/api/name", json={"id": pid, "name": "S. Holmes"}).status_code == 200
    assert "S. Holmes" in [x["name"] for x in post(client, "/api/units")["rows"]]
    assert client.post("/api/links/unlink", json={"id": pid, "book": "beta", "coref": 5}).json() == {"ok": True}
    assert client.get("/api/links/persons").json()["rows"] == []
    client.post("/api/links/reject", json={"a": a, "b": b})
    assert not any({s["a"]["id"], s["b"]["id"]} == {a, b} for s in client.get("/api/links/suggestions").json()["rows"])


def test_auto_link(client):
    r = client.post("/api/links/auto").json()["linked"]
    assert any(row["name"] == "Holmes" and row["books"] == 3 for row in r)


def test_unlink_all(client, unit):
    a, b, c = unit("Holmes", "alpha"), unit("Holmes", "beta"), unit("Holmes", "gamma")
    pid = client.post("/api/links/link", json={"a": a, "b": b}).json()["id"]
    pid = client.post("/api/links/link", json={"a": pid, "b": c}).json()["id"]
    assert len(client.get("/api/links/persons").json()["rows"][0]["members"]) == 3
    assert client.post("/api/links/unlink_all", json={"id": pid}).json() == {"ok": True}
    assert client.get("/api/links/persons").json()["rows"] == []
    assert client.post("/api/links/unlink_all", json={"id": "p:404"}).status_code == 404


def test_links_errors(client, unit):
    a = unit("Holmes", "alpha")
    assert client.post("/api/links/link", json={"a": a, "b": a}).json()["detail"] == "Choose two different entities"
    assert client.post("/api/links/link", json={"a": a, "b": "p:404"}).status_code == 404
    assert client.post("/api/links/unlink", json={"id": "p:404", "book": "alpha", "coref": 1}).status_code == 404
    assert client.post("/api/name", json={"id": "p:404", "name": "X"}).status_code == 404
    assert client.post("/api/note", json={"id": "p:404", "note": "X"}).status_code == 404
    assert client.post("/api/links/link", json={"a": a}).json()["detail"] == "“b” is missing."


# ---------- general behaviour ----------
def test_bad_requests_get_messages_not_crashes(client):
    assert client.post("/api/units", json={}).json()["detail"] == "No books selected"
    assert client.post("/api/units", json={"books": "alpha"}).status_code == 400
    assert client.post("/api/units", json={"books": ["nope"]}).json()["detail"] == "None of the selected books were found"
    assert client.post("/api/units", content=b"not json", headers={"content-type": "application/json"}).status_code == 422
    assert client.get("/api/nothing").status_code == 404
    assert client.get("/api/library", params={"x": 1}).status_code == 200


def test_unexpected_errors_are_json_and_logged(lib, caplog, monkeypatch):
    from alex.core import view as view_module
    c = TestClient(app_module.build_app(lib), base_url=LOCAL, raise_server_exceptions=False)
    monkeypatch.setattr(view_module.View, "unit_rows", lambda self, typ=None: 1 / 0)
    with caplog.at_level("ERROR", logger="analyser"):
        r = c.post("/api/units", json={"books": ALL})
    assert r.status_code == 500 and r.json()["detail"].startswith("Something went wrong (ZeroDivisionError") and "/api/units" in caplog.text


def test_selections_are_independent_and_cached(client):
    a = client.post("/api/units", json={"books": ["alpha"]}).json()
    both = client.post("/api/units", json={"books": ["alpha", "beta"]}).json()
    assert len(a["rows"]) < len(both["rows"])
    assert client.post("/api/units", json={"books": ["alpha", "alpha", "nope"]}).json() == a


def test_many_requests_at_once(client):
    errors = []

    def work(books):
        for _ in range(6):
            r = client.post("/api/units", json={"books": books})
            if r.status_code != 200:
                errors.append(r.text)
            r = client.post("/api/corpus/kwic", json={"books": books, "query": "the", "limit": 5})
            if r.status_code != 200:
                errors.append(r.text)

    sets = [["alpha"], ["beta"], ["gamma"], ["alpha", "beta"], ["beta", "gamma"], ALL, ["alpha", "gamma"], ["gamma", "beta", "alpha"]]
    threads = [threading.Thread(target=work, args=(s,)) for s in sets]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []


# ---------- chapters ----------
def test_chapter_routes_change_what_the_text_view_and_arcs_show(client):
    cfg = {"mode": "chapters", "min_words": 50, "rules": {}}
    read = lambda **kw: post(client, "/api/read", book="alpha", seg=cfg, layers=[], **kw)
    r = read(index=0)
    n = len(r["segments"])
    second = next(s for s in r["segments"] if s["pid"] is not None and s["source"] == "auto" and s["pid"] != r["segments"][0]["pid"])
    assert post(client, "/api/narrative/chapters", book="alpha", action="remove", pid=second["pid"]) == {"edited": True}
    r2 = read(index=0)
    assert len(r2["segments"]) == n - 1 and r2["info"]["edited"] and second["label"] not in [s["label"] for s in r2["segments"]]
    new = r2["paragraphs"][3]["pid"]
    post(client, "/api/narrative/chapters", book="alpha", action="add", pid=new)
    post(client, "/api/narrative/chapters", book="alpha", action="rename", pid=new, name="My chapter")
    r3 = read(index=0)
    assert [s["label"] for s in r3["segments"]].count("My chapter") == 1 and next(s for s in r3["segments"] if s["label"] == "My chapter")["source"] == "yours"
    assert len([x for x in post(client, "/api/narrative/segments", books=["alpha"], seg=cfg)["segments"]]) == len(r3["segments"])
    assert post(client, "/api/narrative/chapters", book="alpha", action="reset") == {"edited": False}
    assert len(read(index=0)["segments"]) == n
    quiet = read(tok=r["paragraphs"][0]["tok"], mark=False)
    assert quiet["anchor"] == r["paragraphs"][0]["pid"] and not any(p["hit"] for p in quiet["paragraphs"])
    assert post(client, "/api/read", book="alpha", seg=cfg, layers=["sentences"], index=0)["paragraphs"][0]["text"].count("\x01sn|") >= 1


def test_chapter_route_errors(client):
    assert client.post("/api/narrative/chapters", json={"book": "nope", "action": "reset"}).status_code == 404
    assert client.post("/api/narrative/chapters", json={"book": "alpha", "action": "colour", "pid": 1}).status_code == 400
    assert client.post("/api/narrative/chapters", json={"book": "alpha", "action": "add", "pid": 10 ** 7}).status_code == 400


# ---------- limits, paging and bad input ----------
def test_the_concordance_is_found_once_and_paged(client):
    first = post(client, "/api/corpus/kwic", query="the", limit=10)
    assert first["total"] > 10 and len(first["hits"]) == 10 and first["offset"] == 0 and first["per_book"] and not first["capped"]
    assert len(first["per_book"][0]["bins"]) == 200
    later = post(client, "/api/corpus/kwic", query="the", limit=10, offset=10)
    assert later["offset"] == 10 and "per_book" not in later and "speakers" not in later and later["total"] == first["total"]
    everything = post(client, "/api/corpus/kwic", query="the", limit=100000)["hits"]
    assert everything[:10] == first["hits"] and everything[10:20] == later["hits"]
    wide = post(client, "/api/corpus/kwic", query="the", limit=1, context=20)["hits"][0]
    narrow = post(client, "/api/corpus/kwic", query="the", limit=1, context=2)["hits"][0]
    assert len(wide["left"]) > len(narrow["left"]) and wide["key"] == narrow["key"]       # the context is chosen per page, not per search


def test_a_network_is_limited_to_the_number_of_entities_asked_for(client):
    full = post(client, "/api/network", kind="sentence", types=["PER", "LOC"], min_weight=1)
    assert full["info"]["total_nodes"] == full["info"]["nodes"] == 9
    assert post(client, "/api/network", kind="sentence", types=["PER", "LOC"], min_weight=1, max_nodes=2)["info"]["nodes"] == 9     # 10 is the least that can be asked for
    assert "whole number" in detail(client, "/api/network", {"kind": "sentence", "max_nodes": "many"})
    # (that a larger network is really cut is tested over sixty books in test_scale.py)


def test_unknown_statistics_options_are_refused_with_the_choices(client):
    target = {"kind": "type", "type": "PER"}
    for bad in ({"measure": "magic"}, {"test": "tarot"}):
        message = detail(client, "/api/distinctive", {"target": target, "reference": {"kind": "others"}, **bad})
        assert "Unknown" in message and "ll" in message
    assert post(client, "/api/distinctive", target=target, reference={"kind": "others"}, measure="lr", test="chi2")["summary"]["measure"] == "lr"


def test_corrections_to_a_book_that_does_not_exist_are_refused(client, lib):
    for path, body in (("/api/annot/narrator", {"book": "nope", "narrator": "e:alpha:1"}), ("/api/narrators/reject", {"book": "nope", "key": "k"}),
                       ("/api/annot/chapter_narrator", {"book": "nope", "narrator": "anon"})):
        assert client.post(path, json=body).status_code == 404, path
    assert "nope" not in lib.ann["books"]                                         # and nothing was invented


def test_settings_reject_sources_that_are_not_a_list(client):
    assert "list of folders" in detail(client, "/api/settings", {"sources": "/some/folder"})
    sources = client.get("/api/library").json()["sources"]
    assert post(client, "/api/settings", sources=sources)["sources"] == sources


def test_the_reference_upload_ignores_entries_that_are_not_files(client):
    r = client.post("/api/refs", json={"files": ["just a string", 5, None, {"name": "ok.txt", "text": "the cat and the hat"}]})
    assert r.status_code == 200 and r.json()["tokens"] == 5
    client.post("/api/refs/delete", json={"id": r.json()["id"]})
