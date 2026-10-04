"""View: what a selection of books contains, with your thresholds and links applied."""
from __future__ import annotations

import pytest

from alex.core.view import View


def unit_named(view, name, book=None):
    return next(u for u in view.units.values() if u.name == name and (book is None or u.books == {book}))


def test_books_go_by_year_ascending_then_undated_last(lib):
    """Wherever several books are shown together they follow publication year, regardless of the order requested;
    an undated book (gamma here) sorts after every dated one, by title."""
    lib.set_meta("alpha", {"year": 1902})
    lib.set_meta("beta", {"year": 1890})
    assert View(lib, ["alpha", "beta", "gamma"]).books == ["beta", "alpha", "gamma"]
    assert View(lib, ["gamma", "alpha", "beta"]).books == ["beta", "alpha", "gamma"]


def test_a_units_own_books_follow_the_views_order(lib):
    lib.set_meta("alpha", {"year": 1902})
    lib.set_meta("beta", {"year": 1890})
    p = lib.link(lib.link("e:alpha:1", "e:beta:5"), "e:gamma:3")
    v = View(lib, ["alpha", "beta", "gamma"])
    row = v.units[p].as_row(v)
    assert row["books"] == ["beta", "alpha", "gamma"]


def test_units_and_mention_counts_match_the_generator(view, truth):
    for bid, t in truth.items():
        holmes = unit_named(view, "Holmes", bid)
        c = BOOK_HOLMES[bid]
        assert holmes.mentions == t.mentions[(c, "PROP")] + t.mentions[(c, "PRON")]
    assert view.type_counts()["PER"] >= 6 and view.type_counts()["LOC"] == 3


BOOK_HOLMES = {"alpha": 1, "beta": 5, "gamma": 3}
BOOK_WATSON = {"alpha": 2, "beta": 6, "gamma": 4}


def test_minimum_per_book_drops_small_entities(lib):
    lib.state["settings"]["min"]["LOC"] = 15
    v = View(lib, ["alpha", "beta", "gamma"])
    locs = [u for u in v.units.values() if u.type == "LOC"]
    assert sorted(u.mentions for u in locs) == [17, 24]          # gamma's Baker Street (13 mentions) falls below 15


def test_combined_minimum_counts_a_linked_entity_across_books(lib):
    lib.link("e:alpha:10", "e:beta:20")
    lib.link(lib.link("e:alpha:10", "e:beta:20"), "e:gamma:9")
    lib.state["settings"]["min"]["LOC"] = 40
    lib.state["settings"]["count_mode"] = "per_book"
    assert not [u for u in View(lib, ["alpha", "beta", "gamma"]).units.values() if u.type == "LOC"]
    lib.state["settings"]["count_mode"] = "combined"
    (street,) = [u for u in View(lib, ["alpha", "beta", "gamma"]).units.values() if u.type == "LOC"]
    assert street.mentions == 24 + 17 + 13 and street.linked and street.books == {"alpha", "beta", "gamma"}


def test_linked_person_combines_books(lib, truth):
    p = lib.link("e:alpha:1", "e:beta:5")
    p = lib.link(p, "e:gamma:3")
    v = View(lib, ["alpha", "beta", "gamma"])
    u = v.units[p]
    total = sum(truth[b].mentions[(BOOK_HOLMES[b], k)] for b in truth for k in ("PROP", "PRON"))
    assert u.mentions == total and u.linked and u.name == "Holmes" and u.books == {"alpha", "beta", "gamma"}
    assert v.member_unit[("beta", 5)] == p and not any(x.startswith("e:") and x.endswith(":5") for x in v.units)


def test_a_person_name_you_set_wins(lib):
    p = lib.link("e:alpha:1", "e:beta:5", name="Sherlock")
    assert View(lib, ["alpha", "beta"]).units[p].name == "Sherlock"


def test_an_unlinked_entitys_name_you_set_wins(lib):
    v = View(lib, ["alpha"])
    holmes = next(u for u in v.units.values() if u.id == "e:alpha:1")
    assert holmes.name != "Alpha Holmes" and not holmes.as_row(v)["custom_name"] and holmes.as_row(v)["note"] == ""
    lib.set_name("e:alpha:1", "Alpha Holmes")
    lib.set_note("e:alpha:1", "The detective")
    v = View(lib, ["alpha"])
    row = v.units["e:alpha:1"].as_row(v)
    assert v.units["e:alpha:1"].name == "Alpha Holmes" and row["custom_name"] is True and row["note"] == "The detective"


