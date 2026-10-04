"""The text view: paragraphs with well-formed marks, jumping to a token, layers, narrators and topics."""
from __future__ import annotations

import re

from alex.core import dialogue, reader, topics
from alex.core.corpus import cindex
from alex.core.view import View

CHAPTERS = {"mode": "chapters", "min_words": 50, "rules": {}}


def balanced(text):
    """Every \\x01…\\x02 opens a mark and every \\x03 closes one, and never more closes than opens."""
    depth = 0
    for ch in text:
        depth += ch == "\x01"
        depth -= ch == "\x03"
        if depth < 0:
            return False
    return depth == 0


def test_paragraphs_have_balanced_marks_and_the_text_is_not_lost(view):
    r = reader.read(view, "alpha", CHAPTERS, index=0, layers=["entities", "quotes", "events", "supersenses"])
    assert r["paragraphs"] and all(balanced(p["text"]) for p in r["paragraphs"])
    bd = view.bd["alpha"]
    plain = " ".join(re.sub(r"\x01[^\x02]*\x02|\x03", "", p["text"]) for p in r["paragraphs"])
    assert "CHAPTER" in plain and "Holmes" in plain
    first = r["paragraphs"][0]
    assert re.sub(r"\x01[^\x02]*\x02|\x03", "", first["text"]) == bd.span_text(*bd.para_bounds[first["pid"]])


def test_only_the_asked_for_layers_are_marked(view):
    only_entities = reader.read(view, "alpha", CHAPTERS, index=1, layers=["entities"])
    text = "".join(p["text"] for p in only_entities["paragraphs"])
    assert "\x01e " in text and "\x01q|" not in text and "\x01ev|" not in text and only_entities["quotes"] != {} and only_entities["topic_layer"] is None
    default = reader.read(view, "alpha", CHAPTERS, index=1)
    assert "\x01q|" in "".join(p["text"] for p in default["paragraphs"])
    assert "\x01ss|verb.communication\x02said" in "".join(p["text"] for p in reader.read(view, "alpha", CHAPTERS, index=1, layers=["supersenses"])["paragraphs"])


def test_entity_marks_say_whether_the_entity_has_a_profile(lib):
    lib.state["settings"]["min"]["LOC"] = 10 ** 6
    v = View(lib, ["alpha"])
    text = "".join(p["text"] for p in reader.read(v, "alpha", CHAPTERS, index=0, layers=["entities"])["paragraphs"])
    assert "\x01e PER PROP in|" in text and "\x01e LOC PROP|e:alpha:10" in text and "\x01e LOC PROP in|" not in text


def test_quote_details_come_with_the_text(view, truth):
    r = reader.read(view, "alpha", CHAPTERS, index=1, layers=["quotes"])
    q = next(iter(r["quotes"].values()))
    assert set(q) >= {"qi", "speaker", "speaker_id", "addressees", "method", "conv", "first", "verb"} and q["verb"] == "say"
    assert all(re.search(rf"\x01q\|{qi}\x02", "".join(p["text"] for p in r["paragraphs"])) for qi in r["quotes"])


def test_jumping_to_a_token_finds_its_segment_and_marks_it(view):
    bd = view.bd["beta"]
    tok = bd.para_bounds[20][0] + 2
    r = reader.read(view, "beta", CHAPTERS, tok=tok, end=tok + 1, layers=["entities"])
    seg_starts = [i for i in range(bd.n_tokens) if bd.word[i].startswith("CHAPTER")]
    assert r["index"] == max(k for k, s in enumerate(seg_starts) if s <= tok)
    hit = [p for p in r["paragraphs"] if p["hit"]]
    assert len(hit) == 1 and hit[0]["pid"] == 20 and hit[0]["text"].count("\x01hit|\x02") == 1
    assert reader.read(view, "beta", CHAPTERS, index=99)["index"] == 2 and reader.read(view, "beta", CHAPTERS, index=-4)["index"] == 0


