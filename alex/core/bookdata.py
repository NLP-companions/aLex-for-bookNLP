"""Read one book's BookNLP files and build the indexes the analyser needs.

Everything here is per book. Combining books, thresholds and links happens in `view.py`.
Nothing in the book's folder is ever written to.

A book is a folder holding (with `<id>` the book's id):

    <id>.tokens      one row per token: paragraph and sentence numbers, word, lemma, byte
                     offsets, universal and fine POS tags, dependency relation, head, EVENT flag
    <id>.entities    one row per mention: coreference group, first and last token, PROP/NOM/PRON,
                     category (PER, LOC…), text
    <id>.quotes      one row per quote: first and last token, the mention BookNLP used to
                     attribute it, the speaker's coreference group, the text        (optional)
    <id>.supersense  WordNet supersense spans                                       (optional)
    <id>.book        BookNLP's own character summary: names and pronouns            (optional)
    <id>.txt         the original text the export was made from                     (optional)

Tokens are addressed by their position in `.tokens` (0, 1, 2 …), which is also their
"token_ID_within_document"; every index in the analyser is such a position.

The main structures, used everywhere else:

    bd.mentions[i]   (coref, start, end, prop, cat, text, head)   `head` is the token that heads the mention
    bd.groups[c]     Group: all mentions of coreference group c and what is said about it
    bd.quotes[i]     {start, end, mstart, mend, char, text}        `char` is the speaker's coref (or None)
    bd.sent_bounds   sentence id -> (first token, last token);  bd.para_bounds likewise for paragraphs

Plural groups. You can declare in the analyser that a group ("Holmes and Watson", and the "they" BookNLP linked to it)
stands for several groups together (plurals.py); `set_members` gives the book those declarations (`Group.members`,
`Group.member_of`). As parsed, every group has only its own mentions and quotes. `plural_copy` makes the book the "include
plural-group mentions" way: a plural group's mention also counts as a mention of each member not named inside it (in the
members' mentions, forms, relations and co-occurrence: `credit`, `mention_groups`), and its quotes, addressees and speakers
stand for its members too (`stands_for`). The plural group itself keeps all its own data either way.
"""
from __future__ import annotations

import bisect
import csv
import json
import pickle
import sys
from array import array
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

TYPES = ["PER", "LOC", "FAC", "GPE", "VEH", "ORG", "VAR"]              # entity categories, in display order
RELATIONS = ["agent", "patient", "poss", "mod", "prep"]                # what can be said about an entity
VERBAL = {"VERB", "AUX"}
NON_WORD_POS = ("PUNCT", "SPACE", "SYM", "X")                          # parts of speech that don't count as words
QUOTE_MARKS = {'"', "“", "”", "'", "‘", "’", "``", "''", "«", "»"}     # tokens that open or close a quote: never words


def _raise_csv_limit():
    """Allow very long fields (a whole quote can be one). `sys.maxsize` overflows on some platforms, so back off."""
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


_raise_csv_limit()


def _read_tsv(path: Path):
    """Read a tab-separated file -> (rows, {column name: index}). Blank lines are dropped; quotes are not special. A byte-order
    mark at the start (some programs add one) and Windows line endings are fine; a file that isn't UTF-8 text is reported as such."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
            header = next(reader, None)
            if header is None:
                return [], {}
            return [row for row in reader if row], {h.strip(): i for i, h in enumerate(header)}
    except UnicodeDecodeError as e:
        raise ValueError(f"{path.name} isn't UTF-8 text (an unreadable byte at position {e.start}). Save it as UTF-8 and try again.") from None


def ekey(book, coref):
    """The unit id of one coreference group in one book: `e:<book>:<coref>`."""
    return f"e:{book}:{coref}"


def parse_ekey(uid):
    """(book id, coref) of an `e:<book>:<coref>` unit id; None for anything else (a linked person `p:<n>`, a damaged id).
    The coref is what follows the last colon, so a book id may itself contain colons."""
    if not isinstance(uid, str) or not uid.startswith("e:"):
        return None
    book, _, coref = uid[2:].rpartition(":")
    try:
        return (book, int(coref)) if book else None
    except ValueError:
        return None


def shared(values):
    """The same list with equal strings made one object. A book repeats a few dozen tags and a few thousand words tens of
    thousands of times, and the parser makes a new string for each: sharing them saves a fifth of the book's memory and of its cache file."""
    pool = {}
    return [pool.setdefault(v, v) for v in values]


