"""Narrator suggestions, entity networks, link suggestions."""
from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET

import networkx as nx

from alex.core import dialogue as dl
from alex.core import links, narrators, network
from alex.core.corpus import cindex
from alex.core.library import Library
from alex.core.view import View


# ---------- narrators ----------
def first_person(bd):
    """(paragraph, mention index) of every "I" outside quotes, counted straight from the files."""
    ci = cindex(bd)
    return [(bd.para[m[1]], mi) for mi, m in enumerate(bd.mentions) if m[3] == "PRON" and m[5].lower() == "i" and not ci["in_quote"][m[1]]]


def test_the_first_person_narrator_is_suggested(view):
    r = narrators.book_suggestions(view, "alpha")
    n = len(first_person(view.bd["alpha"]))
    watson = view.member_unit[("alpha", 2)]
    assert r["first_person"] == n and r["suggested"]["id"] == watson and r["suggested"]["share"] == 100
    assert r["narrator"] == watson and r["runs"] == [] and r["current"] is None


def test_third_person_books_have_no_suggestion(view):
    for b in ("beta", "gamma"):
        r = narrators.book_suggestions(view, b)
        assert r["first_person"] == 0 and r["suggested"] is None and r["runs"] == []


def test_a_stretch_told_by_someone_else_is_found(tmp_path, corpus):
    """Relabel the "I" of a stretch of paragraphs as Holmes: that stretch should be suggested as told by Holmes."""
    folder = tmp_path / "exports" / "alpha-20260101-000000"
    shutil.copytree(next(corpus[0].glob("alpha-*")), folder)
    lib0 = Library(data_dir=tmp_path / "d0", sources=[corpus[0]])
    bd = lib0.book("alpha")
    fp = first_person(bd)
    lo, hi = fp[4][0], fp[11][0]                       # from the paragraph of the 5th "I" to that of the 12th
    mine = {mi for para, mi in fp if lo <= para <= hi}
    assert len(mine) >= 6
    rows = (folder / "alpha.entities").read_text().splitlines()
    out = [rows[0]]
    for i, line in enumerate(rows[1:]):
        c = line.split("\t")
        out.append("\t".join(["1"] + c[1:]) if i in mine else line)
    (folder / "alpha.entities").write_text("\n".join(out) + "\n", encoding="utf-8")
    lib = Library(data_dir=tmp_path / "d1", sources=[tmp_path / "exports"])
    v = View(lib, ["alpha"])
    r = narrators.book_suggestions(v, "alpha", max_gap=50, min_evidence=2)
    assert r["runs"], "a run of paragraphs told by Holmes should be suggested"
    run = r["runs"][0]
    assert run["unit"] == v.member_unit[("alpha", 1)] and run["evidence"] == len(mine) and not run["done"] and run["samples"]
    assert set(run["pids"]) >= {p for p, mi in first_person(lib.book("alpha")) if mi in mine}
    # accepting it (as the API does) marks it done; rejecting hides it
    keys = dl.keys(v.bd["alpha"])["p"]
    for pid in run["pids"]:
        lib.ann_book("alpha")["para_narrators"][keys[pid]] = run["unit"]
    v2 = View(lib, ["alpha"])
    assert narrators.book_suggestions(v2, "alpha", max_gap=50)["runs"][0]["done"]
    lib.ann_book("alpha")["narr_rejected"] = [run["key"]]
    assert narrators.book_suggestions(View(lib, ["alpha"]), "alpha", max_gap=50)["runs"] == []
    assert narrators.book_suggestions(v, "alpha", max_gap=50, min_evidence=10 ** 6)["runs"] == []


def test_suggestions_cover_every_book(view):
    r = narrators.suggestions(view)
    assert [b["book"] for b in r["books"]] == ["alpha", "beta", "gamma"] and "first-person pronouns" in r["note"]


# ---------- network ----------
def test_sentence_network_counts_shared_sentences(view):
    G = network.build(view, "sentence", ["PER"])
    h, w = view.member_unit[("alpha", 1)], view.member_unit[("alpha", 2)]
    bd = view.bd["alpha"]
    assert G[h][w]["weight"] == sum(1 for cs in bd.sent_members.values() if {1, 2} <= cs) and not G.is_directed()
    assert all(view.units[n].type == "PER" for n in G)


