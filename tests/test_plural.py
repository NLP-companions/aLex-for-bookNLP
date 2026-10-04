"""Plural groups ("Holmes and Watson", "they"), declared in the analyser (plurals.py). Counted the default way, every group
has only its own mentions and quotes; with plural groups included, a plural group's mentions (except members named inside
them), quotes and addressees count for its members too. The setting has a default and a per-request override."""
from __future__ import annotations

import json

import pytest

from alex.core import dialogue, network, plurals
from alex.core.library import Library
from alex.core.view import View

# word, lemma, POS, dependency, head (index in the sentence); one list of sentences per paragraph
SENTS = [
    [[("Holmes", "Holmes", "PROPN", "nsubj", 3), ("and", "and", "CCONJ", "cc", 0), ("Watson", "Watson", "PROPN", "conj", 0),
      ("walked", "walk", "VERB", "ROOT", 3), (".", ".", "PUNCT", "punct", 3)],
     [("They", "they", "PRON", "nsubj", 1), ("talked", "talk", "VERB", "ROOT", 1), (".", ".", "PUNCT", "punct", 1)]],
    [[("Lestrade", "Lestrade", "PROPN", "nsubj", 1), ("met", "meet", "VERB", "ROOT", 1), ("them", "they", "PRON", "dobj", 1),
      (".", ".", "PUNCT", "punct", 1)]],
    [[('"', '"', "PUNCT", "punct", 7), ("We", "we", "PRON", "nsubj", 3), ("must", "must", "AUX", "aux", 3), ("go", "go", "VERB", "ccomp", 7),
      (",", ",", "PUNCT", "punct", 3), ('"', '"', "PUNCT", "punct", 7), ("they", "they", "PRON", "nsubj", 7), ("said", "say", "VERB", "ROOT", 7),
      (".", ".", "PUNCT", "punct", 7)]],
    [[('"', '"', "PUNCT", "punct", 5), ("Go", "go", "VERB", "ccomp", 5), ("then", "then", "ADV", "advmod", 1), (",", ",", "PUNCT", "punct", 1),
      ('"', '"', "PUNCT", "punct", 5), ("said", "say", "VERB", "ROOT", 5), ("Lestrade", "Lestrade", "PROPN", "nsubj", 5), (".", ".", "PUNCT", "punct", 5)]],
]
# group, sentence number (in the book), first word, last word, prop
MENTIONS = [(2, 0, 0, 2, "PROP"), (0, 0, 0, 0, "PROP"), (1, 0, 2, 2, "PROP"), (2, 1, 0, 0, "PRON"), (3, 2, 0, 0, "PROP"),
            (2, 2, 2, 2, "PRON"), (2, 3, 1, 1, "PRON"), (2, 3, 6, 6, "PRON"), (3, 4, 6, 6, "PROP")]
# sentence, first word, last word, speaker, (first, last word of the attributing mention)
QUOTES = [(3, 0, 5, 2, (6, 6)), (4, 0, 4, 3, (6, 6))]


