"""BookData: parsing a book's BookNLP files and building its indexes."""
from __future__ import annotations

import shutil
from collections import Counter

import pytest

from alex.core.bookdata import BookData


def test_counts_match_the_generator(alpha, truth):
    t = truth["alpha"]
    assert alpha.n_tokens == t.tokens
    assert alpha.n_words == t.words
    assert alpha.n_sents == t.sentences
    assert alpha.n_paras == t.paragraphs
    assert len(alpha.quotes) == sum(t.quotes.values())
    assert alpha.problems == []


def test_mentions_and_forms(alpha, truth):
    t = truth["alpha"]
    for (coref, prop), n in t.mentions.items():
        assert alpha.groups[coref].by_prop[prop] == n
    assert sum(len(g.mentions) for g in alpha.groups.values()) == sum(t.mentions.values())
    holmes = alpha.groups[1]
    assert holmes.type == "PER" and holmes.name == "Holmes"        # the name comes from the .book file
    assert holmes.pronouns == "he/him/his"
    assert holmes.forms["PROP"]["Holmes"] == t.mentions[(1, "PROP")]
    assert alpha.groups[10].type == "LOC" and alpha.groups[10].forms["PROP"]["Baker Street"] == t.mentions[(10, "PROP")]


def test_group_without_book_name_falls_back_to_most_common_form(lib, truth):
    beta = lib.book("beta")
    assert beta.groups[5].name == "Holmes"
    ryder = [g for c, g in beta.groups.items() if c == 7]
    assert ryder == [] or ryder[0].name            # Ryder is only in the .book, never mentioned: no group at all


def test_relations_match_the_generator(alpha, truth):
    t = truth["alpha"]
    for coref in (1, 2):
        got = {k: v for k, v in alpha.groups[coref].rel["agent"].items()}
        assert got == dict(t.agent[coref])
    assert dict(alpha.groups[1].rel["poss"]) == dict(t.poss[1])
    assert dict(alpha.groups[10].rel["prep"]) == dict(t.prep[10])


def test_events_and_supersenses(alpha):
    verbs = [i for i, p in enumerate(alpha.pos) if p == "VERB"]
    assert verbs and all(alpha.event[i] for i in verbs)
    assert not any(alpha.event[i] for i, p in enumerate(alpha.pos) if p != "VERB")
    said = [i for i, l in enumerate(alpha.lemma) if l == "say" and alpha.pos[i] == "VERB"]
    assert all(alpha.ss[i] == "verb.communication" for i in said)


def test_span_text_restores_spacing_and_marks(alpha):
    q = alpha.quotes[0]
    text = alpha.span_text(q["start"], q["end"])
    assert text.startswith('" ') is False and text.startswith('"') and text.endswith('"')
    assert " ," not in text and "  " not in text and not text.startswith('" ')
    marked = alpha.span_text(q["start"], q["end"], [(q["start"] + 1, q["start"] + 1, "m")])
    assert "\x01m\x02" in marked and marked.count("\x03") == 1


def test_fixture_books_have_their_original_text(alpha):
    """The editor now copies the original .txt into every export folder; the fixture mirrors that."""
    assert alpha.has_original is True
    assert alpha.raw_bytes and alpha.word[0] in alpha.raw_bytes.decode("utf-8")


def test_span_text_uses_the_original_text_for_exact_spacing(tmp_path):
    """Without a .txt, span_text can only guess at spacing (a single space, or none). With one, an unusual gap
    (here a double space) between two tokens comes through exactly instead of being collapsed."""
    folder = tmp_path / "raw"
    folder.mkdir()
    header = ("paragraph_ID\tsentence_ID\ttoken_ID_within_document\tword\tlemma\tbyte_onset\tbyte_offset\t"
              "POS_tag\tfine_POS_tag\tdependency_relation\tsyntactic_head_ID\tevent")
    rows = ["0\t0\t0\tSherlock\tSherlock\t0\t8\tPROPN\tNNP\tcompound\t1\tO",
            "0\t0\t1\tHolmes\tHolmes\t10\t16\tPROPN\tNNP\troot\t1\tO"]
    (folder / "book.tokens").write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    (folder / "book.entities").write_text("COREF\tstart_token\tend_token\tprop\tcat\ttext\n", encoding="utf-8")
    (folder / "book.txt").write_text("Sherlock  Holmes.", encoding="utf-8")   # a double space, on purpose
    with_txt = BookData("book", folder)
    assert with_txt.has_original is True
    assert with_txt.span_text(0, 1) == "Sherlock  Holmes"

    (folder / "book.txt").unlink()
    without_txt = BookData("book", folder)
    assert without_txt.has_original is False
    assert without_txt.span_text(0, 1) == "Sherlock Holmes"


