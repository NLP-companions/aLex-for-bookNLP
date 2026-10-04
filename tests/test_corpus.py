"""Corpus tools: query parsing, concordance, word lists, n-grams, collocates, keywords, reference files."""
from __future__ import annotations

import re

import pytest

from alex.core import corpus
from alex.core.corpus import QueryError

HOLMES = {"alpha": 1, "beta": 5, "gamma": 3}
WATSON = {"alpha": 2, "beta": 6, "gamma": 4}


def total_quotes(truth, who=None):
    return sum(t.quotes[c] if who is None else t.quotes[who[b]] for b, t in truth.items() for c in ([0] if who else t.quotes))


def quotes_by(truth, who):
    return sum(t.quotes[who[b]] for b, t in truth.items())


# ---------- values and queries ----------
@pytest.mark.parametrize("pattern,text,ok", [
    ("said", "said", True), ("said", "Said", True), ("said", "sad", False),
    ("look*", "looked", True), ("look*", "look", True), ("s?id", "said", True), ("s?id", "sid", False),
    ("said|cried", "cried", True), ("said|cried", "cry", False), ("a.c", "a.c", True), ("a.c", "abc", False),
    ("*", "anything", True),
])
def test_wildcard_matching(pattern, text, ok):
    assert corpus.value_matcher(pattern)(text) is ok


def test_case_sensitivity_and_regex_mode():
    assert corpus.value_matcher("Holmes", case=True)("holmes") is False
    assert corpus.value_matcher("s(ai|ay)d", regex=True)("say") is False
    assert corpus.value_matcher("s(ai|ay)d", regex=True)("said") is True
    with pytest.raises(QueryError, match="regular expression"):
        corpus.value_matcher("(", regex=True)


def test_wildcards_off_makes_the_wildcard_characters_literal():
    assert corpus.value_matcher("?", wildcards=False)("?") is True
    assert corpus.value_matcher("?", wildcards=False)("a") is False
    assert corpus.value_matcher("look*", wildcards=False)("look*") is True
    assert corpus.value_matcher("look*", wildcards=False)("looked") is False
    assert corpus.value_matcher("said|cried", wildcards=False)("said|cried") is True
    assert corpus.value_matcher("said|cried", wildcards=False)("said") is False
    assert corpus.value_matcher("s?id", wildcards=False)("said") is False       # no wildcard: literal "?" doesn't match "a"
    # regex still wins over wildcards being off (wildcards is moot when regex is on)
    assert corpus.value_matcher("s.id", regex=True, wildcards=False)("said") is True


def test_simple_queries_parse_words_and_any_word_marker():
    assert corpus.parse_simple("said # Holmes", {}) == [([("word", "=", "said")], 1, 1), ([], 1, 1), ([("word", "=", "Holmes")], 1, 1)]
    assert corpus.parse_simple("said # Holmes", {"wildcards": False}) == [([("word", "=", "said")], 1, 1), ([("word", "=", "#")], 1, 1), ([("word", "=", "Holmes")], 1, 1)]
    assert corpus.parse_simple("said", {"match": "lemma"})[0][0] == [("lemma", "=", "said")]
    with pytest.raises(QueryError):
        corpus.parse_simple("   ", {})


def test_pattern_queries_parse_conditions_and_quantifiers():
    items = corpus.parse_pattern('[lemma="say" & pos="VERB"] [pos!="PUNCT"]? bare [char=Holmes]{2}')
    assert items[0] == ([("lemma", "=", "say"), ("pos", "=", "VERB")], 1, 1)
    assert items[1] == ([("pos", "!=", "PUNCT")], 0, 1)
    assert items[2] == ([("word", "=", "bare")], 1, 1) and items[3][1:] == (2, 2)
    assert corpus.parse_pattern('[word="a"]{1,3}')[0][1:] == (1, 3) and corpus.parse_pattern('[word="a"]* [word="b"]')[0][1:] == (0, 10)
    assert corpus.parse_pattern('[word="a & b"]')[0][0] == [("word", "=", "a & b")]       # & inside quotes is not "and"
    assert corpus.parse_pattern('[]')[0][0] == []


@pytest.mark.parametrize("q,msg", [
    ('[lemma="say"', "no matching"), ("[lemma=]", "Can't read"), ('[colour="red"]', "Unknown attribute"),
    ("", "Type a pattern"), ('[word="a"]?', "optional"),
])
def test_pattern_errors_are_clear(q, msg):
    with pytest.raises(QueryError, match=msg):
        corpus.parse_pattern(q)