def test_paragraph_network_counts_shared_paragraphs(view):
    G = network.build(view, "paragraph", ["PER"])
    h, w = view.member_unit[("alpha", 1)], view.member_unit[("alpha", 2)]
    assert G[h][w]["weight"] == sum(1 for cs in view.bd["alpha"].para_members.values() if {1, 2} <= cs)


def test_type_filter_minimum_weight_and_isolated_nodes(view):
    both = network.build(view, "sentence", ["PER", "LOC"])
    assert any(view.units[n].type == "LOC" for n in both)
    strong = network.build(view, "sentence", ["PER"], min_weight=10 ** 6)
    assert strong.number_of_nodes() == 0
    lonely = network.build(view, "sentence", ["PER"], min_weight=10 ** 6, keep_isolated=True)
    assert lonely.number_of_nodes() == view.type_counts()["PER"] and lonely.number_of_edges() == 0


def test_dialogue_network_is_directed(view, truth):
    G = network.build(view, "dialogue", ["PER"])
    h, w = view.member_unit[("alpha", 1)], view.member_unit[("alpha", 2)]
    assert G.is_directed() and G[w][h]["weight"] == truth["alpha"].vocatives[(2, 1)]     # Watson says "Holmes" inside his quotes
    assert not G.has_edge(h, h)


def test_addressed_network_uses_estimated_addressees(view):
    G = network.build(view, "addressed", ["PER"])
    h, w = view.member_unit[("alpha", 1)], view.member_unit[("alpha", 2)]
    assert G.is_directed() and G.has_edge(h, w) and G.has_edge(w, h)


def test_focus_keeps_the_entity_and_its_top_neighbours(view):
    G = network.build(view, "sentence", ["PER", "LOC"], focus=view.member_unit[("alpha", 1)], focus_top=1)
    assert G.number_of_nodes() == 2 and view.member_unit[("alpha", 1)] in G


def test_measures(view):
    G = network.build(view, "sentence", ["PER", "LOC"])
    m, info = network.measures(G)
    h = view.member_unit[("alpha", 1)]
    assert m[h]["degree"] == G.degree(h) and m[h]["strength"] == G.degree(h, weight="weight")
    assert 0 <= m[h]["betweenness"] <= 1 and m[h]["clustering"] is not None and m[h]["community"] >= 1
    assert info["nodes"] == G.number_of_nodes() and info["edges"] == G.number_of_edges() and info["components"] >= 1
    assert network.measures(nx.Graph()) == ({}, {})
    D = network.build(view, "dialogue", ["PER"])
    md, _ = network.measures(D)
    n = next(iter(D))
    assert md[n]["in_degree"] == D.in_degree(n) and md[n]["out_strength"] == D.out_degree(n, weight="weight")


def test_layout_places_every_node_inside_the_canvas_and_repeats(view):
    G = network.build(view, "sentence", ["PER", "LOC"], keep_isolated=True)
    pos = network.layout(G)
    assert set(pos) == set(G) and all(0 <= x <= 1 and 0 <= y <= 1 for x, y in pos.values())
    assert pos == network.layout(G)                                                # deterministic (fixed seed)
    assert network.layout(nx.Graph()) == {}
    one = nx.Graph()
    one.add_node("a")
    assert network.layout(one)["a"]


def test_json_and_exports(view):
    G = network.build(view, "sentence", ["PER", "LOC"])
    j = network.as_json(view, G)
    assert len(j["nodes"]) == G.number_of_nodes() and len(j["edges"]) == G.number_of_edges() and j["directed"] is False
    assert {"x", "y", "strength", "community", "name", "type"} <= set(j["nodes"][0])
    for fmt in ("graphml", "gexf"):
        xml = network.export(view, G, fmt)
        root = ET.fromstring(xml)
        assert root.tag.endswith("graphml" if fmt == "graphml" else "gexf")
        assert xml.count(b"<node ") == G.number_of_nodes() and xml.count(b"<edge ") == G.number_of_edges()
    D = network.build(view, "dialogue", ["PER"])
    assert network.export(view, D, "graphml")


