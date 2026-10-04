"""Library: finding books, caching them, and keeping your details, tags and links."""
from __future__ import annotations

import json

import pytest

from alex.core.library import Library, LibraryError


def test_scan_finds_the_three_books_and_their_versions(lib, corpus):
    found, problems = lib.scan()
    assert sorted(found) == ["alpha", "beta", "gamma"] and problems == []
    assert found["alpha"][0]["stamp"] == "20260101-000000" and found["alpha"][0]["exported"]


def test_scan_reports_missing_and_non_folder_sources(lib, tmp_path):
    (tmp_path / "afile").write_text("x")
    lib.state["sources"] = [str(tmp_path / "nowhere"), str(tmp_path / "afile")]
    found, problems = lib.scan()
    assert found == {} and len(problems) == 2


def test_the_newest_export_is_used_unless_one_is_pinned(lib, corpus, tmp_path):
    import shutil
    older = tmp_path / "exports" / "alpha-20250101-000000"
    shutil.copytree(next(corpus[0].glob("alpha-2026*")), older)
    lib.state["sources"] = [str(tmp_path / "exports"), str(corpus[0])]
    found, _ = lib.scan()
    assert [v["stamp"] for v in found["alpha"]] == ["20260101-000000", "20250101-000000"]
    assert lib.folder_for("alpha").name == "alpha-20260101-000000"
    lib.set_meta("alpha", {"pinned": str(older)})
    assert lib.folder_for("alpha") == older
    lib.set_meta("alpha", {"pinned": "/no/such/folder"})
    assert lib.folder_for("alpha").name == "alpha-20260101-000000"     # a pin that no longer exists is ignored


def test_books_are_cached_in_memory_and_on_disk(lib):
    a = lib.book("alpha")
    assert lib.book("alpha") is a
    assert len(list(lib.cache_dir.glob("alpha-*.pkl"))) == 1
    fresh = Library(data_dir=lib.data_dir, sources=lib.state["sources"])
    b = fresh.book("alpha")                                  # from the pickle
    assert b is not a and b.n_tokens == a.n_tokens and len(b.mentions) == len(a.mentions)


def test_a_damaged_cache_file_is_rebuilt(lib):
    lib.book("alpha")
    (pkl,) = lib.cache_dir.glob("alpha-*.pkl")
    pkl.write_bytes(b"not a pickle")
    fresh = Library(data_dir=lib.data_dir, sources=lib.state["sources"])
    assert fresh.book("alpha").n_tokens > 0


def test_changing_a_file_invalidates_the_cache(lib, corpus):
    import os
    before = lib.book("gamma")
    tok = next(corpus[0].glob("gamma-*/gamma.tokens"))
    st = tok.stat()
    os.utime(tok, (st.st_atime, st.st_mtime + 5))
    try:
        assert lib.book("gamma") is not before
    finally:
        os.utime(tok, (st.st_atime, st.st_mtime))


def test_unknown_book_raises_keyerror(lib):
    with pytest.raises(KeyError):
        lib.book("nope")


def test_book_details_persist(lib):
    lib.set_meta("alpha", {"title": "A", "author": "X", "year": 1890, "series": "S", "tags": ["t1"], "bogus": 1})
    again = Library(data_dir=lib.data_dir, sources=lib.state["sources"])
    m = again.meta("alpha")
    assert (m["title"], m["author"], m["year"], m["series"], m["tags"]) == ("A", "X", 1890, "S", ["t1"])
    assert again.meta("beta")["title"] == "beta"          # unset details fall back sensibly


def test_settings_survive_a_partial_settings_file(lib):
    lib.state_path.write_text(json.dumps({"settings": {"min": {"PER": 5}}}), encoding="utf-8")
    again = Library(data_dir=lib.data_dir)
    s = again.state["settings"]
    assert s["min"]["PER"] == 5 and s["min"]["LOC"] == 2 and s["count_mode"] == "per_book" and s["conv_gap"] == 100


def test_a_damaged_library_file_is_a_clear_error_and_is_left_alone(lib):
    lib.state_path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(LibraryError, match="can't be read"):
        Library(data_dir=lib.data_dir)
    assert lib.state_path.read_text() == "{ not json"


def test_saving_leaves_no_temporary_files(lib):
    lib.set_meta("alpha", {"title": "A"})
    lib.save_ann()
    assert not list(lib.data_dir.glob("*.tmp"))


# ---------- tags and links ----------
def test_tags_are_sorted_deduplicated_and_listed(lib):
    lib.set_tags("e:alpha:1", [" b ", "a", "b", ""])
    assert lib.tags_of("e:alpha:1") == ["a", "b"]
    lib.set_tags("e:alpha:2", ["Z"])
    assert lib.all_tags() == ["a", "b", "Z"]
    lib.set_tags("e:alpha:1", [])
    assert lib.tags_of("e:alpha:1") == []
    with pytest.raises(KeyError):
        lib.set_tags("p:99", ["x"])


