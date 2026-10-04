"""Topic modelling: settings, documents, words, fitting, quality, storage, a topic's page, comparisons and uses elsewhere."""
from __future__ import annotations

import json

import numpy as np
import pytest

from alex.core import topics
from alex.core.library import Library
from alex.core.topics import model as tm
from alex.core.topics import page as tp
from alex.core.topics import store
from alex.core.view import View

from fixture import THEMES

BOOKS = ["alpha", "beta", "gamma"]
CFG = {"unit": "chunk", "chunk_words": 60, "k": 4, "min_df": 2, "runs": 3}


@pytest.fixture(scope="module")
def env(tmp_path_factory, corpus):
    """One fitted model of the synthetic books, shared (read-only) by the tests below."""
    root = tmp_path_factory.mktemp("topics")
    lib = Library(data_dir=root / "data", sources=[corpus[0]])
    topics.configure(root / "data" / "topics")
    view = View(lib, BOOKS)
    model = topics.build(view, topics.clean_cfg(CFG), "Themes")
    return lib, view, model


@pytest.fixture(autouse=True)
def _models_folder(request):
    """The models folder is global; point it back at the shared model's folder for tests that use that model."""
    if "env" in request.fixturenames:
        lib, _, _ = request.getfixturevalue("env")
        topics.configure(lib.data_dir / "topics")


@pytest.fixture
def store_in(tmp_path):
    topics.configure(tmp_path / "topics")
    return tmp_path / "topics"


def theme_of(word):
    return next((t for t, v in THEMES.items() if word in v["nouns"]), None)


# ---------- settings ----------
def test_clean_cfg_fills_clamps_and_falls_back():
    c = topics.clean_cfg({})
    assert c["method"] == "nmf" and c["k"] == 8 and c["pos"] == ["NOUN"] and c["seg"]["mode"] == "chapters"
    c = topics.clean_cfg({"k": 500, "runs": 0, "chunk_words": 1, "max_df": 9, "unit": "nonsense", "pos": ["VERB", "XYZ"], "method": "??",
                          "drop": "??", "text": "??", "form": "??", "seed": -5, "bogus": 1})
    assert (c["k"], c["runs"], c["chunk_words"], c["max_df"]) == (60, 1, 50, 1.0)
    assert c["unit"] == "chunk" and c["pos"] == ["VERB"] and c["method"] == "nmf" and c["drop"] == "names" and c["text"] == "all"
    assert c["form"] == "lemma" and c["seed"] == 0 and "bogus" not in c
    assert topics.clean_cfg({"pos": ["XYZ"]})["pos"] == ["NOUN"] and topics.clean_cfg({"pos": "NOUN"})["pos"] == ["NOUN"]
    assert topics.clean_cfg({"alpha": "", "beta": None}) ["alpha"] is None and topics.clean_cfg({"beta": None})["beta"] == 0.01


@pytest.mark.parametrize("key,value", [("k", "many"), ("chunk_words", None), ("max_df", "x"), ("seed", [1]), ("alpha", "abc")])
def test_clean_cfg_reports_non_numbers(key, value):
    with pytest.raises(topics.TopicError, match="number"):
        topics.clean_cfg({key: value})


# ---------- documents ----------
def test_chunks_end_at_sentences_and_cover_each_book(view):
    docs = tm.make_docs(view, topics.clean_cfg({"chunk_words": 100}))
    for b in BOOKS:
        mine = [d for d in docs if d["book"] == b]
        bd = view.bd[b]
        assert mine[0]["start"] == 0 and mine[-1]["end"] == bd.n_tokens - 1
        assert all(a["end"] + 1 == c["start"] for a, c in zip(mine, mine[1:]))
        assert all(d["end"] == bd.sentence_of(d["end"])[1] for d in mine)          # every chunk ends where a sentence ends
        assert sum(d["words"] for d in mine) == bd.n_words
        assert all(d["words"] >= 100 for d in mine[:-1]) and mine[-1]["words"] >= 50  # a short tail is folded into the last chunk
        assert all(0 <= d["pos_pct"] <= 100 for d in mine)


