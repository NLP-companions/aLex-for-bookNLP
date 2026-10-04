"""Narrative: segments, arcs, style, stylometry, sentiment and emotion."""
from __future__ import annotations

import pytest

from alex.core import narrative as nar
from alex.core.view import View

CHAPTERS = {"alpha": 4, "beta": 3, "gamma": 2}
CHAPTER_CFG = {"mode": "chapters", "min_words": 50, "rules": {"numbered": True, "caps": True, "short": False}}
SLICES = {"mode": "slices", "n": 10}


# ---------- segments ----------
def test_slices_divide_each_book_into_equal_token_counts(view):
    segs, info = nar.all_segments(view, SLICES)
    assert len(segs) == 30 and all(i == {"mode": "slices", "fallback": False} for i in info.values())
    for b in view.books:
        mine = [s for s in segs if s["book"] == b]
        assert mine[0]["start"] == 0 and mine[-1]["end"] == view.bd[b].n_tokens - 1
        assert all(a["end"] + 1 == c["start"] for a, c in zip(mine, mine[1:]))
        assert sum(s["words"] for s in mine) == view.bd[b].n_words
        assert max(s["end"] - s["start"] for s in mine) - min(s["end"] - s["start"] for s in mine) <= 1


def test_corpus_scope_shares_slices_by_each_books_words(view):
    """"Whole corpus" timeline: the slice count is a total shared out by each book's words, not repeated per book."""
    segs, info = nar.all_segments(view, {**SLICES, "scope": "corpus", "n": 12})
    assert all(i == {"mode": "slices", "fallback": False} for i in info.values())
    counts = {b: len([s for s in segs if s["book"] == b]) for b in view.books}
    assert abs(sum(counts.values()) - 12) <= len(view.books)   # rounding each book's share may add or drop a couple
    assert all(n >= 1 for n in counts.values())
    words = {b: view.bd[b].n_words for b in view.books}
    longest = max(words, key=words.get)
    assert counts[longest] == max(counts.values())             # the longest book gets no fewer slices than any other
    for b in view.books:
        mine = [s for s in segs if s["book"] == b]
        assert sum(s["words"] for s in mine) == view.bd[b].n_words    # still covers the whole book


def test_corpus_scope_has_no_effect_on_one_book_or_on_chapters(view, lib):
    one = View(lib, ["alpha"])
    assert len(nar.all_segments(one, {**SLICES, "scope": "corpus"})[0]) == 10        # one book: same as "book" scope
    with_scope, _ = nar.all_segments(view, {**CHAPTER_CFG, "scope": "corpus"})
    without, _ = nar.all_segments(view, CHAPTER_CFG)
    assert [s["start"] for s in with_scope] == [s["start"] for s in without]         # chapters aren't found differently


def test_chapters_start_at_headings(view, truth):
    segs, info = nar.all_segments(view, CHAPTER_CFG)
    for b, n in CHAPTERS.items():
        mine = [s for s in segs if s["book"] == b]
        assert len(mine) == n and info[b]["mode"] == "chapters" and not info[b]["fallback"]
        assert mine[0]["label"].startswith("CHAPTER") and mine[0]["start"] == 0
        assert mine[-1]["end"] == view.bd[b].n_tokens - 1
        assert sum(s["words"] for s in mine) == view.bd[b].n_words


def test_short_chapters_are_ignored_and_books_fall_back_to_slices(view):
    segs, info = nar.all_segments(view, {**CHAPTER_CFG, "min_words": 5000, "n": 5})
    assert all(i["fallback"] for i in info.values()) and len(segs) == 15


def test_heading_rules_can_be_switched_off(view):
    segs, info = nar.all_segments(view, {**CHAPTER_CFG, "rules": {"numbered": False, "caps": False, "short": False}, "n": 4})
    assert all(i["fallback"] for i in info.values())


def test_locate_finds_the_segment_of_a_token(view):
    segs, _ = nar.all_segments(view, SLICES)
    idx = nar._seg_index(segs)
    for k, s in enumerate(segs):
        assert nar._locate(idx, s["book"], s["start"]) == k and nar._locate(idx, s["book"], s["end"]) == k
    assert nar._locate(idx, "alpha", -5) is None