def test_an_impossible_quantifier_is_an_error_not_a_silent_no_match():
    with pytest.raises(QueryError):
        corpus.parse_pattern('[word="a"]{12}')


# ---------- concordance ----------
def test_kwic_counts_match_the_generator(view, truth):
    r = corpus.kwic(view, "said")
    assert r["total"] == sum(sum(t.quotes.values()) for t in truth.values())
    assert [p["hits"] for p in r["per_book"]] == [sum(truth[b].quotes.values()) for b in ("alpha", "beta", "gamma")]
    r2 = corpus.kwic(view, "said Holmes")
    assert r2["total"] == quotes_by(truth, HOLMES)
    assert {s["name"] for s in r2["speakers"]} == {"Narration"}                 # "said Holmes" is in narration, not a quote


def test_kwic_lines_have_context_and_position(view):
    r = corpus.kwic(view, "said Watson", context=4)
    hit = r["hits"][0]
    assert hit["key"].lower() == "said watson" and hit["left"] and hit["right"] is not None
    assert 0 <= hit["pos"] <= 100 and hit["book"] in ("alpha", "beta", "gamma")
    assert "\x01" not in hit["key"]


def test_wildcards_lemmas_and_the_any_word_marker(view, truth):
    assert corpus.kwic(view, "said|whispered")["total"] == corpus.kwic(view, "said")["total"]
    assert corpus.kwic(view, "say", settings={"match": "lemma"})["total"] == corpus.kwic(view, "said")["total"]
    n_said = corpus.kwic(view, "said")["total"]
    assert corpus.kwic(view, "said #")["total"] == n_said          # said <any one word>: the speaker's name (punctuation is ignored by default)
    assert corpus.kwic(view, "said . #", settings={"skip_punct": False})["total"] == 0


def test_wildcards_can_be_turned_off_to_search_punctuation(view):
    # "?" is the "any one letter" wildcard by default: matches every one-letter token (a, I…)
    assert corpus.kwic(view, "?", settings={"skip_punct": False})["total"] > 0
    # with wildcards off it's a literal character, and the fixture never writes one
    assert corpus.kwic(view, "?", settings={"skip_punct": False, "wildcards": False})["total"] == 0
    # a literal "." (not a wildcard character) works the same either way
    dots = corpus.kwic(view, ".", settings={"skip_punct": False})["total"]
    assert dots and corpus.kwic(view, ".", settings={"skip_punct": False, "wildcards": False})["total"] == dots


def test_batch_query_merges_several_lines_into_one_search(view):
    said, watched = corpus.kwic(view, "said")["total"], corpus.kwic(view, "watched")["total"]
    assert said and watched                                      # both must actually occur, or the test proves nothing
    r = corpus.kwic(view, "said\nwatched")
    assert r["total"] == said + watched and r["batch"] is True
    assert {h["matched"] for h in r["hits"]} == {"said", "watched"}
    assert all(h["key"].lower() in ("said", "watched") for h in r["hits"])


def test_batch_query_ignores_blank_lines_and_a_single_line_is_not_a_batch(view):
    assert corpus.kwic(view, "said\n\n")["total"] == corpus.kwic(view, "said")["total"]
    r = corpus.kwic(view, "said")
    assert r["batch"] is False and all(h["matched"] == "said" for h in r["hits"])


def test_batch_query_works_with_whole_patterns_as_alternatives(view, truth):
    r = corpus.kwic(view, '[lemma="say"]\n[lemma="look"]', mode="pattern")
    say = corpus.kwic(view, '[lemma="say"]', mode="pattern")["total"]
    look = corpus.kwic(view, '[lemma="look"]', mode="pattern")["total"]
    assert r["total"] == say + look
    assert {h["matched"] for h in r["hits"]} == {'[lemma="say"]', '[lemma="look"]'}


def test_batch_query_also_merges_collocates(view):
    said, watched = corpus.collocates(view, "said"), corpus.collocates(view, "watched")
    both = corpus.collocates(view, "said\nwatched")
    assert both["hits"] == said["hits"] + watched["hits"]