def test_paragraph_groups_segments_and_whole_books(view):
    paras = tm.make_docs(view, topics.clean_cfg({"unit": "paras", "paras": 8}))
    assert {d["book"] for d in paras} == set(BOOKS) and all(d["words"] > 0 for d in paras)
    segs = tm.make_docs(view, topics.clean_cfg({"unit": "segments", "seg": {"mode": "chapters", "min_words": 50, "rules": {}}}))
    assert len(segs) == 9 and all(d["label"].startswith("CHAPTER") for d in segs)
    whole = tm.make_docs(view, topics.clean_cfg({"unit": "book"}))
    assert [d["book"] for d in whole] == BOOKS and [d["words"] for d in whole] == [view.bd[b].n_words for b in BOOKS]


# ---------- words ----------
def words_of(view, **cfg):
    c = topics.clean_cfg({"chunk_words": 200, **cfg})
    return {w for doc in tm.tokenize(view, tm.make_docs(view, c), c) for w in doc}


def test_part_of_speech_lemma_and_form(view):
    assert {"candle", "moor"} <= words_of(view) and "look" not in words_of(view)
    verbs = words_of(view, pos=["VERB"], generic=False)
    assert {"look", "watch", "say"} <= verbs and "candle" not in verbs
    forms = words_of(view, pos=["VERB"], form="word", generic=False)
    assert {"looked", "said"} <= forms and "watch" not in forms          # "watch" only occurs as "watched"


def test_general_words_and_your_own_are_removed(view):
    assert "say" not in words_of(view, pos=["VERB"]) and "say" in words_of(view, pos=["VERB"], generic=False)
    assert "candle" not in words_of(view, extra_stop="candle, lamp") and "lamp" not in words_of(view, extra_stop="candle lamp")
    assert {"wife", "hat", "door"} <= words_of(view) and not ({"wife", "hat", "door"} & words_of(view, min_len=5))    # too short: dropped
    assert "carpet" in words_of(view, min_len=5) and "hat" not in words_of(view, min_len=4)


def test_names_are_removed_using_mentions(view):
    assert {"holmes", "watson"} <= words_of(view, pos=["PROPN"], drop="none")
    assert not ({"holmes", "watson"} & words_of(view, pos=["PROPN"], drop="names"))
    assert "street" in words_of(view, pos=["PROPN"], drop="people") and "street" not in words_of(view, pos=["PROPN"], drop="entities")
    assert not ({"holmes", "watson", "street"} & words_of(view, pos=["PROPN"], drop="entities"))


def test_narration_and_dialogue_scopes(view):
    both = words_of(view, pos=["VERB"], generic=False, form="word")
    narration = words_of(view, pos=["VERB"], generic=False, form="word", text="narration")
    dialogue = words_of(view, pos=["VERB"], generic=False, form="word", text="dialogue")
    assert "see" in dialogue and "see" not in narration and {"looked", "waited"} <= narration and both >= narration | dialogue


def test_the_matrix_refuses_too_little_text(view):
    with pytest.raises(topics.TopicError, match="Only 3 documents"):
        tm.matrix([["a"], ["b"], ["c"]], topics.clean_cfg({}))
    with pytest.raises(topics.TopicError, match="No words are left"):
        tm.matrix([[], [], [], []], topics.clean_cfg({}))
    with pytest.raises(topics.TopicError, match="Only 12 words are left"):
        tm.matrix([[f"w{i}", f"x{i}"] for i in range(6)], topics.clean_cfg({"min_df": 1}))


# ---------- fitting and quality ----------
def test_fit_is_reproducible_and_well_formed(view):
    c = topics.clean_cfg(CFG)
    docs, X, vocab = tm.prepare(view, c)
    assert all(d["kept"] > 0 for d in docs) and X.shape == (len(docs), len(vocab))
    theta, phi = tm.fit(X, c, 1)
    theta2, phi2 = tm.fit(X, c, 1)
    assert np.allclose(theta, theta2) and np.allclose(phi, phi2)
    assert theta.shape == (len(docs), 4) and np.allclose(theta.sum(1), 1) and np.allclose(phi.sum(1), 1) and (theta >= 0).all()
    assert not np.allclose(phi, tm.fit(X, c, 2)[1])                   # another seed gives another (similar) model