# ---------- arcs ----------
def test_entity_arcs_add_up_to_the_mentions(view, truth):
    h = view.member_unit[("alpha", 1)]
    r = nar.arcs(view, SLICES, "entities", [h, "bogus"])
    (s,) = r["series"]
    assert sum(s["counts"]) == truth["alpha"].mentions[(1, "PROP")] + truth["alpha"].mentions[(1, "PRON")]
    assert s["counts"][10:] == [0] * 20                               # nothing from the other books
    assert all(v == pytest.approx(1000 * c / seg["words"]) for v, c, seg in zip(s["values"], s["counts"], r["segments"]))


def test_event_supersense_and_dialogue_arcs(view, truth):
    ev = nar.arcs(view, SLICES, "events")["series"][0]
    assert sum(ev["counts"]) == sum(sum(view.bd[b].event) for b in view.books)
    ss = nar.arcs(view, SLICES, "supersenses")
    assert ss["series"] and {x["item"] for x in ss["info"]["available"]} >= {"verb.communication", "noun.artifact"}
    said = nar.arcs(view, SLICES, "supersenses", cats=["verb.communication"])["series"][0]
    assert sum(said["counts"]) == sum(sum(t.quotes.values()) for t in truth.values())
    dia = nar.arcs(view, SLICES, "dialogue")["series"][0]
    assert sum(dia["counts"]) == sum(t.dialogue_words for t in truth.values())
    assert all(0 <= v <= 100 for v in dia["values"])


def test_unknown_arc_kind_is_empty(view):
    assert nar.arcs(view, SLICES, "nonsense")["series"] == []


# ---------- style ----------
def test_style_metrics_match_the_generator(view, truth):
    rows = {r["book"]: r for r in nar.style(view, SLICES)["rows"]}
    for b, t in truth.items():
        r = rows[b]
        assert r["words"] == t.words and r["sentences"] == t.sentences
        assert r["sent_len"] == pytest.approx(t.words / t.sentences)
        assert r["dialogue"] == pytest.approx(100 * t.dialogue_words / t.words)
        assert r["questions"] == 0 and r["passive"] == 0
        assert r["mattr_ok"] and 0 < r["mattr"] < 1 and 0 <= r["hapax"] <= 100
        assert sum(r["pos"].values()) <= 100 + 1e-9
        assert r["flesch"] == pytest.approx(206.835 - 1.015 * r["sent_len"] - 84.6 * (r["flesch"] and (206.835 - 1.015 * r["sent_len"] - r["flesch"]) / 84.6))


def test_style_by_segment_has_one_row_per_segment(view):
    r = nar.style(view, CHAPTER_CFG, by="segment")
    assert len(r["rows"]) == 9 and {x["label"][:7] for x in r["rows"]} == {"CHAPTER"}
    assert sum(x["words"] for x in r["rows"]) == sum(view.bd[b].n_words for b in view.books)


@pytest.mark.parametrize("word,n", [("the", 1), ("candle", 2), ("table", 2), ("stone", 1), ("hound", 1), ("agree", 2), ("fly", 1), ("", 1)])
def test_syllable_estimate(word, n):
    assert nar._syllables(word) == n


# ---------- stylometry ----------
def test_stylometry_of_whole_books(view):
    r = nar.stylometry(view, SLICES, "books", mfw=30)
    assert [t["book"] for t in r["texts"]] == ["alpha", "beta", "gamma"]
    D = r["matrix"]
    assert all(D[i][i] == 0 for i in range(3)) and all(D[i][j] == D[j][i] for i in range(3) for j in range(3))
    leaves = []
    walk = lambda t: [walk(c) for c in t["children"]] if "children" in t else leaves.append(t["leaf"])
    walk(r["tree"])
    assert sorted(leaves) == [0, 1, 2] and r["tree"]["size"] == 3
    assert 0 < r["variance"][0] <= 1 and len(r["loadings"]) == 2 and len(r["nearest"]) == 3
    assert all(len(n["nearest"]) == 2 for n in r["nearest"])


@pytest.mark.parametrize("measure", ["cosine", "classic", "euclidean"])
@pytest.mark.parametrize("linkage", ["average", "complete", "ward"])
def test_stylometry_measures_and_linkages_run(view, measure, linkage):
    r = nar.stylometry(view, SLICES, "books", mfw=20, measure=measure, linkage=linkage)
    assert "error" not in r and all(d >= 0 for row in r["matrix"] for d in row)


def test_stylometry_scope_and_pronoun_options(view):
    narr = nar.stylometry(view, SLICES, "books", mfw=40, scope="narration", exclude_pronouns=True)
    assert not ({"he", "i"} & set(narr["words"]))
    dia = nar.stylometry(view, SLICES, "books", mfw=40, scope="dialogue")
    assert "said" not in dia["words"] and set(dia["words"]) & {"see", "look"}


