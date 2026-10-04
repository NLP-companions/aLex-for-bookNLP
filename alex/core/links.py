"""Suggest entities in different books that may be the same person, place, etc."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from .bookdata import ekey, parse_ekey

TITLES = {"mr", "mrs", "ms", "miss", "dr", "doctor", "sir", "lady", "lord", "father", "mother", "brother", "sister",
          "inspector", "captain", "colonel", "major", "general", "professor", "prof", "rev", "reverend", "st", "saint",
          "monsieur", "madame", "mademoiselle", "herr", "frau", "signor", "don", "dona", "king", "queen", "prince",
          "princess", "count", "countess", "duke", "duchess", "baron", "baroness", "the", "a", "an", "old", "young", "little"}
MIN_MENTIONS = 2


def norm_tokens(text):
    """A name as comparable words: lowercase, possessive 's dropped, titles (Mr, Dr, the…) set aside unless nothing else is left."""
    text = re.sub(r"[’']s\b", "", text.lower())
    toks = re.findall(r"[a-zà-ÿ0-9]+", text)
    core = [t for t in toks if t not in TITLES]
    return core or toks


def _units(lib, min_mentions=MIN_MENTIONS):
    """Every entity and linked group across the whole library, with name info and the series (book detail) of its books.
    Going through every group of every book takes a moment with many books, so the result is kept on the library until
    something changes (your settings and links, or a book's files); callers must not modify it."""
    found, _ = lib.scan()
    stamp = (lib.version, min_mentions, tuple((bid, lib.book_key(bid)) for bid in sorted(found)))
    kept = lib.link_units.get(min_mentions)
    if kept and kept[0] == stamp:
        return kept[1]
    units = _collect_units(lib, found, min_mentions)
    lib.link_units[min_mentions] = (stamp, units)
    return units


def _collect_units(lib, found, min_mentions):
    """The work of `_units`: one dict per entity or linked person (names, type, pronouns, mentions, members) with its comparison keys."""
    person_of = lib.person_of()
    series_of = {bid: lib.meta(bid)["series"].strip().lower() for bid in found}
    units = {}
    for bid in found:
        try:
            bd = lib.book(bid)
        except Exception:  # noqa: BLE001
            continue
        for c, g in bd.groups.items():
            if len(g.mentions) < min_mentions:
                continue
            pid = person_of.get((bid, c))
            uid = f"p:{pid}" if pid else ekey(bid, c)
            u = units.setdefault(uid, {"id": uid, "books": set(), "series": set(), "names": Counter(), "type": Counter(),
                                       "pron": Counter(), "mentions": 0, "members": [], "proper": 0})
            u["books"].add(bid)
            if series_of[bid]:
                u["series"].add(series_of[bid])
            u["names"].update(g.forms["PROP"])
            u["proper"] += g.by_prop.get("PROP", 0)
            if not g.forms["PROP"]:
                u["names"][g.name] += 1
            u["type"][g.type] += len(g.mentions)
            if g.pronouns:
                u["pron"][g.pronouns] += 1
            u["mentions"] += len(g.mentions)
            u["members"].append({"book": bid, "title": lib.meta(bid)["title"], "name": g.name, "mentions": len(g.mentions)})
    for u in units.values():
        u["type"] = u["type"].most_common(1)[0][0]
        u["name"] = lib.state["persons"][u["id"][2:]].get("name") if u["id"].startswith("p:") else None
        u["name"] = u["name"] or u["members"][0]["name"]
        u["keys"] = {" ".join(norm_tokens(n)) for n, _ in u["names"].most_common(6)} - {""}
        u["last"] = {k.split()[-1] for k in u["keys"] if k}
        u["pron1"] = u["pron"].most_common(1)[0][0] if u["pron"] else None
    return units


