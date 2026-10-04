"""A large library: sixty books at once. The analyser must give the right figures and stay quick with that many books, and the tools
that compare everything with everything (networks, link suggestions, lists) must keep their results to a size a person can read."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from fixture import LOCAL

from alex import app as app_module
import fixture
from alex.core import corpus, dialogue, links, network
from alex.core.library import Library
from alex.core.view import View

COUNT = 60


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    """(library over sixty generated books, {book id: Truth}); every book belongs to one series, so link suggestions are possible."""
    root = tmp_path_factory.mktemp("big")
    truth = fixture.build_many(root / "exports", COUNT)
    lib = Library(data_dir=root / "data", sources=[root / "exports"])
    for bid in truth:
        lib.set_meta(bid, {"series": "Sherlock Holmes", "year": 1890 + int(bid[1:])})
    return lib, truth


@pytest.fixture(scope="module")
def view(big):
    return View(big[0], sorted(big[1]))


@pytest.fixture(scope="module")
def client(big):
    return TestClient(app_module.build_app(big[0]), base_url=LOCAL, raise_server_exceptions=False)


def quoted(truth):
    return sum(sum(t.quotes.values()) for t in truth.values())


def test_every_book_is_found_and_read(big, view):
    lib, truth = big
    assert len(lib.found()) == COUNT and len(view.books) == COUNT and view.problems == []
    assert sum(bd.n_words for bd in view.bd.values()) == sum(t.words for t in truth.values())


def test_counts_over_many_books_match_what_was_generated(big, view):
    truth = big[1]
    assert corpus.kwic(view, "said")["total"] == quoted(truth)                       # one "said" per quote
    assert sum(r["quotes"] for r in dialogue.overview(view)["books"]) == quoted(truth)
    assert corpus.kwic(view, "said", scope={"kind": "dialogue"})["total"] == 0        # "said" is always outside the quotes
    assert corpus.kwic(view, "said", scope={"kind": "narration"})["total"] == quoted(truth)
    wl = corpus.wordlist(view)
    assert wl["tokens"] == sum(t.words for t in truth.values()) and wl["books"] == COUNT


def test_a_capped_search_still_reaches_the_later_books(view):
    """With a limit smaller than the hits, the hits are the first ones in reading order, wherever the scope allows them."""
    r = corpus.kwic(view, "the", scope={"kind": "dialogue"}, limit=40)
    assert r["total"] == 40 and r["capped"]
    first_books = {h["book"] for h in r["hits"]}
    assert first_books <= set(view.books[:5])                                         # the first books, not a random few


def test_a_network_is_cut_to_the_strongest_entities(view):
    full = network.build(view, "sentence", ("PER",), max_nodes=10_000)
    assert full.number_of_nodes() > 40 and full.graph["total_nodes"] == full.number_of_nodes()
    small = network.build(view, "sentence", ("PER",), max_nodes=25)
    assert small.number_of_nodes() <= 25 and small.graph["total_nodes"] == full.number_of_nodes()
    strongest = sorted(full.degree(weight="weight"), key=lambda kv: -kv[1])[:5]
    assert all(n in small for n, _ in strongest)
    assert network.as_json(view, small)["info"]["total_nodes"] == full.number_of_nodes()


def test_link_suggestions_over_many_books_are_limited_and_quick(big):
    lib, _ = big
    started = time.time()
    rows, total = links.suggest(lib, limit=50)
    assert total > 50 and len(rows) == 50 and time.time() - started < 30
    assert rows[0]["score"] >= rows[-1]["score"]
    again = time.time()
    links.suggest(lib, limit=50)
    assert time.time() - again < max(1.0, (again - started) / 2)                    # the per-entity summaries are kept between calls


def test_the_routes_that_look_at_everything_answer_for_sixty_books(client, big):
    books = sorted(big[1])
    body = {"books": books}
    units = client.post("/api/units", json=body).json()
    assert len(units["rows"]) > 100
    assert len(client.post("/api/network", json={**body, "kind": "paragraph", "min_weight": 1, "max_nodes": 30}).json()["nodes"]) <= 30
    for path, extra in (("/api/dialogue/overview", {}), ("/api/dialogue/style", {}), ("/api/corpus/wordlist", {}), ("/api/corpus/ngrams", {}),
                        ("/api/corpus/collocates", {"query": "said"}), ("/api/narrative/style", {}), ("/api/narrative/stylometry", {}),
                        ("/api/narrative/arcs", {"kind": "dialogue", "seg": {"mode": "slices", "n": 5}}),
                        ("/api/dialogue/entity", {"id": units["rows"][0]["id"]}), ("/api/profile", {"id": units["rows"][0]["id"]})):
        r = client.post(path, json={**body, **extra})
        assert r.status_code == 200, (path, r.status_code, r.text[:200])


def test_a_pattern_with_many_optional_parts_is_quick_over_many_books(view):
    started = time.time()
    r = corpus.kwic(view, '[]? []? []? []? []? []? []? []? [lemma="see"]', mode="pattern")
    assert r["total"] > 0 and time.time() - started < 20


def test_strings_are_shared_so_a_book_costs_little_memory(big):
    bd = big[0].book("b00")
    assert len({id(w) for w in bd.pos}) == len(set(bd.pos)) and len({id(w) for w in bd.dep}) == len(set(bd.dep))
    assert len({id(w) for w in bd.word}) == len(set(bd.word))