def test_stylometry_needs_three_texts(lib):
    r = nar.stylometry(View(lib, ["alpha", "beta"]), SLICES)
    assert "at least three" in r["error"]
    seg = nar.stylometry(View(lib, ["alpha", "beta"]), CHAPTER_CFG, "segments", mfw=20)
    assert "error" not in seg and len(seg["texts"]) == 7


def test_stylometry_needs_enough_words(view):
    r = nar.stylometry(view, SLICES, "books", mfw=0)
    assert "texts" in r and r["mfw"] == 2                       # too small a request is raised to two words
    r = nar.stylometry(view, SLICES, "books", mfw=20, culling=100)
    assert "texts" in r and r["mfw"] > 0


def test_stylometry_refuses_an_unmanageable_number_of_texts(view, monkeypatch):
    monkeypatch.setattr(nar, "MAX_TEXTS", 2)
    assert "at most 2 texts" in nar.stylometry(view, SLICES, "books")["error"]


def test_cluster_orders_merges_by_distance():
    D = [[0, 1, 5, 6], [1, 0, 5, 6], [5, 5, 0, 2], [6, 6, 2, 0]]
    for linkage in ("average", "complete", "ward"):
        tree = nar._cluster(D, linkage)
        first_pair = sorted(sorted(c["leaf"] for c in t["children"]) for t in _nodes(tree) if all("leaf" in c for c in t["children"]))
        assert first_pair == [[0, 1], [2, 3]]
        assert tree["size"] == 4 and tree["height"] > 0
    avg = nar._cluster(D, "average")
    assert avg["height"] == pytest.approx((5 + 5 + 6 + 6) / 4)
    assert nar._cluster(D, "complete")["height"] == 6


def _nodes(t):
    if "children" in t:
        yield t
        for c in t["children"]:
            yield from _nodes(c)


# ---------- sentiment and emotion ----------
def test_sentiment_scores_every_sentence(view):
    assert nar.vader_available()
    r = nar.sentiment(view, SLICES)
    assert [b["sentences"] for b in r["books"]] == [view.bd[b].n_sents for b in ("alpha", "beta", "gamma")]
    whole = r["series"][0]
    assert sum(whole["counts"]) == sum(view.bd[b].n_sents for b in view.books)
    assert all(-1 <= v <= 1 for v in whole["values"] if v is not None)
    h = view.member_unit[("alpha", 1)]
    around = nar.sentiment(view, SLICES, [h])["series"]
    assert len(around) == 2 and around[1]["name"] == "Around Holmes" and sum(around[1]["counts"]) == len(view.bd["alpha"].group_sents[1])


def test_lexicon_parsing():
    text = "# a comment\nword\temotion\tassociation\nmoor\tnature\t1\nhound\tnature\t1\nhound\tfear\t1\ngoose\tfear\t0\nbird,nature,1\nlonely\tsadness\n"
    lex = nar.parse_lexicon(text)
    assert lex == {"nature": ["bird", "hound", "moor"], "fear": ["hound"], "sadness": ["lonely"]}
    assert nar.parse_lexicon("") == {} and nar.parse_lexicon("just one column\n") == {}


def test_emotion_arcs_count_lexicon_words(view):
    lex = {"cats": {"nature": ["moor", "hill"], "fear": ["hound"]}}
    r = nar.emotion(view, SLICES, lex)
    by = {s["name"]: s for s in r["series"]}
    words = {w: sum(1 for b in view.books for i, x in enumerate(view.bd[b].word) if x.lower() == w) for w in ("moor", "hill", "hound")}
    assert sum(by["nature"]["counts"]) == words["moor"] + words["hill"] and sum(by["fear"]["counts"]) == words["hound"]
    only = nar.emotion(view, SLICES, lex, cats=["fear"])
    assert [s["name"] for s in only["series"]] == ["fear"]
    lem = nar.emotion(view, SLICES, {"cats": {"look": ["look"]}})            # the lemma also counts ("looked")
    assert sum(lem["series"][0]["counts"]) >= sum(1 for b in view.bd for l in view.bd[b].lemma if l == "look")


def test_lexicon_load_missing_file(tmp_path):
    assert nar.load_lexicon(tmp_path / "none.json") is None