def test_span_text_handles_multibyte_characters_in_the_original_text(tmp_path):
    """A real bug: BookNLP's byte_onset/byte_offset are character positions into the original text (Unicode
    codepoints), not true UTF-8 byte offsets. A multi-byte character (£ here: one codepoint, two UTF-8 bytes) must
    not throw off the alignment for every token after it — reading raw bytes instead of the decoded text did."""
    folder = tmp_path / "pound"
    folder.mkdir()
    header = ("paragraph_ID\tsentence_ID\ttoken_ID_within_document\tword\tlemma\tbyte_onset\tbyte_offset\t"
              "POS_tag\tfine_POS_tag\tdependency_relation\tsyntactic_head_ID\tevent")
    # "The £1000 reward": T-h-e-_-£-1-0-0-0-_-r-e-w-a-r-d, by character position (not UTF-8 byte position)
    rows = ["0\t0\t0\tThe\tthe\t0\t3\tDET\tDT\tdet\t3\tO",
            "0\t0\t1\t£\t£\t4\t5\tSYM\t$\tnmod\t3\tO",
            "0\t0\t2\t1000\t1000\t5\t9\tNUM\tCD\tnummod\t3\tO",
            "0\t0\t3\treward\treward\t10\t16\tNOUN\tNN\troot\t3\tO"]
    (folder / "book.tokens").write_text(header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    (folder / "book.entities").write_text("COREF\tstart_token\tend_token\tprop\tcat\ttext\n", encoding="utf-8")
    (folder / "book.txt").write_text("The £1000 reward", encoding="utf-8")
    bd = BookData("book", folder)
    assert bd.has_original is True
    assert bd.span_text(0, 3) == "The £1000 reward"


def test_span_text_strips_control_characters_from_tokens(tmp_path, corpus):
    """Marks use \\x01 \\x02 \\x03; a token containing them must not be able to forge a mark."""
    folder = tmp_path / "evil"
    shutil.copytree(next(corpus[0].glob("gamma-*")), folder)
    tok = folder / "gamma.tokens"
    tok.write_text(tok.read_text().replace("\tCHAPTER\t", "\tCHA\x01x\x02PTER\t", 1), encoding="utf-8")
    bd = BookData("gamma", folder)
    assert "\x01" not in bd.span_text(0, 2)


def test_mentions_in_and_sentence_of(alpha):
    s, e = alpha.sent_bounds[5]
    inside = alpha.mentions_in(s, e)
    assert all(s <= alpha.mentions[i][1] <= e for i in inside)
    assert alpha.sentence_of(s) == (s, e)


def test_cooccurrence_is_by_sentence_and_paragraph(alpha):
    travel = [sid for sid, cs in alpha.sent_members.items() if {1, 2, 10} <= cs]
    assert travel, "Holmes, Watson and Baker Street share the 'travel' sentences"
    assert all(sid in alpha.group_sents[1] for sid in travel)


def test_missing_optional_files_are_fine(tmp_path, corpus):
    folder = tmp_path / "bare"
    folder.mkdir()
    for ext in ("tokens", "entities"):
        shutil.copy(next(corpus[0].glob(f"gamma-*/gamma.{ext}")), folder)
    bd = BookData("gamma", folder)
    assert bd.quotes == [] and bd.ss == {} and bd.groups
    assert bd.has_original is False


def test_missing_token_columns_give_a_clear_error(tmp_path, corpus):
    folder = tmp_path / "broken"
    shutil.copytree(next(corpus[0].glob("gamma-*")), folder)
    (folder / "gamma.tokens").write_text("word\tlemma\nthe\tthe\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        BookData("gamma", folder)


def test_bad_rows_are_skipped_not_fatal(tmp_path, corpus):
    folder = tmp_path / "ragged"
    shutil.copytree(next(corpus[0].glob("gamma-*")), folder)
    ent = folder / "gamma.entities"
    ent.write_text(ent.read_text() + "x\ty\n\nnotanumber\t1\t2\tPROP\tPER\tzzz\n", encoding="utf-8")
    quotes = folder / "gamma.quotes"
    quotes.write_text(quotes.read_text() + "a\tb\n", encoding="utf-8")
    clean = BookData("gamma", next(corpus[0].glob("gamma-*")))
    bd = BookData("gamma", folder)
    assert len(bd.mentions) == len(clean.mentions) and len(bd.quotes) == len(clean.quotes)


def test_a_truncated_quote_row_is_kept_as_an_unattributed_quote(tmp_path, corpus):
    folder = tmp_path / "short"
    shutil.copytree(next(corpus[0].glob("gamma-*")), folder)
    q = folder / "gamma.quotes"
    q.write_text(q.read_text() + "1\t2\n", encoding="utf-8")
    bd = BookData("gamma", folder)
    assert bd.quotes[-1]["char"] is None and bd.quotes[-1]["text"] == ""


def test_blank_token_id_names_the_file_and_line(tmp_path, corpus):
    folder = tmp_path / "blank"
    shutil.copytree(next(corpus[0].glob("gamma-*")), folder)
    lines = (folder / "gamma.tokens").read_text().splitlines()
    cols = lines[3].split("\t")
    cols[3] = ""
    lines[3] = "\t".join(cols)
    (folder / "gamma.tokens").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"gamma\.tokens line 4: token_ID_within_document"):
        BookData("gamma", folder)


def test_mentions_and_quotes_outside_the_book_are_skipped_with_a_note(tmp_path, corpus):
    folder = tmp_path / "outside"
    shutil.copytree(next(corpus[0].glob("gamma-*")), folder)
    (folder / "gamma.entities").write_text((folder / "gamma.entities").read_text() + "3\t5000000\t5000001\tPROP\tPER\tGhost\n", encoding="utf-8")
    (folder / "gamma.quotes").write_text((folder / "gamma.quotes").read_text() + "5000000\t5000002\t1\t1\tHe\t3\t\" x \"\n", encoding="utf-8")
    clean = BookData("gamma", next(corpus[0].glob("gamma-*")))
    bd = BookData("gamma", folder)
    assert len(bd.mentions) == len(clean.mentions) and len(bd.quotes) == len(clean.quotes)
    assert len([p for p in bd.problems if "outside the book" in p]) == 2


def test_head_ids_out_of_range_are_repaired(tmp_path, corpus):
    folder = tmp_path / "heads"
    shutil.copytree(next(corpus[0].glob("gamma-*")), folder)
    lines = (folder / "gamma.tokens").read_text().splitlines()
    cols = lines[5].split("\t")
    cols[11] = "99999999"
    lines[5] = "\t".join(cols)
    (folder / "gamma.tokens").write_text("\n".join(lines) + "\n", encoding="utf-8")
    bd = BookData("gamma", folder)
    assert bd.head[4] == 4      # a head outside the book makes the token its own root


def test_group_types_use_the_most_common_category(alpha):
    assert Counter(g.type for g in alpha.groups.values()) == Counter({"PER": 2, "LOC": 1})


def test_presence_bins_put_each_position_in_its_slice(alpha):
    n = alpha.n_tokens
    bins = alpha.presence_bins([0, 0, n - 1, n // 2])
    assert len(bins) == 100 and sum(bins) == 4 and bins[0] == 2 and bins[99] == 1 and bins[50] == 1
    assert alpha.presence_bins([], 10) == [0] * 10 and alpha.presence_bins(range(n), 50).count(0) == 0