def test_narrator_labels(lib):
    v = View(lib, ["alpha"])
    r = reader.read(v, "alpha", CHAPTERS, index=1)
    assert r["default_narrator"] is None and r["default_narrator_name"] == "Narrator of alpha"
    assert {p["narrator"] for p in r["paragraphs"] if p["narrator"]} == {"Narrator of alpha"} and not any(p["exception"] for p in r["paragraphs"])
    watson = v.member_unit[("alpha", 2)]
    lib.ann_book("alpha")["narrator"] = watson
    keys = dialogue.keys(v.bd["alpha"])["p"]
    pid = r["paragraphs"][1]["pid"]
    lib.ann_book("alpha")["para_narrators"][keys[pid]] = "anon"
    lib.save_ann()
    r2 = reader.read(View(lib, ["alpha"]), "alpha", CHAPTERS, index=1)
    assert r2["default_narrator_name"] == "Watson, narrating" and r2["paragraphs"][0]["narrator"] == "Watson, narrating"
    assert r2["paragraphs"][1]["exception"] and r2["paragraphs"][1]["narrator"] == "Narrator of alpha"


def test_a_paragraph_without_narration_has_no_narrator(view):
    bd = view.bd["alpha"]
    ci = cindex(bd)
    r = reader.read(view, "alpha", CHAPTERS, index=1)
    for p in r["paragraphs"]:
        s, e = bd.para_bounds[p["pid"]]
        has_narration = any(ci["isword"][t] and not ci["in_quote"][t] for t in range(s, e + 1))
        assert (p["narrator"] is not None) == has_narration and (p["narrator_id"] is not None) == has_narration


def test_nesting_drops_marks_that_would_cross():
    marks = [(0, 5, "outer"), (2, 3, "inner"), (4, 8, "crossing"), (9, 9, "later"), (2, 3, "same-span")]
    assert reader._nest(list(marks)) == [(0, 5, "outer"), (2, 3, "inner"), (2, 3, "same-span"), (9, 9, "later")]


def test_topic_layer_marks_words_and_reports_documents(lib, tmp_path):
    topics.configure(tmp_path / "topics")
    v = View(lib, ["alpha", "beta", "gamma"])
    model = topics.build(v, topics.clean_cfg({"chunk_words": 60, "k": 4, "min_df": 2, "runs": 1}), "T")
    r = reader.read(v, "alpha", CHAPTERS, index=1, layers=["topics"], topics={"model": model["id"], "focus": "all"})
    tl = r["topic_layer"]
    assert tl["error"] is None and tl["model"]["name"] == "T" and len(tl["topics"]) == 4 and tl["focus"] is None
    assert any("\x01tw|" in p["text"] for p in r["paragraphs"]) and all(balanced(p["text"]) for p in r["paragraphs"])
    infos = [p["topic"] for p in r["paragraphs"] if p["topic"]]
    assert infos and infos[0]["first"] is True and all(str(i["doc"]) in tl["docs"] for i in infos)
    assert sum(i["first"] for i in infos) == len({i["doc"] for i in infos})              # a band starts once per document
    focus = reader.read(v, "alpha", CHAPTERS, index=1, layers=["topics"], topics={"model": model["id"], "focus": 2})
    assert focus["topic_layer"]["focus"] == 2 and all(i["topic"]["dom"] == 2 for i in focus["paragraphs"] if i["topic"])
    other = reader.read(v, "alpha", CHAPTERS, index=1, layers=["topics"], topics={"model": "not-a-model"})
    assert other["topic_layer"]["error"] and other["paragraphs"]
    no_layer = reader.read(v, "alpha", CHAPTERS, index=1, layers=["entities"], topics={"model": model["id"]})
    assert no_layer["topic_layer"] is None and not any("\x01tw|" in p["text"] for p in no_layer["paragraphs"])
    topics.configure(tmp_path / "elsewhere")