# ---------- your chapter edits ----------
def edited(lib, book="alpha", cfg=CHAPTER_CFG):
    """(segments, info, bd) of a book with your edits applied, through a fresh view."""
    v = View(lib, [book])
    segs, info = nar.book_segments(v, book, cfg)
    return segs, info, v.bd[book]


def test_chapters_can_be_removed_started_renamed_and_reset(lib):
    auto, info, bd = edited(lib)
    n = len(auto)
    assert not info["edited"] and n >= 3 and all(s["source"] == "auto" for s in auto if s["label"] != "Opening")
    assert nar.edit_chapters(lib, "alpha", "remove", bd.para[auto[1]["head"]]) is True                         # drop the second chapter's start
    segs, info, _ = edited(lib)
    assert len(segs) == n - 1 and info["edited"] and sum(s["words"] for s in segs) == sum(s["words"] for s in auto)   # its text joins the chapter before
    assert all(a["end"] + 1 == b["start"] for a, b in zip(segs, segs[1:])) and segs[0]["start"] == 0 and segs[-1]["end"] == bd.n_tokens - 1
    # start a chapter at a paragraph in the middle of the book: it is yours, and named by its opening words
    heads = {bd.para[s["head"]] for s in auto if s["head"] is not None}
    mid = next(p for p in sorted(bd.para_bounds)[len(bd.para_bounds) // 2:] if p not in heads)
    nar.edit_chapters(lib, "alpha", "add", mid)
    segs, info, _ = edited(lib)
    yours = [s for s in segs if s["source"] == "yours"]
    assert len(segs) == n and len(yours) == 1 and info["yours"] == 1 and yours[0]["start"] == bd.para_bounds[mid][0]
    assert yours[0]["label"] == bd.span_text(yours[0]["start"], min(bd.para_bounds[mid][1], yours[0]["start"] + 12)).strip()
    nar.edit_chapters(lib, "alpha", "rename", mid, "  The turn  ")
    assert next(s for s in edited(lib)[0] if s["source"] == "yours")["label"] == "The turn"
    nar.edit_chapters(lib, "alpha", "rename", mid, "")
    assert next(s for s in edited(lib)[0] if s["source"] == "yours")["label"] != "The turn"
    # a start you added can be taken away again, a removed one brought back: nothing is left over
    assert nar.edit_chapters(lib, "alpha", "remove", mid) is True
    assert nar.edit_chapters(lib, "alpha", "add", bd.para[auto[1]["head"]]) is False
    assert edited(lib)[0] == auto and lib.ann["books"]["alpha"].get("chapters") is None
    nar.edit_chapters(lib, "alpha", "remove", bd.para[auto[1]["head"]])
    assert nar.edit_chapters(lib, "alpha", "reset") is False and edited(lib)[0] == auto


def test_a_chapter_can_be_renamed_and_a_book_without_headings_can_be_split_by_hand(lib):
    none = {"mode": "chapters", "min_words": 10 ** 6, "rules": {}}
    segs, info, bd = edited(lib, cfg=none)
    assert info["fallback"] and all(s["source"] is None for s in segs)                                       # one heading kept is not enough: slices
    pid = sorted(bd.para_bounds)[len(bd.para_bounds) // 3]
    nar.edit_chapters(lib, "alpha", "add", pid)
    segs, info, _ = edited(lib, cfg=none)
    assert [s["source"] for s in segs] == ["auto", "yours"] and info["mode"] == "chapters" and not info["fallback"]      # the book's first heading plus yours
    nar.edit_chapters(lib, "alpha", "rename", pid, "Part two")
    assert edited(lib, cfg=none)[0][1]["label"] == "Part two"


def test_chapter_edits_reach_arcs_and_are_remembered_by_opening_words(lib):
    v0 = View(lib, ["alpha", "beta"])
    before = nar.arcs(v0, CHAPTER_CFG, "dialogue")
    auto, _, bd = edited(lib)
    nar.edit_chapters(lib, "alpha", "remove", bd.para[auto[1]["head"]])
    v1 = View(lib, ["alpha", "beta"])
    after = nar.arcs(v1, CHAPTER_CFG, "dialogue")
    assert len(after["segments"]) == len(before["segments"]) - 1
    assert lib.ann["books"]["alpha"]["chapters"]["remove"][0].endswith("#1")                                    # a key from the paragraph's words, not a number


def test_bad_chapter_edits_are_errors(lib):
    for action, pid in (("add", 10 ** 6), ("colour", 1)):
        with pytest.raises(ValueError):
            nar.edit_chapters(lib, "alpha", action, pid)
