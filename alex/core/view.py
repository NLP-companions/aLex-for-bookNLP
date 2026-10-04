"""Everything computed for a selection of books.

A `View` combines the chosen books: it decides which entities ("units") pass your minimum
number of mentions, merges the ones you have linked across books, and answers questions about
them: profiles, distinctive words, comparisons between groups, book-by-book tables and the
sentences behind any count.

Units and specs
---------------
* A **unit** is one entity of the selection: a single book's coreference group (`e:<book>:<coref>`)
  or a person you linked across books (`p:<n>`). `View.units` maps unit id -> `Unit`.
* A **member** is `(book, coref)`: one book's coreference group. A unit has one or more members.
* A **spec** describes a set of units for comparisons:
  `{"kind": "unit", "id": …}`, `{"kind": "tag", "tag": …, "type": …}`, `{"kind": "type", "type": …}`,
  `{"kind": "group", "ids": […]}` or `{"kind": "group", "group": <saved group id>}` (entities you picked, see below),
  `{"kind": "others", "types": […]}` (everyone else), `{"kind": "book", "book": …}` (everyone counted in one book) or
  `{"kind": "gender", "pron": …}` (every PER entity of one BookNLP-predicted gender, `UNKNOWN_GENDER` for none predicted);
  an optional `"books"` limits it to some books. `resolve(spec)` turns a spec into a set of members.
* A **group** is several units analysed as one. `group_unit` builds a virtual `Unit` for it (its members are those of all the
  units, `parts` lists them), so profiles, speech and topics work on a group exactly as on one entity. Groups you save live in
  `entitygroups.py`; `target_unit` turns a request's `id` / `ids` / `group` into the unit it asks about. `book_profile` and
  `gender_profile` pool a book's or a gender's own units the same way, via `_pooled_profile`, for their own pages.

Statistics live in `stats.py`; this module chooses what to count and compare.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from . import entitygroups, stats
from .bookdata import RELATIONS, TYPES, ekey, parse_ekey

REL_LABELS = {"agent": "Actions", "patient": "Done to them", "poss": "Possessions",
              "mod": "Modifiers", "prep": "Prepositions and settings"}
PROPS = ("PROP", "NOM", "PRON")        # names, descriptions, pronouns
UNKNOWN_GENDER = "unknown"             # the gender bucket for a PER entity with no clear BookNLP pronoun prediction


def gender_label(pron):
    """A gender bucket's display label: its pronouns as BookNLP wrote them, or a note for the unpredicted bucket."""
    return "No BookNLP gender prediction" if pron == UNKNOWN_GENDER else pron or "?"


def _pct(n, total):
    """n as a percentage of total (0 if total is 0)."""
    return 100 * n / total if total else 0


class Unit:
    """One entity of the selection (see the module docstring), or a virtual one standing for a group of them.
    `parts` are the ids of the real units it consists of (just its own id for a real unit); `mixed` is set for a group of several types."""
    __slots__ = ("id", "type", "name", "tags", "members", "mentions", "books", "linked", "all_members", "parts", "mixed")

    def as_row(self, view):
        """The unit as a row of the entity list. `share` (of all mentions of its type) is None for a group of several types."""
        total = view.type_totals[self.type]
        return {"id": self.id, "type": self.type, "name": self.name, "tags": self.tags,
                "mentions": self.mentions, "books": [b for b in view.books if b in self.books], "linked": self.linked,
                "custom_name": bool(view.lib.name_of(self.id)), "note": view.lib.note_of(self.id),
                "share": None if self.mixed else _pct(self.mentions, total)}


