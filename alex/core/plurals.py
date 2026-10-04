"""Plural groups: an entity whose mentions stand for several entities together ("Holmes and Watson", and the "they" and "we"
BookNLP linked to it).

BookNLP gives every mention one coreference group, so "they" belongs to the pair's group only. Declaring the pair a plural
group of Holmes and Watson lets the analyser count its mentions, relations, quotes and addressees for them too, when you ask
for that (the "include plural-group mentions" setting; see bookdata.py for how, and view.py for where the setting is read).

Declarations live in `library.json` under `plurals`: {plural unit id: [member unit ids]}; unit ids are `e:<book>:<coref>`
(one book's group) or `p:<n>` (entities you linked across books), so a declaration on a linked entity applies in every book
where it and its members have a group. Suggestions you dismissed are in `plural_rejected`. `book_map` turns the declarations
into what one book needs. The functions take the `Library`, change its state under its lock and save it; `ValueError` means
a declaration that can't be made. A page shows only the members counted in the selected books, so it changes a declaration
with `change_members` (add or remove some), which keeps the members it doesn't show.
"""
from __future__ import annotations

import re
from collections import Counter

from .bookdata import parse_ekey

SPLIT = re.compile(r"\s*,\s*(?:and\s+)?|\s+and\s+|\s*&\s*", re.I)
TITLES = {"mr", "mrs", "miss", "ms", "dr", "sir", "lady", "lord", "the", "inspector", "captain", "colonel", "professor", "mister",
          "madam", "master", "young", "old", "dear", "poor", "little"}


def groups_of(lib, uid):
    """The (book, coref) groups a unit id stands for: one for `e:<book>:<coref>`, a linked entity's members for `p:<n>`."""
    if uid.startswith("p:"):
        p = lib.state["persons"].get(uid[2:])
        return [(b, int(c)) for b, c in p["members"]] if p else []
    key = parse_ekey(uid)
    return [key] if key else []


def book_map(lib, bid):
    """{plural group coref: [member corefs]} for one book, from every declaration with a group in it."""
    out = {}
    for uid, members in lib.state["plurals"].items():
        ms = [c for m in members for b, c in groups_of(lib, m) if b == bid]
        for b, c in groups_of(lib, uid):
            if b == bid:
                for m in ms:
                    if m != c and m not in out.setdefault(c, []):
                        out[c].append(m)
    return {c: ms for c, ms in out.items() if ms}


def _folded(lib, uid):
    """The declarations that belong to a unit: its own, and those made on its groups before you linked them into it."""
    mine = set(groups_of(lib, uid))
    return [k for k in lib.state["plurals"] if k == uid or mine and set(groups_of(lib, k)) <= mine]


def members_of(lib, uid):
    """The member unit ids declared for a unit, including those declared on its groups before a link (empty if it isn't a
    plural group)."""
    out = []
    for k in _folded(lib, uid):
        out += [m for m in lib.state["plurals"][k] if m not in out]
    return out


def change_members(lib, uid, add=(), remove=()):
    """Add members to a unit's declaration and remove others, keeping every member not named (in other books, or below the
    minimum, where a page doesn't show them). A removed unit takes with it every declared member that shares a group with
    it (a member declared on a group you have since linked into it); members no longer in any book are dropped."""
    remove = {str(r) for r in remove}
    with lib.lock:
        gone = {g for r in remove for g in groups_of(lib, r)}
        keep = [m for m in members_of(lib, uid)
                if m not in remove and groups_of(lib, m) and not set(groups_of(lib, m)) & gone]
        return set_members(lib, uid, [*keep, *(str(a) for a in add)])


