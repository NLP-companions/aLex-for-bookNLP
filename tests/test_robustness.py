"""Damaged and unusual files: they must be read when they can be, and refused with a message that says what is wrong when they can't."""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient
from fixture import LOCAL

from alex import app as app_module
from alex.core.bookdata import BookData, ekey, parse_ekey
from alex.core.library import Library
from alex.core.view import View


@pytest.fixture
def folder(tmp_path, corpus):
    """A copy of gamma's files to damage, as a folder of BookNLP files named 'g'."""
    src = next(corpus[0].glob("gamma-*"))
    out = tmp_path / "g"
    out.mkdir()
    for ext in ("tokens", "entities", "quotes", "supersense", "book", "txt"):
        shutil.copy(src / f"gamma.{ext}", out / f"g.{ext}")
    return out


def facts(bd):
    """What a book amounts to, for comparing two readings of the same book."""
    return (bd.n_tokens, bd.n_words, len(bd.mentions), len(bd.quotes), sorted((c, len(g.mentions)) for c, g in bd.groups.items()), bd.problems)


def test_a_byte_order_mark_and_windows_line_endings_make_no_difference(folder):
    plain = facts(BookData("g", folder))
    for ext in ("tokens", "entities", "quotes", "supersense"):
        raw = (folder / f"g.{ext}").read_bytes().replace(b"\n", b"\r\n")
        (folder / f"g.{ext}").write_bytes(b"\xef\xbb\xbf" + raw)
    (folder / "g.book").write_bytes(b"\xef\xbb\xbf" + (folder / "g.book").read_bytes())
    assert facts(BookData("g", folder)) == plain


def test_a_file_that_is_not_utf8_is_refused_with_a_clear_message(folder):
    (folder / "g.tokens").write_bytes((folder / "g.tokens").read_bytes().replace(b"Holmes", b"Holm\xe9s", 1))
    with pytest.raises(ValueError, match=r"g\.tokens isn't UTF-8 text"):
        BookData("g", folder)


def test_optional_columns_may_be_missing(folder):
    lines = (folder / "g.tokens").read_text().splitlines()
    cols = lines[0].split("\t")
    drop = {cols.index(c) for c in ("fine_POS_tag", "event", "byte_onset", "byte_offset")}
    (folder / "g.tokens").write_text("\n".join("\t".join(v for i, v in enumerate(line.split("\t")) if i not in drop) for line in lines) + "\n")
    bd = BookData("g", folder)
    assert bd.n_tokens == len(lines) - 1 and set(bd.tag) == {""} and not any(bd.event) and bd.onset[0] == -1
    assert bd.span_text(0, 5)                                   # without offsets, spacing is guessed


def test_a_number_that_is_not_a_number_is_reported_with_its_line(folder):
    lines = (folder / "g.tokens").read_text().splitlines()
    cols = lines[0].split("\t")
    bad = lines[7].split("\t")
    bad[cols.index("paragraph_ID")] = "three"
    lines[7] = "\t".join(bad)
    (folder / "g.tokens").write_text("\n".join(lines) + "\n")
    with pytest.raises(ValueError, match=r"g\.tokens line 8: paragraph_ID should be a whole number but is “three”"):
        BookData("g", folder)


def test_a_missing_required_column_is_named(folder):
    text = (folder / "g.tokens").read_text().replace("syntactic_head_ID", "head", 1)
    (folder / "g.tokens").write_text(text)
    with pytest.raises(ValueError, match="missing columns: syntactic_head_ID"):
        BookData("g", folder)


def test_a_damaged_character_file_is_a_note_not_a_failure(folder):
    (folder / "g.book").write_text("{ this is not json", encoding="utf-8")
    bd = BookData("g", folder)
    assert any("g.book" in p for p in bd.problems) and bd.groups and all(g.name for g in bd.groups.values())


def test_mentions_and_quotes_outside_the_book_are_skipped_and_noted(folder):
    with open(folder / "g.entities", "a", encoding="utf-8") as f:
        f.write("77\t999999\t999999\tPROP\tPER\tNobody\n77\t5\t3\tPROP\tPER\tBackwards\nx\t1\t1\tPROP\tPER\tNot a number\n")
    with open(folder / "g.quotes", "a", encoding="utf-8") as f:
        f.write("999990\t999999\t1\t1\tx\t1\tFar away\n")
    bd = BookData("g", folder)
    assert 77 not in bd.groups and not any("Far away" == q["text"] for q in bd.quotes)
    assert any("outside the book" in p for p in bd.problems)
    assert "1 line of g.entities couldn't be read and was skipped." in bd.problems          # the row whose number is not a number


def test_one_unreadable_book_does_not_stop_the_others(tmp_path, corpus):
    root = tmp_path / "exports"
    shutil.copytree(next(corpus[0].glob("gamma-*")), root / "gamma-20260103-000000")
    broken = root / "broken-20260101-000000"
    broken.mkdir()
    (broken / "broken.tokens").write_text("this\tis\tnot\ta\tbook\n", encoding="utf-8")
    (broken / "broken.entities").write_text("COREF\tstart_token\tend_token\tprop\tcat\ttext\n", encoding="utf-8")
    lib = Library(data_dir=tmp_path / "data", sources=[root])
    v = View(lib, ["broken", "gamma"])
    assert v.books == ["gamma"] and len(v.problems) == 1 and v.problems[0].startswith("broken:")
    client = TestClient(app_module.build_app(lib), base_url=LOCAL, raise_server_exceptions=False)
    books = {b["id"]: b for b in client.get("/api/library").json()["books"]}
    assert "error" in books["broken"] and "error" not in books["gamma"]
    units = client.post("/api/units", json={"books": ["broken", "gamma"]}).json()
    assert units["rows"] and units["problems"]
    assert client.get("/api/links/suggestions").status_code == 200
    assert client.post("/api/corpus/wordlist", json={"books": ["broken", "gamma"]}).status_code == 200


def test_unit_ids_round_trip_and_bad_ones_are_refused():
    assert parse_ekey(ekey("alpha", 12)) == ("alpha", 12)
    assert parse_ekey(ekey("odd:name", 3)) == ("odd:name", 3)         # a book id may contain colons
    for bad in ("p:3", "e:alpha", "e:alpha:x", "e::3", "", None, 5, "alpha:1"):
        assert parse_ekey(bad) is None