# ---------- link suggestions ----------
def in_one_series(lib, books=("alpha", "beta", "gamma")):
    """Put the books in one series: link suggestions are only made inside a series."""
    for b in books:
        lib.set_meta(b, {"series": "Baker Street"})


def test_same_names_across_books_are_suggested(lib):
    in_one_series(lib)
    rows, total = links.suggest(lib)
    pairs = {frozenset((r["a"]["id"], r["b"]["id"])): r for r in rows}
    assert frozenset(("e:alpha:1", "e:beta:5")) in pairs and frozenset(("e:alpha:2", "e:gamma:4")) in pairs
    top = pairs[frozenset(("e:alpha:1", "e:beta:5"))]
    assert top["score"] >= 0.85 and any("Same name" in x for x in top["reasons"])
    assert frozenset(("e:alpha:1", "e:alpha:2")) not in pairs                      # never within one book
    assert all(r["a"]["type"] == r["b"]["type"] for r in rows)
    assert frozenset(("e:alpha:1", "e:beta:6")) not in pairs                       # Holmes is not Watson
    assert total == len(rows) or total > len(rows)


def test_suggestions_stay_inside_a_series(lib):
    assert links.suggest(lib) == ([], 0)                                            # no series set: nothing is suggested
    lib.set_meta("alpha", {"series": "Baker Street"})
    lib.set_meta("beta", {"series": "baker street "})                               # same series, spelled a little differently
    lib.set_meta("gamma", {"series": "Marple"})
    ids = {frozenset((r["a"]["id"], r["b"]["id"])) for r in links.suggest(lib)[0]}
    assert frozenset(("e:alpha:1", "e:beta:5")) in ids
    assert not any(any(x.startswith("e:gamma") for x in pair) for pair in ids)      # gamma is in another series


def test_rejected_and_linked_pairs_are_not_suggested(lib):
    in_one_series(lib)
    lib.reject("e:alpha:1", "e:beta:5")
    ids = {frozenset((r["a"]["id"], r["b"]["id"])) for r in links.suggest(lib)[0]}
    assert frozenset(("e:alpha:1", "e:beta:5")) not in ids
    p = lib.link("e:alpha:2", "e:beta:6")
    rows = links.suggest(lib)[0]
    assert any(p in (r["a"]["id"], r["b"]["id"]) and "e:gamma:4" in (r["a"]["id"], r["b"]["id"]) for r in rows)


def test_auto_link_merges_exact_name_type_and_pronoun_matches(lib):
    """Unlike `suggest`, auto_link needs no series at all: an exact name, type and pronoun match is evidence enough
    on its own, across the whole library."""
    linked = links.auto_link(lib)
    by_name = {r["name"]: r for r in linked}
    assert by_name["Holmes"]["books"] == 3 and by_name["Holmes"]["type"] == "PER"
    assert by_name["Watson"]["books"] == 3
    assert lib.person_of()[("alpha", 1)] == lib.person_of()[("beta", 5)] == lib.person_of()[("gamma", 3)]
    assert lib.person_of()[("alpha", 2)] == lib.person_of()[("beta", 6)] == lib.person_of()[("gamma", 4)]


def test_auto_link_respects_rejections(lib):
    lib.reject("e:alpha:1", "e:beta:5")
    linked = links.auto_link(lib)
    holmes = next(r for r in linked if r["name"] == "Holmes")
    assert holmes["books"] == 2                                     # alpha and gamma joined; beta stayed apart, rejected
    assert ("alpha", 1) in lib.person_of() and ("beta", 5) not in lib.person_of()


def test_auto_link_needs_pronoun_agreement_so_places_are_left_alone(lib):
    """Baker Street (a LOC) recurs by the same name in every book, but places have no BookNLP pronouns, so the
    safeguard against merging two different same-named things leaves it for you to link by hand (or `suggest`)."""
    linked = links.auto_link(lib)
    assert not any(r["type"] == "LOC" for r in linked)