@dataclass
class Group:
    """One coreference group (BookNLP's idea of one character, place or thing) in one book."""
    coref: int
    mentions: list = field(default_factory=list)   # indexes into BookData.mentions
    type: str = "PER"                              # the group's most common category
    by_prop: Counter = field(default_factory=Counter)                                        # PROP / NOM / PRON -> mentions
    forms: dict = field(default_factory=lambda: {"PROP": Counter(), "NOM": Counter(), "PRON": Counter()})   # text of each kind of mention
    name: str = ""
    pronouns: str | None = None      # BookNLP's most likely pronouns from `.book`, e.g. "he/him/his"
    rel: dict = field(default_factory=lambda: defaultdict(Counter))       # relation -> word -> count
    rel_event: dict = field(default_factory=lambda: defaultdict(Counter))  # relation -> word -> count of those BookNLP marks as EVENT
    rel_ss: dict = field(default_factory=lambda: defaultdict(Counter))     # relation -> supersense -> count
    rel_ev: dict = field(default_factory=lambda: defaultdict(list))        # relation -> [(word, mention index, tokens to highlight)]
    members: list = field(default_factory=list)      # a plural group: the groups its mentions also stand for (from `.book`)
    member_of: list = field(default_factory=list)    # the plural groups this group is a member of