def test_nmf_recovers_the_four_themes(env):
    lib, view, model = env
    o = topics.overview(lib, model["id"])
    dominant = []
    for t in o["topics"]:
        themes = [theme_of(w["w"]) for w in t["words"][:6]]
        best = max(set(themes) - {None}, key=themes.count)
        assert themes.count(best) >= 5, (best, [w["w"] for w in t["words"][:6]])          # the top words belong to one theme
        dominant.append(best)
    assert sorted(dominant) == sorted(THEMES)                                            # ...and each theme has its topic
    assert all(t["stability"]["recurs"] == t["stability"]["of"] == 3 for t in o["topics"])


def test_lda_runs_and_respects_its_limits(view):
    c = topics.clean_cfg({**CFG, "method": "lda", "chunk_words": 40})
    docs, X, vocab = tm.prepare(view, c)
    theta, phi = tm.fit(X, c, 1)
    assert np.allclose(theta.sum(1), 1) and np.allclose(phi.sum(1), 1)
    big = tm.fit(X, {**c, "k": 60}, 1)
    assert big[1].shape[0] < 60 and big[1].shape[0] <= X.shape[1] - 1              # k is held below the documents and words
    with pytest.raises(topics.TopicError, match="Too few"):
        tm.fit(X[:2], c, 1)


def test_quality_measures():
    phi = np.array([[0.4, 0.4, 0.1, 0.1, 0, 0], [0, 0, 0.1, 0.1, 0.4, 0.4]])
    B = np.array([[1, 1, 0, 0, 0, 0]] * 5 + [[0, 0, 0, 0, 1, 1]] * 5, float)
    coh = tm.npmi_coherence(B, phi, top=2)
    assert all(c == pytest.approx(1.0) for c in coh)                                # top words always occur together
    B2 = np.array([[1, 0, 0, 0, 0, 0]] * 5 + [[0, 1, 0, 0, 0, 0]] * 5, float)
    assert tm.npmi_coherence(B2, phi, top=2)[0] == pytest.approx(-1.0)              # never together
    assert tm.diversity(phi, top=2) == 1.0 and tm.diversity(np.array([[.5, .5], [.5, .5]]), top=2) == 0.5
    assert list(tm.match(phi, phi[::-1], top=2)) == [1.0, 1.0]              # the same topics in another order still match one to one
    assert list(tm.match(phi, np.array([[.5, .5, 0, 0, 0, 0], [0, 0, 0, 0, .5, .5]]), top=2)) == [1.0, 1.0]
    assert list(tm.match(phi, np.array([[0, 0, .5, .5, 0, 0], [0, 0, 0, 0, .5, .5]]), top=2)) == [0.0, 1.0]
    assert tm.relevance(np.array([[.9, .1]]), np.array([50., 50.]), lam=1)[0, 0] > tm.relevance(np.array([[.9, .1]]), np.array([50., 50.]), lam=1)[0, 1]


def test_stability_of_a_single_run_is_trivial(view):
    c = topics.clean_cfg({**CFG, "runs": 1})
    docs, X, vocab = tm.prepare(view, c)
    _, phi = tm.fit(X, c, 1)
    assert tm.stability(X, c, phi, 1) == [{"recurs": 1, "of": 1, "similarity": None}] * 4


def test_scan_reports_each_number_of_topics(view):
    r = topics.scan(view, topics.clean_cfg({**CFG, "runs": 2}), [2, 4, 6])
    assert [x["k"] for x in r["rows"]] == [2, 4, 6] and r["docs"] > 20
    assert all(-1 <= x["coherence"] <= 1 and 0 < x["diversity"] <= 1 and 0 <= x["stability"] <= 1 for x in r["rows"])
    assert topics.scan(view, topics.clean_cfg({**CFG, "runs": 1}), [3])["rows"][0]["stability"] is None


# ---------- storage ----------
def test_models_are_stored_listed_renamed_and_deleted(view, store_in):
    m = topics.build(view, topics.clean_cfg({**CFG, "runs": 1}), "First one")
    assert (store_in / f"{m['id']}.json").exists() and not list(store_in.glob("*.tmp")) and m["id"].startswith("first-one-")
    (row,) = topics.list_models()
    assert row["name"] == "First one" and row["k"] == 4 and row["titles"] == [view.title(b) for b in BOOKS] and row["stable"] is None
    topics.rename(m["id"], name="  Second name ", topic=2, label="  my label ")
    loaded = topics.load(m["id"])
    assert loaded["name"] == "Second name" and loaded["labels"][2] == "my label" and loaded["labels"][0] == ""
    assert topics.overview(view.lib, m["id"])["name"] == "Second name"
    with pytest.raises(topics.TopicError, match="Unknown topic"):
        topics.rename(m["id"], topic=99, label="x")
    with pytest.raises(topics.TopicError, match="Unknown topic"):
        topics.rename(m["id"], topic="abc", label="x")
    topics.delete(m["id"])
    topics.delete(m["id"])                                                          # deleting twice is fine
    assert topics.list_models() == []