def set_members(lib, uid, members):
    """Declare a unit a plural group of `members` (unit ids), replacing what was declared; no members makes it an ordinary
    entity again. A plural group can't be its own member, a member can't be a plural group itself, and a plural group can't
    be a member of another one. Declarations made on one of its groups before you linked it are folded into this one."""
    members = list(dict.fromkeys(str(m) for m in members or []))
    mine = set(groups_of(lib, uid))
    if not mine:
        raise ValueError("That entity isn't in any book.")
    with lib.lock:
        plurals = lib.state["plurals"]
        folded = _folded(lib, uid)       # this one, and declarations made on its groups before a link: replaced by this one
        if members:
            # checked by group, so a linked entity and the groups it was made of count as the same
            others = {k: ms for k, ms in plurals.items() if k not in folded}
            plural_groups = {g for k in others for g in groups_of(lib, k)}
            member_groups = {g for ms in others.values() for m in ms for g in groups_of(lib, m)}
            if uid in members or any(set(groups_of(lib, m)) & mine for m in members):
                raise ValueError("A plural group can't be a member of itself.")
            for m in members:
                gs = set(groups_of(lib, m))
                if not gs:
                    raise ValueError(f"{m} isn't in any book.")
                if gs & plural_groups:
                    raise ValueError("A plural group can't be a member of another one; add its members instead.")
            if mine & member_groups:
                raise ValueError("This entity is a member of a plural group, so it can't be one itself.")
            books = {b for b, c in mine}
            if not any(b in books for m in members for b, c in groups_of(lib, m)):
                raise ValueError("None of these entities appears in the same book as the plural group.")
        for k in folded:
            del plurals[k]
        if not members:
            lib.save()
            return []
        plurals[uid] = members
        if uid in lib.state["plural_rejected"]:
            lib.state["plural_rejected"].remove(uid)
        lib.save()
        return members


def reject(lib, uid):
    """Remember that a suggested plural group isn't one, so it isn't suggested again."""
    with lib.lock:
        if uid not in lib.state["plural_rejected"]:
            lib.state["plural_rejected"].append(uid)
            lib.save()


def name_key(name):
    """A name without titles, lower case, for matching the parts of a plural name ("Mr. Holmes" → "holmes")."""
    words = re.findall(r"[\w'’-]+", name.lower())
    while words and words[0].rstrip(".") in TITLES:
        words.pop(0)
    return " ".join(words) or name.lower().strip()


def split_name(name):
    """The names in a plural name ("Holmes and Watson", "Holmes, Watson, and the Inspector"), or [] if it isn't one."""
    parts = [p.strip() for p in SPLIT.split(name.strip()) if p and p.strip()]
    return parts if len(parts) >= 2 else []


def suggestions(view):
    """People named after two or more other people ("Holmes and Watson"), with the members found -> [{id, name, mentions,
    text, members: [{id, name}], unmatched}]. A part is a member when it is (without titles) a name another person of the
    selection goes by, the most mentioned one if several do; at least two parts, and half of them, must be members.
    Plural groups, their members and suggestions you dismissed are left out."""
    lib = view.lib
    plurals, rejected = lib.state["plurals"], set(lib.state["plural_rejected"])
    # by group, so an entity linked since a declaration is left out too
    declared = {g for k, ms in plurals.items() for u in (k, *ms) for g in groups_of(lib, u)}
    people = [u for u in view.units.values() if u.type == "PER"]
    owner = {}
    for u in people:
        names = Counter()
        for b, c in u.members:
            names.update(view.bd[b].groups[c].forms["PROP"])
        for n in set(names) | {u.name}:
            k = name_key(n)
            if k not in owner or u.mentions > owner[k].mentions:
                owner[k] = u
    out = []
    for u in people:
        if u.id in rejected or declared & {(b, int(c)) for b, c in u.members}:
            continue
        texts = Counter()
        for b, c in u.members:
            g = view.bd[b].groups[c]
            texts.update(g.forms["PROP"])
            texts.update(g.forms["NOM"])
        for text in dict.fromkeys([u.name, *(t for t, _ in texts.most_common())]):
            parts = split_name(text)
            found = {p: owner.get(name_key(p)) for p in parts}
            ms = list(dict.fromkeys(m for m in found.values() if m is not None and m.id != u.id))
            if len(ms) >= 2 and 2 * len(ms) >= len(parts):
                out.append({"id": u.id, "name": u.name, "mentions": u.mentions, "text": text,
                            "members": [{"id": m.id, "name": m.name} for m in ms],
                            "unmatched": [p for p, m in found.items() if m is None or m.id == u.id]})
                break
    out.sort(key=lambda x: -x["mentions"])
    return out
