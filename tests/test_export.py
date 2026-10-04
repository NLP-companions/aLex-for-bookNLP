"""Export: what goes into the zip, how your state is cut down to the selected books, and that the zip's books can be read again."""
from __future__ import annotations

import json
import zipfile

from alex.core import bookcollections, entitygroups, export, plurals
from alex.core.library import EXTS, Library


def make_work(lib):
    """Give the library some of every kind of work the export has to filter, across all three books."""
    lib.set_meta("alpha", {"title": "Alpha", "pinned": str(lib.folder_for("alpha"))})
    lib.set_meta("gamma", {"title": "Gamma"})
    a = lib.link("e:alpha:1", "e:beta:5", name="Sherlock")          # in the selection only
    b = lib.link("e:alpha:2", "e:gamma:3")                          # one selected member, one not
    c = lib.link("e:gamma:4", "e:gamma:5")                          # no selected member
    lib.set_tags("e:alpha:9", ["x"])
    lib.set_tags("e:gamma:9", ["y"])
    lib.set_name("e:gamma:9", "Outsider")
    lib.set_note("e:beta:9", "a note")
    lib.reject("e:alpha:3", "e:beta:3")
    lib.reject("e:alpha:3", "e:gamma:3")                            # a pair with an outsider is left out
    outer = bookcollections.create(lib, "Outer")
    inner = bookcollections.create(lib, "Inner", outer)
    other = bookcollections.create(lib, "Elsewhere")
    bookcollections.update(lib, inner, add=["alpha", "gamma"])
    bookcollections.update(lib, other, add=["gamma"])
    entitygroups.create(lib, "Mixed", ["e:alpha:1", "e:gamma:1"])
    entitygroups.create(lib, "Outsiders", ["e:gamma:1"])
    plurals.set_members(lib, "e:alpha:7", [a, "e:alpha:8"])
    plurals.set_members(lib, "e:gamma:7", ["e:gamma:8"])
    lib.link_narrators("nar:anon:alpha", "nar:anon:gamma")
    lib.link_narrators("nar:anon:gamma", "nar:e:gamma:4")
    lib.ann_book("alpha")["narrator"] = a
    lib.ann_book("gamma")["narrator"] = c
    lib.save_ann()
    return a, b, c


def state_of(lib, *books):
    """The scoped state for some books, after a round through JSON (as it is written to the zip)."""
    return json.loads(json.dumps(export.scoped_state(lib, set(books))))


def test_the_state_keeps_only_what_touches_the_selected_books(lib):
    a, b, c = make_work(lib)
    s = state_of(lib, "alpha", "beta")
    assert set(s["books"]) == {"alpha"} and s["books"]["alpha"]["title"] == "Alpha"        # beta has no details; gamma's are cut
    assert "pinned" not in s["books"]["alpha"] and "sources" not in s
    assert s["settings"] == lib.state["settings"]
    assert set(s["persons"]) == {a[2:], b[2:]}                                              # c has no selected member
    assert s["persons"][a[2:]]["members"] == [["alpha", 1], ["beta", 5]] and s["persons"][a[2:]]["name"] == "Sherlock"
    assert s["persons"][b[2:]]["members"] == [["alpha", 2]]                                 # kept, with one member, so its id stays valid
    assert s["entity_tags"] == {"e:alpha:9": ["x"]} and s["entity_names"] == {} and s["entity_notes"] == {"e:beta:9": "a note"}
    assert s["rejected"] == [["e:alpha:3", "e:beta:3"]]
    assert {k: s[k] for k in ("next_person", "next_collection", "next_group", "next_narrator_link")} == \
        {k: lib.state[k] for k in ("next_person", "next_collection", "next_group", "next_narrator_link")}


def test_collections_groups_plurals_and_narrator_links_are_cut_down(lib):
    a, b, c = make_work(lib)
    s = state_of(lib, "alpha", "beta")
    names = {c["name"]: c for c in s["collections"].values()}
    assert set(names) == {"Outer", "Inner"}                                                 # Outer stays because Inner is in it; Elsewhere has nothing selected
    assert names["Inner"]["books"] == ["alpha"] and names["Outer"]["books"] == []
    assert names["Inner"]["parent"] in s["collections"]
    assert [g["ids"] for g in s["groups"].values()] == [["e:alpha:1"]]                      # the group of outsiders is dropped
    assert s["plurals"] == {"e:alpha:7": [a, "e:alpha:8"]}
    assert [k["members"] for k in s["narrator_links"].values()] == [["nar:anon:alpha"]]    # the member in gamma is cut; the link stays