def write_book(folder):
    """The book in the editor's export layout: Holmes (0), Watson (1), "Holmes and Watson" / they (2) and Lestrade (3). Its
    .book still has the `members` field an earlier editor wrote, which the analyser no longer reads."""
    folder.mkdir(parents=True)
    rows, starts, doc, pos, sid = [], [], 0, 0, 0
    for pid, para in enumerate(SENTS):
        for sent in para:
            starts.append(doc)
            for i, (w, lemma, p, dep, head) in enumerate(sent):
                rows.append("\t".join(map(str, (pid, sid, i, doc, w, lemma, pos, pos + len(w), p, p, dep, starts[-1] + head, "O"))))
                pos += len(w) + 1
                doc += 1
            sid += 1
    head = ("paragraph_ID\tsentence_ID\ttoken_ID_within_sentence\ttoken_ID_within_document\tword\tlemma\tbyte_onset\t"
            "byte_offset\tPOS_tag\tfine_POS_tag\tdependency_relation\tsyntactic_head_ID\tevent")
    (folder / "pair.tokens").write_text(head + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    words = [r.split("\t")[4] for r in rows]
    text = lambda a, b: " ".join(words[a:b + 1])
    ents = [f"{c}\t{starts[s] + a}\t{starts[s] + b}\t{prop}\tPER\t{text(starts[s] + a, starts[s] + b)}" for c, s, a, b, prop in MENTIONS]
    (folder / "pair.entities").write_text("COREF\tstart_token\tend_token\tprop\tcat\ttext\n" + "\n".join(ents) + "\n", encoding="utf-8")
    qs = [f"{starts[s] + a}\t{starts[s] + b}\t{starts[s] + ma}\t{starts[s] + mb}\t{text(starts[s] + ma, starts[s] + mb)}\t{c}\t{text(starts[s] + a, starts[s] + b)}"
          for s, a, b, c, (ma, mb) in QUOTES]
    (folder / "pair.quotes").write_text("quote_start\tquote_end\tmention_start\tmention_end\tmention_phrase\tchar_id\tquote\n" + "\n".join(qs) + "\n",
                                        encoding="utf-8")
    chars = [{"id": 0, "name": "Holmes"}, {"id": 1, "name": "Watson"}, {"id": 3, "name": "Lestrade"},
             {"id": 2, "name": "Holmes and Watson", "members": [0, 1]}]
    (folder / "pair.book").write_text(json.dumps({"characters": chars}), encoding="utf-8")


@pytest.fixture
def plain(tmp_path):
    """A library over the book, with the minimum mentions lowered so every group counts, and no plural group declared."""
    write_book(tmp_path / "exports" / "pair-20260101-000000")
    lib = Library(data_dir=tmp_path / "data", sources=[tmp_path / "exports"])
    lib.state["settings"]["min"] = {t: 1 for t in ("PER", "LOC", "FAC", "GPE", "VEH", "ORG", "VAR")}
    return lib


@pytest.fixture
def plib(plain):
    """The same, with "Holmes and Watson" declared the plural group of Holmes and Watson."""
    plurals.set_members(plain, "e:pair:2", ["e:pair:0", "e:pair:1"])
    return plain


def ids(view):
    """Unit ids by name."""
    return {u.name: u.id for u in view.units.values()}


# ---------- declaring ----------
def test_members_come_from_your_declarations_not_the_book_file(plain, plib):
    bd = plib.book("pair")
    assert bd.groups[2].members == [0, 1]
    assert bd.groups[0].member_of == [2] and bd.groups[3].member_of == []
    assert bd.plural_pair(2, 0) and bd.plural_pair(1, 2) and not bd.plural_pair(0, 1)
    plurals.set_members(plib, "e:pair:2", [])        # an ordinary entity again: the .book's own `members` field is ignored
    assert plib.book("pair").groups[2].members == [] and plib.state["plurals"] == {}


def test_what_can_be_declared(plib):
    for uid, members in [("e:pair:2", ["e:pair:2"]),                     # itself
                         ("e:pair:3", ["e:pair:2"]),                     # a plural group as member
                         ("e:pair:0", ["e:pair:3"]),                     # a member made plural
                         ("e:nobook:1", ["e:pair:0"]),                   # not in any book
                         ("e:pair:3", ["e:other:1"])]:                   # not in its book
        with pytest.raises(ValueError):
            plurals.set_members(plib, uid, members)
    assert plurals.book_map(plib, "pair") == {2: [0, 1]} and plurals.members_of(plib, "e:pair:2") == ["e:pair:0", "e:pair:1"]


def test_a_declaration_on_a_linked_entity_applies_in_its_books(plain):
    pid = plain.link("e:pair:2", "e:pair:3")                            # a person made of two groups (one book is enough here)
    plurals.set_members(plain, pid, ["e:pair:0"])
    assert plurals.book_map(plain, "pair") == {2: [0], 3: [0]}
    assert plain.book("pair").groups[3].members == [0]


def test_linking_folds_older_declarations_into_the_new_one(plib):
    pid = plib.link("e:pair:2", "e:pair:3")
    plurals.set_members(plib, pid, ["e:pair:0", "e:pair:1"])
    assert list(plib.state["plurals"]) == [pid]


def test_adding_and_removing_keeps_the_members_a_page_does_not_show(plib):
    # a page lists only the members counted in its books; it sends what changed, and the rest stays
    assert plurals.change_members(plib, "e:pair:2", remove=["e:pair:1"]) == ["e:pair:0"]
    assert plurals.change_members(plib, "e:pair:2", add=["e:pair:1"]) == ["e:pair:0", "e:pair:1"]
    plib.state["plurals"]["e:pair:2"].append("p:gone")                    # a linked entity deleted since
    assert plurals.change_members(plib, "e:pair:2", remove=["e:pair:0"]) == ["e:pair:1"]


def test_a_declaration_made_before_a_link_belongs_to_the_linked_entity(plib):
    pid = plib.link("e:pair:2", "e:pair:3")
    assert plurals.members_of(plib, pid) == ["e:pair:0", "e:pair:1"]
    assert plurals.change_members(plib, pid, remove=["e:pair:1"]) == ["e:pair:0"]
    assert plib.state["plurals"] == {pid: ["e:pair:0"]}
    assert plurals.book_map(plib, "pair") == {2: [0], 3: [0]}


def test_rules_hold_for_linked_entities_too(plib):
    holmes = plib.link("e:pair:0", "e:pair:3")                           # a member, linked with another group
    with pytest.raises(ValueError):
        plurals.set_members(plib, holmes, ["e:pair:1"])                  # a member made plural
    with pytest.raises(ValueError):
        plurals.set_members(plib, "e:pair:1", [holmes])                  # ... and it stays as it was
    assert plib.state["plurals"] == {"e:pair:2": ["e:pair:0", "e:pair:1"]}
    plurals.set_members(plib, "e:pair:2", ["e:pair:0", holmes, "e:pair:1"])   # one group reached twice counts once
    assert plurals.book_map(plib, "pair") == {2: [0, 3, 1]}


def test_suggestions_and_dismissing_them(plain):
    view = View(plain, ["pair"])
    s = plurals.suggestions(view)
    assert [(x["name"], [m["name"] for m in x["members"]], x["unmatched"]) for x in s] == [("Holmes and Watson", ["Holmes", "Watson"], [])]
    plurals.reject(plain, s[0]["id"])
    assert plurals.suggestions(View(plain, ["pair"])) == []
    assert plurals.split_name("Holmes, Watson, and the Inspector") == ["Holmes", "Watson", "the Inspector"]
    assert plurals.split_name("Sherlock Holmes") == [] and plurals.name_key("Mr. Sherlock Holmes") == "sherlock holmes"


def test_accepted_suggestions_are_not_suggested_again(plib):
    assert plurals.suggestions(View(plib, ["pair"])) == []
    plib.link("e:pair:2", "e:pair:3")                                   # not even once linked into another entity
    assert plurals.suggestions(View(plib, ["pair"])) == []


# ---------- reading the book ----------


def test_off_every_group_has_only_its_own_mentions(plib):
    bd = plib.book("pair")
    assert not bd.plural and bd.credit == {}
    assert len(bd.groups[0].mentions) == 1 and bd.groups[0].rel["agent"] == {"walk": 1}
    assert bd.sent_members[1] == {2}                # "They talked": only the pair
    assert bd.stands_for(2) == (2,) and bd.stands_for(None) == ()


def test_on_members_are_credited_except_where_named_inside(plib):
    bd = plib.book("pair", plural=True)
    assert plib.book("pair") is not bd and plib.book("pair", plural=True) is bd       # two ways, each kept
    holmes = bd.groups[0]
    # "Holmes and Watson walked" names him inside: counted once, through his own mention; They, them, We, they through the pair
    assert len(holmes.mentions) == 5 and holmes.by_prop["PRON"] == 4
    assert holmes.forms["PRON"] == {"They": 1, "them": 1, "We": 1, "they": 1}
    assert holmes.rel["agent"] == {"walk": 1, "talk": 1, "go": 1, "say": 1}
    assert bd.groups[1].rel["patient"] == {"meet": 1}
    assert bd.groups[2].rel["agent"] == {"walk": 1, "talk": 1, "go": 1, "say": 1}   # the pair keeps its own
    assert {0, 1, 2} <= bd.sent_members[1]
    assert bd.stands_for(2) == (2, 0, 1)
    assert [bd.mentions[i][1] for i in holmes.mentions] == sorted(bd.mentions[i][1] for i in holmes.mentions)


def test_the_plural_copy_shares_the_tokens_but_not_the_groups(plib):
    """Counting plural groups' mentions for their members changes only the groups: the copy must not duplicate the whole book in
    memory, and crediting its groups must leave the book's own untouched."""
    own, copy = plib.book("pair"), plib.book("pair", plural=True)
    for column in ("word", "lemma", "pos", "dep", "head", "para", "sent", "onset", "mentions", "quotes", "children"):
        assert getattr(copy, column) is getattr(own, column), column
    assert copy.groups is not own.groups and copy.groups[0] is not own.groups[0]
    assert len(own.groups[0].mentions) == 1 and len(copy.groups[0].mentions) == 5
    assert own.credit == {} and copy.credit and not own.plural and copy.plural


def test_without_declarations_both_ways_agree(plain):
    assert plain.book("pair", plural=True).groups[0].rel["agent"] == {"walk": 1}


def test_changing_a_declaration_recounts_without_reading_the_files_again(plib, monkeypatch):
    before = plib.book("pair", plural=True)
    import alex.core.library as L
    monkeypatch.setattr(L, "BookData", None)                                          # reading the files again would fail
    plurals.set_members(plib, "e:pair:2", ["e:pair:0"])
    after = plib.book("pair", plural=True)
    assert after is not before and len(after.groups[1].mentions) == 1 and len(after.groups[0].mentions) == 5


# ---------- views ----------
def test_the_setting_and_its_override_choose_the_variant(plib):
    assert View(plib, ["pair"]).plural is False
    own, incl = View(plib, ["pair"]), View(plib, ["pair"], plural=True)
    assert own.units[ids(own)["Holmes"]].mentions == 1 and incl.units[ids(incl)["Holmes"]].mentions == 5
    plib.state["settings"]["plural"] = True
    assert View(plib, ["pair"]).plural is True and View(plib, ["pair"], plural=False).plural is False


def test_appearing_together(plib):
    own, incl = View(plib, ["pair"]), View(plib, ["pair"], plural=True)
    co = lambda v, name: {r["name"]: r["n"] for r in v.cooccurring(ids(v)[name])}
    assert co(own, "Holmes") == {"Watson": 1}                   # named together once
    assert co(incl, "Holmes") == {"Watson": 4, "Lestrade": 1}   # and through They, them, We / they
    assert co(incl, "Holmes and Watson") == {"Lestrade": 1}      # never with its own members
    G = network.build(incl, "sentence", ["PER"])
    i = ids(incl)
    assert G.has_edge(i["Holmes"], i["Lestrade"]) and not G.has_edge(i["Holmes and Watson"], i["Holmes"])


def test_speech_and_addressees(plib):
    own, incl = View(plib, ["pair"]), View(plib, ["pair"], plural=True)
    said = lambda v, name: len(dialogue.recs_for(v, {"kind": "unit", "id": ids(v)[name]})[0])
    assert (said(own, "Holmes"), said(incl, "Holmes"), said(incl, "Holmes and Watson")) == (0, 1, 1)
    # Lestrade replies to the pair: addressed to the pair, and with plural groups on to its members too
    q = dialogue.quotes(incl, {"speaker": {"kind": "unit", "id": ids(incl)["Lestrade"]}})["items"][0]
    assert {a["name"] for a in q["addressees"]} == {"Holmes and Watson", "Holmes", "Watson"}
    assert {a["name"] for a in dialogue.quotes(own, {"speaker": {"kind": "unit", "id": ids(own)["Lestrade"]}})["items"][0]["addressees"]} == {"Holmes and Watson"}
    holmes = dialogue.entity(incl, ids(incl)["Holmes"])
    assert [x["name"] for x in holmes["talks_to"]] == ["Lestrade"] and [x["name"] for x in holmes["addressed_by"]] == ["Lestrade"]
    assert {r["name"]: r["quotes"] for r in dialogue.overview(incl)["speakers"]} == {"Holmes and Watson": 1, "Holmes": 1, "Watson": 1, "Lestrade": 1}


def test_profiles_link_plural_groups_and_members(plib):
    view = View(plib, ["pair"])
    i = ids(view)
    assert view.profile(i["Holmes and Watson"])["plural"] == {
        "members": [{"id": i["Holmes"], "name": "Holmes", "type": "PER"}, {"id": i["Watson"], "name": "Watson", "type": "PER"}], "member_of": [],
        "hidden": 0}
    assert view.profile(i["Watson"])["plural"]["member_of"] == [{"id": i["Holmes and Watson"], "name": "Holmes and Watson", "type": "PER"}]
    assert view.profile(i["Holmes and Watson"])["plural"]["hidden"] == 0
    plib.state["settings"]["min"]["PER"] = 2                             # Holmes and Watson have one mention each
    view = View(plib, ["pair"])
    assert view.profile(ids(view)["Holmes and Watson"])["plural"] == {"members": [], "member_of": [], "hidden": 2}


# ---------- the web API ----------
def test_requests_override_the_default_which_you_can_change(plib):
    from fastapi.testclient import TestClient
    from fixture import LOCAL

    from alex import app as app_module
    client = TestClient(app_module.build_app(plib), base_url=LOCAL)
    mentions = lambda **kw: {r["name"]: r["mentions"] for r in client.post("/api/units", json={"books": ["pair"], **kw}).json()["rows"]}["Holmes"]
    assert (mentions(), mentions(plural=True), mentions(plural=False)) == (1, 5, 1)
    assert client.post("/api/settings", json={"plural_default": True, "plural": False}).json()["settings"]["plural"] is True
    assert (mentions(), mentions(plural=False)) == (5, 1)


def test_the_api_adds_removes_and_replaces_members(plib):
    from fastapi.testclient import TestClient
    from fixture import LOCAL

    from alex import app as app_module
    client = TestClient(app_module.build_app(plib), base_url=LOCAL)
    post = lambda **body: client.post("/api/plurals", json={"id": "e:pair:2", **body})
    assert post(remove=["e:pair:1"]).json()["members"] == ["e:pair:0"]
    assert post(add=["e:pair:1"]).json()["members"] == ["e:pair:0", "e:pair:1"]
    assert post(add=["e:pair:2"]).status_code == 400                     # itself
    assert post(members=[]).json()["members"] == [] and plib.state["plurals"] == {}