def test_pattern_search_uses_bookNLP_layers(view, truth):
    r = corpus.kwic(view, '[lemma="say"] [char="Holmes"]', mode="pattern")
    assert r["total"] == quotes_by(truth, HOLMES)
    verbs = corpus.kwic(view, '[pos="VERB" & lemma="see"]', mode="pattern")
    assert verbs["total"] == sum(t.agent[c]["see"] for b, t in truth.items() for c in (HOLMES[b], WATSON[b]))
    assert corpus.kwic(view, '[quote="in"] [lemma="see"]', mode="pattern")["total"] == verbs["total"]
    assert corpus.kwic(view, '[lemma="see" & quote="out"]', mode="pattern")["total"] == 0
    assert corpus.kwic(view, '[ent="LOC"]+', mode="pattern")["total"] == sum(v for t in truth.values() for (c, p), v in t.mentions.items() if c in (10, 20, 9))


def test_speaker_and_scope_filters(view, truth):
    said = corpus.kwic(view, "the", scope={"kind": "narration"})["total"]
    dialogue = corpus.kwic(view, "the", scope={"kind": "dialogue"})["total"]
    everywhere = corpus.kwic(view, "the")["total"]
    assert said + dialogue == everywhere and dialogue > 0
    holmes = view.units[view.member_unit[("alpha", 1)]].id
    r = corpus.kwic(view, "see", scope={"kind": "speech", "speaker": {"kind": "unit", "id": holmes}})
    assert r["total"] == truth["alpha"].agent[1]["see"] and {s["name"] for s in r["speakers"]} == {"Holmes"}


def test_near_filter_keeps_hits_with_a_word_close_by(view, truth):
    voc = sum(v for (sp, other), v in ((k, n) for t in truth.values() for k, n in t.vocatives.items()))
    all_look = corpus.kwic(view, "look")["total"]
    assert all_look == voc
    near = corpus.kwic(view, "look", near={"item": "watson", "left": 3, "right": 0, "within_sentence": True})["total"]
    assert near == sum(t.vocatives[(HOLMES[b], WATSON[b])] for b, t in truth.items())
    # the window may also reach back over a sentence end ("... said Watson. "Holmes, look ..."), so it finds one more
    assert corpus.kwic(view, "look", near={"item": "watson", "left": 3, "right": 0})["total"] == near + 1
    assert corpus.kwic(view, "look", near={"item": "watson", "left": 0, "right": 3})["total"] == 0


def test_kwic_sorting_and_limits(view):
    r = corpus.kwic(view, "the", sort=("R1",), limit=50)
    assert r["capped"] and r["total"] == 50
    rights = [re.sub(r"\W", "", h["right"].split(" ")[0].lower()) for h in r["hits"] if h["right"]]
    assert rights == sorted(rights)
    by_book = corpus.kwic(view, "said", sort=("book",))["hits"]
    assert [h["book"] for h in by_book] == sorted((h["book"] for h in by_book), key=["alpha", "beta", "gamma"].index)


def test_kwic_with_an_unknown_sort_key_or_missing_near_item_is_a_clear_error(view):
    with pytest.raises(QueryError):
        corpus.kwic(view, "said", sort=("X9",))
    with pytest.raises(QueryError):
        corpus.kwic(view, "said", near={"left": 3})


def test_kwic_dispersion_and_plot_bins(view):
    r = corpus.kwic(view, "said")
    for p in r["per_book"]:
        assert 0 <= p["d"] <= 1 and len(p["bins"]) == corpus.PLOT_BINS and sum(p["bins"]) == p["hits"]
    assert corpus.kwic(view, "zzzz")["per_book"][0]["d"] is None


def test_the_hit_limit_counts_only_hits_that_pass_the_scope_and_filters(view):
    """The cap must not be used up by hits that are then thrown away: a common word searched in dialogue only, with a small
    limit, still gives that many hits (the first hits of the text are mostly narration)."""
    everywhere = corpus.kwic(view, "the")["total"]
    in_quotes = corpus.kwic(view, "the", scope={"kind": "dialogue"})
    assert 5 < in_quotes["total"] < everywhere
    capped = corpus.kwic(view, "the", scope={"kind": "dialogue"}, limit=5)
    assert capped["total"] == 5 and capped["capped"]
    iq = {h["book"]: corpus.cindex(view.bd[h["book"]])["in_quote"] for h in capped["hits"]}
    assert all(iq[h["book"]][h["tok"]] for h in capped["hits"])
    near = corpus.kwic(view, "the", near={"item": "see", "left": 2, "right": 0}, limit=3)
    assert near["total"] == 3
    ctx = corpus.kwic(view, "the", ctx={"query": "see", "left": 2, "right": 0}, limit=3)
    assert ctx["total"] == 3