def test_scoping_does_not_change_the_library(lib):
    make_work(lib)
    before = json.dumps([lib.state, lib.ann], sort_keys=True)
    export.scoped_state(lib, {"alpha"})
    export.scoped_annotations(lib, {"alpha"})
    assert json.dumps([lib.state, lib.ann], sort_keys=True) == before


def test_annotations_keep_only_the_selected_books(lib):
    make_work(lib)
    assert set(export.scoped_annotations(lib, {"alpha", "beta"})["books"]) == {"alpha"}
    assert export.scoped_annotations(lib, {"beta"}) == {"books": {}}


def test_the_zip_holds_the_books_state_and_manifest(lib, tmp_path):
    make_work(lib)
    dest = tmp_path / "out.zip"
    manifest = export.write_zip(lib, ["alpha", "beta"], dest)
    with zipfile.ZipFile(dest) as z:
        names = set(z.namelist())
        wanted = {f"books/{b}/{p.name}" for b in ("alpha", "beta") for p in export.book_files(lib, b)}
        assert {"manifest.json", "state/library.json", "state/annotations.json"} | wanted == names     # nothing of gamma
        assert any(n.endswith(".tokens") for n in wanted) and any(n.endswith("beta.entities") for n in wanted)
        assert json.loads(z.read("manifest.json")) == manifest
        assert json.loads(z.read("state/library.json")) == state_of(lib, "alpha", "beta")
        assert set(json.loads(z.read("state/annotations.json"))["books"]) == {"alpha"}
        for n in wanted:                                                                                 # byte for byte what is on disk
            assert z.read(n) == (lib.folder_for(n.split("/")[1]) / n.split("/")[2]).read_bytes()
    assert manifest["format"] == export.FORMAT and set(manifest["books"]) == {"alpha", "beta"}
    assert manifest["books"]["alpha"] == lib.folder_for("alpha").name


def test_a_pinned_export_is_the_one_exported(lib, tmp_path):
    older = tmp_path / "more" / "alpha-20200101-000000"
    older.mkdir(parents=True)
    for p in export.book_files(lib, "alpha"):
        (older / p.name).write_bytes(p.read_bytes())
    lib.state["sources"].append(str(older.parent))
    lib.reset_scan()
    lib.set_meta("alpha", {"pinned": str(older)})
    manifest = export.write_zip(lib, ["alpha"], tmp_path / "out.zip")
    assert manifest["books"]["alpha"] == older.name
    assert {p.parent for p in export.book_files(lib, "alpha")} == {older}


def test_topic_models_and_references(lib, tmp_path):
    topics, refs = lib.data_dir / "topics", lib.data_dir / "references"
    topics.mkdir(), refs.mkdir()
    (topics / "mine.json").write_text(json.dumps({"books": ["alpha"]}))
    (topics / "both.json").write_text(json.dumps({"books": ["alpha", "beta"]}))
    (topics / "outsider.json").write_text(json.dumps({"books": ["alpha", "gamma"]}))      # one document source is not selected
    (topics / "damaged.json").write_text("{not json")
    (refs / "words.json").write_text(json.dumps({"name": "Words"}))
    dest = tmp_path / "out.zip"
    export.write_zip(lib, ["alpha", "beta"], dest)
    with zipfile.ZipFile(dest) as z:
        names = set(z.namelist())
    assert {n for n in names if n.startswith("topics/")} == {"topics/mine.json", "topics/both.json"}
    assert {n for n in names if n.startswith("references/")} == {"references/words.json"}
    assert {n for n in _names(lib, ["alpha"], tmp_path, "single.zip") if n.startswith("topics/")} == {"topics/mine.json"}


def _names(lib, books, tmp_path, name):
    """The entries of a zip made for `books`."""
    dest = tmp_path / name
    export.write_zip(lib, books, dest)
    with zipfile.ZipFile(dest) as z:
        return z.namelist()


def test_without_topics_or_references_the_zip_is_still_made(lib, tmp_path):
    names = _names(lib, ["alpha"], tmp_path, "plain.zip")
    assert not any(n.startswith(("topics/", "references/")) for n in names)


def test_the_books_in_a_zip_can_be_read_again(lib, tmp_path):
    export.write_zip(lib, ["alpha", "beta"], tmp_path / "out.zip")
    unpacked = tmp_path / "unpacked"
    zipfile.ZipFile(tmp_path / "out.zip").extractall(unpacked)
    again = Library(data_dir=tmp_path / "data2", sources=[unpacked / "books"])
    assert sorted(again.found()) == ["alpha", "beta"]
    assert again.book("alpha").n_tokens == lib.book("alpha").n_tokens
    assert all(any((unpacked / "books" / b).glob(f"*.{e}")) for b in ("alpha", "beta") for e in EXTS[:2])