def test_model_ids_cannot_escape_the_folder(store_in):
    for bad in ("../x", "a/b", "A", "", None, 5, "x.json"):
        with pytest.raises(topics.TopicError):
            topics.load(bad)
    with pytest.raises(topics.TopicError, match="no longer exists"):
        topics.load("nothing-here")


def test_a_damaged_model_file_is_reported_and_does_not_hide_the_others(view, store_in):
    good = topics.build(view, topics.clean_cfg({**CFG, "runs": 1}), "good")
    (store_in / "broken-123456.json").write_text("{ nope", encoding="utf-8")
    (store_in / "empty-123456.json").write_text("{}", encoding="utf-8")
    assert [r["id"] for r in topics.list_models()] == [good["id"]]
    with pytest.raises(topics.TopicError, match="can't be read"):
        topics.load("broken-123456")


def test_loading_notices_a_changed_file(view, store_in):
    m = topics.build(view, topics.clean_cfg({**CFG, "runs": 1}), "x")
    assert topics.load(m["id"]) is topics.load(m["id"])                            # cached
    topics.rename(m["id"], name="changed")
    assert topics.load(m["id"])["name"] == "changed"


# ---------- the overview and one topic ----------
def test_overview(env):
    lib, view, model = env
    o = topics.overview(lib, model["id"])
    assert o["docs"] == len(model["docs"]) and o["stale"] == [] and len(o["topics"]) == 4 and o["cfg"]["k"] == 4
    shares = [t["share"] for t in o["topics"]]
    assert shares == sorted(shares, reverse=True) and sum(shares) == pytest.approx(1, abs=1e-3)      # stored values are rounded to 4 digits
    t = o["topics"][0]
    assert len(t["words"]) == min(30, len(model["vocab"])) and t["words"][0]["p"] >= t["words"][1]["p"] and len(t["passages"]) == 3
    assert t["passages"][0]["text"] and set(t["by_book"]) == set(BOOKS) and t["passages"][0]["weight"] >= t["passages"][1]["weight"]


def test_a_changed_book_is_flagged_and_passages_are_withheld(env, tmp_path):
    lib, view, model = env
    store.configure(lib.data_dir / "topics")
    changed = json.loads(json.dumps(model))
    changed["id"] = "changed-abcdef"
    changed["tokens"]["alpha"] += 5
    store.save(changed)
    o = topics.overview(lib, "changed-abcdef")
    assert o["stale"] == [view.title("alpha")] and all(p["text"] == "" for t in o["topics"] for p in t["passages"])
    with pytest.raises(topics.TopicError, match="changed since"):
        tp.Topic("changed-abcdef", 0, view)
    with pytest.raises(topics.TopicError, match="changed since"):
        tp.Topic("changed-abcdef", 0, view, strict=False)
    store.delete("changed-abcdef")


def test_topic_lookup_and_view_checks(env):
    lib, view, model = env
    T = tp.Topic(model["id"], np.int64(2), view)
    assert T.t == 2 and T.k == 4 and abs(T.share_all.sum() - 1) < 1e-3 and len(T.words()) == min(30, len(T.vocab))
    for bad in (4, -1, "1", 1.5, None):
        with pytest.raises(topics.TopicError, match="Unknown topic"):
            tp.Topic(model["id"], bad)
    with pytest.raises(topics.TopicError, match="not found"):
        tp.Topic(model["id"], 0, View(lib, ["alpha"]))                             # strict: every book of the model is needed
    assert tp.Topic(model["id"], 0, View(lib, ["alpha"]), strict=False).by_book.keys() == {"alpha", "beta", "gamma"}
    with pytest.raises(topics.TopicError, match="None of the model"):
        tp.Topic(model["id"], 0, View(lib, []), strict=False)