def test_the_context_search_looks_at_every_match_not_only_the_first_ones(view, monkeypatch):
    seen = []
    real = corpus.Matcher.hits

    def spy(self, b, stream, limit=corpus.MAX_HITS, accept=None):
        seen.append((len(stream), limit))
        return real(self, b, stream, limit, accept)
    monkeypatch.setattr(corpus.Matcher, "hits", spy)
    corpus.kwic(view, "said", ctx={"query": "the", "left": 3, "right": 3})
    assert any(limit >= n for n, limit in seen[1:])        # the second search's limit never cuts it short


def test_a_near_word_is_found_whatever_its_capitals(view):
    lower = corpus.kwic(view, "look", near={"item": "watson", "left": 3, "right": 0})["total"]
    assert lower and corpus.kwic(view, "look", near={"item": "Watson", "left": 3, "right": 0})["total"] == lower


def test_search_and_lines_can_be_separated_for_paging(view):
    whole = corpus.kwic(view, "said", context=4)
    search = corpus.kwic_search(view, "said")
    assert search["total"] == whole["total"] and "hits" not in search
    assert corpus.kwic_lines(view, search["found"][3:6], 4) == whole["hits"][3:6]


def test_a_pattern_with_many_repeated_parts_stays_fast(view):
    import time
    started = time.time()
    r = corpus.kwic(view, '[]* []* []* []* []* []* []* [lemma="see"]', mode="pattern")
    assert time.time() - started < 5 and r["total"] > 0
    bd = view.bd
    assert all(bd[h["book"]].lemma[h["end"]] == "see" for h in r["hits"])


def test_context_returns_the_paragraph(view):
    r = corpus.kwic(view, "said Watson")
    h = r["hits"][0]
    c = corpus.context(view, h["book"], h["tok"], h["end"])
    assert "said" in c["text"] and "\x01k\x02" in c["text"]
    with pytest.raises(QueryError):
        corpus.context(view, "alpha", 10 ** 9)


# ---------- lists ----------
def test_wordlist_counts(view, truth):
    r = corpus.wordlist(view)
    said = next(x for x in r["rows"] if x["item"] == "said")
    assert said["n"] == sum(sum(t.quotes.values()) for t in truth.values()) and said["range"] == 3 and 0 <= said["d"] <= 1
    assert r["tokens"] == sum(t.words for t in truth.values())
    lem = corpus.wordlist(view, unit="lemma")
    assert next(x for x in lem["rows"] if x["item"] == "say")["n"] == said["n"]
    pos = corpus.wordlist(view, unit="pos")
    assert {x["item"] for x in pos["rows"]} >= {"NOUN", "VERB", "DET"}
    assert corpus.wordlist(view, min_freq=100)["rows"] and all(x["n"] >= 100 for x in corpus.wordlist(view, min_freq=100)["rows"])
    assert [x["rank"] for x in r["rows"][:3]] == [1, 2, 3]


def test_wordlist_scope_and_range(view):
    narr = corpus.wordlist(view, scope={"kind": "narration"})
    dia = corpus.wordlist(view, scope={"kind": "dialogue"})
    assert narr["tokens"] + dia["tokens"] == corpus.wordlist(view)["tokens"]
    only_beta = {x["item"] for x in corpus.wordlist(view, min_range=3)["rows"]}
    assert "said" in only_beta and "ryder" not in only_beta


def test_ngrams(view, truth):
    r = corpus.ngrams(view, 2, 3)
    said_holmes = next(x for x in r["rows"] if x["item"] == "said holmes")
    assert said_holmes["n"] == quotes_by(truth, HOLMES) and said_holmes["size"] == 2
    tri = [x for x in r["rows"] if x["size"] == 3]
    assert tri and all(x["item"].count(" ") == 2 for x in tri)
    left = corpus.ngrams(view, 2, 2, contains="said", position="left")
    assert all(x["item"].startswith("said ") for x in left["rows"])
    right = corpus.ngrams(view, 2, 2, contains="holmes", position="right")
    assert all(x["item"].endswith(" holmes") for x in right["rows"])
    assert all("said" in x["item"].split() for x in corpus.ngrams(view, 2, 3, contains="said")["rows"])