def test_selecting_one_book_hides_the_others(lib):
    v = View(lib, ["gamma"])
    assert v.books == ["gamma"] and all(u.books == {"gamma"} for u in v.units.values())


def test_unreadable_books_are_reported_not_fatal(lib, corpus):
    v = View(lib, ["alpha", "nope"])
    assert v.books == ["alpha"] and v.problems and "nope" in v.problems[0]


def test_profile_matches_the_generator(view, truth):
    t = truth["alpha"]
    h = unit_named(view, "Holmes", "alpha")
    P = view.profile(h.id)
    assert P["unit"]["mentions"] == h.mentions and P["by_prop"] == {"PROP": t.mentions[(1, "PROP")], "NOM": 0, "PRON": t.mentions[(1, "PRON")]}
    agent = {r["item"]: r["n"] for r in P["relations"]["agent"]["rows"]}
    assert agent == dict(t.agent[1])
    assert {r["item"]: r["n"] for r in P["relations"]["poss"]["rows"]} == dict(t.poss[1])
    assert P["relations"]["agent"]["total"] == sum(t.agent[1].values())
    assert P["pronouns"] == [{"item": "he/him/his", "n": h.mentions}]
    assert sum(P["presence"][0]["bins"]) == h.mentions and len(P["presence"][0]["bins"]) == 100
    assert P["forms"]["PROP"][0] == {"item": "Holmes", "n": t.mentions[(1, "PROP")]}
    # events and supersenses of the actions
    said = next(r for r in P["relations"]["agent"]["rows"] if r["item"] == "say")
    assert said["events"] == said["n"] and said["supersense"] == "verb.communication"


def test_who_names_whom_inside_quotes(view, truth):
    h = unit_named(view, "Holmes", "alpha")
    w = unit_named(view, "Watson", "alpha")
    named_by = {x["id"]: x["n"] for x in view.profile(h.id)["named_by"]}
    assert named_by == {w.id: truth["alpha"].vocatives[(2, 1)]}          # Watson addresses "Holmes" in his quotes


def test_cooccurrence_counts_shared_sentences(view):
    h, w = unit_named(view, "Holmes", "alpha"), unit_named(view, "Watson", "alpha")
    co = {x["id"]: x["n"] for x in view.cooccurring(h.id)}
    bd = view.bd["alpha"]
    assert co[w.id] == sum(1 for cs in bd.sent_members.values() if {1, 2} <= cs)


def test_profile_of_unknown_or_hidden_unit_is_none(view):
    assert view.profile("e:alpha:999") is None


def test_distinctive_puts_holmes_only_verbs_first(lib):
    view = View(lib, ["alpha"])         # with one book, "everyone else" is only Watson and the place
    h = unit_named(view, "Holmes", "alpha")
    rows, summary = view.distinctive({"kind": "unit", "id": h.id}, {"kind": "others"}, "agent", min_freq=1, show_all=True)
    items = {r["item"]: r for r in rows}
    assert "take" in items and items["take"]["b"] == 0             # only Holmes takes things
    assert summary["target_units"] == 1 and summary["reference_units"] >= 1


def test_group_summary_by_tag_and_type(lib):
    lib.set_tags("e:alpha:1", ["detective"])
    lib.set_tags("e:beta:5", ["detective"])
    v = View(lib, ["alpha", "beta", "gamma"])
    g = v.group_summary({"kind": "tag", "tag": "detective"})
    assert g["units"] == 2 and g["books"] == 2 and g["mentions"] == unit_named(v, "Holmes", "alpha").mentions + unit_named(v, "Holmes", "beta").mentions
    assert v.group_summary({"kind": "type", "type": "LOC"})["units"] == 3


def test_resolve_others_excludes_the_target(view):
    h = unit_named(view, "Holmes", "alpha")
    tm, _, _ = view.resolve({"kind": "unit", "id": h.id})
    om, label, types = view.resolve({"kind": "others", "types": ["PER"]}, exclude=frozenset(tm))
    assert not (tm & om) and types == {"PER"} and om


def test_resolve_limits_to_books_and_survives_unknown_specs(view):
    m, label, _ = view.resolve({"kind": "type", "type": "PER", "books": ["alpha"]})
    assert m and {b for b, _ in m} == {"alpha"} and "in" in label
    assert view.resolve({"kind": "unit", "id": "e:alpha:999"})[0] == set()
    assert view.resolve({"kind": "???"})[0] == set()
    assert view.resolve({"kind": "unit"})[0] == set()        # a spec without an id is "not in this selection", not an error