def test_doc_at_finds_the_document_of_a_token(env):
    lib, view, model = env
    T = tp.Topic(model["id"], 0)
    for i, d in enumerate(T.docs[:20]):
        assert T.doc_at(d["book"], d["start"]) == i and T.doc_at(d["book"], d["end"]) == i
    assert T.doc_at("alpha", -1) is None and T.doc_at("alpha", 10 ** 9) is None and T.doc_at("nowhere", 5) is None


def test_group_helpers():
    w, kept = np.array([1.0, 0.0, 0.5]), np.array([10., 10., 20.])
    assert tp.share_of(w, kept, [0, 1, 2]) == pytest.approx(0.5) and tp.share_of(w, kept, []) == 0.0 and tp.share_of(w, kept, [1]) == 0.0
    assert tp.mann_whitney([1, 2, 3], [4, 5, 6]) is None and tp.mann_whitney([1.0] * 6, [1.0] * 6) == 1.0
    assert tp.mann_whitney(list(range(10)), list(range(10, 20))) < 0.01


# ---------- the parts of a topic's page ----------
def moor_topic(env):
    lib, view, model = env
    o = topics.overview(lib, model["id"])
    return next(t["id"] for t in o["topics"] if "moor" in [w["w"] for w in t["words"][:6]])


def test_part_words(env):
    lib, view, model = env
    t = moor_topic(env)
    r = topics.part_words(model["id"], t)
    assert r["form"] == "lemma" and 20 < len(r["words"]) <= 300 and r["words"][0]["p"] >= r["words"][-1]["p"]
    w = next(x for x in r["words"] if x["w"] == "moor")
    assert 0.5 < w["excl"] <= 1 and w["n"] > 5 and 0 < w["pw"] < w["p"]


def test_part_where(env):
    lib, view, model = env
    t = moor_topic(env)
    r = topics.part_where(view, model["id"], t, {"mode": "slices", "n": 5})
    assert [s["book"] for s in r["strips"]] == BOOKS and r["max"] == max(d["w"] for s in r["strips"] for d in s["docs"])
    books = {b["group"]: b for b in r["books"]}
    assert books[view.title("alpha")]["ratio"] > 1 > books[view.title("beta")]["ratio"]      # the moor theme is mostly in alpha
    assert books[view.title("alpha")]["p"] < 0.05
    assert len(r["arc"]["values"]) == 15 and sum(r["arc"]["counts"]) == len(model["docs"])
    assert all(v is None or 0 <= v <= 100 for v in r["arc"]["values"])


def test_part_groups(env):
    lib, view, model = env
    lib.set_meta("alpha", {"series": "S1", "author": "A", "year": 1890, "tags": ["x", "y"]})
    lib.set_meta("beta", {"series": "S1", "author": "B", "year": 1900, "tags": ["y"]})
    r = topics.part_groups(view, lib, model["id"], 0)
    series = {g["group"]: g for g in r["fields"]["series"]}
    assert set(series) == {"S1", "(none)"} and series["S1"]["docs"] > 0 and set(series["S1"]["books"]) == {view.title("alpha"), view.title("beta")}
    assert {g["group"] for g in r["fields"]["tag"]} == {"x", "y", "(no tag)"} and {g["group"] for g in r["fields"]["year"]} == {"1890", "1900", "(none)"}
    assert sum(g["docs"] for g in r["fields"]["tag"]) > sum(g["docs"] for g in r["fields"]["author"])   # alpha counts under both tags


def test_part_passages(env):
    lib, view, model = env
    t = moor_topic(env)
    r = topics.part_passages(view, model["id"], t, n=4)
    assert len(r["passages"]) == 4 and r["passages"][0]["weight"] >= r["passages"][3]["weight"] and len(r["words"]) == min(30, len(model["vocab"]))
    p = r["passages"][0]
    assert p["marked"] == p["text"].count("\x01tw\x02") > 0
    assert topics.part_passages(view, model["id"], t, n=50, book="gamma")["passages"][0]["book"] == "gamma"
    assert len(topics.part_passages(view, model["id"], t, n=0)["passages"]) == 1