def test_ngrams_do_not_cross_sentence_or_scope_gaps(view):
    within = {x["item"] for x in corpus.ngrams(view, 2, 2, within_sentence=True)["rows"]}
    across = {x["item"] for x in corpus.ngrams(view, 2, 2, within_sentence=False, min_freq=1)["rows"]}
    assert "holmes the" not in within and len(across) >= len(within)
    dia = {x["item"] for x in corpus.ngrams(view, 2, 2, scope={"kind": "dialogue"}, min_freq=1)["rows"]}
    assert "said holmes" not in dia


def test_collocates(view, truth):
    r = corpus.collocates(view, "said", left=1, right=1, min_freq=1, sort="n")
    by = {x["item"]: x for x in r["rows"]}
    assert r["hits"] == sum(sum(t.quotes.values()) for t in truth.values())
    assert by["holmes"]["right"] == quotes_by(truth, HOLMES) and by["holmes"]["left"] == 0
    assert by["holmes"]["mi"] > by["the"]["mi"] if "the" in by else True
    for m in ("mi", "t", "logdice", "mi3", "ll"):
        assert m in by["holmes"]
    assert 0 <= by["holmes"]["p"] <= 1 and r["rows"][0]["rank"] == 1
    ordered = corpus.collocates(view, "said", min_freq=1, sort="logdice")["rows"]
    assert [x["logdice"] for x in ordered if x["logdice"] is not None] == sorted((x["logdice"] for x in ordered if x["logdice"] is not None), reverse=True)


def test_collocate_windows_respect_the_sentence_and_scope(view):
    inside = corpus.collocates(view, "said", left=8, right=8, min_freq=1, within_sentence=True, sort="n")["window_tokens"]
    loose = corpus.collocates(view, "said", left=8, right=8, min_freq=1, within_sentence=False, sort="n")["window_tokens"]
    assert inside < loose
    quoted = corpus.collocates(view, "see", left=3, right=3, min_freq=1, scope={"kind": "dialogue"})
    assert quoted["hits"] > 0 and "holmes" not in {x["item"] for x in quoted["rows"]}


def test_keywords_dialogue_against_narration(view):
    r = corpus.keywords(view, {"scope": {"kind": "narration"}}, scope={"kind": "dialogue"}, kw={"min_freq": 3, "direction": "target"}, ref_view=view)
    items = [x["item"] for x in r["rows"]]
    assert "see" in items and all(x["ll"] > 0 for x in r["rows"]) and r["rows"][0]["rank"] == 1
    assert r["summary"]["target_tokens"] > 0 and all(x["range"] >= 1 for x in r["rows"])


def test_keywords_against_a_reference_file(view):
    ref = corpus.make_reference("ref", [{"name": "r.txt", "text": "the the the the a a a of of of and and and to to to " * 20}])
    r = corpus.keywords(view, {}, kw={"min_freq": 3}, ref_counts=corpus.Counter(ref["counts"]))
    assert r["rows"] and r["summary"]["reference_tokens"] == ref["tokens"]


# ---------- reference files ----------
def test_tokenize_splits_clitics_and_lowercases():
    assert corpus.tokenize("Don't stop, Holmes's dog isn’t here.") == ["do", "n't", "stop", "holmes", "'s", "dog", "is", "n't", "here"]
    assert corpus.tokenize("") == [] and corpus.tokenize("state-of-the-art") == ["state-of-the-art"]


def test_parse_wordlist_formats():
    antconc = "Rank\tFreq\tWord\n1\t100\tthe\n2\t50\tof\n"
    assert corpus.parse_wordlist("1\t100\tthe\n2\t50\tof\n3\t20\tand\n") == {"the": 100, "of": 50, "and": 20}
    assert corpus.parse_wordlist("word,freq\nthe,100\nof,50\n") == {"the": 100, "of": 50}
    assert corpus.parse_wordlist("the\t100\nof\t50\n") == {"the": 100, "of": 50}
    assert corpus.parse_wordlist("Type\tFrequency\nThe\t1,000\n") == {"the": 1000}
    assert corpus.parse_wordlist("This is plain text with no numbers at all.\nSecond line here.") is None
    assert corpus.parse_wordlist("") is None and corpus.parse_wordlist("# comment only\n") is None
    assert corpus.parse_wordlist("!!!\t5\n---\t3\n") is None and corpus.parse_wordlist("12345 !!!") is None     # entries need a letter
    assert corpus.parse_wordlist(antconc) == {"the": 100, "of": 50}