def suggest(lib, limit=300):
    """Pairs of entities in different books that may be the same person or place -> (top pairs, total).
    Candidates share a name word or a spelling prefix; each pair is scored from how their names compare (same full name, same
    single name, same last name, similar spelling, a shared word) and, for people, whether BookNLP's pronouns agree.
    Pairs within one book, of different types, already linked or rejected are never suggested, and neither are pairs whose books
    share no series: names recur between unrelated books, so a match is only plausible inside a series (set under Library).
    Books without a series therefore get no suggestions (you can still link them by hand)."""
    units = {k: u for k, u in _units(lib).items() if u["proper"]}  # named entities only
    index = defaultdict(set)
    for uid, u in units.items():
        for k in u["keys"]:
            for t in k.split():
                if len(t) > 2:
                    index[("tok", t)].add(uid)
                    index[("pre", t[:3])].add(uid)
    rejected = lib.rejected_set()
    pairs = set()
    for ids in index.values():
        if len(ids) > 400:
            continue
        ids = sorted(ids)
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                pairs.add((a, b))
    out = []
    for a, b in pairs:
        ua, ub = units[a], units[b]
        if ua["type"] != ub["type"] or ua["books"] & ub["books"] or not ua["series"] & ub["series"]:
            continue
        if lib.is_rejected(a, b, rejected):
            continue
        reasons, score = [], 0.0
        same = ua["keys"] & ub["keys"]
        if same:
            k = max(same, key=len)
            score = 1.0 if len(k.split()) > 1 else 0.85
            reasons.append(f"Same name once titles are set aside: “{k}”")
        else:
            shared_last = ua["last"] & ub["last"]
            if shared_last and ua["type"] == "PER":
                score = 0.6
                reasons.append(f"Same last name: “{sorted(shared_last)[0]}”")
            else:
                best = max((SequenceMatcher(None, x, y).ratio(), x, y) for x in ua["keys"] for y in ub["keys"])
                if best[0] >= 0.85:
                    score = 0.7 * best[0]
                    reasons.append(f"Similar spelling: “{best[1]}” and “{best[2]}”")
                else:
                    shared = {t for k in ua["keys"] for t in k.split()} & {t for k in ub["keys"] for t in k.split()}
                    shared = {t for t in shared if len(t) > 3}
                    if shared:
                        score = 0.35
                        reasons.append(f"Share the word “{sorted(shared)[0]}”")
        if score == 0:
            continue
        if ua["type"] == "PER" and ua["pron1"] and ub["pron1"]:
            if ua["pron1"] == ub["pron1"]:
                reasons.append(f"Same pronouns ({ua['pron1']})")
                score += 0.05
            else:
                reasons.append(f"Different pronouns ({ua['pron1']} / {ub['pron1']})")
                score -= 0.4
        if score <= 0.2:
            continue
        side = lambda u: {"id": u["id"], "name": u["name"], "type": u["type"], "mentions": u["mentions"],
                          "linked": u["id"].startswith("p:"), "members": u["members"],
                          "forms": [n for n, _ in u["names"].most_common(5)]}
        out.append({"a": side(ua), "b": side(ub), "score": round(min(score, 1), 2), "reasons": reasons})
    out.sort(key=lambda s: (-s["score"], -(s["a"]["mentions"] + s["b"]["mentions"])))
    return out[:limit], len(out)


def auto_link(lib):
    """Automatically link entities that share an exact name (once titles are set aside), the same type and, for people,
    the same BookNLP pronouns. Unlike `suggest`, this works across the whole library, not only within a series: an exact
    three-way match is strong enough evidence on its own. The pronoun match is the safeguard against merging two
    different "John"s — an entity with no pronoun evidence (so most places and things) is never auto-linked, and a pair
    you've rejected never is either, however well they otherwise match.
    -> [{"id", "name", "type", "books": how many entities were merged into it}], newest first."""
    units = {k: u for k, u in _units(lib).items() if u["proper"]}
    rejected = lib.rejected_set()
    groups = defaultdict(list)
    for uid, u in units.items():
        key = " ".join(norm_tokens(u["name"]))
        if key and u["pron1"]:
            groups[(key, u["type"], u["pron1"])].append(uid)
    linked = []
    for ids in groups.values():
        if len(ids) < 2:
            continue
        pid, n, name = ids[0], 1, units[ids[0]]["name"]
        for uid in ids[1:]:
            if lib.is_rejected(pid, uid, rejected):
                continue
            pid = lib.link(pid, uid)
            n += 1
        if n > 1:
            linked.append({"id": pid, "name": name, "type": units[ids[0]]["type"], "books": n})
    return linked


