"""Collections of books: nesting, membership, moving, removing, saving, and the routes."""
from __future__ import annotations

import pytest

from alex.core import bookcollections as bc
from alex.core.library import Library


def test_create_nest_and_list(lib):
    a = bc.create(lib, "Holmes")
    b = bc.create(lib, " Novels ", a)
    bc.update(lib, a, add=["alpha", "beta"])
    bc.update(lib, b, add=["beta", "not-a-book"])                       # unknown books are ignored
    rows = bc.listing(lib)
    assert [r["name"] for r in rows] == ["Holmes", "Novels"]            # parents before children
    holmes, novels = rows
    assert novels["parent"] == a and novels["books"] == ["beta"]
    assert holmes["books"] == ["alpha", "beta"] and set(holmes["deep"]) == {"alpha", "beta"}   # each book once, nested ones included
    assert bc.books_in(lib, a, deep=False) == ["alpha", "beta"] and bc.books_in(lib, b) == ["beta"]


def test_a_book_can_be_in_several_collections(lib):
    a, b = bc.create(lib, "Early"), bc.create(lib, "Favourites")
    bc.update(lib, a, add=["alpha"])
    bc.update(lib, b, add=["alpha"])
    assert all(r["books"] == ["alpha"] for r in bc.listing(lib))
    bc.update(lib, a, remove=["alpha"])
    assert [r["books"] for r in bc.listing(lib)] == [[], ["alpha"]]


def test_names_must_be_given_and_unique_among_siblings(lib):
    a = bc.create(lib, "Holmes")
    for bad in ("", "   ", None):
        with pytest.raises(ValueError):
            bc.create(lib, bad)
    with pytest.raises(ValueError):
        bc.create(lib, "holmes")                                        # same name, different case, same level
    inner = bc.create(lib, "Holmes", a)                                 # the same name one level down is fine
    with pytest.raises(ValueError):
        bc.update(lib, inner, parent=None)                              # moving it up would clash
    with pytest.raises(KeyError):
        bc.create(lib, "x", "404")


def test_rename_and_move_and_no_cycles(lib):
    a, b, c = bc.create(lib, "A"), bc.create(lib, "B"), bc.create(lib, "C")
    bc.update(lib, b, parent=a)
    bc.update(lib, c, parent=b)
    bc.update(lib, c, name="Deep")
    assert {r["id"]: (r["name"], r["parent"]) for r in bc.listing(lib)}[c] == ("Deep", b)
    for target in (a, b, c):
        with pytest.raises(ValueError):
            bc.update(lib, a, parent=target)                            # into itself or a descendant
    bc.update(lib, c, parent=None)
    assert {r["id"]: r["parent"] for r in bc.listing(lib)}[c] is None


def test_deleting_keeps_books_and_moves_children_up(lib):
    a, b = bc.create(lib, "Series"), bc.create(lib, "Sub")
    bc.update(lib, b, parent=a, add=["gamma"])
    bc.update(lib, a, add=["alpha"])
    other = bc.create(lib, "Sub")                                       # a top-level clash for the child that moves up
    bc.delete(lib, a)
    rows = {r["id"]: r for r in bc.listing(lib)}
    assert set(rows) == {b, other} and rows[b]["parent"] is None and rows[b]["books"] == ["gamma"]
    assert rows[b]["name"] == "Sub (2)"                                 # renamed rather than merged
    assert len(lib.found()) == 3


def test_collections_survive_a_restart(lib, tmp_path, corpus):
    a = bc.create(lib, "Holmes")
    bc.update(lib, a, add=["beta"])
    again = Library(data_dir=lib.data_dir, sources=[corpus[0]])
    assert bc.listing(again) == bc.listing(lib) and bc.create(again, "Next") != a


def test_routes(client):
    made = client.post("/api/collections", json={"name": "Holmes"}).json()
    cid = made["id"]
    assert [c["name"] for c in made["collections"]] == ["Holmes"]
    sub = client.post("/api/collections", json={"name": "Novels", "parent": cid}).json()["id"]
    r = client.post(f"/api/collections/{sub}", json={"add": ["alpha", "gamma"], "name": "Long books"}).json()
    by_id = {c["id"]: c for c in r["collections"]}
    assert by_id[sub]["name"] == "Long books" and by_id[sub]["books"] == ["alpha", "gamma"] and set(by_id[cid]["deep"]) == {"alpha", "gamma"}
    assert client.get("/api/library").json()["collections"] == r["collections"]
    assert client.post("/api/collections", json={"name": ""}).status_code == 400
    assert client.post("/api/collections/404", json={"name": "x"}).status_code == 404
    assert client.post("/api/collections", json={"name": "y", "parent": "404"}).status_code == 404
    assert client.post(f"/api/collections/{cid}", json={"parent": sub}).status_code == 400
    left = client.post("/api/collections/delete", json={"id": cid}).json()["collections"]
    assert [c["name"] for c in left] == ["Long books"] and left[0]["parent"] is None
    assert client.post("/api/collections/delete", json={"id": cid}).status_code == 404