def test_make_reference_mixes_lists_and_texts():
    ref = corpus.make_reference("mixed", [{"name": "a.tsv", "text": "the\t10\nof\t5\n"}, {"name": "b.txt", "text": "The dog didn't bark."}])
    assert ref["kinds"] == {"word list": 1, "text": 1} and ref["counts"]["the"] == 11 and ref["counts"]["n't"] == 1
    assert ref["tokens"] == sum(ref["counts"].values()) and ref["types"] == len(ref["counts"])


def test_juilland_d():
    assert corpus.juilland({k: 5 for k in range(10)}) == pytest.approx(1.0)
    assert corpus.juilland({0: 50}) == pytest.approx(0.0)
    assert corpus.juilland({}) is None


# ---------- word-type filters ----------
def words(view, book_ok=lambda i, bd: True):
    """(bd, i) of every word token of the view whose test passes, counted straight from the files."""
    return [(bd, i) for b in view.books for bd in [view.bd[b]] for i, w in enumerate(corpus.cindex(bd)["isword"]) if w and book_ok(i, bd)]


def in_entity(bd, i, *cats):
    return any(bd.mentions[mi][4] in cats for mi in corpus.cindex(bd)["cover"].get(i, ()))


def test_the_word_list_can_be_limited_to_word_classes(view):
    everything = corpus.wordlist(view)
    verbs = corpus.wordlist(view, flt={"pos": ["VERB"]})
    want = sum(1 for bd, i in words(view) if bd.pos[i] == "VERB")
    assert verbs["kept"] == sum(x["n"] for x in verbs["rows"]) == want > 0
    assert verbs["tokens"] == everything["tokens"]                                  # rates still refer to all the words of the text
    assert next(x for x in verbs["rows"] if x["item"] == "said")["per1k"] == pytest.approx(1000 * next(x for x in verbs["rows"] if x["item"] == "said")["n"] / everything["tokens"])
    both = corpus.wordlist(view, flt={"pos": ["VERB", "NOUN"]})                    # several values of one kind: either
    assert both["kept"] == want + sum(1 for bd, i in words(view) if bd.pos[i] == "NOUN")
    assert corpus.wordlist(view, flt={"pos": []}) == everything and corpus.wordlist(view, flt=None) == everything     # nothing chosen: nothing removed


def test_word_type_filters_combine_and_reach_fine_tags_and_entities(view):
    tags = corpus.wordlist(view, flt={"tag": ["VBD"]})
    assert tags["kept"] == sum(1 for bd, i in words(view) if bd.tag[i] == "VBD") > 0
    people = corpus.wordlist(view, flt={"ent": ["PER"]})
    assert people["kept"] == sum(1 for bd, i in words(view) if in_entity(bd, i, "PER")) > 0
    assert {"holmes", "watson"} <= {x["item"] for x in people["rows"]}
    inside = corpus.wordlist(view, flt={"ent": ["PER", "LOC"]})["kept"]
    assert inside == sum(1 for bd, i in words(view) if in_entity(bd, i, "PER", "LOC"))
    both = corpus.wordlist(view, flt={"pos": ["PROPN"], "ent": ["PER"]})            # different kinds: all must hold
    assert both["kept"] == sum(1 for bd, i in words(view) if bd.pos[i] == "PROPN" and in_entity(bd, i, "PER"))
    assert both["kept"] <= min(people["kept"], corpus.wordlist(view, flt={"pos": ["PROPN"]})["kept"])


def test_a_filtered_word_list_keeps_range_and_dispersion_of_the_text(view):
    plain = {x["item"]: x for x in corpus.wordlist(view, unit="pos")["rows"]}
    only = {x["item"]: x for x in corpus.wordlist(view, unit="pos", flt={"pos": ["NOUN"]})["rows"]}
    assert set(only) == {"NOUN"} and only["NOUN"] == {**plain["NOUN"], "rank": 1}