def test_evidence_finds_the_sentences_behind_a_count(view, truth):
    h = unit_named(view, "Holmes", "alpha")
    r = view.evidence({"kind": "unit", "id": h.id}, "agent", key="take")
    assert r["total"] == truth["alpha"].agent[1]["take"] and r["shown"] == r["total"]
    assert all("\x01m\x02" in x["text"] and "\x01k\x02" in x["text"] for x in r["items"])
    named = view.evidence({"kind": "unit", "id": h.id}, "named", other=unit_named(view, "Watson", "alpha").id)
    assert named["total"] == truth["alpha"].vocatives[(2, 1)]
    assert view.evidence({"kind": "unit", "id": h.id}, "form", key="Holmes")["total"] == truth["alpha"].mentions[(1, "PROP")]
    assert view.evidence({"kind": "unit", "id": h.id}, "agent", key="take", limit=2)["shown"] == 2


def test_evidence_of_an_unknown_kind_is_empty_not_an_error(view):
    h = unit_named(view, "Holmes", "alpha")
    assert view.evidence({"kind": "unit", "id": h.id}, "nonsense")["total"] == 0


def test_by_book_for_a_linked_person(lib, truth):
    p = lib.link(lib.link("e:alpha:1", "e:beta:5"), "e:gamma:3")
    v = View(lib, ["alpha", "beta", "gamma"])
    r = v.by_book({"kind": "unit", "id": p}, "agent", min_freq=1)
    assert [x["book"] for x in r["overview"]] == ["alpha", "beta", "gamma"]
    assert [x["mentions"] for x in r["overview"]] == [sum(truth[b].mentions[(BOOK_HOLMES[b], k)] for k in ("PROP", "PRON")) for b in ("alpha", "beta", "gamma")]
    say = next(x for x in r["rows"] if x["item"] == "say")
    assert say["counts"] == [truth[b].agent[BOOK_HOLMES[b]]["say"] for b in ("alpha", "beta", "gamma")]
    assert say["tested"] and say["p"] is not None and len(say["resid"]) == 3
    assert r["summary"]["tested"] >= 1 and r["totals"] == [sum(t.agent[BOOK_HOLMES[b]].values()) for b, t in truth.items()]


def test_unit_rows_are_sorted_and_share_sums_to_100(view):
    rows = view.unit_rows("PER")
    assert [r["mentions"] for r in rows] == sorted((r["mentions"] for r in rows), reverse=True)
    assert sum(r["share"] for r in rows) == pytest.approx(100)


def test_name_of_handles_hidden_and_unknown_ids(lib):
    lib.state["settings"]["min"]["PER"] = 10 ** 6
    v = View(lib, ["alpha"])
    assert v.name_of("e:alpha:1") == "Holmes (below minimum)"
    assert v.name_of("garbage") == "garbage"


# ---------- books and genders as their own pools ----------
def test_genders_bucket_per_entities_by_bookNLPs_pronoun_prediction(view):
    holmes = unit_named(view, "Holmes", "gamma")
    view.bd["gamma"].groups[BOOK_HOLMES["gamma"]].pronouns = None   # simulate one entity BookNLP made no prediction for
    g = {row["pron"]: row for row in view.genders()}
    assert sum(row["entities"] for row in g.values()) == view.type_counts()["PER"]
    assert g["he/him/his"]["entities"] >= 3                          # Holmes and Watson, at least, in the other books
    assert view._gender_of(holmes) == "unknown" and g["unknown"]["entities"] == 1
    assert "she/her" not in g                                        # no character of that gender in the fixture


def test_resolve_gender_matches_the_genders_listing(view):
    g = {row["pron"]: row for row in view.genders()}
    mem, label, types = view.resolve({"kind": "gender", "pron": "he/him/his"})
    assert types == {"PER"} and label == "he/him/his"
    assert len({view.member_unit[m] for m in mem if m in view.member_unit}) == g["he/him/his"]["entities"]
    assert view.resolve({"kind": "gender", "pron": "she/her"})[0] == set()   # no such gender here: empty, not an error


def test_gender_profile_pools_one_bucket_as_one_group(view):
    holmes = unit_named(view, "Holmes", "gamma")
    view.bd["gamma"].groups[BOOK_HOLMES["gamma"]].pronouns = None
    p = view.gender_profile("he/him/his")
    names = {u["name"] for u in p["group"]["units"]}
    assert "Holmes" in names and "Watson" in names
    unknown = view.gender_profile("unknown")
    assert holmes.id in {u["id"] for u in unknown["group"]["units"]}
    assert view.gender_profile("she/her") is None