def search(lib, q, limit=40):
    """Find units by name anywhere in the library, for linking by hand, most mentioned first. A blank `q` lists the most mentioned of all."""
    units = _units(lib, 1)
    q = q.lower().strip()
    hits = [u for u in units.values() if q in u["name"].lower() or any(q in n.lower() for n in u["names"])]
    hits.sort(key=lambda u: -u["mentions"])
    return [{"id": u["id"], "name": u["name"], "type": u["type"], "mentions": u["mentions"],
             "members": u["members"], "linked": u["id"].startswith("p:")} for u in hits[:limit]]


def persons(lib):
    """The persons you have linked, with each member's name and mention count (members no longer in their book are flagged)
    and the person's type (its members' most-mentioned category, for the type indicator on its card)."""
    out = []
    for pid, p in list(lib.state["persons"].items()):     # a snapshot: a concurrent request must not mutate this while we iterate
        mem = []
        types = Counter()
        for bid, c in p["members"]:
            try:
                g = lib.book(bid).groups.get(int(c))
            except Exception:  # noqa: BLE001
                g = None
            mem.append({"book": bid, "title": lib.meta(bid)["title"], "coref": int(c),
                        "name": g.name if g else "(no longer in this book)",
                        "mentions": len(g.mentions) if g else 0, "missing": g is None})
            if g:
                types[g.type] += len(g.mentions) or 1
        names = [m for m in mem if not m["missing"] and m["name"].lower() not in ("i", "me", "my", "myself", "mine")] or [m for m in mem if not m["missing"]]
        out.append({"id": "p:" + pid, "name": p.get("name") or (max(names, key=lambda m: m["mentions"])["name"] if names else "?"),
                    "custom_name": bool(p.get("name")), "type": types.most_common(1)[0][0] if types else "PER",
                    "tags": p.get("tags", []), "members": mem})
    out.sort(key=lambda p: p["name"].lower())
    return out


def _unit_name(lib, uid):
    """A unit's own display name (your name for it, else its most-mentioned member's own name), the same way `persons`
    resolves one, but usable for a single id without a View: `uid` is `e:<book>:<coref>` or `p:<n>`."""
    if uid.startswith("p:"):
        p = lib.state["persons"].get(uid[2:])
        if not p:
            return uid
        if p.get("name"):
            return p["name"]
        best = None
        for bid, c in p["members"]:
            try:
                g = lib.book(bid).groups.get(int(c))
            except Exception:  # noqa: BLE001
                g = None
            if g and (best is None or len(g.mentions) > best[1]):
                best = (g.name, len(g.mentions))
        return best[0] if best else uid
    custom = lib.name_of(uid)
    if custom:
        return custom
    key = parse_ekey(uid)
    try:
        g = lib.book(key[0]).groups.get(key[1]) if key else None
    except Exception:  # noqa: BLE001
        g = None
    return g.name if g else "(no longer in this book)"


def narrator_links(lib):
    """The narrator roles you have linked (`nl:<n>`, see `Library.link_narrators`), for the Links page: each member
    with its own name and the book(s) it covers (an anonymous role's one book, or a named character's — its linked
    books too, if it's also a linked person), and the link's own name if you gave it one, else its first named
    member's, else "N narrators, linked"."""
    out = []
    for lid, link in list(lib.state["narrator_links"].items()):    # a snapshot: a concurrent request must not mutate this while we iterate
        mem = []
        for rid in link["members"]:
            if rid.startswith("nar:anon:"):
                bid = rid[len("nar:anon:"):]
                mem.append({"id": rid, "name": f"Narrator of {lib.meta(bid)['title']}", "unit": None, "books": [bid]})
            else:
                uid = rid[len("nar:"):]
                books = [b for b, c in lib.state["persons"][uid[2:]]["members"]] if uid.startswith("p:") else [(parse_ekey(uid) or (uid,))[0]]
                mem.append({"id": rid, "name": f"{_unit_name(lib, uid)}, narrating", "unit": uid, "books": books})
        named = [m for m in mem if m["unit"]]
        out.append({"id": "nl:" + lid, "name": link.get("name") or (named[0]["name"].replace(", narrating", "") if named else f"{len(mem)} narrators, linked"),
                    "custom_name": bool(link.get("name")), "members": mem})
    out.sort(key=lambda p: p["name"].lower())
    return out