def test_narrator_links_lists_anonymous_and_named_members(lib):
    """`links.narrator_links` needs no View: it resolves names straight from `lib`, like `persons` does."""
    lid = lib.link_narrators("nar:anon:alpha", "nar:anon:beta")
    rows = links.narrator_links(lib)
    assert [r["id"] for r in rows] == [lid]
    row = rows[0]
    assert row["custom_name"] is False and row["name"] == "N narrators, linked".replace("N", "2")
    assert {m["id"] for m in row["members"]} == {"nar:anon:alpha", "nar:anon:beta"}
    assert all(m["unit"] is None and m["name"].startswith("Narrator of ") for m in row["members"])
    assert next(m for m in row["members"] if m["id"] == "nar:anon:alpha")["books"] == ["alpha"]


def test_narrator_links_names_a_character_role_and_follows_your_own_name(lib):
    lid = lib.link_narrators("nar:e:alpha:1", "nar:anon:beta")           # Holmes, narrating alpha, + beta's anonymous narrator
    row = next(r for r in links.narrator_links(lib) if r["id"] == lid)
    holmes = next(m for m in row["members"] if m["unit"] == "e:alpha:1")
    assert holmes["name"] == "Holmes, narrating" and holmes["books"] == ["alpha"]
    assert row["name"] == "Holmes"                                       # no name of your own yet: follows the named member
    lib.set_name(lid, "The Chronicler")
    row = next(r for r in links.narrator_links(lib) if r["id"] == lid)
    assert row["name"] == "The Chronicler" and row["custom_name"] is True


def test_narrator_links_follows_a_member_thats_also_a_linked_person(lib):
    p = lib.link("e:alpha:1", "e:beta:5")                                 # Holmes, linked across alpha and beta
    lid = lib.link_narrators("nar:" + p, "nar:anon:gamma")
    row = next(r for r in links.narrator_links(lib) if r["id"] == lid)
    holmes = next(m for m in row["members"] if m["unit"] == p)
    assert sorted(holmes["books"]) == ["alpha", "beta"]                   # both of the linked person's books, not just one


def test_norm_tokens_sets_titles_aside():
    assert links.norm_tokens("Mr. Sherlock Holmes") == ["sherlock", "holmes"]
    assert links.norm_tokens("Dr. Watson's") == ["watson"]
    assert links.norm_tokens("the") == ["the"] and links.norm_tokens("???") == []


def test_units_without_usable_names_do_not_break_suggestions(tmp_path, corpus):
    """A proper-name mention made of punctuation only used to crash the suggestion step."""
    folder = tmp_path / "exports" / "gamma-20260103-000000"
    shutil.copytree(next(corpus[0].glob("gamma-*")), folder)
    with open(folder / "gamma.entities", "a", encoding="utf-8") as f:
        f.write("77\t0\t0\tPROP\tPER\t???\n77\t1\t1\tPROP\tPER\t???\n")
    shutil.copytree(next(corpus[0].glob("beta-*")), tmp_path / "exports" / "beta-20260102-000000")
    with open(tmp_path / "exports" / "beta-20260102-000000" / "beta.entities", "a", encoding="utf-8") as f:
        f.write("78\t0\t0\tPROP\tPER\t!!!\n78\t1\t1\tPROP\tPER\t!!!\n")
    lib = Library(data_dir=tmp_path / "d", sources=[tmp_path / "exports"])
    rows, total = links.suggest(lib)
    assert isinstance(rows, list)


def test_search_and_persons(lib):
    hits = links.search(lib, "holmes")
    assert {h["id"] for h in hits} >= {"e:alpha:1", "e:beta:5", "e:gamma:3"} and hits[0]["mentions"] >= hits[-1]["mentions"]
    assert links.search(lib, "zzzz") == []
    p = lib.link("e:alpha:1", "e:beta:5", name="Sherlock")
    (row,) = links.persons(lib)
    assert row["id"] == p and row["name"] == "Sherlock" and row["custom_name"] and len(row["members"]) == 2 and row["type"] == "PER"
    assert all(not m["missing"] for m in row["members"])
    lib.state["persons"][p[2:]]["members"].append(["nowhere", 1])
    assert any(m["missing"] for m in links.persons(lib)[0]["members"])
