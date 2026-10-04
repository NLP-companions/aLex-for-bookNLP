"""Groups of entities (analysed as one, or saved under a name) and narrators as entities."""
from __future__ import annotations

from collections import Counter

import pytest

from alex.core import dialogue as dl
from alex.core import entitygroups as eg
from alex.core.view import View

HOLMES = {"alpha": 1, "beta": 5, "gamma": 3}
WATSON = {"alpha": 2, "beta": 6, "gamma": 4}


def unit(view, book, coref):
    return view.member_unit[(book, coref)]


@pytest.fixture
def pair(view):
    """Holmes and Watson of the first book, as unit ids."""
    return [unit(view, "alpha", 1), unit(view, "alpha", 2)]


# ---------- a group's figures are the entities' figures pooled ----------
def test_a_group_pools_its_entities(view, truth, pair):
    t = truth["alpha"]
    P = view.group_profile({"ids": pair})
    holmes, watson = (view.units[i] for i in pair)
    assert P["unit"]["mentions"] == holmes.mentions + watson.mentions and P["unit"]["type"] == "PER" and P["unit"]["share"] is not None
    assert Counter({r["item"]: r["n"] for r in P["relations"]["agent"]["rows"]}) == t.agent[1] + t.agent[2]
    assert P["relations"]["agent"]["total"] == sum(t.agent[1].values()) + sum(t.agent[2].values())
    assert sum(P["presence"][0]["bins"]) == holmes.mentions + watson.mentions
    assert P["forms"]["PROP"][0]["n"] == max(t.mentions[(1, "PROP")], t.mentions[(2, "PROP")])
    g = P["group"]
    assert [u["id"] for u in g["units"]] == sorted(pair, key=lambda i: -view.units[i].mentions) and g["missing"] == []
    assert sum(u["pct"] for u in g["units"]) == pytest.approx(100) and g["types"] == {"PER": 2}


def test_members_of_the_group_do_not_count_as_outsiders(view, pair):
    """Holmes and Watson only name each other, so for the pair nobody names them, and they appear with nobody they didn't already have."""
    P = view.group_profile({"ids": pair})
    assert P["named_by"] == []
    assert not {x["id"] for x in P["cooccurring"]} & set(pair)
    single = view.cooccurring(pair[0])                         # for one of them, the other is a companion
    assert pair[1] in {x["id"] for x in single}


def test_a_shared_sentence_is_counted_once_for_a_group(view):
    """A sentence holding two of the group's entities counts once for each outsider in it, not once per entity."""
    everyone = [u.id for u in view.units.values() if u.type == "PER" and u.books == {"alpha"}]
    place = next(u for u in view.units.values() if u.type == "LOC" and u.books == {"alpha"})
    bd = view.bd["alpha"]
    members = {c for b, c in view.units[everyone[0]].members} | {c for i in everyone[1:] for b, c in view.units[i].members}
    (loc_coref,) = [c for b, c in place.members]
    truth = sum(1 for cs in bd.sent_members.values() if loc_coref in cs and members & cs)
    got = next(x["n"] for x in view.cooccurring(view.group_unit([view.units[i] for i in everyone], "PER")) if x["id"] == place.id)
    assert got == truth


def test_a_group_of_several_types_has_no_share(view, pair):
    place = next(u.id for u in view.units.values() if u.type == "LOC")
    P = view.group_profile({"ids": pair + [place]})
    assert P["unit"]["type"] == "PER" and P["unit"]["share"] is None and P["group"]["types"] == {"PER": 2, "LOC": 1}


def test_group_specs_work_wherever_a_spec_does(view, pair):
    mem, label, types = view.resolve({"kind": "group", "ids": pair})
    assert mem == set(view.units[pair[0]].members) | set(view.units[pair[1]].members) and types == {"PER"} and label == "Holmes, Watson"
    assert view.resolve({"kind": "group", "ids": pair, "name": "The pair"})[1] == "The pair"
    assert view.resolve({"kind": "group", "ids": [pair[0], pair[0]]})[0] == set(view.units[pair[0]].members)          # repeats are ignored
    assert view.resolve({"kind": "group", "ids": ["e:alpha:999"]})[0] == set()
    many = view.resolve({"kind": "group", "ids": [u.id for u in list(view.units.values())[:5]]})[1]
    assert many == "5 entities"
    rows, summary = view.distinctive({"kind": "group", "ids": pair}, {"kind": "others"}, "agent", min_freq=1, show_all=True)
    assert summary["target_units"] == 2 and rows
    ev = view.evidence({"kind": "group", "ids": pair}, "agent", "say")
    assert ev["total"] == sum(1 for u in pair for b, c in view.units[u].members for k, mi, hl in view.bd[b].groups[c].rel_ev.get("agent", []) if k == "say")