def test_part_entities_and_speech(env):
    lib, view, model = env
    t = moor_topic(env)
    e = topics.part_entities(view, model["id"], t, min_mentions=5)
    assert e["rows"] and e["rows"] == sorted(e["rows"], key=lambda r: -r["ll"]) and all(r["count"] >= 5 for r in e["rows"])
    street = next(r for r in e["rows"] if r["name"] == "Baker Street" and r["id"] == view.member_unit[("alpha", 10)])
    assert street["type"] == "LOC" and 0 <= street["share"] <= 1
    s = topics.part_speech(view, model["id"], t, min_words=10)
    assert 0 <= s["dialogue"]["strong"] <= 1 and 0 <= s["dialogue"]["base"] <= 1 and s["speakers"] and s["narrators"]
    assert any(r["name"].startswith("Holmes") for r in s["speakers"]) and all(r["count"] >= 10 for r in s["speakers"])
    assert s["dialogue"]["vocab_dialogue"] + s["dialogue"]["vocab_narration"] > 0


def test_names_are_told_apart_only_when_they_collide(env):
    lib, view, model = env
    s = topics.part_speech(view, model["id"], 0, min_words=10)
    holmes = [r["name"] for r in s["speakers"] if r["name"].startswith("Holmes")]
    assert len(holmes) == 3 and len(set(holmes)) == 3 and all("(" in n for n in holmes)          # three unlinked Holmes: books shown
    lib.link(lib.link("e:alpha:1", "e:beta:5"), "e:gamma:3")
    linked = topics.part_speech(View(lib, BOOKS), model["id"], 0, min_words=10)
    assert [r["name"] for r in linked["speakers"] if r["name"].startswith("Holmes")] == ["Holmes"]


# ---------- comparing topics ----------
def test_compare_map(env):
    lib, view, model = env
    m = topics.compare_map(model["id"])
    assert len(m["topics"]) == 4 and len(m["pairs"]) == 6
    for basis in ("words", "docs"):
        S = np.array(m["bases"][basis]["sim"])
        assert np.allclose(S, S.T) and np.allclose(np.diag(S), 1) and len(m["bases"][basis]["coords"]) == 4
        assert 0 <= sum(m["bases"][basis]["variance"]) <= 1 + 1e-9 and m["bases"][basis]["tree"]["size"] == 4
    assert all(abs(p["words"]) <= 1 and abs(p["docs"]) <= 1 for p in m["pairs"])
    assert max(p["words"] for p in m["pairs"]) < 0.2                          # the themes share no words


def test_compare_pair(env):
    lib, view, model = env
    o = topics.overview(lib, model["id"])
    moor = moor_topic(env)
    goose = next(t["id"] for t in o["topics"] if "goose" in [w["w"] for w in t["words"][:6]])
    r = topics.compare_pair(view, model["id"], moor, goose, {"mode": "slices", "n": 4})
    assert "moor" in [w["w"] for w in r["words"]["a"][:6]] and "goose" in [w["w"] for w in r["words"]["b"][:6]]
    assert all(w["pa"] > w["pb"] for w in r["words"]["a"]) and all(w["pb"] > w["pa"] for w in r["words"]["b"])
    assert r["similarity"]["words"] < 0.1 and len(r["arc_a"]["values"]) == 12 and len(r["books"]) == 3
    assert r["entities"] == sorted(r["entities"], key=lambda x: -x["ll"]) and 0 <= r["dialogue"]["a"] <= 1
    swapped = topics.compare_pair(view, model["id"], goose, moor, {"mode": "slices", "n": 4})
    top = {x["id"]: x["ll"] for x in r["entities"]}
    assert all(top[x["id"]] == pytest.approx(-x["ll"]) for x in swapped["entities"])       # swapping flips the sign
    with pytest.raises(topics.TopicError, match="different"):
        topics.compare_pair(view, model["id"], moor, moor, None)