def test_a_jump_into_a_paragraph_that_straddles_a_slice_boundary_shows_that_paragraph(view):
    """Slices cut by token count, so a boundary usually falls mid-paragraph. The paragraph is shown in the slice where it starts;
    jumping to a token in its tail must open that slice, not the next one."""
    bd = view.bd["alpha"]
    cfg = {"mode": "slices", "n": 7}
    from alex.core.narrative import segments
    segs, _ = segments(bd, cfg)
    straddling = [(k, pid) for k, sg in enumerate(segs[:-1]) for pid, (ps, pe) in bd.para_bounds.items() if ps <= sg["end"] < pe]
    assert straddling, "the fixture should have slice boundaries inside paragraphs"
    for k, pid in straddling:
        ps, pe = bd.para_bounds[pid]
        tail = segs[k]["end"] + 1                                   # the first token of the paragraph that lies in the next slice
        r = reader.read(view, "alpha", cfg, tok=tail)
        assert r["index"] == k, (k, pid)
        assert any(p["pid"] == pid and p["hit"] for p in r["paragraphs"])
        assert sum(p["text"].count("\x01hit|\x02") for p in r["paragraphs"]) == 1


def test_a_position_outside_the_book_falls_back_to_the_segment_asked_for(view):
    r = reader.read(view, "alpha", CHAPTERS, index=2, tok=10 ** 9)
    assert r["index"] == 2 and not any(p["hit"] for p in r["paragraphs"])


# ---------- numbers, sentences, anchors ----------
def test_paragraph_numbers_run_through_the_book_in_reading_order(view):
    bd = view.bd["alpha"]
    n = len(reader.read(view, "alpha", CHAPTERS, index=0)["segments"])
    numbers = [p["no"] for i in range(n) for p in reader.read(view, "alpha", CHAPTERS, index=i, layers=[])["paragraphs"]]
    assert numbers == list(range(1, bd.n_paras + 1))
    p = reader.read(view, "alpha", CHAPTERS, index=1, layers=[])["paragraphs"][0]
    assert p["tok"] == bd.para_bounds[p["pid"]][0] and "\x01" not in p["text"]                # no layers: plain text, and where the paragraph starts


def test_the_sentences_layer_numbers_every_sentence_once(view):
    bd = view.bd["alpha"]
    r = reader.read(view, "alpha", CHAPTERS, index=1, layers=["sentences", "entities", "quotes"])
    marks = [int(m) for p in r["paragraphs"] for m in re.findall(r"\x01sn\|(\d+)\x02", p["text"])]
    lo, hi = r["paragraphs"][0]["tok"], bd.para_bounds[r["paragraphs"][-1]["pid"]][1]
    inside = [k + 1 for k, sid in enumerate(sorted(bd.sent_bounds)) if lo <= bd.sent_bounds[sid][0] <= hi]
    assert marks == inside and marks and all(balanced(p["text"]) for p in r["paragraphs"])
    assert "\x01sn|" not in "".join(p["text"] for p in reader.read(view, "alpha", CHAPTERS, index=1)["paragraphs"])   # only when asked for


def test_jumping_can_find_a_place_without_marking_it(view):
    bd = view.bd["alpha"]
    tok = bd.para_bounds[sorted(bd.para_bounds)[-3]][0] + 2
    marked = reader.read(view, "alpha", CHAPTERS, tok=tok, layers=[])
    quiet = reader.read(view, "alpha", CHAPTERS, tok=tok, layers=[], mark=False)
    assert marked["anchor"] == quiet["anchor"] == bd.para[tok] and marked["index"] == quiet["index"]
    assert "\x01hit|" in "".join(p["text"] for p in marked["paragraphs"]) and "\x01hit|" not in "".join(p["text"] for p in quiet["paragraphs"])
    assert any(p["hit"] for p in marked["paragraphs"]) and not any(p["hit"] for p in quiet["paragraphs"])
    assert reader.read(view, "alpha", CHAPTERS, index=0)["anchor"] is None


def test_each_segment_says_where_its_heading_is(view):
    r = reader.read(view, "alpha", CHAPTERS, index=0, layers=[])
    bd = view.bd["alpha"]
    heads = [s for s in r["segments"] if s["pid"] is not None]
    assert heads and all(s["source"] == "auto" for s in heads) and r["info"]["mode"] == "chapters" and not r["info"]["edited"]
    assert r["paragraphs"][0]["pid"] in {s["pid"] for s in heads} or r["segments"][0]["label"] == "Opening"
    slices = reader.read(view, "alpha", {"mode": "slices", "n": 4}, index=0, layers=[])
    assert all(s["pid"] is None and s["source"] is None for s in slices["segments"])