def test_a_group_can_be_compared_with_another_side_and_by_book(view, pair):
    a = {"kind": "group", "ids": pair}
    G = view.group_summary(a)
    assert G["units"] == 2 and G["mentions"] == sum(view.units[i].mentions for i in pair)
    bb = view.by_book({"kind": "group", "ids": [unit(view, "alpha", 1), unit(view, "beta", 5)]}, "agent")
    assert [b["id"] for b in bb["books"]] == ["alpha", "beta"]


def test_group_speech_pools_quotes_and_counts_talk_within_the_group(view, truth, pair):
    e = dl.entity(view, view.group_unit([view.units[i] for i in pair], "pair"))
    t = truth["alpha"]
    assert e["style"]["quotes"] == t.quotes[1] + t.quotes[2]
    assert e["within"] and e["within"] > 0
    assert not {x["id"] for x in e["talks_to"]} & set(pair) and not {x["id"] for x in e["addressed_by"]} & set(pair)
    assert dl.entity(view, pair[0])["within"] is None                                    # one entity has no "within"


# ---------- saved groups ----------
def test_saving_listing_renaming_and_deleting_groups(lib, pair):
    gid = eg.create(lib, "  Detectives ", pair + [pair[0], "junk"])
    assert eg.get(lib, gid) == ("Detectives", pair)                                     # trimmed, unique, junk dropped
    assert eg.listing(lib) == [{"id": gid, "name": "Detectives", "ids": pair}]
    other = eg.create(lib, "Others", [pair[0]])
    with pytest.raises(ValueError, match="already"):
        eg.create(lib, "detectives", pair)
    with pytest.raises(ValueError, match="already"):
        eg.update(lib, other, name="DETECTIVES")
    eg.update(lib, gid, name="Pair", ids=[pair[1]])
    assert eg.get(lib, gid) == ("Pair", [pair[1]])
    for bad in ({"name": "", "ids": pair}, {"name": "x", "ids": []}, {"name": "x", "ids": ["nope"]}):
        with pytest.raises(ValueError):
            eg.create(lib, **bad)
    with pytest.raises(ValueError):
        eg.update(lib, gid, ids=[])
    eg.delete(lib, gid)
    with pytest.raises(KeyError):
        eg.get(lib, gid)
    with pytest.raises(KeyError):
        eg.delete(lib, gid)


def test_a_saved_group_follows_links_and_the_selection(lib, view, pair):
    gid = eg.create(lib, "Detectives", pair)
    assert View(lib, ["alpha"]).group_of({"group": gid})[2] == "Detectives"
    lib.link("e:alpha:1", "e:beta:5")                                                   # Holmes is now one person across books
    v = View(lib, ["alpha", "beta"])
    units, missing, _ = v.group_of({"group": gid})
    assert missing == [] and {u.name for u in units} == {"Holmes", "Watson"} and any(u.linked for u in units)
    only_beta = View(lib, ["beta"])
    units, missing, _ = only_beta.group_of({"group": gid})
    assert [u.name for u in units] == ["Holmes"] and missing == [pair[1]]              # Watson of alpha isn't in the selection
    assert only_beta.group_profile({"group": gid})["group"]["missing"] == [pair[1]]
    eg.delete(lib, gid)
    assert view.group_of({"group": gid}) == ([], [], "(this group no longer exists)") and view.group_profile({"group": gid}) is None


def test_a_group_survives_a_restart(lib, pair, corpus):
    from alex.core.library import Library
    gid = eg.create(lib, "Detectives", pair)
    again = Library(data_dir=lib.data_dir, sources=[corpus[0]])
    assert eg.listing(again) == eg.listing(lib) and eg.create(again, "Next", pair) != gid


# ---------- narrators as entities ----------
@pytest.fixture
def narrated(lib):
    """The first book told by Watson, with paragraph 4 given to the unnamed narrator; all three books selected."""
    v = View(lib, ["alpha", "beta", "gamma"])
    w = unit(v, "alpha", 2)
    lib.ann_book("alpha")["narrator"] = w
    lib.ann_book("alpha")["para_narrators"][dl.keys(v.bd["alpha"])["p"][4]] = "anon"
    lib.save_ann()
    return View(lib, ["alpha", "beta", "gamma"]), w