def test_pool_unit_builds_a_virtual_unit_for_any_scope(view):
    """`pool_unit` is `resolve`'s companion for views (In-Depth Who Speaks) that need a unit's-worth of figures for a
    scope, not just its flat member set: a `group_unit` pooling everyone the spec matches."""
    holmes_alpha, watson_alpha = unit_named(view, "Holmes", "alpha"), unit_named(view, "Watson", "alpha")
    assert view.pool_unit({"kind": "unit", "id": holmes_alpha.id}) is holmes_alpha
    g = view.pool_unit({"kind": "group", "ids": [holmes_alpha.id, watson_alpha.id]})
    assert set(g.parts) == {holmes_alpha.id, watson_alpha.id} and g.name == "Holmes, Watson"
    assert view.pool_unit({"kind": "group", "ids": ["e:alpha:999"]}) is None            # matches nobody: None, not an empty unit
    gender = view.pool_unit({"kind": "gender", "pron": "he/him/his"})
    assert holmes_alpha.id in gender.parts and gender.name == "he/him/his"
    assert view.pool_unit({"kind": "gender", "pron": "she/her"}) is None
    holmes_alpha.tags = ["detective"]
    tag = view.pool_unit({"kind": "tag", "tag": "detective", "type": ""})
    assert set(tag.parts) == {holmes_alpha.id} and tag.name == "tag “detective”"
    assert view.pool_unit({"kind": "tag", "tag": "no-such-tag"}) is None
    assert view.pool_unit({"kind": "others"}) is None                                   # not a supported scope here


def test_resolve_book_gives_every_counted_entity_in_it(view):
    mem, label, types = view.resolve({"kind": "book", "book": "alpha"})
    assert label == view.title("alpha") and "PER" in types
    assert mem == {m for m in view.member_unit if m[0] == "alpha"}
    assert view.resolve({"kind": "book", "book": "nope"})[0] == set()


def test_book_profile_restricts_a_linked_person_to_that_books_own_mentions(lib, truth):
    p = lib.link("e:alpha:1", "e:beta:5")             # Holmes, linked across alpha and beta
    v = View(lib, ["alpha", "beta", "gamma"])
    prof = v.book_profile("alpha")
    assert prof["book"]["title"] == v.title("alpha") and prof["book"]["words"] == v.bd["alpha"].n_words
    holmes_row = next(u for u in prof["group"]["units"] if u["id"] == p)
    assert holmes_row["mentions"] == truth["alpha"].mentions[(1, "PROP")] + truth["alpha"].mentions[(1, "PRON")]
    assert holmes_row["mentions"] < v.units[p].mentions       # less than Holmes's combined alpha+beta mentions
    assert v.book_profile("nope") is None


def test_book_grid_gives_every_characters_mentions_in_each_of_two_books(view, truth):
    """Unlinked, alpha's Holmes and beta's Holmes are different entities (as everywhere else in the app), so each
    gets its own row, present in one book and absent (0) from the other."""
    rows = {r["id"]: r for r in view.book_grid("alpha", "beta")}
    holmes_alpha, holmes_beta = unit_named(view, "Holmes", "alpha").id, unit_named(view, "Holmes", "beta").id
    assert rows[holmes_alpha]["a"] == truth["alpha"].mentions[(1, "PROP")] + truth["alpha"].mentions[(1, "PRON")]
    assert rows[holmes_alpha]["b"] == 0
    assert rows[holmes_beta]["a"] == 0 and rows[holmes_beta]["b"] > 0
    assert all(r["a"] or r["b"] for r in rows.values())                     # never a character absent from both
    assert list(rows.values()) == sorted(rows.values(), key=lambda r: -(r["a"] + r["b"]))
    same = view.book_grid("alpha", "alpha")
    assert same and all(r["a"] == r["b"] for r in same)                    # a book against itself


def test_book_grid_merges_a_linked_person_into_one_row(lib):
    p = lib.link("e:alpha:1", "e:beta:5")             # Holmes, linked across alpha and beta
    v = View(lib, ["alpha", "beta", "gamma"])
    row = next(r for r in v.book_grid("alpha", "beta") if r["id"] == p)
    assert row["a"] > 0 and row["b"] > 0