class BookData:
    """One book, parsed. Building it reads the files once (slowly); the library caches the result.
    Attributes are documented where they are made: tokens (`_tokens`), supersenses, mentions and groups, quotes, `.book`,
    grammatical relations, co-occurrence."""
    def __init__(self, book_id: str, folder: Path):
        self.book_id = book_id
        self.folder = Path(folder)
        self.plural = False                # counts plural groups' mentions and quotes for their members too (see `plural_copy`)
        self.credit = {}                   # with `plural`: mention index -> the members it also counts for
        self.members_sig = "{}"            # the plural-group declarations applied (`set_members`)
        self.problems: list[str] = []      # things that look wrong in the files, shown on the Library page
        self._tokens()
        self._original_text()
        self._supersense()
        self._entities()
        self._quotes()
        self._book_json()
        self._relations()
        self._cooccurrence()

    # ---------- files ----------
    def _file(self, ext):
        """The path of one of the book's files."""
        return self.folder / f"{self.book_id}.{ext}"

    def _int(self, value, what, line, default=None):
        """Parse an integer from a file, saying which file, line and column is at fault if it isn't one."""
        if value == "" and default is not None:
            return default
        try:
            return int(value)
        except ValueError:
            raise ValueError(f"{self.book_id}.tokens line {line}: {what} should be a whole number but is “{value}”.") from None

    def _note_skipped(self, count, filename):
        """Say in `problems` that `count` lines of a file couldn't be read (if any)."""
        if count:
            self.problems.append(f"{count} line{'s' if count != 1 else ''} of {filename} couldn't be read and {'were' if count != 1 else 'was'} skipped.")

    def _tokens(self):
        """Read `.tokens` into parallel lists (one entry per token) and index sentences, paragraphs and heads."""
        rows, h = _read_tsv(self._file("tokens"))
        need = ["paragraph_ID", "sentence_ID", "token_ID_within_document", "word", "lemma", "POS_tag",
                "dependency_relation", "syntactic_head_ID"]
        missing = [c for c in need if c not in h]
        if missing:
            raise ValueError(f"{self.book_id}.tokens is missing columns: {', '.join(missing)}")

        def cell(r, c, d=""):
            return r[h[c]] if c in h and h[c] < len(r) else d

        n = len(rows)
        self.n_tokens = n
        self.word = shared(cell(r, "word") for r in rows)
        self.lemma = shared(cell(r, "lemma") for r in rows)
        self.pos = shared(cell(r, "POS_tag") for r in rows)
        self.tag = shared(cell(r, "fine_POS_tag") for r in rows)
        self.dep = shared(cell(r, "dependency_relation") for r in rows)
        # whole-number columns are kept as arrays of machine integers (8 bytes a token, where a list costs 36)
        self.para = array("q", (self._int(cell(r, "paragraph_ID"), "paragraph_ID", k + 2, 0) for k, r in enumerate(rows)))
        self.sent = array("q", (self._int(cell(r, "sentence_ID"), "sentence_ID", k + 2, 0) for k, r in enumerate(rows)))
        ids = [self._int(cell(r, "token_ID_within_document"), "token_ID_within_document", k + 2) for k, r in enumerate(rows)]
        if ids != list(range(n)):
            self.problems.append("Token IDs are not numbered 0, 1, 2… in order; positions may be off.")
        self.head = array("q")              # syntactic head of each token (a token is its own head when it is the root)
        for i, r in enumerate(rows):
            try:
                hd = int(cell(r, "syntactic_head_ID", str(i)))
            except ValueError:
                hd = i
            self.head.append(hd if 0 <= hd < n else i)
        self.event = [cell(r, "event") == "EVENT" for r in rows]
        try:
            self.onset = array("q", (int(cell(r, "byte_onset", "-1")) for r in rows))
            self.offset = array("q", (int(cell(r, "byte_offset", "-1")) for r in rows))
        except ValueError:
            self.onset = array("q", [-1]) * n        # without offsets, span_text falls back to single spaces
            self.offset = array("q", [-1]) * n
        self.children = defaultdict(list)   # head -> its dependents
        for i, hd in enumerate(self.head):
            if hd != i:
                self.children[hd].append(i)
        self.sent_bounds, self.para_bounds = {}, {}
        for i in range(n):
            s, p = self.sent[i], self.para[i]
            self.sent_bounds[s] = (self.sent_bounds[s][0], i) if s in self.sent_bounds else (i, i)
            self.para_bounds[p] = (self.para_bounds[p][0], i) if p in self.para_bounds else (i, i)
        self.n_words = sum(1 for p in self.pos if p not in NON_WORD_POS)
        self.n_sents = len(self.sent_bounds)
        self.n_paras = len(self.para_bounds)

    def _original_text(self):
        """Load `.txt`, the original text the export was made from, if the editor copied one into this book's folder
        (the same folder, found the same way, as `.quotes` and the other optional files). Missing or unreadable: `has_original`
        stays false and `span_text` falls back to its spacing heuristic.

        `byte_onset`/`byte_offset` in `.tokens` are, despite the name, character offsets into this text (Unicode
        codepoints), not true UTF-8 byte offsets: a multi-byte character (curly quotes, em dashes, £…) is one unit
        there but two or three bytes in the file. `raw_text` (decoded once here) is what `span_text` indexes by
        position; `raw_bytes` is kept only for downloading the file as-is."""
        self.has_original = False
        self.raw_bytes = b""
        self.raw_text = ""
        p = self._file("txt")
        if not p.exists():
            return
        try:
            self.raw_bytes = p.read_bytes()
            self.raw_text = self.raw_bytes.decode("utf-8")
            self.has_original = True
        except (OSError, UnicodeDecodeError):
            pass

    def _supersense(self):
        """Read `.supersense` -> self.ss: token -> supersense (the first span to cover a token wins)."""
        self.ss = {}
        p = self._file("supersense")
        if not p.exists():
            return
        rows, h = _read_tsv(p)
        skipped = 0
        for r in rows:
            try:
                s, e, cat = int(r[h["start_token"]]), int(r[h["end_token"]]), r[h["supersense_category"]]
            except (KeyError, ValueError, IndexError):
                skipped += 1
                continue
            for i in range(max(s, 0), min(e, self.n_tokens - 1) + 1):
                self.ss.setdefault(i, cat)
        self._note_skipped(skipped, p.name)

    def _entities(self):
        """Read `.entities` into mentions and coreference groups."""
        rows, h = _read_tsv(self._file("entities"))
        self.mentions = []
        self.groups: dict[int, Group] = {}
        skipped = 0
        for r in rows:
            try:
                c, s, e = int(r[h["COREF"]]), int(r[h["start_token"]]), int(r[h["end_token"]])
                prop, cat, text = r[h["prop"]], r[h["cat"]], r[h["text"]]
            except (KeyError, ValueError, IndexError):
                skipped += 1
                continue
            if not 0 <= s <= e < self.n_tokens:
                self.problems.append(f"A mention of group {c} lies outside the book (tokens {s}–{e}) and was skipped.")
                continue
            if cat not in TYPES:                      # e.g. "PER_FAC" style categories: take the last part
                last = cat.split("_")[-1]
                cat = last if last in TYPES else cat
            idx = len(self.mentions)
            self.mentions.append((c, s, e, prop, cat, text, self._mention_head(s, e)))
            g = self.groups.setdefault(c, Group(c))
            g.mentions.append(idx)
            g.by_prop[prop] += 1
            if prop in g.forms:
                g.forms[prop][text] += 1
        self._note_skipped(skipped, self._file("entities").name)
        for g in self.groups.values():
            g.type = Counter(self.mentions[i][4] for i in g.mentions).most_common(1)[0][0]
        self.mention_starts = sorted((m[1], i) for i, m in enumerate(self.mentions))   # for finding mentions by position

    def _mention_head(self, s, e):
        """The token that heads the mention s..e: the first whose own head lies outside it."""
        for i in range(s, e + 1):
            hd = self.head[i]
            if hd < s or hd > e or hd == i:
                return i
        return e

    def _quotes(self):
        """Read `.quotes`; self.quote_at maps each token inside a quote to the quote's index."""
        self.quotes = []
        self.quote_at = {}
        self.quote_mentions = defaultdict(set)     # quote index -> {(coref, prop, mention index)} of mentions inside it
        p = self._file("quotes")
        if not p.exists():
            return
        rows, h = _read_tsv(p)

        def cell(r, c):
            return r[h[c]] if c in h and h[c] < len(r) else ""

        skipped = 0
        for r in rows:
            try:
                ms, me = cell(r, "mention_start"), cell(r, "mention_end")
                char = cell(r, "char_id")
                q = dict(start=int(r[h["quote_start"]]), end=int(r[h["quote_end"]]),
                         mstart=int(ms) if ms.lstrip("-").isdigit() else None,
                         mend=int(me) if me.lstrip("-").isdigit() else None,
                         char=int(char) if char not in ("", "None", "-1") else None,
                         text=cell(r, "quote"))
            except (KeyError, ValueError, IndexError):
                skipped += 1
                continue
            if not 0 <= q["start"] <= q["end"] < self.n_tokens:
                self.problems.append(f"A quote lies outside the book (tokens {q['start']}–{q['end']}) and was skipped.")
                continue
            qi = len(self.quotes)
            self.quotes.append(q)
            for i in range(q["start"], q["end"] + 1):
                self.quote_at[i] = qi
        self._note_skipped(skipped, p.name)
        for mi, m in enumerate(self.mentions):
            qi = self.quote_at.get(m[1])
            if qi is not None:
                self.quote_mentions[qi].add((m[0], m[3], mi))

    def _book_json(self):
        """Read `.book` for BookNLP's own character names and pronouns, then give every group a name:
        BookNLP's, else its most common name, description or pronoun, else its first mention's text."""
        self.book_names, self.book_pron = {}, {}
        p = self._file("book")
        if p.exists():
            try:
                data = json.loads(p.read_text(encoding="utf-8-sig"))
                for ch in data.get("characters", []):
                    cid = ch.get("id")
                    if ch.get("name"):
                        self.book_names[cid] = ch["name"]
                    gi = ch.get("g") or {}
                    if isinstance(gi, dict) and gi.get("argmax"):
                        self.book_pron[cid] = gi["argmax"]
            except (ValueError, OSError, AttributeError) as e:
                self.problems.append(f"Could not read {p.name}: {e}")
        for c, g in self.groups.items():
            g.pronouns = self.book_pron.get(c)
            if c in self.book_names:
                g.name = self.book_names[c]
                continue
            for prop in ("PROP", "NOM", "PRON"):
                if g.forms[prop]:
                    g.name = g.forms[prop].most_common(1)[0][0]
                    break
            else:
                g.name = self.mentions[g.mentions[0]][5]

    def cache(self, owner):
        """A dict that another module keeps results derived from this book in (a lookup table, one result per setting…), named by
        `owner`. It lives as long as the book does in memory, and is neither saved with the book nor copied into its plural copy
        (see `plural_copy`); it is the owner's job to keep it small and to build a result again when what it depends on changes."""
        return self.__dict__.setdefault("_cache_" + owner, {})

    # ---------- plural groups ----------
    def set_members(self, members):
        """Apply your plural-group declarations for this book ({plural group coref: [member corefs]}): who is a member of whom.
        Groups without mentions and a group listed as its own member are left out. Cheap: nothing is recounted."""
        sig = json.dumps(sorted((int(c), sorted(int(m) for m in ms)) for c, ms in (members or {}).items()))
        if sig == self.members_sig:
            return
        for g in self.groups.values():
            g.members, g.member_of = [], []
        for c, ms in (members or {}).items():
            if c in self.groups:
                self.groups[c].members = [m for m in dict.fromkeys(ms) if m in self.groups and m != c]
                for m in self.groups[c].members:
                    self.groups[m].member_of.append(c)
        self.members_sig = sig

    def plural_copy(self):
        """This book counted the "include plural-group mentions" way (module docstring), as a new BookData: a copy without the
        caches other modules keep on the book (`cache`), with members credited and relations and co-occurrence counted again. The
        files are not read again. Only the groups are copied (they are what crediting changes); the tokens and everything else
        that crediting leaves alone are shared with this book, so a plural copy costs a fraction of a book's memory."""
        pd = object.__new__(BookData)
        pd.__dict__ = {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
        pd.groups = pickle.loads(pickle.dumps(self.groups))
        pd.plural = True
        for g in pd.groups.values():
            g.rel, g.rel_event, g.rel_ss, g.rel_ev = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter), defaultdict(list)
        pd._credit()
        pd._relations()
        pd._cooccurrence()
        return pd

    def _credit(self):
        """Make `credit` (mention index -> the members a plural group's mention also counts for: those not named inside it, so
        "Holmes and Watson" doesn't count again for the "Holmes" within it) and add those mentions to the members' mentions,
        kinds and forms."""
        self.credit = {}
        for g in self.groups.values():
            for mi in g.mentions if g.members else ():
                s, e = self.mentions[mi][1], self.mentions[mi][2]
                inside = {self.mentions[i][0] for i in self.mentions_in(s, e) if self.mentions[i][2] <= e}
                ms = tuple(m for m in g.members if m not in inside)
                if ms:
                    self.credit[mi] = ms
        touched = set()
        for mi, ms in self.credit.items():
            prop, text = self.mentions[mi][3], self.mentions[mi][5]
            for m in ms:
                t = self.groups[m]
                t.mentions.append(mi)
                t.by_prop[prop] += 1
                if prop in t.forms:
                    t.forms[prop][text] += 1
                touched.add(m)
        for m in touched:                             # keep every group's mentions in reading order
            self.groups[m].mentions.sort(key=lambda i: (self.mentions[i][1], i))

    def mention_groups(self, mi):
        """The groups a mention counts for: its own, and with `plural` on the members it is credited to."""
        return (self.mentions[mi][0], *self.credit.get(mi, ()))

    def stands_for(self, c):
        """The groups a speaker or addressee stands for: itself, and with `plural` on a plural group's members; () for None."""
        if c is None:
            return ()
        g = self.groups.get(c)
        return (c, *g.members) if self.plural and g else (c,)

    def plural_pair(self, a, b):
        """Whether one of two groups is a plural group the other is a member of (they always appear together)."""
        ga, gb = self.groups.get(a), self.groups.get(b)
        return bool(ga and b in ga.members or gb and a in gb.members)

    # ---------- grammatical relations ----------
    def _relations(self):
        """What each group does and what is done to it, from the dependency parse.

        BookNLP's rules: subject of a verb -> agent; object or passive subject -> patient;
        possessor -> poss; adjectival modifier or copula complement -> mod. Three extensions:
        conjoined mentions share their first conjunct's role, a subject is also the agent of
        verbs coordinated with its verb, and prepositional attachments ("went to London") are
        recorded as `prep` for every type. Each finding keeps the tokens to highlight as evidence. With `plural` on, a plural
        group's findings ("they waited") count for the members the mention is credited to as well (`credit`)."""
        dep, head, pos, lemma, word = self.dep, self.head, self.pos, self.lemma, self.word
        for mi, (c, s, e, prop, cat, text, h) in enumerate(self.mentions):
            g = self.groups[c]
            targets = [g, *(self.groups[m] for m in self.credit.get(mi, ()))]

            def add(rel, key, hl, gov=None):
                for t in targets:
                    self._add(t, rel, key, mi, hl, gov)

            he = h
            for _ in range(5):                       # a conjunct takes the role of the first conjunct
                if dep[he] == "conj" and head[he] != he:
                    he = head[he]
                else:
                    break
            d, gv = dep[he], head[he]
            if gv == he:
                d = "ROOT"
            if d == "nsubj" and pos[gv] == "VERB":
                add("agent", lemma[gv].lower(), (gv,), gv)
                for cj in self.children.get(gv, []):         # ...and of verbs coordinated with its verb
                    if dep[cj] == "conj" and pos[cj] == "VERB" and not any(dep[x].startswith("nsubj") for x in self.children.get(cj, [])):
                        add("agent", lemma[cj].lower(), (cj,), cj)
            elif d == "pobj" and dep[gv] == "agent" and head[gv] != gv:      # "by" agent of a passive
                v = head[gv]
                add("agent", lemma[v].lower(), (gv, v), v)
            elif d in ("dobj", "nsubjpass", "dative") and pos[gv] in VERBAL:
                add("patient", lemma[gv].lower(), (gv,), gv)
            elif d == "poss":
                add("poss", lemma[gv].lower(), (gv,))
            elif d == "pobj" and dep[gv] == "prep":
                att = head[gv]                                                # what the preposition attaches to
                prep = word[gv].lower()
                if att != gv and pos[att] in ("VERB", "NOUN", "ADJ", "AUX"):
                    add("prep", f"{lemma[att].lower()} {prep}", (gv, att), att if pos[att] == "VERB" else None)
                else:
                    add("prep", prep, (gv,))
            if d == "nsubj" and lemma[gv].lower() == "be":                    # "Brown was small"
                for x in self.children.get(gv, []):
                    if dep[x] in ("acomp", "attr") and not (s <= x <= e):
                        add("mod", lemma[x].lower(), (x,))
            for x in self.children.get(h, []):                                # adjectives and appositions
                if dep[x] == "amod" or (dep[x] == "appos" and pos[x] in ("NOUN", "PROPN")):
                    add("mod", lemma[x].lower(), (x,))

    def _add(self, g, rel, key, mi, hl, gov):
        """Record one finding for group g: relation, word, evidence, and (for verbs) event and supersense counts."""
        if not key.strip():
            return
        g.rel[rel][key] += 1
        g.rel_ev[rel].append((key, mi, hl))
        if gov is not None:
            if self.event[gov]:
                g.rel_event[rel][key] += 1
            g.rel_ss[rel][self.ss.get(gov, "none")] += 1

    # ---------- co-occurrence ----------
    def _cooccurrence(self):
        """Which groups are mentioned in each sentence and paragraph (for networks and "appears with"), counting a mention for
        every group it counts for (`mention_groups`). Pairs of a plural group and its own member are skipped by their users
        (`plural_pair`): they always appear together."""
        self.sent_members = defaultdict(set)
        self.para_members = defaultdict(set)
        for mi, (c, s, *_) in enumerate(self.mentions):
            for x in self.mention_groups(mi):
                self.sent_members[self.sent[s]].add(x)
                self.para_members[self.para[s]].add(x)
        self.group_sents = defaultdict(set)      # group -> sentences it is mentioned in
        for sid, cs in self.sent_members.items():
            for c in cs:
                self.group_sents[c].add(sid)

    # ---------- text ----------
    def _raw_gap(self, start, end):
        """The exact original text between two character positions in `raw_text` (from `.txt`, when there is one), for
        `span_text`'s spacing. A newline in it (a line break inside the paragraph) falls back to a single space, so a
        passage never gains a stray line break; control characters are stripped so a gap can't forge a mark."""
        text = self.raw_text[start:end]
        if "\n" in text or "\r" in text:
            return " "
        return text.replace("\x01", "").replace("\x02", "").replace("\x03", "") or " "

    def span_text(self, s, e, marks=()):
        """Rebuild the text of tokens s..e, spacing them by their byte offsets: the exact original spacing when `.txt` is
        available (so double spaces, unusual dashes and the like come through as written), else a single space or none,
        guessed from the offsets alone.

        marks: (start, end, class) triples to wrap around tokens. The result uses control
        characters instead of HTML so it can carry marks safely: `\\x01class\\x02` opens a mark
        and `\\x03` closes one (the browser turns these into <mark> elements). Control characters
        occurring in a token are removed, so a token can't forge a mark."""
        out = []
        opened = {}
        for a, b, cls in marks:
            opened.setdefault(a, []).append(cls)
        closes = Counter(b for a, b, cls in marks)
        for i in range(s, e + 1):
            if i > s:
                gap = self.onset[i] - self.offset[i - 1] if self.onset[i] >= 0 and self.offset[i - 1] >= 0 else 1
                if gap > 0 and self.has_original and self.onset[i] <= len(self.raw_text):
                    out.append(self._raw_gap(self.offset[i - 1], self.onset[i]))
                elif gap > 0 or (gap < 0 and self.pos[i] != "PUNCT"):
                    out.append(" ")
            for cls in opened.get(i, []):
                out.append("\x01" + cls + "\x02")
            out.append(self.word[i].replace("\x01", "").replace("\x02", "").replace("\x03", ""))
            out.append("\x03" * closes.get(i, 0))
        return "".join(out)

    def presence_bins(self, positions, bins=100):
        """How many of the token `positions` fall in each of `bins` equal slices of the book (100: the strip charts of where something
        occurs, one slice per percent)."""
        out = [0] * bins
        for t in positions:
            out[min(bins - 1, int(bins * t / max(1, self.n_tokens)))] += 1
        return out

    def mentions_in(self, s, e):
        """Indexes of the mentions that start within tokens s..e."""
        i = bisect.bisect_left(self.mention_starts, (s, -1))
        out = []
        while i < len(self.mention_starts) and self.mention_starts[i][0] <= e:
            out.append(self.mention_starts[i][1])
            i += 1
        return out

    def sentence_of(self, tok):
        """(first, last) token of the sentence containing tok."""
        return self.sent_bounds[self.sent[tok]]