def test_narrator_rows_are_the_roles(narrated):
    v, w = narrated
    rows = dl.narrator_rows(v)
    by_id = {r["id"]: r for r in rows}
    assert set(by_id) == {"nar:" + w, "nar:anon:alpha", "nar:anon:beta", "nar:anon:gamma"} and {r["type"] for r in rows} == {"NARR"}
    assert by_id["nar:" + w]["name"] == "Watson, narrating" and by_id["nar:" + w]["books"] == ["alpha"]
    assert rows == sorted(rows, key=lambda r: -r["mentions"]) and sum(r["share"] for r in rows) == pytest.approx(100)
    assert sum(r["mentions"] for r in rows) == dl.narrators(v)["narration_words"]


def test_a_narrator_profile(narrated):
    v, w = narrated
    P = dl.narrator_profile(v, "nar:" + w)
    mine = [r for b, r in dl.narration_recs(v) if r["role"] == "nar:" + w]
    assert P["role"]["unit"] == w and P["role"]["unit_name"] == "Watson" and not P["role"]["anonymous"] and P["role"]["books"] == ["alpha"]
    assert P["paragraphs"] == len(mine) and P["words"] == sum(r["n"] for r in mine) and P["exceptions"] == 0
    assert P["all_style"]["words"] == dl.narrators(v)["narration_words"] and 0 < P["share"] < 100
    assert P["spoken"]["quotes"] > 0                                                       # the same character speaks in quotes too
    (row,) = P["per_book"]
    assert row["book"] == "alpha" and row["paragraphs"] == len(mine) and 0 < row["share"] < 100
    assert sum(P["presence"][0]["bins"]) == len(mine) and len(P["presence"][0]["bins"]) == 100
    anon = dl.narrator_profile(v, "nar:anon:alpha")
    assert anon["role"]["anonymous"] and anon["role"]["unit"] is None and anon["spoken"] is None and anon["exceptions"] == anon["paragraphs"] == 1
    assert dl.narrator_profile(v, "nar:e:alpha:999") is None and dl.narrator_profile(v, "nar:anon:nope") is None


def test_narration_can_be_compared_with_all_other_narration(narrated):
    """The comparison side must not contain the target's own paragraphs (narration has no quote numbers to tell them apart)."""
    v, w = narrated
    r = dl.voice(v, {"kind": "narration", "id": "nar:" + w}, {"kind": "narration", "id": "all"})
    total = dl.narrators(v)["narration_words"]
    assert r["target"]["words"] + r["reference"]["words"] == total and r["reference"]["words"] > 0


# ---------- routes ----------
def test_group_and_narrator_routes(client):
    post = lambda path, **body: client.post(path, json={"books": ["alpha", "beta", "gamma"], **body})
    rows = post("/api/units").json()["rows"]
    ids = [next(r["id"] for r in rows if r["name"] == name and r["books"] == ["alpha"]) for name in ("Holmes", "Watson")]
    P = post("/api/profile", ids=ids).json()
    assert P["group"]["units"] and P["unit"]["mentions"] == sum(u["mentions"] for u in P["group"]["units"])
    assert post("/api/profile", ids=["e:alpha:999"]).status_code == 404
    assert post("/api/dialogue/entity", ids=ids).json()["within"] > 0 and post("/api/dialogue/entity", ids=["e:alpha:999"]).status_code == 404
    assert post("/api/dialogue/entity").status_code == 400                                 # neither an id nor ids
    made = client.post("/api/groups", json={"name": "Pair", "ids": ids}).json()
    gid = made["id"]
    assert made["groups"] == [{"id": gid, "name": "Pair", "ids": ids}] and client.get("/api/library").json()["groups"] == made["groups"]
    assert post("/api/profile", group=gid).json()["unit"]["name"] == "Pair"
    assert client.get("/api/groups").json()["groups"] == made["groups"]
    assert client.post(f"/api/groups/{gid}", json={"name": "Duo"}).json()["groups"][0]["name"] == "Duo"
    assert post("/api/compare", a={"kind": "group", "group": gid}, b={"kind": "others", "types": ["PER"]}).json()["a"]["units"] == 2
    assert client.post("/api/groups", json={"name": "", "ids": ids}).status_code == 400
    assert client.post("/api/groups/404", json={"name": "x"}).status_code == 404
    assert client.post("/api/groups/delete", json={"id": gid}).json()["groups"] == [] and client.post("/api/groups/delete", json={"id": gid}).status_code == 404
    assert post("/api/profile", group=gid).status_code == 404
    # narrators
    rows = post("/api/units").json()["narrators"]
    assert {r["id"] for r in rows} == {"nar:anon:alpha", "nar:anon:beta", "nar:anon:gamma"}
    p = post("/api/profile", id="nar:anon:alpha").json()
    assert p["role"]["anonymous"] and p["words"] > 0
    assert post("/api/profile", id="nar:anon:nope").status_code == 404