def test_grids(env):
    lib, view, model = env
    g = topics.grid_groups(lib, model["id"], "book")
    assert [c["label"] for c in g["columns"]] == sorted(view.title(b) for b in BOOKS)
    for c in g["columns"]:
        assert sum(c["shares"]) == pytest.approx(1, abs=1e-3)                 # a document's topic shares add up to 1
    assert sum(g["overall"]) == pytest.approx(1, abs=1e-3) and topics.grid_groups(lib, model["id"], "tag")["columns"][0]["label"] == "(no tag)"
    with pytest.raises(topics.TopicError, match="Group by"):
        topics.grid_groups(lib, model["id"], "colour")
    items = topics.grid_items(view, model["id"], "mentions", ["PER"], min_count=20, limit=5)
    assert 0 < len(items["rows"]) <= 5 and all(sum(r["shares"]) == pytest.approx(1, abs=1e-3) for r in items["rows"])
    assert all(r["type"] == "PER" for r in items["rows"]) and items["rows"] == sorted(items["rows"], key=lambda r: -r["count"])
    sp = topics.grid_items(view, model["id"], "speakers", None, min_count=50)
    assert sp["rows"] and all(sum(r["shares"]) == pytest.approx(1, abs=1e-3) for r in sp["rows"])
    assert topics.grid_items(view, model["id"], "mentions", ["VEH"], min_count=1)["rows"] == []


# ---------- uses elsewhere ----------
def test_arc_series_for_a_selection_of_the_books(env):
    lib, view, model = env
    r = topics.arc_series(view, model["id"], [], {"mode": "slices", "n": 5})
    assert len(r["series"]) == 4 and len(r["segments"]) == 15 and r["info"]["model"]["name"] == "Themes"
    one = topics.arc_series(View(lib, ["alpha"]), model["id"], [moor_topic(env), 99], {"mode": "slices", "n": 5})
    assert [s["id"] for s in one["series"]] == [moor_topic(env)] and len(one["segments"]) == 5
    assert one["info"]["model"]["books"] == [view.title("alpha")] and len(one["info"]["topics"]) == 4
    with pytest.raises(topics.TopicError, match="None of the model"):
        topics.arc_series(View(lib, []), model["id"], [], None)


def test_entity_topics(env):
    lib, view, model = env
    holmes = view.member_unit[("alpha", 1)]
    for kind in ("mentions", "speech"):
        r = topics.entity_topics(view, model["id"], holmes, kind)
        assert r["count"] > 0 and len(r["rows"]) == 4 and sum(x["share"] for x in r["rows"]) == pytest.approx(1, abs=1e-3)
        assert all(x["lift"] == pytest.approx(x["share"] / x["topic_share"]) for x in r["rows"]) and r["rows"] == sorted(r["rows"], key=lambda x: -x["ll"])
    assert topics.entity_topics(view, model["id"], view.member_unit[("beta", 6)], "speech")["count"] > 0
    with pytest.raises(topics.TopicError, match="isn't in the selected"):
        topics.entity_topics(view, model["id"], "e:alpha:999")
    only_gamma = View(lib, ["gamma"])
    assert topics.entity_topics(only_gamma, model["id"], only_gamma.member_unit[("gamma", 3)])["count"] > 0


def test_entity_topics_of_a_group_pool_its_entities(env):
    lib, view, model = env
    a, b = view.member_unit[("alpha", 1)], view.member_unit[("alpha", 2)]
    group = view.group_unit([view.units[a], view.units[b]], "pair")
    for kind in ("mentions", "speech"):
        one, two, both = (topics.entity_topics(view, model["id"], x, kind) for x in (a, b, group))
        assert both["count"] == one["count"] + two["count"] > 0 and sum(x["share"] for x in both["rows"]) == pytest.approx(1, abs=1e-3)


def test_reader_layer(env):
    lib, view, model = env
    bd = view.bd["alpha"]
    r = topics.reader_layer(view, "alpha", model["id"], None, 0, 400)
    assert r["error"] is None and r["tok_topic"] and set(r["tok_topic"].values()) <= {0, 1, 2, 3} and r["docs"]
    assert all(0 <= t <= 400 for t in r["tok_topic"]) and r["focus"] is None
    moor = moor_topic(env)
    focus = topics.reader_layer(view, "alpha", model["id"], moor, 0, 400)
    assert set(focus["tok_topic"].values()) == {moor} and focus["focus"] == moor and len(focus["tok_topic"]) <= len(r["tok_topic"]) + 50
    assert topics.reader_layer(view, "alpha", model["id"], "9", 0, 10)["focus"] is None
    assert topics.reader_layer(view, "nowhere", model["id"], None, 0, 10)["error"] == "This book isn't in the model."
    assert bd.n_tokens > 400