def test_word_pos_lemma_lists_have_three_columns(view):
    r = corpus.wordlist(view, unit="word_pos_lemma")
    said = next(x for x in r["rows"] if (x["word"], x["pos"], x["lemma"]) == ("said", "VERB", "say"))
    assert said["item"] == "said_VERB_say" and said["n"] == sum(1 for bd, i in words(view) if (bd.word[i].lower(), bd.pos[i], bd.lemma[i].lower()) == ("said", "VERB", "say"))
    assert sum(x["n"] for x in r["rows"]) == r["tokens"] == r["kept"]
    assert len(r["rows"]) >= len(corpus.wordlist(view, unit="word_pos")["rows"])         # a word of one class can still have several lemmas
    nouns = corpus.wordlist(view, unit="word_pos_lemma", flt={"pos": ["NOUN"]})
    assert {x["pos"] for x in nouns["rows"]} == {"NOUN"}


def test_filter_options_list_what_the_books_contain(view):
    o = corpus.filter_options(view)
    n = sum(1 for _ in words(view))
    assert sum(x["n"] for x in o["pos"]) == sum(x["n"] for x in o["tag"]) == n
    assert {"NOUN", "VERB"} <= {x["value"] for x in o["pos"]} and next(x for x in o["pos"] if x["value"] == "NOUN")["label"] == "noun"
    assert [x["n"] for x in o["pos"]] == sorted((x["n"] for x in o["pos"]), reverse=True)
    per = next(x for x in o["ent"] if x["value"] == "PER")
    assert per["n"] == sum(1 for bd, i in words(view) if in_entity(bd, i, "PER")) and per["label"] == "people"


def test_collocates_can_be_limited_to_word_classes(view):
    plain = corpus.collocates(view, "said", left=3, right=3, min_freq=1, sort="n")
    verbs = corpus.collocates(view, "said", left=3, right=3, min_freq=1, sort="n", flt={"pos": ["PROPN"]})
    assert verbs["rows"] and {x["item"] for x in verbs["rows"]} < {x["item"] for x in plain["rows"]}
    assert verbs["hits"] == plain["hits"] and verbs["window_tokens"] == plain["window_tokens"] and verbs["tokens"] == plain["tokens"]   # windows unchanged
    by = {x["item"]: x for x in plain["rows"]}
    for x in verbs["rows"]:
        assert by[x["item"]]["n"] >= x["n"] and x["n"] > 0
    holmes = next(x for x in verbs["rows"] if x["item"] == "holmes")
    assert holmes["n"] == by["holmes"]["n"] and holmes["mi"] == pytest.approx(by["holmes"]["mi"])      # only ever a proper noun: same figures
    nobody = corpus.collocates(view, "said", left=3, right=3, min_freq=1, flt={"ent": ["VEH"]})
    assert nobody["rows"] == [] and nobody["hits"] == plain["hits"]


# ---------- concordance: sort levels and the context search ----------
def first_word(text):
    return re.sub(r"\W", "", (text.split(" ") or [""])[0].lower())


def test_sort_levels_can_use_lemma_pos_frequency_and_be_reversed(view):
    az = corpus.kwic(view, "the", sort=[{"pos": "R1", "by": "word"}])["hits"]
    za = corpus.kwic(view, "the", sort=[{"pos": "R1", "by": "word", "desc": True}])["hits"]
    words_az = [first_word(h["right"]) for h in az]
    assert words_az == sorted(words_az) and [first_word(h["right"]) for h in za] == sorted(words_az, reverse=True)
    assert [h["tok"] for h in corpus.kwic(view, "the", sort=["R1"])["hits"]] == [h["tok"] for h in az]           # plain text levels still mean word A–Z
    # by frequency: the most frequent word at R1 comes first, then the next, each group together
    fq = corpus.kwic(view, "the", sort=[{"pos": "R1", "by": "freq"}])["hits"]
    seq = [first_word(h["right"]) for h in fq]
    counts = corpus.Counter(seq)
    assert counts[seq[0]] == max(counts.values())
    groups = [w for k, w in enumerate(seq) if k == 0 or w != seq[k - 1]]
    assert len(groups) == len(set(groups)) and [counts[w] for w in groups] == sorted((counts[w] for w in groups), reverse=True)
    # by class: the POS of the word at R1 never goes back
    by_pos = corpus.kwic(view, "the", sort=[{"pos": "R1", "by": "pos"}])["hits"]
    tags = []
    for h in by_pos:
        bd = view.bd[h["book"]]
        j = next(i for i in range(h["end"] + 1, bd.n_tokens) if corpus.cindex(bd)["isword"][i])
        tags.append(bd.pos[j])
    assert tags == sorted(tags) and len(set(tags)) > 1
    lem = corpus.kwic(view, "the", sort=[{"pos": "R1", "by": "lemma"}])["hits"]
    assert len(lem) == len(az)