def test_linking_merges_members_tags_and_name(lib):
    lib.set_tags("e:alpha:1", ["detective"])
    p = lib.link("e:alpha:1", "e:beta:5", name="Sherlock")
    assert p.startswith("p:") and lib.tags_of(p) == ["detective"]
    assert lib.tags_of("e:alpha:1") == []                          # the tags moved to the person
    assert lib.person_of() == {("alpha", 1): p[2:], ("beta", 5): p[2:]}
    p2 = lib.link(p, "e:gamma:3")
    assert p2 == p and len(lib.state["persons"][p[2:]]["members"]) == 3
    assert lib.state["persons"][p[2:]]["name"] == "Sherlock"


def test_linking_two_persons_absorbs_the_second(lib):
    a = lib.link("e:alpha:1", "e:beta:5")
    b = lib.link("e:alpha:2", "e:beta:6")
    c = lib.link(a, b)
    assert c == a and b[2:] not in lib.state["persons"] and len(lib.state["persons"][a[2:]]["members"]) == 4


def test_unlinking_dissolves_a_person_with_one_member_and_keeps_tags(lib):
    lib.set_tags("e:alpha:1", ["x"])
    p = lib.link("e:alpha:1", "e:beta:5")
    lib.unlink(p[2:], "beta", 5)
    assert p[2:] not in lib.state["persons"]
    assert lib.tags_of("e:alpha:1") == ["x"] and lib.tags_of("e:beta:5") == ["x"]


def test_unlink_all_dissolves_a_person_of_several_members(lib):
    p = lib.link("e:alpha:1", "e:beta:5", name="Sherlock")
    p = lib.link(p, "e:gamma:3")
    lib.set_tags(p, ["detective"])
    lib.set_note(p, "The detective")
    lib.unlink_all(p[2:])
    assert p[2:] not in lib.state["persons"]
    for uid in ("e:alpha:1", "e:beta:5", "e:gamma:3"):
        assert lib.tags_of(uid) == ["detective"] and lib.name_of(uid) == "Sherlock" and lib.note_of(uid) == "The detective"
    with pytest.raises(KeyError):
        lib.unlink_all("nope")


def test_rename_person(lib):
    p = lib.link("e:alpha:1", "e:beta:5")
    lib.rename_person(p[2:], "  Holmes ")
    assert lib.state["persons"][p[2:]]["name"] == "Holmes"
    lib.rename_person(p[2:], "  ")
    assert lib.state["persons"][p[2:]]["name"] is None


def test_name_and_note_of_an_entity(lib):
    assert lib.name_of("e:alpha:1") is None and lib.note_of("e:alpha:1") == ""
    lib.set_name("e:alpha:1", "  Sherlock  ")
    lib.set_note("e:alpha:1", "  The detective  ")
    assert lib.name_of("e:alpha:1") == "Sherlock" and lib.note_of("e:alpha:1") == "The detective"
    lib.set_name("e:alpha:1", "  ")
    lib.set_note("e:alpha:1", "  ")
    assert lib.name_of("e:alpha:1") is None and lib.note_of("e:alpha:1") == ""
    with pytest.raises(KeyError):
        lib.set_name("p:99", "x")
    with pytest.raises(KeyError):
        lib.set_note("p:99", "x")


def test_linking_merges_names_and_descriptions_too(lib):
    lib.set_name("e:alpha:1", "Sherlock")
    lib.set_note("e:beta:5", "The detective")
    p = lib.link("e:alpha:1", "e:beta:5")
    assert lib.name_of("e:alpha:1") is None                        # moved to the person, like tags
    assert lib.state["persons"][p[2:]]["name"] == "Sherlock" and lib.state["persons"][p[2:]]["note"] == "The detective"


def test_unlinking_keeps_name_and_description_too(lib):
    p = lib.link("e:alpha:1", "e:beta:5", name="Sherlock")
    lib.set_note(p, "The detective")
    lib.unlink(p[2:], "beta", 5)
    assert lib.name_of("e:alpha:1") == "Sherlock" and lib.note_of("e:alpha:1") == "The detective"
    assert lib.name_of("e:beta:5") == "Sherlock" and lib.note_of("e:beta:5") == "The detective"


def test_rejection_survives_later_links(lib):
    lib.reject("e:alpha:1", "e:beta:5")
    assert lib.is_rejected("e:alpha:1", "e:beta:5") and lib.is_rejected("e:beta:5", "e:alpha:1")
    p = lib.link("e:alpha:1", "e:gamma:3")
    assert lib.is_rejected(p, "e:beta:5")                          # a member of the person was rejected
    lib.reject(p, "e:beta:5")
    assert len(lib.state["rejected"]) == 2                        # no duplicate pairs, but the new member is recorded