class View:
    """The books selected, combined: `bd` (book id -> BookData), `units` (entities passing your minimum, with links applied) and
    `member_unit` (which unit each counted (book, coref) belongs to). Everything else is a method computing something from these.
    `plural` says whether plural groups' mentions and quotes also count for their members (the books are read that way, see
    bookdata.py); None takes your setting."""
    def __init__(self, lib, books, plural=None):
        self.lib = lib
        self.cache = {}              # results other modules keep for this view (dialogue.bdlg…), named by owner
        self.plural = bool(lib.state["settings"].get("plural", False) if plural is None else plural)
        self.bd = {}                 # book id -> BookData, for the books that could be read
        self.problems = []
        for b in books:
            try:
                self.bd[b] = lib.book(b, self.plural)
            except Exception as e:  # noqa: BLE001 - one unreadable book must not stop the rest
                self.problems.append(f"{b}: {e}")
        # wherever several books are shown together (book by book, stylometry, arcs…) they go by publication year,
        # ascending; books without one sort last, by title, so a selection's display order doesn't depend on how it was made
        self.books = sorted(self.bd, key=lambda b: (lib.meta(b)["year"] in ("", None), lib.meta(b)["year"] or 0, lib.meta(b)["title"].lower()))
        self.narrator_link_of = lib.narrator_link_of()   # narrator role id -> nl:<n>, for dialogue.narrator_of; built
                                                          # once per view rather than per paragraph
        settings = lib.state["settings"]
        person_of = self.person_of = lib.person_of()
        raw = defaultdict(list)      # unit id -> [(book, coref, mentions, type)] before applying the minimum
        for b, bd in self.bd.items():
            for c, g in bd.groups.items():
                pid = person_of.get((b, c))
                raw[f"p:{pid}" if pid else ekey(b, c)].append((b, c, len(g.mentions), g.type))
        self.units: dict[str, Unit] = {}
        self.member_unit = {}        # (book, coref) -> unit id, for members that are counted
        for uid, mem in raw.items():
            unit = self._make_unit(uid, mem, settings)
            if unit:
                self.units[uid] = unit
                for m in unit.members:
                    self.member_unit[m] = uid
        self.type_totals = Counter()             # mentions per type over all units
        self.type_totals_book = Counter()        # (book, type) -> mentions
        for u in self.units.values():
            self.type_totals[u.type] += u.mentions
            for b, c in u.members:
                self.type_totals_book[(b, u.type)] += len(self.bd[b].groups[c].mentions)

    def _make_unit(self, uid, mem, settings):
        """Apply the minimum-mentions setting to one unit's members; None if nothing is left."""
        by_type = Counter()
        for b, c, n, t in mem:
            by_type[t] += n
        typ = by_type.most_common(1)[0][0]
        need = int(settings["min"].get(typ, 2))
        if settings["count_mode"] == "combined":
            keep = mem if sum(m[2] for m in mem) >= need else []
        else:
            keep = [m for m in mem if m[2] >= need]
        if not keep:
            return None
        u = Unit()
        u.id, u.type, u.linked = uid, typ, uid.startswith("p:")
        u.parts, u.mixed = (uid,), False
        u.all_members = mem
        u.members = [(b, c) for b, c, n, t in keep]
        u.mentions = sum(m[2] for m in keep)
        u.books = {b for b, c in u.members}
        group = lambda m: self.bd[m[0]].groups[m[1]]
        if u.linked:
            # your name for the person, else the most frequent name among its members (names before descriptions)
            named = [m for m in keep if group(m).forms["PROP"]] or [m for m in keep if group(m).forms["NOM"]] or keep
            u.name = self.lib.name_of(uid) or group(max(named, key=lambda m: m[2])).name
        else:
            u.name = self.lib.name_of(uid) or group(keep[0]).name
        u.tags = self.lib.tags_of(uid)
        return u

    # ---------- lists ----------
    def unit_rows(self, typ=None):
        """Rows for the entity list, most mentioned first, optionally of one type."""
        rows = [u.as_row(self) for u in self.units.values() if typ in (None, "ALL", u.type)]
        rows.sort(key=lambda r: -r["mentions"])
        return rows

    def type_counts(self):
        """Number of units of each type."""
        c = Counter(u.type for u in self.units.values())
        return {t: c.get(t, 0) for t in TYPES}

    def title(self, b):
        """A book's title."""
        return self.lib.meta(b)["title"]

    def name_of(self, uid):
        """A unit's name; for entities below the minimum, their name with a note; otherwise the id itself."""
        if uid in self.units:
            return self.units[uid].name
        key = parse_ekey(uid)
        if key and key[0] in self.bd and key[1] in self.bd[key[0]].groups:
            return self.bd[key[0]].groups[key[1]].name + " (below minimum)"
        return uid

    # ---------- groups of units ----------
    def _current_id(self, uid):
        """The unit an id stands for now: itself, or (for a single entity you have since linked) the person it became; else itself unchanged."""
        key = parse_ekey(uid)
        if uid in self.units or key is None:
            return uid
        pid = self.person_of.get(key)
        return f"p:{pid}" if pid else uid

    def group_of(self, spec):
        """The entities of a group spec (`ids`, or `group` = a saved group; optional `name`) -> (units in this selection, ids that aren't, name).
        Ids of entities you linked since are followed to their person; the rest (below the minimum, in unselected books) are the second list."""
        ids, name = list(spec.get("ids") or []), spec.get("name")
        if spec.get("group"):
            try:
                saved_name, ids = entitygroups.get(self.lib, spec["group"])
            except KeyError:
                return [], [], name or "(this group no longer exists)"
            name = name or saved_name
        units, missing = {}, []
        for i in ids:
            cur = self._current_id(str(i))
            if cur in self.units:
                units[cur] = self.units[cur]
            else:
                missing.append(str(i))
        us = list(units.values())
        if not name:
            name = ", ".join(u.name for u in us) if 0 < len(us) <= 3 else f"{len(us)} entities"
        return us, missing, name

    def group_unit(self, units, name):
        """A virtual `Unit` standing for several units at once: their members, mentions and books together; its type is the
        one with most mentions, and `mixed` says there were several."""
        by_type = Counter()
        for u in units:
            by_type[u.type] += u.mentions
        g = Unit()
        g.id, g.name, g.type, g.mixed = "group", name, by_type.most_common(1)[0][0], len(by_type) > 1
        g.members = list(dict.fromkeys(m for u in units for m in u.members))
        g.all_members = list(dict.fromkeys(m for u in units for m in u.all_members))
        g.mentions = sum(u.mentions for u in units)
        g.books = {b for u in units for b in u.books}
        g.tags, g.linked = [], False
        g.parts = tuple(u.id for u in units)
        return g

    def target_unit(self, ref):
        """The unit a request asks about, from its `id` (one unit), or its `ids` / `group` (several, as a virtual unit), or None if it isn't in this selection."""
        if ref.get("ids") is not None or ref.get("group"):
            units, _, name = self.group_of(ref)
            return self.group_unit(units, name) if units else None
        return self.units.get(ref.get("id"))

    def _tagged(self, spec):
        """(units, label) of a `tag` spec: every unit with the tag, of the spec's type if it names one."""
        tag, typ = spec.get("tag"), spec.get("type")
        return ([u for u in self.units.values() if tag in u.tags and typ in (None, "", "ALL", u.type)],
                f"tag “{tag}”" + (f" ({typ})" if typ and typ != "ALL" else ""))

    def _of_gender(self, pron):
        """The PER units whose predominant BookNLP gender prediction is `pron` (`UNKNOWN_GENDER` for none)."""
        return [u for u in self.units.values() if u.type == "PER" and self._gender_of(u) == pron]

    def pool_unit(self, spec):
        """Like `target_unit`, but from any spec `resolve` accepts (unit/group/tag/gender), as a single virtual `Unit`
        pooling everyone it matches — for views (dialogue's In-Depth Who Speaks) that need a unit's-worth of figures
        (per-book breakdown, narrating) for a scope rather than just `resolve`'s flat set of members. None if it
        matches nobody. `books` on the spec is not applied here (the view is already scoped to your book selection)."""
        kind = spec.get("kind")
        if kind == "unit":
            return self.units.get(spec.get("id"))
        if kind == "group":
            units, _, name = self.group_of(spec)
            return self.group_unit(units, name) if units else None
        if kind == "tag":
            us, label = self._tagged(spec)
            return self.group_unit(us, label) if us else None
        if kind == "gender":
            us = self._of_gender(spec.get("pron"))
            return self.group_unit(us, gender_label(spec.get("pron"))) if us else None
        return None

    def resolve(self, spec, exclude=frozenset()):
        """spec -> (set of members, label, set of types). `exclude` members are left out."""
        mem, label, types = self._resolve(spec, exclude)
        books = spec.get("books")
        if books:
            books = set(books)
            mem = {m for m in mem if m[0] in books}
            label = f"{label} in {self.books_label(books)}"
        return mem, label, types

    def books_label(self, books):
        """'Title', 'A + B + C' or '5 books', in the selection's order."""
        titles = [self.title(b) for b in self.books if b in books]
        return titles[0] if len(titles) == 1 else f"{len(titles)} books" if len(titles) > 3 else " + ".join(titles)

    def _resolve(self, spec, exclude=frozenset()):
        """See `resolve`; this does the work before the optional book filter."""
        kind = spec.get("kind")
        if kind == "unit":
            u = self.units.get(spec.get("id"))
            if not u:
                return set(), "(not in this selection)", set()
            return set(u.members) - exclude, u.name, {u.type}
        if kind == "group":
            us, _, name = self.group_of(spec)
            return {m for u in us for m in u.members} - exclude, name, {u.type for u in us}
        if kind == "tag":
            us, label = self._tagged(spec)
            return {m for u in us for m in u.members} - exclude, label, {u.type for u in us}
        if kind == "type":
            typ = spec.get("type")
            us = [u for u in self.units.values() if u.type == typ]
            return {m for u in us for m in u.members} - exclude, f"all {typ}", {typ}
        if kind == "others":
            types = spec.get("types") or TYPES
            us = [u for u in self.units.values() if u.type in types]
            return {m for u in us for m in u.members} - exclude, "everyone else of the same type" if len(types) == 1 else "all others", set(types)
        if kind == "book":
            b = spec.get("book")
            if b not in self.bd:
                return set(), "(not in this selection)", set()
            mem = {m for m in self.member_unit if m[0] == b} - exclude
            return mem, self.title(b), {self.bd[bb].groups[c].type for bb, c in mem}
        if kind == "gender":
            us = self._of_gender(spec.get("pron"))
            return {m for u in us for m in u.members} - exclude, gender_label(spec.get("pron")), {"PER"} if us else set()
        return set(), "?", set()

    def _gender_of(self, u):
        """The BookNLP pronoun prediction (`Group.pronouns`, e.g. "he/him/his") most common among a unit's members,
        weighted by their mentions, or `UNKNOWN_GENDER` with no prediction at all."""
        counts = Counter()
        for b, c in u.members:
            g = self.bd[b].groups[c]
            if g.pronouns:
                counts[g.pronouns] += len(g.mentions)
        return counts.most_common(1)[0][0] if counts else UNKNOWN_GENDER

    def genders(self):
        """Every gender bucket among this selection's PER entities (BookNLP's pronoun prediction, or `UNKNOWN_GENDER`
        with none), most entities first: {pron, entities, mentions}."""
        entities, mentions = Counter(), Counter()
        for u in self.units.values():
            if u.type != "PER":
                continue
            g = self._gender_of(u)
            entities[g] += 1
            mentions[g] += u.mentions
        return [{"pron": g, "entities": entities[g], "mentions": mentions[g]} for g in sorted(entities, key=lambda g: -mentions[g])]

    def rel_counts(self, members, rel):
        """Counter of words for one relation (agent, patient…) over the members' groups."""
        out = Counter()
        for b, c in members:
            out.update(self.bd[b].groups[c].rel.get(rel, {}))
        return out

    def words_in(self, members):
        """Words (not punctuation) in the books the members come from, each book once."""
        return sum(self.bd[b].n_words for b in {b for b, c in members})

    # ---------- profile ----------
    def profile(self, uid, top=60):
        """Everything shown on an entity's page, or None if the unit isn't in this selection."""
        u = self.units.get(uid)
        return self._profile(u, top) if u else None

    def group_profile(self, ref, top=60):
        """The same figures for several entities counted as one (`ref`: `ids` or a saved `group`), plus a `group` part: the
        entities it consists of with each one's mentions, share of the group and rate per 1,000 words, and the ids that
        aren't in this selection. None if none of them is."""
        units, missing, name = self.group_of(ref)
        p = self._pooled_profile(units, name, top)
        if p is not None:
            p["group"]["missing"] = missing
        return p

    def _pooled_profile(self, units, name, top):
        """The profile shape (`_profile`, plus a `group` breakdown: the entities pooled, each with its mentions, share of the pool and rate
        per 1,000 words) for a pool of real units: a hand-picked group (`group_profile`), every entity in a book, or every entity of a
        gender. None if the pool is empty."""
        if not units:
            return None
        p = self._profile(self.group_unit(units, name), top)
        total = p["unit"]["mentions"]
        p["group"] = {"types": dict(Counter(u.type for u in units)),
                      "units": [{**u.as_row(self), "pct": _pct(u.mentions, total), "per1k": 1000 * u.mentions / self.words_in(u.members) if u.members else 0}
                                for u in sorted(units, key=lambda u: -u.mentions)]}
        return p

    def _book_units(self, book_id):
        """Every counted unit's presence restricted to one book: a sub-`Unit` per unit with only its members there
        (so a person linked across books is judged, here, only by what they are in this one)."""
        us = []
        for u in self.units.values():
            mem = [m for m in u.members if m[0] == book_id]
            if not mem:
                continue
            sub = Unit()
            sub.id, sub.type, sub.linked, sub.parts, sub.mixed = u.id, u.type, u.linked, u.parts, False
            sub.members = mem
            sub.all_members = [(b, c, len(self.bd[b].groups[c].mentions), self.bd[b].groups[c].type) for b, c in mem]
            sub.mentions = sum(m[2] for m in sub.all_members)
            sub.books, sub.name, sub.tags = {book_id}, u.name, u.tags
            us.append(sub)
        return us

    def book_profile(self, book_id, top=60):
        """A book's own page: its own facts (title, author, words, quotes…) plus, pooling every entity counted in it
        as one group, the same profile shape as an entity's page (mentions, relations, dialogue style, topics) —
        "how does this book look". None if the book isn't in this selection or has nothing counted in it."""
        if book_id not in self.bd:
            return None
        p = self._pooled_profile(self._book_units(book_id), self.title(book_id), top)
        if p is None:
            return None
        bd, meta = self.bd[book_id], self.lib.meta(book_id)
        p["book"] = {"id": book_id, "title": meta["title"], "author": meta["author"], "year": meta["year"],
                     "series": meta["series"], "tags": meta["tags"], "words": bd.n_words, "quotes": len(bd.quotes)}
        return p

    def book_grid(self, book_a, book_b, top=25):
        """Comparing two books "split into characters": every PER entity in either, most mentions in either book
        first, with its mentions in each (0 if it isn't there) — for a character-by-book comparison."""
        ua = {u.id: u for u in self._book_units(book_a) if u.type == "PER"}
        ub = {u.id: u for u in self._book_units(book_b) if u.type == "PER"}
        rows = sorted(({"id": i, "name": (ua.get(i) or ub[i]).name, "a": ua[i].mentions if i in ua else 0, "b": ub[i].mentions if i in ub else 0}
                       for i in set(ua) | set(ub)), key=lambda r: -(r["a"] + r["b"]))
        return rows[:top]

    def gender_profile(self, pron, top=60):
        """A gender's own page: every PER entity whose predominant BookNLP pronoun prediction is `pron` (or
        `UNKNOWN_GENDER`), pooled as one group — "how do men, women… talk, act, appear" across the selection."""
        return self._pooled_profile(self._of_gender(pron), gender_label(pron), top)

    def _profile(self, u, top):
        """The profile of a `Unit`, real or virtual (a group); see `profile`."""
        mem = u.members
        words = self.words_in(mem)
        members = []      # where the unit comes from, including books below the minimum
        for b, c, n, t in sorted(u.all_members, key=lambda m: -m[2]):
            if b not in self.bd:
                continue
            members.append({"book": b, "title": self.title(b), "coref": c, "name": self.bd[b].groups[c].name, "mentions": n,
                            "type": t, "included": (b, c) in mem, "words": self.bd[b].n_words})
        pron = Counter()
        for b, c in mem:
            g = self.bd[b].groups[c]
            if g.pronouns:
                pron[g.pronouns] += len(g.mentions)
        # how the unit is referred to
        by_prop = Counter()
        forms = {k: Counter() for k in PROPS}
        for b, c in mem:
            g = self.bd[b].groups[c]
            by_prop.update(g.by_prop)
            for k in forms:
                for f, n in g.forms[k].items():
                    forms[k][f if k != "PRON" else f.lower()] += n
        return {
            "unit": u.as_row(self), "members": members, "words": words,
            "per1k": 1000 * u.mentions / words if words else 0,
            "pronouns": [{"item": k, "n": n} for k, n in pron.most_common()],
            "by_prop": {k: by_prop.get(k, 0) for k in PROPS},
            "forms": {k: [{"item": f, "n": n} for f, n in v.most_common(25)] for k, v in forms.items()},
            "named_by": [{"id": k, "name": self.name_of(k), "n": n} for k, n in self._named_by(u).most_common(20)],
            "relations": self._relation_tables(mem, words, top), "supersenses": self._supersense_tables(mem),
            "presence": self._presence(u), "cooccurring": self.cooccurring(u)[:30], "plural": self._plural(mem),
            "count_mode": self.lib.state["settings"]["count_mode"],
        }

    def _named_by(self, u):
        """Who names or describes the unit inside their quotes: speaker unit -> number of mentions (members of a group don't count
        for the group, nor does a plural speaker the unit belongs to). Pronouns are left out (inside a quote they mostly mean the
        speaker or the listener)."""
        out = Counter()
        for b, c in u.members:
            bd = self.bd[b]
            for mi in bd.groups[c].mentions:
                m = bd.mentions[mi]
                qi = bd.quote_at.get(m[1])
                if qi is None or m[3] == "PRON":
                    continue
                sus = [self.member_unit.get((b, x)) or ekey(b, x) for x in bd.stands_for(bd.quotes[qi]["char"])]
                if not any(su in u.parts for su in sus):
                    out.update(sus)
        return out

    def _relation_tables(self, mem, words, top):
        """For each relation: total, distinct words and the top rows with counts, rates, events and supersenses."""
        rels = {}
        for rel in RELATIONS:
            cnt, events, supersense = Counter(), Counter(), defaultdict(Counter)
            for b, c in mem:
                g = self.bd[b].groups[c]
                cnt.update(g.rel.get(rel, {}))
                events.update(g.rel_event.get(rel, {}))
                if rel in ("agent", "patient"):
                    for key, mi, hl in g.rel_ev.get(rel, []):
                        supersense[key][self.bd[b].ss.get(hl[-1], "")] += 1
            total = sum(cnt.values())
            rows = []
            for key, n in cnt.most_common(top):
                r = {"item": key, "n": n, "per1k": 1000 * n / words if words else 0, "pct": _pct(n, total)}
                if rel in ("agent", "patient", "prep"):
                    r["events"] = events.get(key, 0)
                if rel in ("agent", "patient"):
                    s = supersense[key].most_common(1)
                    r["supersense"] = s[0][0] if s and s[0][0] else ""
                rows.append(r)
            rels[rel] = {"total": total, "distinct": len(cnt), "rows": rows}
        return rels

    def _supersense_tables(self, mem):
        """Supersenses of the verbs the unit does (agent) or suffers (patient); verbs without one are counted apart."""
        out = {}
        for rel in ("agent", "patient"):
            tot = Counter()
            for b, c in mem:
                tot.update(self.bd[b].groups[c].rel_ss.get(rel, {}))
            out[rel] = [{"item": k, "n": n} for k, n in tot.most_common() if k != "none"]
            out[rel + "_none"] = tot.get("none", 0)
        return out

    def _presence(self, u):
        """Mentions in each 1% of each book, for the strip chart."""
        presence = []
        for b in sorted(u.books, key=lambda x: self.books.index(x)):
            bd = self.bd[b]
            starts = (bd.mentions[mi][1] for bb, c in u.members if bb == b for mi in bd.groups[c].mentions)
            presence.append({"book": b, "title": self.title(b), "bins": bd.presence_bins(starts)})
        return presence

    def _plural(self, mem):
        """For a plural group, its members; for a member, the plural groups it belongs to (as counted units: id, name, type);
        `hidden`: how many of its members' groups in these books aren't counted (below the minimum)."""
        out, hidden = {"members": {}, "member_of": {}}, set()
        for b, c in mem:
            g = self.bd[b].groups[c]
            for key, cs in (("members", g.members), ("member_of", g.member_of)):
                for x in cs:
                    uid = self.member_unit.get((b, x))
                    if uid:
                        out[key][uid] = self.units[uid]
                    elif key == "members":
                        hidden.add((b, x))
        return {**{k: [{"id": i, "name": u.name, "type": u.type} for i, u in v.items()] for k, v in out.items()},
                "hidden": len(hidden)}

    def cooccurring(self, u):
        """Units mentioned in the same sentence as this one (a unit or its id; for a group, as any of its entities), with the number of
        shared sentences, most first. A sentence counts once per other unit, however many of the group's entities it holds.
        A plural group and its own members are not counted as appearing with each other."""
        u = self.units[u] if isinstance(u, str) else u
        seen = defaultdict(set)
        for b, c in u.members:
            bd = self.bd[b]
            for sid in bd.group_sents.get(c, ()):
                for x in bd.sent_members[sid]:
                    o = self.member_unit.get((b, x))
                    if o and o not in u.parts and not bd.plural_pair(c, x):
                        seen[o].add((b, sid))
        co = Counter({o: len(s) for o, s in seen.items()})
        return [{"id": k, "name": self.units[k].name, "type": self.units[k].type, "n": n} for k, n in co.most_common()]

    # ---------- distinctiveness ----------
    def distinctive(self, target, reference, rel, **kw):
        """Words of one relation that are markedly more (or less) typical of the target than of the reference.
        Both are specs; `kw` goes to `stats.keyness`. -> (rows, summary)."""
        tmem, tlabel, ttypes = self.resolve(target)
        if reference.get("kind") == "others":
            reference = {**reference, "types": sorted(ttypes)}       # compare with the same kind of entity
        rmem, rlabel, _ = self.resolve(reference, exclude=frozenset(tmem))
        rows, summary = stats.keyness(self.rel_counts(tmem, rel), self.rel_counts(rmem, rel), **kw)
        summary.update(target=tlabel, reference=rlabel, rel=rel, rel_label=REL_LABELS[rel],
                       target_units=len({self.member_unit[m] for m in tmem if m in self.member_unit}),
                       reference_units=len({self.member_unit[m] for m in rmem if m in self.member_unit}))
        return rows, summary

    def group_summary(self, spec, top=15, exclude=frozenset()):
        """Overview figures for a group of units: how they are referred to, and their top words per relation."""
        mem, label, types = self.resolve(spec, exclude=exclude)
        units = {self.member_unit[m] for m in mem if m in self.member_unit}
        by_prop = Counter()
        for b, c in mem:
            by_prop.update(self.bd[b].groups[c].by_prop)
        words = self.words_in(mem)
        n = sum(by_prop.values())
        rels = {}
        for rel in RELATIONS:
            cnt = self.rel_counts(mem, rel)
            tot = sum(cnt.values())
            rels[rel] = {"total": tot, "rows": [{"item": k, "n": v, "pct": _pct(v, tot)} for k, v in cnt.most_common(top)]}
        ss = Counter()
        for b, c in mem:
            ss.update(self.bd[b].groups[c].rel_ss.get("agent", {}))
        ss.pop("none", None)
        return {"label": label, "units": len(units), "mentions": n, "books": len({b for b, c in mem}),
                "words": words, "per1k": 1000 * n / words if words else 0,
                "by_prop": {k: by_prop.get(k, 0) for k in PROPS}, "relations": rels,
                "agent_ss": [{"item": k, "n": v} for k, v in ss.most_common()]}

    # ---------- evidence ----------
    def evidence(self, spec, kind, key=None, other=None, limit=150):
        """The sentences behind a count. kind: a relation (with `key` the word), "form" (key = the text
        of a mention), "cooc" (other = a unit mentioned in the same sentence) or "named" (other = the
        speaker who names the unit in a quote). -> {total, shown, items: [{book, pos, tok, text}]};
        text carries marks (see BookData.span_text): m = the unit, k = the word, o = the other unit."""
        mem, _, _ = self.resolve(spec)
        out, total = [], 0
        for b, c in sorted(mem, key=lambda m: (self.books.index(m[0]), m[1])):
            bd = self.bd[b]
            g = bd.groups[c]
            items = []             # (token, marks)
            if kind in RELATIONS:
                for k, mi, hl in g.rel_ev.get(kind, []):
                    if k == key:
                        m = bd.mentions[mi]
                        items.append((m[1], [(m[1], m[2], "m")] + [(t, t, "k") for t in hl]))
            elif kind == "form":
                for mi in g.mentions:
                    m = bd.mentions[mi]
                    if m[5] == key or (m[3] == "PRON" and m[5].lower() == key):
                        items.append((m[1], [(m[1], m[2], "m")]))
            elif kind == "cooc" and other in self.units:
                others = {cc for bb, cc in self.units[other].members if bb == b}
                for sid in sorted(bd.group_sents.get(c, ())):
                    s, e = bd.sent_bounds[sid]
                    marks = []
                    for mi in bd.mentions_in(s, e):
                        m = bd.mentions[mi]
                        counts_for = bd.mention_groups(mi)
                        if c in counts_for:
                            marks.append((m[1], m[2], "m"))
                        elif others.intersection(counts_for):
                            marks.append((m[1], m[2], "o"))
                    if any(x[2] == "o" for x in marks):
                        items.append((s, marks))
            elif kind == "named" and other:
                for mi in g.mentions:
                    m = bd.mentions[mi]
                    qi = bd.quote_at.get(m[1])
                    if qi is None or m[3] == "PRON":
                        continue
                    if any((self.member_unit.get((b, x)) or ekey(b, x)) == other for x in bd.stands_for(bd.quotes[qi]["char"])):
                        items.append((m[1], [(m[1], m[2], "m")]))
            total += len(items)
            for tok, marks in items:
                if len(out) >= limit:
                    break
                s, e = bd.sentence_of(tok)
                out.append({"book": b, "title": self.title(b), "pos": round(100 * tok / max(1, bd.n_tokens), 1), "tok": tok,
                            "text": bd.span_text(s, e, marks)})
        return {"total": total, "shown": len(out), "items": out}

    # ---------- the same entity or group, book by book ----------
    def by_book(self, spec, rel, top=40, min_freq=3, alpha=0.05, bonferroni=False, **_):
        """A group's figures per book, and how one relation's words change from book to book
        (chi-squared for each word across books, `stats.across`)."""
        mem, label, types = self.resolve(spec)
        books = [b for b in self.books if any(m[0] == b for m in mem)]
        per = {b: [m for m in mem if m[0] == b] for b in books}
        overview = [self._book_overview(b, per[b], spec, types) for b in books]
        counts = {b: self.rel_counts(per[b], rel) for b in books}
        totals = [sum(counts[b].values()) for b in books]
        items = Counter()
        for b in books:
            items.update(counts[b])
        tested = [k for k, n in items.items() if n >= min_freq]
        thresh = alpha / len(tested) if (bonferroni and tested) else alpha
        rows = []
        for k, n in items.most_common(400):
            cs = [counts[b].get(k, 0) for b in books]
            row = {"item": k, "total": n, "counts": cs, "pcts": [_pct(c, t) for c, t in zip(cs, totals)],
                   "chi2": None, "df": None, "p": None, "v": None, "resid": [None] * len(books), "sig": False, "tested": False}
            if n >= min_freq:
                a = stats.across(cs, totals)
                row.update(chi2=a["chi2"], df=a["df"], p=a["p"], v=a["v"], resid=a["resid"], sig=a["p"] < thresh, tested=True)
            rows.append(row)
        ss = []
        for b in books:
            c = Counter()
            for bb, co in per[b]:
                c.update(self.bd[bb].groups[co].rel_ss.get("agent", {}))
            c.pop("none", None)
            ss.append({"book": b, "title": self.title(b), "rows": [{"item": k, "n": n} for k, n in c.most_common()]})
        return {"label": label, "books": [{"id": b, "title": self.title(b)} for b in books], "overview": overview,
                "rel": rel, "totals": totals, "rows": rows, "distinct": len(items),
                "summary": {"tested": len(tested), "min_freq": min_freq, "alpha": alpha, "bonferroni": bonferroni,
                            "threshold": thresh, "significant": sum(r["sig"] for r in rows)},
                "supersenses": ss}

    def _book_overview(self, b, members, spec, types):
        """One row of the book-by-book overview: mentions, how they are referred to, and each relation per 100 mentions."""
        bd = self.bd[b]
        by_prop = Counter()
        for bb, c in members:
            by_prop.update(self.bd[bb].groups[c].by_prop)
        n = sum(by_prop.values())
        row = {"book": b, "title": self.title(b), "mentions": n, "words": bd.n_words,
               "per1k": 1000 * n / bd.n_words if bd.n_words else 0,
               "names": _pct(by_prop["PROP"], n), "descriptions": _pct(by_prop["NOM"], n), "pronouns": _pct(by_prop["PRON"], n),
               "names_used": ", ".join(f for f, _ in self._forms(members).most_common(3))}
        if spec.get("kind") in ("unit", "group") and len(types) == 1:
            row["share"] = _pct(n, self.type_totals_book[(b, next(iter(types)))])
        for r in RELATIONS:
            row["rel_" + r] = _pct(sum(self.rel_counts(members, r).values()), n)
        return row

    def _forms(self, members):
        """Names used for the members (descriptions if none has a name)."""
        f = Counter()
        for b, c in members:
            f.update(self.bd[b].groups[c].forms["PROP"])
        if not f:
            for b, c in members:
                f.update(self.bd[b].groups[c].forms["NOM"])
        return f