def test_sort_levels_are_applied_in_order_and_ties_keep_the_text_order(view):
    hits = corpus.kwic(view, "the", sort=[{"pos": "R1", "by": "word"}, {"pos": "L1", "by": "word", "desc": True}])["hits"]
    key = [(first_word(h["right"]), first_word(h["left"].split(" ")[-1]) if h["left"] else "") for h in hits]
    assert [k[0] for k in key] == sorted(k[0] for k in key)                            # the first level decides…
    for a, b in zip(key, key[1:]):
        if a[0] == b[0]:
            assert a[1] >= b[1]                                                        # …the second (reversed) only breaks its ties
    books = ["alpha", "beta", "gamma"]
    by_book = [h["book"] for h in corpus.kwic(view, "said", sort=[{"pos": "book", "desc": True}])["hits"]]
    assert by_book == sorted(by_book, key=books.index, reverse=True)


@pytest.mark.parametrize("sort,msg", [([{"pos": "R1", "by": "colour"}], "Can't sort by “colour”"), ([{"pos": "Z9"}], "Can't sort by “Z9”"), ([5], "Can't sort by")])
def test_bad_sort_levels_are_clear_errors(view, sort, msg):
    with pytest.raises(QueryError, match=msg):
        corpus.kwic(view, "said", sort=sort)


def test_the_context_search_matches_the_near_filter_and_can_exclude(view):
    near = corpus.kwic(view, "look", near={"item": "watson", "left": 3, "right": 0, "within_sentence": True})["total"]
    ctx = {"query": "watson", "mode": "simple", "left": 3, "right": 0, "within_sentence": True}
    assert corpus.kwic(view, "look", ctx=ctx)["total"] == near > 0
    everything = corpus.kwic(view, "look")["total"]
    assert corpus.kwic(view, "look", ctx={**ctx, "exclude": True})["total"] == everything - near
    assert corpus.kwic(view, "look", ctx={**ctx, "left": 0, "right": 3})["total"] == 0                 # Watson is named before the request, not after
    assert corpus.kwic(view, "look", ctx={**ctx, "query": ""})["total"] == everything                  # no query: no filter
    assert corpus.kwic(view, "look", ctx={**ctx, "left": 0, "right": 0})["total"] == 0


def test_the_context_search_uses_the_same_modes_as_the_search(view):
    ctx = {"left": 3, "right": 0, "within_sentence": True}
    base = corpus.kwic(view, "look", ctx={**ctx, "query": "watson"})["total"]
    assert corpus.kwic(view, "look", ctx={**ctx, "query": '[lemma="watson"]', "mode": "pattern"})["total"] == base
    assert corpus.kwic(view, "look", ctx={**ctx, "query": '[pos="PROPN"]', "mode": "pattern"})["total"] >= base          # any proper noun close by
    assert corpus.kwic(view, "look", ctx={**ctx, "query": "wats*"})["total"] == base                                    # wildcards
    assert corpus.kwic(view, "look", ctx={**ctx, "query": '[char="Watson"]', "mode": "pattern"})["total"] == base
    with pytest.raises(QueryError, match="matching"):
        corpus.kwic(view, "look", ctx={**ctx, "query": '[lemma="x"', "mode": "pattern"})


def test_the_context_search_respects_scope_and_a_multi_word_context(view):
    ctx = {"query": "said holmes", "left": 0, "right": 4}
    inside = corpus.kwic(view, "the", ctx=ctx)["total"]
    assert 0 < inside < corpus.kwic(view, "the")["total"]
    assert corpus.kwic(view, "the", scope={"kind": "dialogue"}, ctx=ctx)["total"] == 0                # "said Holmes" is in narration, and windows stop at the scope's edge
    lo = corpus.kwic(view, "the", ctx={**ctx, "right": 1})["total"]
    assert lo <= inside                                                                               # a smaller window can't find more



def test_a_word_list_may_contain_words_that_look_like_numbers_to_python():
    counts = corpus.parse_wordlist("the 10\nnan 5\ninf 3\nsay 7\n")
    assert counts == {"the": 10, "nan": 5, "inf": 3, "say": 7}
    assert corpus.parse_wordlist("infinity 4\nbeing 9\n") == {"infinity": 4, "being": 9}