def test_links_persist(lib):
    p = lib.link("e:alpha:1", "e:beta:5", name="H")
    again = Library(data_dir=lib.data_dir, sources=lib.state["sources"])
    assert again.person_of()[("alpha", 1)] == p[2:] and again.state["next_person"] == 2


def test_linking_narrator_roles(lib):
    """Narrator roles (nar:<unit id> / nar:anon:<book>) aren't units, so they go through their own link/unlink
    (link_narrators/unlink_narrator/unlink_narrators_all), separate from link/unlink above — same shape, own store."""
    lid = lib.link_narrators("nar:anon:alpha", "nar:anon:beta", name="Chronicle")
    assert lid == "nl:1"
    assert lib.state["narrator_links"]["1"]["members"] == ["nar:anon:alpha", "nar:anon:beta"]
    assert lib.state["narrator_links"]["1"]["name"] == "Chronicle"
    assert lib.narrator_link_of() == {"nar:anon:alpha": lid, "nar:anon:beta": lid}
    # growing an existing link
    lid2 = lib.link_narrators(lid, "nar:anon:gamma")
    assert lid2 == lid and lib.state["narrator_links"]["1"]["members"] == ["nar:anon:alpha", "nar:anon:beta", "nar:anon:gamma"]
    # renaming via the same unified name store entities and persons use
    lib.set_name(lid, "The Editors")
    assert lib.name_of(lid) == "The Editors"
    with pytest.raises(KeyError):
        lib.set_name("nl:404", "x")


def test_unlinking_a_narrator_role_dissolves_a_link_of_two(lib):
    lid = lib.link_narrators("nar:anon:alpha", "nar:anon:beta")
    lib.unlink_narrator(lid[3:], "nar:anon:beta")
    assert lid[3:] not in lib.state["narrator_links"] and lib.narrator_link_of() == {}


def test_unlink_narrators_all_dissolves_a_link_of_several(lib):
    lid = lib.link_narrators("nar:anon:alpha", "nar:anon:beta")
    lib.link_narrators(lid, "nar:anon:gamma")
    lib.unlink_narrators_all(lid[3:])
    assert lid[3:] not in lib.state["narrator_links"] and lib.narrator_link_of() == {}


def test_corrections_persist_and_bump_versions(lib):
    v = lib.version
    lib.ann_book("alpha")["narrator"] = "p:1"
    lib.save_ann()
    assert lib.version == v + 1 and lib.ann_version == 1
    again = Library(data_dir=lib.data_dir)
    assert again.ann["books"]["alpha"]["narrator"] == "p:1"


def test_warming_loads_every_book_and_skips_the_ones_that_cannot_be_read(lib, tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "broken.tokens").write_text("not\ta\tbook\n", encoding="utf-8")
    (tmp_path / "x" / "broken.entities").write_text("COREF\n", encoding="utf-8")
    lib.state["sources"].append(str(tmp_path / "x"))
    lib.reset_scan()
    lib.warm()
    assert {key[0] for key in lib._loaded} == {"alpha", "beta", "gamma"}


def test_a_folder_reached_through_two_sources_is_one_version(corpus, tmp_path):
    """Adding a folder and also its parent (or a link to it) must not list the same export twice."""
    exports = corpus[0]
    one = next(exports.glob("alpha-*"))
    lib = Library(data_dir=tmp_path / "data", sources=[exports, one, exports])
    found, _ = lib.scan()
    assert [len(v) for b, v in found.items() if b == "alpha"] == [1]


def test_a_fresh_library_has_no_source_folders_and_finds_no_books(tmp_path):
    """Nothing is assumed about where books are: a new install starts empty and is told to add a folder."""
    fresh = Library(data_dir=tmp_path / "data")
    assert fresh.state["sources"] == [] and fresh.scan() == ({}, [])


def test_add_sources_adds_full_paths_once_and_remembers_them(corpus, tmp_path):
    lib = Library(data_dir=tmp_path / "data")
    added = lib.add_sources([corpus[0], corpus[0], str(corpus[0]) + "/."])                      # the same folder, spelled three ways
    assert added == [str(corpus[0].resolve())] and sorted(lib.scan()[0]) == ["alpha", "beta", "gamma"]
    assert lib.add_sources([corpus[0]]) == [] and lib.add_sources([]) == []                   # nothing new: nothing changes
    assert Library(data_dir=lib.data_dir).state["sources"] == [str(corpus[0].resolve())]      # it was saved
