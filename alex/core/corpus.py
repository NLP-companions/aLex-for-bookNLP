"""Corpus tools after AntConc: concordance (KWIC) and concordance plot, word lists, n-grams,
collocates and keywords, over the selected books, with BookNLP's layers available to
pattern queries.

Sections: per-book index · value matching · query parsing · matching · scope · KWIC ·
word lists and n-grams · collocates · keywords · reference files.

Every search is cut down to what the user asked for *before* any limit applies: a hit that is out of scope, or lacks the
near word or context the user asked for, is never found, so a cap on the number of hits can't be used up by hits
that would be thrown away anyway.

Vocabulary used below:

* a **stream** is the list of token positions a search runs over: the words (punctuation and
  quotation marks left out) unless "ignore punctuation" is off;
* a **scope** restricts a tool to narration, dialogue or one speaker's quotes;
* a **hit** is `(start, end, line)`, `start`/`end` indexes into the stream (end exclusive), `line` the batch query line
  that produced it (see `Matcher`) — the query's own text when there's only one.
* a **batch query** is several complete queries, one per line, tried as alternatives and merged into one search: type
  a list ("say", "ask", "shout" on their own lines, or `[lemma="say"]`, `[lemma="ask"]`) instead of searching each on
  its own. Unlike `a|b` inside one simple word (which is still there, for a quick single-word alternative), a batch
  line can be a whole multi-token pattern.
"""
from __future__ import annotations

import bisect
import heapq
import math
import re
from collections import Counter, defaultdict

from . import stats
from .bookdata import QUOTE_MARKS, ekey

TYPE_LABELS = {"PER": "people", "LOC": "locations", "FAC": "facilities", "GPE": "geo-political entities", "VEH": "vehicles", "ORG": "organisations", "VAR": "various"}

ATTRS = {
    "word": "word form", "lemma": "lemma", "pos": "universal POS (NOUN, VERB…)", "tag": "fine POS tag (NN, VBD…)",
    "dep": "dependency relation", "ent": "entity type of a mention covering the token (PER, LOC…)",
    "prop": "PROP, NOM or PRON for a mention covering the token", "char": "name of the entity a covering mention refers to",
    "ss": "supersense (verb.communication, noun.person…)", "event": "yes if BookNLP marks the token as an event",
    "quote": "in or out: inside a quote or not", "speaker": "name of the speaker of the quote the token is in",
}
SORT_KEYS = ["key"] + [f"L{i}" for i in range(1, 6)] + [f"R{i}" for i in range(1, 6)] + ["book"]   # the positions concordance lines can be sorted by
SORT_BY = {"word": "Word", "lemma": "Lemma", "pos": "Word class (POS)", "tag": "Fine POS tag", "freq": "Frequency"}   # what is compared at that position
MAX_HITS = 20000       # a search stops here
PLOT_BINS = 200        # the concordance plot divides each book into this many slices
MEMO_LIMIT = 500_000   # a pattern search remembers at most this many partial matches before starting again
POS_LABELS = {"ADJ": "adjective", "ADP": "preposition", "ADV": "adverb", "AUX": "auxiliary", "CCONJ": "coordinating conjunction", "DET": "determiner",
              "INTJ": "interjection", "NOUN": "noun", "NUM": "numeral", "PART": "particle", "PRON": "pronoun", "PROPN": "proper noun",
              "SCONJ": "subordinating conjunction", "VERB": "verb", "X": "other"}
TAG_LABELS = {"CC": "coordinating conjunction", "CD": "number", "DT": "determiner", "EX": "existential there", "FW": "foreign word", "IN": "preposition or conjunction",
              "JJ": "adjective", "JJR": "comparative adjective", "JJS": "superlative adjective", "MD": "modal verb", "NN": "singular noun", "NNP": "singular proper noun",
              "NNPS": "plural proper noun", "NNS": "plural noun", "PDT": "predeterminer", "POS": "possessive ending", "PRP": "personal pronoun", "PRP$": "possessive pronoun",
              "RB": "adverb", "RBR": "comparative adverb", "RBS": "superlative adverb", "RP": "particle", "TO": "to", "UH": "interjection", "VB": "verb, base form",
              "VBD": "verb, past tense", "VBG": "verb, -ing form", "VBN": "verb, past participle", "VBP": "verb, present (not 3rd person)", "VBZ": "verb, present 3rd person",
              "WDT": "wh-determiner", "WP": "wh-pronoun", "WP$": "possessive wh-pronoun", "WRB": "wh-adverb"}
MAX_REPEAT = 10        # `*`, `+` and `{n,}` mean "up to this many"


class QueryError(ValueError):
    """A search the user wrote can't be run; the message says why and is shown to them."""


# ---------- per-book index ----------
def cindex(bd):
    """Per-book lookup tables, built once and kept on the book:
    isword[i]    True for words (not punctuation or quotation marks)
    in_quote[i]  inside a quote;  speaker[i]  the quote's speaker (coref) or None
    cover[i]     mentions covering token i;  vals  cache for `values`"""
    c = bd.cache("index")
    if "isword" in c:
        return c
    n = bd.n_tokens
    isword = [bd.pos[i] not in ("PUNCT", "SPACE", "SYM") and bd.word[i] not in QUOTE_MARKS for i in range(n)]
    in_quote, speaker = [False] * n, [None] * n
    for q in bd.quotes:
        for i in range(q["start"], min(q["end"] + 1, n)):
            in_quote[i] = True
            speaker[i] = q["char"]
    cover = defaultdict(list)
    for mi, m in enumerate(bd.mentions):
        for i in range(m[1], m[2] + 1):
            cover[i].append(mi)
    c.update(isword=isword, in_quote=in_quote, speaker=speaker, cover=cover, vals={}, n_words=sum(isword))
    return c


def values(bd, attr):
    """attr value -> token positions, for the attributes that have a vocabulary (word, lemma, pos, tag, dep, ss)."""
    ci = cindex(bd)
    if attr in ci["vals"]:
        return ci["vals"][attr]
    src = {"word": bd.word, "lemma": bd.lemma, "pos": bd.pos, "tag": bd.tag, "dep": bd.dep}.get(attr)
    d = defaultdict(list)
    if src is not None:
        for i, v in enumerate(src):
            d[v].append(i)
    elif attr == "ss":
        for i, v in bd.ss.items():
            d[v].append(i)
    ci["vals"][attr] = d
    return d


def token_test(bd, flt):
    """A function telling whether token i of a book satisfies a word-type filter, or None if the filter restricts nothing.
    `flt` is `{"pos": [...], "tag": [...], "ent": [...]}`: universal POS tags, fine POS tags, and entity types of a mention covering the
    token. A token must match one value of every list that isn't empty (so `pos` NOUN and VERB, `ent` PER, gives nouns and verbs that
    are part of a person's mention)."""
    flt = flt or {}
    pos, tag, ent = (set(flt.get(k) or ()) for k in ("pos", "tag", "ent"))
    if not (pos or tag or ent):
        return None
    cover = cindex(bd)["cover"]
    return lambda i: ((not pos or bd.pos[i] in pos) and (not tag or bd.tag[i] in tag)
                      and (not ent or any(bd.mentions[mi][4] in ent for mi in cover.get(i, ()))))


def filter_options(view):
    """The values a word-type filter can choose from in the selected books, with how many words each covers:
    `{"pos": [{value, label, n}], "tag": […], "ent": […]}`, most frequent first. Only words count (not punctuation)."""
    pos, tag, ent = Counter(), Counter(), Counter()
    for b in view.books:
        bd = view.bd[b]
        ci = cindex(bd)
        for i, w in enumerate(ci["isword"]):
            if w:
                pos[bd.pos[i]] += 1
                tag[bd.tag[i]] += 1
                for c in {bd.mentions[mi][4] for mi in ci["cover"].get(i, ())}:
                    ent[c] += 1
    rows = lambda cnt, labels: [{"value": v, "label": labels.get(v, ""), "n": n} for v, n in cnt.most_common()]
    return {"pos": rows(pos, POS_LABELS), "tag": rows(tag, TAG_LABELS), "ent": rows(ent, TYPE_LABELS)}


# ---------- value matching ----------
def value_matcher(value, regex=False, case=False, wildcards=True):
    """A function telling whether a whole string matches `value`.
    Simple syntax: `*` any letters, `?` one letter, `a|b` either. With `regex`, `value` is a Python regular expression
    (and `wildcards` is moot). With `wildcards` off, `*`, `?` and `|` are literal characters, e.g. to search punctuation
    itself: a bare `?` then matches a literal "?" instead of "any one letter"."""
    flags = 0 if case else re.IGNORECASE
    if regex:
        try:
            r = re.compile(value, flags)
        except re.error as e:
            raise QueryError(f"Not a valid regular expression: {value} ({e})") from None
        return lambda v: r.fullmatch(v) is not None
    if not wildcards:
        r = re.compile(re.escape(value), flags)
        return lambda v: r.fullmatch(v) is not None
    alts = [a for a in value.split("|") if a != ""] or [value]
    pats = [re.escape(a).replace(r"\*", ".*").replace(r"\?", ".") for a in alts]
    r = re.compile("(?:" + "|".join(pats) + ")", flags)
    return lambda v: r.fullmatch(v) is not None


# ---------- query parsing ----------
# A parsed query is a list of items (conditions, lo, hi): a token that must satisfy every condition
# (attribute, "=" or "!=", value), repeated between lo and hi times. No conditions means "any token".
def parse_simple(q, settings):
    """`said # Holmes` -> one item per word; `#` is any one word (unless wildcards are off in `settings`, when it's a
    literal "#"); the words match word forms or lemmas."""
    items = []
    for tok in q.split():
        items.append(([], 1, 1) if tok == "#" and settings.get("wildcards", True) else ([(settings.get("match", "word"), "=", tok)], 1, 1))
    if not items:
        raise QueryError("Type something to search for.")
    return items


def parse_pattern(q):
    """`[lemma="say" & pos="VERB"] [pos!="PUNCT"]? bare` -> items. Quantifiers after a token: ? * + {n} {n,m}."""
    items, i, n = [], 0, len(q)
    while i < n:
        if q[i].isspace():
            i += 1
            continue
        if q[i] != "[":                                    # a bare word matches that word form
            j = i
            while j < n and not q[j].isspace() and q[j] != "[":
                j += 1
            items.append(([("word", "=", q[i:j])], 1, 1))
            i = j
            continue
        j, inq = i + 1, None                               # find the matching ], ignoring ] inside quotes
        while j < n and (q[j] != "]" or inq):
            if q[j] in "\"'":
                inq = None if inq == q[j] else (inq or q[j])
            j += 1
        if j >= n:
            raise QueryError("A [ has no matching ].")
        conds = _conditions(q[i + 1:j])
        i = j + 1
        lo, hi = 1, 1
        m = re.match(r"\?|\*|\+|\{(\d+)(?:,(\d*))?\}", q[i:])
        if m:
            t = m.group(0)
            lo, hi = {"?": (0, 1), "*": (0, MAX_REPEAT), "+": (1, MAX_REPEAT)}.get(t, (None, None))
            if lo is None:                                 # {n} or {n,m} or {n,}
                lo = int(m.group(1))
                hi = lo if m.group(2) is None else (int(m.group(2)) if m.group(2) else MAX_REPEAT)
            if lo > MAX_REPEAT or hi < lo:
                raise QueryError(f"{t} isn't allowed: repeat a token between 0 and {MAX_REPEAT} times, and the largest number can't be smaller than the first.")
            hi = min(hi, MAX_REPEAT)
            i += len(t)
        items.append((conds, lo, hi))
    if not items:
        raise QueryError("Type a pattern to search for, e.g. [lemma=\"say\"] [pos=\"ADV\"].")
    if all(lo == 0 for _, lo, _ in items):
        raise QueryError("Every part of the pattern is optional; at least one must match a word.")
    return items


def _conditions(text):
    """`lemma="say" & pos!="ADV"` -> [("lemma", "=", "say"), ("pos", "!=", "ADV")]."""
    text = text.strip()
    if not text:
        return []
    out = []
    for part in _split_and(text):
        m = re.match(r"\s*(\w+)\s*(!=|=)\s*(\"(.*)\"|'(.*)'|(\S+))\s*$", part, re.S)
        if not m:
            raise QueryError(f"Can't read the condition “{part.strip()}”. Write it as attribute=\"value\".")
        attr = m.group(1).lower()
        if attr not in ATTRS:
            raise QueryError(f"Unknown attribute “{attr}”. Available: {', '.join(ATTRS)}.")
        out.append((attr, m.group(2), next(g for g in (m.group(4), m.group(5), m.group(6)) if g is not None)))
    return out


def _split_and(text):
    """Split on `&`, except inside quotes."""
    parts, cur, inq = [], "", None
    for ch in text:
        if ch in "\"'":
            inq = None if inq == ch else (inq or ch)
        if ch == "&" and not inq:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return parts


# ---------- matching ----------
class Matcher:
    """Finds the hits of a query — or a batch query, one line per alternative — in the books of a view. Sets of
    matching token positions are cached per book and condition, shared across the batch's lines."""

    def __init__(self, view, query, mode="simple", settings=None):
        self.view = view
        self.s = settings or {}
        parse = parse_pattern if mode == "pattern" else (lambda q: parse_simple(q, self.s))
        lines = [ln.strip() for ln in str(query).split("\n") if ln.strip()]
        if not lines:
            parse("")                          # raise the usual "type something" error
        self.batch = [(ln, parse(ln)) for ln in lines]
        self._cache = {}

    def cond_set(self, b, cond):
        """Token positions of book b satisfying one condition (attribute, op, value)."""
        key = (b, cond)
        if key in self._cache:
            return self._cache[key]
        bd = self.view.bd[b]
        ci = cindex(bd)
        attr, op, val = cond
        mt = value_matcher(val, bool(self.s.get("regex")), bool(self.s.get("case")) and attr == "word", self.s.get("wildcards", True))
        pos = set()
        if attr in ("word", "lemma", "pos", "tag", "dep", "ss"):
            for v, ps in values(bd, attr).items():
                if mt(v):
                    pos.update(ps)
        elif attr in ("ent", "prop"):                      # a covering mention's category / kind
            k = 4 if attr == "ent" else 3
            for i, ms in ci["cover"].items():
                if any(mt(bd.mentions[mi][k]) for mi in ms):
                    pos.add(i)
        elif attr == "char":                               # a covering mention's entity, by name (with plural groups on, a member's too)
            ok = {}
            for i, ms in ci["cover"].items():
                for c in (c for mi in ms for c in bd.mention_groups(mi)):
                    if c not in ok:
                        ok[c] = mt(self._name(b, c))
                    if ok[c]:
                        pos.add(i)
                        break
        elif attr == "speaker":                            # inside a quote by this speaker (with plural groups on, by a group they're in)
            ok = {}
            for i, sp in enumerate(ci["speaker"]):
                if sp is None:
                    continue
                if sp not in ok:
                    ok[sp] = any(mt(self._name(b, c)) for c in bd.stands_for(sp))
                if ok[sp]:
                    pos.add(i)
        elif attr == "event":
            want = mt("yes") or mt("event") or mt("true")
            pos = {i for i, e in enumerate(bd.event) if e == want}
        elif attr == "quote":
            want = mt("in") or mt("yes")
            pos = {i for i, q in enumerate(ci["in_quote"]) if q == want}
        if op == "!=":
            pos = set(range(bd.n_tokens)) - pos
        self._cache[key] = pos
        return pos

    def _name(self, b, c):
        """The name shown for a coreference group (its unit's name if it is counted)."""
        u = self.view.member_unit.get((b, c))
        if u:
            return self.view.units[u].name
        g = self.view.bd[b].groups.get(c)
        return g.name if g else ""

    def item_set(self, b, conds):
        """Positions satisfying all of an item's conditions; None means "any token"."""
        if not conds:
            return None
        sets = [self.cond_set(b, c) for c in conds]
        out = sets[0]
        for x in sets[1:]:
            out = out & x
        return out

    def hits(self, b, stream, limit=MAX_HITS, accept=None):
        """Non-overlapping hits in book b over `stream`, leftmost first, at most `limit`: `(start, end, line)`.
        Repeated items are greedy with backing off, like a regular expression. With a batch query (see the module
        docstring), each candidate position tries the batch's lines in order and takes the first that matches.
        `accept(start, end)`, if given, can turn a candidate down: it is then not a hit, doesn't count towards `limit`
        and doesn't block the text it covers, so scope and filters apply before the limit does."""
        if limit <= 0:
            return []
        L = len(stream)
        batch = [(ln, [(self.item_set(b, c), lo, hi) for c, lo, hi in items]) for ln, items in self.batch]
        # a line with a repeated item (`*`, `+`, `{1,3}`) can try many ways of matching the same stretch: it remembers the
        # outcome of each (line, item, position), which cannot change, so such a pattern costs no more than its length
        variable = [any(lo != hi for _, lo, hi in specs) for _, specs in batch]
        memo = {}

        def go(li, k, j):
            """Match items k… of batch line li from stream position j -> the end position, or None."""
            specs = batch[li][1]
            if k == len(specs):
                return j
            if variable[li] and (li, k, j) in memo:
                return memo[li, k, j]
            st, lo, hi = specs[k]
            cnt = 0
            while cnt < hi and j + cnt < L and (st is None or stream[j + cnt] in st):
                cnt += 1
            result = None
            while cnt >= lo:
                result = go(li, k + 1, j + cnt)
                if result is not None:
                    break
                cnt -= 1
            if variable[li]:
                if len(memo) >= MEMO_LIMIT:
                    memo.clear()
                memo[li, k, j] = result
            return result

        # candidate starting positions: the union of what each line's own first item could start on, or every
        # position if any line's first item is unrestricted (matches anywhere, or is optional)
        cand, unrestricted = set(), False
        for ln, specs in batch:
            first, lo = specs[0][0], specs[0][1]
            if first is None or lo == 0:
                unrestricted = True
            else:
                cand.update(j for j in range(L) if stream[j] in first)
        cand = range(L) if unrestricted else sorted(cand)
        out, nxt = [], 0
        for j in cand:
            if j < nxt:
                continue                                       # hits don't overlap: carry on after the previous one
            for li, (ln, _) in enumerate(batch):
                e = go(li, 0, j)
                if e is not None and e > j and (accept is None or accept(j, e)):
                    out.append((j, e, ln))
                    nxt = e
                    break
            if len(out) >= limit:
                break
        return out


# ---------- scope ----------
class Scope:
    """Which tokens of a view's books a tool may use: the whole text, narration only, dialogue only, or the quotes of one speaker.
    `scope` is `{"kind": "all" | "narration" | "dialogue" | "speech", "speaker": spec}` (`speaker` is a spec `View.resolve` accepts).
    The mask of each book is made once and kept, so a tool that asks for it book after book, or twice, doesn't pay twice."""

    def __init__(self, view, scope=None):
        scope = scope or {}
        self.view = view
        self.kind = scope.get("kind", "all")
        self.speaker = scope.get("speaker")
        self._corefs = None
        self._masks = {}

    def _speaker_corefs(self):
        """{book: set of coreference groups} the scope's speaker stands for."""
        if self._corefs is None:
            self._corefs = defaultdict(set)
            for b, c in (self.view.resolve(self.speaker)[0] if self.speaker else ()):
                self._corefs[b].add(c)
        return self._corefs

    def mask(self, b):
        """One boolean per token of book b: in scope or not. None means everything is (don't modify the list)."""
        if b in self._masks:
            return self._masks[b]
        bd = self.view.bd[b]
        ci = cindex(bd)
        if self.kind == "narration":
            mask = [not q for q in ci["in_quote"]]
        elif self.kind == "dialogue":
            mask = ci["in_quote"]
        elif self.kind == "speech":
            corefs, said = self._speaker_corefs()[b], {}
            mask = [said[sp] if sp in said else said.setdefault(sp, any(c in corefs for c in bd.stands_for(sp))) for sp in ci["speaker"]]
        else:
            mask = None
        self._masks[b] = mask
        return mask

    def words(self, b):
        """Positions of the words of book b that are in scope."""
        iw, mask = cindex(self.view.bd[b])["isword"], self.mask(b)
        return [i for i, w in enumerate(iw) if w] if mask is None else [i for i, w in enumerate(iw) if w and mask[i]]


def as_scope(view, scope):
    """`scope` as a `Scope` of this view (it may be one already, or the dict the browser sends, or None)."""
    return scope if isinstance(scope, Scope) and scope.view is view else Scope(view, scope if isinstance(scope, dict) else None)


def stream_of(view, b, settings):
    """The token positions a search runs over (words only, unless punctuation is switched on)."""
    bd = view.bd[b]
    if settings.get("skip_punct", True):
        return [i for i, w in enumerate(cindex(bd)["isword"]) if w]
    return list(range(bd.n_tokens))


def item_of(bd, i, unit, case=False):
    """What token i counts as in a list: its lemma, word form (lowercased unless `case`), word_POS, word_POS_lemma (tab-separated,
    which `wordlist` splits into columns) or POS."""
    if unit == "lemma":
        return bd.lemma[i].lower()
    w = bd.word[i] if case else bd.word[i].lower()
    if unit == "word_pos":
        return f"{w}_{bd.pos[i]}"
    if unit == "word_pos_lemma":
        return f"{w}\t{bd.pos[i]}\t{bd.lemma[i].lower()}"
    if unit == "pos":
        return bd.pos[i]
    return w


def juilland(part_counts, parts=10):
    """Juilland's D, a dispersion measure: 1 - V / sqrt(parts - 1), V the coefficient of variation of
    the counts in equal-sized parts. 1 is perfectly even, 0 concentrated in one part; None if never seen."""
    vals = [part_counts.get(k, 0) for k in range(parts)]
    mean = sum(vals) / parts
    if mean == 0:
        return None
    sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / parts)
    return max(0.0, 1 - (sd / mean) / math.sqrt(parts - 1))


# ---------- KWIC ----------
def kwic_search(view, query, mode="simple", settings=None, scope=None, sort=("R1", "R2", "R3"), near=None, limit=MAX_HITS, ctx=None):
    """Find and sort the hits of a concordance, without their text (`kwic_lines` makes the lines), plus per-book figures for the plot.

    sort: up to any number of levels, each a position (`SORT_KEYS`: the hit itself, a word left or right of it, or the book) as text, or
          `{"pos", "by", "desc"}` with `by` one of `SORT_BY` (see `_sort_levels`);
    near: {"item", "unit", "left", "right", "within_sentence"} keeps only hits with that item close by;
    ctx:  a second search in the words around each hit (see `_ctx_test`): {"query", "mode", "left", "right", "within_sentence", "exclude"}.
    -> {found (the sorted hits: book, first and last token, the batch line that matched), total, per_book (hits, words, rate,
        dispersion and `bins`, the hits in each of `PLOT_BINS` slices of the book), speakers (who says the hits), capped, per1k, batch}"""
    settings = settings or {}
    levels = _sort_levels(sort)
    if near is not None and not str(near.get("item", "")).strip():
        raise QueryError("The near-word filter needs a word.")
    m = Matcher(view, query, mode, settings)
    m2 = Matcher(view, ctx["query"], ctx.get("mode", "simple"), settings) if ctx and str(ctx.get("query", "")).strip() else None
    sc = as_scope(view, scope)
    found, per_book, spk = [], [], Counter()
    for b in view.books:
        bd = view.bd[b]
        ci = cindex(bd)
        stream = stream_of(view, b, settings)
        mask = sc.mask(b)
        tests = []
        if mask is not None:
            tests.append(lambda j, e, mask=mask, stream=stream: all(mask[x] for x in stream[j:e]))      # hits must lie wholly inside the scope
        if near:
            tests.append(_near_test(bd, stream, mask, near, settings))
        if m2:
            tests.append(_ctx_test(b, bd, stream, mask, ctx, m2))
        accept = (lambda j, e: all(t(j, e) for t in tests)) if tests else None
        words_in_scope = sum(1 for i, w in enumerate(ci["isword"]) if w and (mask is None or mask[i]))
        bins, parts, n_hits = [0] * PLOT_BINS, Counter(), 0
        for j, e, ln in m.hits(b, stream, limit - len(found), accept):
            s, t = stream[j], stream[e - 1]
            rel = s / max(1, bd.n_tokens)
            bins[min(PLOT_BINS - 1, int(PLOT_BINS * rel))] += 1
            parts[min(9, int(10 * rel))] += 1
            n_hits += 1
            for c in bd.stands_for(ci["speaker"][s]) or (None,):
                spk[view.member_unit.get((b, c)) or (ekey(b, c) if c is not None else None)] += 1
            found.append({"book": b, "s": s, "e": t, "matched": ln})
        per_book.append({"book": b, "title": view.title(b), "hits": n_hits, "words": words_in_scope,
                         "per1k": 1000 * n_hits / words_in_scope if words_in_scope else 0,
                         "d": juilland(parts) if n_hits else None, "bins": bins})
    _sort_hits(view, found, levels)
    for h in found:
        h.pop("_v", None)
    speakers = [{"id": k, "name": "Narration" if k is None else view.name_of(k), "n": n} for k, n in spk.most_common(40)]
    total_words = sum(p["words"] for p in per_book)
    return {"found": found, "total": len(found), "per_book": per_book, "speakers": speakers, "capped": len(found) >= limit,
            "per1k": 1000 * len(found) / total_words if total_words else 0, "batch": len(m.batch) > 1}


def kwic_lines(view, found, context=10):
    """The concordance lines of some of a search's hits (`kwic_search`'s `found`, or a slice of it): each hit with `context` tokens of
    text on either side, its book and its position in the book in percent."""
    out = []
    for h in found:
        bd = view.bd[h["book"]]
        s, e = h["s"], h["e"]
        out.append({"book": h["book"], "title": view.title(h["book"]), "tok": s, "end": e,
                    "pos": round(100 * s / max(1, bd.n_tokens), 1),
                    "left": bd.span_text(max(0, s - context), s - 1) if s > 0 else "",
                    "key": bd.span_text(s, e), "matched": h["matched"],
                    "right": bd.span_text(e + 1, min(bd.n_tokens - 1, e + context)) if e + 1 < bd.n_tokens else ""})
    return out


def kwic(view, query, mode="simple", settings=None, scope=None, context=10, sort=("R1", "R2", "R3"),
         near=None, limit=MAX_HITS, ctx=None):
    """Concordance: every hit with its left and right context, sorted, plus per-book figures for the plot (see `kwic_search`
    for the arguments and `kwic_lines` for the lines). -> the search's result with `hits` (the lines) in place of `found`."""
    result = kwic_search(view, query, mode, settings, scope, sort, near, limit, ctx)
    result["hits"] = kwic_lines(view, result.pop("found"), context)
    return result


def _sort_levels(sort):
    """Sort levels as `[(position, by, desc)]`. A level is a position such as "R1" (sorted by its word, A to Z) or
    `{"pos": "R1", "by": "lemma", "desc": True}`; `by` is a key of `SORT_BY` ("freq" puts the most frequent value first),
    and `desc` reverses the order (Z to A, least frequent first, last in the text first)."""
    levels = []
    for lv in sort:
        if isinstance(lv, str):
            pos, by, desc = lv, "word", False
        elif isinstance(lv, dict):
            pos, by, desc = lv.get("pos"), lv.get("by", "word"), bool(lv.get("desc"))
        else:
            pos, by, desc = None, None, False
        if pos not in SORT_KEYS:
            raise QueryError(f"Can't sort by “{pos}”. Choose one of: {', '.join(SORT_KEYS)}.")
        if by not in SORT_BY:
            raise QueryError(f"Can't sort by “{by}”. Choose one of: {', '.join(SORT_BY)}.")
        levels.append((pos, by, desc))
    return levels


def _sort_hits(view, hits, levels):
    """Order hits by the levels, the first being the most important; ties keep the order of the text. Each level is one stable sort,
    applied from the least important to the most important, so that a reversed level can't upset the others."""
    order = {b: k for k, b in enumerate(view.books)}
    in_text = lambda h: (order[h["book"]], h["s"])
    for n, (pos, by, desc) in enumerate(levels):
        for h in hits:
            if pos != "book":
                h.setdefault("_v", {})[n] = _sort_value(view.bd[h["book"]], h, pos, by)
    hits.sort(key=in_text)
    for n in reversed(range(len(levels))):
        pos, by, desc = levels[n]
        if pos == "book":
            key = in_text
        elif by == "freq":
            freq = Counter(h["_v"][n] for h in hits)
            key = lambda h, n=n, freq=freq: (-freq[h["_v"][n]], h["_v"][n])
        else:
            key = lambda h, n=n: h["_v"][n]
        hits.sort(key=key, reverse=desc)


def _sort_tokens(bd, h, k):
    """The token positions a sort position refers to: the words of the hit itself ("key"), or the n-th word left (L1…) or right (R1…) of it (none if the book ends)."""
    iw = cindex(bd)["isword"]
    if k == "key":
        return [i for i in range(h["s"], h["e"] + 1) if iw[i]] or [h["s"]]
    side, n = k[0], int(k[1:])
    i = h["s"] if side == "L" else h["e"]
    step = -1 if side == "L" else 1
    found = 0
    while 0 <= i + step < bd.n_tokens:
        i += step
        if iw[i]:
            found += 1
            if found == n:
                return [i]
    return []


def _sort_value(bd, h, k, by):
    """What a hit is sorted on at position k: the lowercased word(s) (also what "freq" counts), their lemmas, POS tags or fine tags."""
    toks = _sort_tokens(bd, h, k)
    if by == "lemma":
        return " ".join(bd.lemma[i].lower() for i in toks)
    if by == "pos":
        return " ".join(bd.pos[i] for i in toks)
    if by == "tag":
        return " ".join(bd.tag[i] for i in toks)
    return bd.span_text(h["s"], h["e"]).lower() if k == "key" else " ".join(bd.word[i].lower() for i in toks)


def _ctx_test(b, bd, stream, mask, ctx, m2):
    """A test `(start, end) -> bool` for a hit: does a match of the context search (`m2`) lie wholly inside the hit's window? `ctx["left"]` /
    `ctx["right"]` words each side (stopping at the edge of the scope, and of the sentence if `ctx["within_sentence"]`), not counting the hit
    itself. With `ctx["exclude"]` the answer is reversed: keep hits that have none. The context search finds its matches over the whole
    book first (every one: leftmost, not overlapping, like any search), then each hit only asks whether one lies inside its window."""
    left, right, within, exclude = int(ctx.get("left", 5)), int(ctx.get("right", 5)), bool(ctx.get("within_sentence")), bool(ctx.get("exclude"))
    matches = m2.hits(b, stream, limit=len(stream))
    starts = [s for s, _, _ in matches]

    def test(j, e):
        lw, rw = _window(bd, stream, j, e, left, right, mask, within)
        spans = [(j - len(lw), j), (e, e + len(rw))]
        has = any(matches[i][1] <= hi for lo, hi in spans for i in range(bisect.bisect_left(starts, lo), bisect.bisect_left(starts, hi)))
        return has != exclude
    return test


def _near_test(bd, stream, mask, near, settings):
    """A test `(start, end) -> bool` for a hit: is `near["item"]` within its window? The item is compared as the list it
    came from spells it, so a word typed with capitals still finds the lowercased words unless Case sensitive is on."""
    unit, item = near.get("unit", "word"), str(near["item"])
    case = bool(settings.get("case"))
    if unit == "lemma" or (unit == "word" and not case):
        item = item.lower()
    left, right = int(near.get("left", 5)), int(near.get("right", 5))
    within = bool(near.get("within_sentence"))

    def test(j, e):
        lw, rw = _window(bd, stream, j, e, left, right, mask, within)
        return any(item_of(bd, stream[x], unit, case) == item for x in lw + rw)
    return test


def _window(bd, stream, j, e, left, right, mask, within):
    """Stream positions within `left` words before and `right` words after the hit (j, e); the window
    stops at the edge of the scope, and at the sentence's edge if `within`."""
    lw, rw = [], []
    s0 = bd.sent[stream[j]]
    x = j - 1
    while x >= 0 and len(lw) < left:
        t = stream[x]
        if (mask is not None and not mask[t]) or (within and bd.sent[t] != s0):
            break
        lw.append(x)
        x -= 1
    s1 = bd.sent[stream[e - 1]]
    x = e
    while x < len(stream) and len(rw) < right:
        t = stream[x]
        if (mask is not None and not mask[t]) or (within and bd.sent[t] != s1):
            break
        rw.append(x)
        x += 1
    return lw, rw


def context(view, b, tok, end=None):
    """The paragraph around a hit (shortened if very long), with the hit marked `k`."""
    bd = view.bd[b]
    if not 0 <= tok < bd.n_tokens:
        raise QueryError("That position is outside the book.")
    p0, p1 = bd.para_bounds[bd.para[tok]]
    if p1 - p0 > 400:
        p0, p1 = max(p0, tok - 150), min(p1, tok + 150)
    end = tok if end is None else end
    return {"title": view.title(b), "pos": round(100 * tok / max(1, bd.n_tokens), 1),
            "text": bd.span_text(p0, p1, [(tok, end, "k")])}


# ---------- word lists and n-grams ----------
def counts(view, books, scope, unit, settings, parts=10, flt=None, dispersion=True):
    """-> (total Counter of items, {book: Counter}, {item: Counter of counts per tenth of the text}, total tokens).
    With a word-type filter (see `token_test`) only the tokens that pass are counted as items, but the total and the tenths still
    refer to all words in scope, so rates and dispersion mean "per words of text" whatever is being counted.
    Without `dispersion` the tenths are not worked out (the third result is None): tools that don't show dispersion are quicker."""
    sc = as_scope(view, scope)
    case = settings.get("case")
    positions = {b: sc.words(b) for b in books}
    N = sum(len(p) for p in positions.values())
    total, per_book, part_counts = Counter(), {}, defaultdict(Counter) if dispersion else None
    k = 0                                                  # how many words of the text have been passed
    for b in books:
        bd = view.bd[b]
        keep = token_test(bd, flt)
        c = per_book[b] = Counter()
        for i in positions[b]:
            if keep is None or keep(i):
                item = item_of(bd, i, unit, case)
                c[item] += 1
                if dispersion:
                    part_counts[item][min(parts - 1, parts * k // N)] += 1
            k += 1
        total.update(c)
    return total, per_book, part_counts, N


def wordlist(view, scope=None, unit="word", settings=None, min_freq=1, min_range=1, limit=5000, flt=None):
    """Frequency list of words, lemmas, word_POS, word_POS_lemma or POS, with range (books it occurs in) and dispersion.
    `flt` (see `token_test`) lists only tokens of the chosen word types; rates stay per 1,000 words of the text in scope. A
    word_POS_lemma row also carries its `word`, `pos` and `lemma` as separate fields."""
    settings = settings or {}
    total, per_book, parts, N = counts(view, view.books, scope, unit, settings, flt=flt)
    listed = []
    for item, n in total.most_common():
        if n < min_freq:
            break
        if min_range <= 1 or sum(1 for c in per_book.values() if item in c) >= min_range:
            listed.append(item)
    rows = []
    for rank, item in enumerate(listed[:limit], 1):
        row = {"rank": rank, "item": item, "n": total[item], "per1k": 1000 * total[item] / N if N else 0,
               "range": sum(1 for c in per_book.values() if item in c), "d": juilland(parts[item])}
        if unit == "word_pos_lemma":
            row["word"], row["pos"], row["lemma"] = item.split("\t")
            row["item"] = "_".join(item.split("\t"))
        rows.append(row)
    return {"rows": rows, "types": len(total), "tokens": N, "kept": sum(total.values()), "listed": len(listed), "books": len(view.books)}


def ngrams(view, n_min=2, n_max=3, scope=None, unit="word", settings=None, min_freq=2, min_range=1,
           contains=None, position="any", within_sentence=True, limit=5000):
    """Runs of n_min..n_max consecutive words, most frequent first. `contains` keeps n-grams with a
    matching word (anywhere, or as the first or last word). Runs don't cross sentence ends (if
    `within_sentence`) or gaps in the scope (a narration stretch between two quotes, say)."""
    settings = settings or {}
    n_min = max(1, int(n_min))
    n_max = max(n_min, int(n_max))
    case = settings.get("case")
    cm = value_matcher(contains, settings.get("regex"), case, settings.get("wildcards", True)) if contains else None
    sc = as_scope(view, scope)
    total, rng = Counter(), Counter()                      # rng: n-gram -> the number of books it occurs in
    N = 0
    for b in view.books:
        bd = view.bd[b]
        pos = sc.words(b)
        N += len(pos)
        here = Counter()                                   # this book's n-grams, so the range can be counted without a set for each
        for run in _ngram_runs(bd, pos, sc.mask(b), within_sentence):
            sg = [item_of(bd, i, unit, case) for i in run]
            for n in range(n_min, n_max + 1):
                for k in range(len(sg) - n + 1):
                    g = sg[k:k + n]
                    if cm:
                        idx = [x for x, w in enumerate(g) if cm(w)]
                        if not idx or (position == "left" and 0 not in idx) or (position == "right" and n - 1 not in idx):
                            continue
                    here[" ".join(g)] += 1
        total.update(here)
        rng.update(here.keys())
    qualifying = [key for key, c in total.items() if c >= min_freq and rng[key] >= min_range]
    rows = [{"rank": rank, "item": key, "n": total[key], "per1k": 1000 * total[key] / N if N else 0, "range": rng[key], "size": key.count(" ") + 1}
            for rank, key in enumerate(heapq.nlargest(limit, qualifying, key=total.__getitem__), 1)]      # only the rows that will be shown are made
    return {"rows": rows, "listed": len(qualifying), "types": len(total), "tokens": N}


def _ngram_runs(bd, pos, mask, within_sentence):
    """The runs of consecutive in-scope words (lists of token positions) that n-grams are cut from. A run ends at the end of a sentence
    (if `within_sentence`) and wherever the scope has a gap between two words (a stretch of narration between two quotes, say)."""
    run, prev = [], None
    for i in pos:
        if run and ((within_sentence and bd.sent[i] != bd.sent[prev])
                    or (mask is not None and any(not mask[x] for x in range(prev + 1, i)))):
            yield run
            run = []
        run.append(i)
        prev = i
    if run:
        yield run


# ---------- collocates ----------
COLL_MEASURES = {"mi": "MI", "t": "T-score", "ll": "Log-likelihood", "logdice": "logDice", "mi3": "MI3", "n": "Frequency"}
COLL_NOTE = ("O is how often the collocate occurs within the window around the search term; L and R split it by side. "
             "E, the expected count, is (hits × collocate frequency × window size) ÷ tokens. MI = log₂(O/E). T-score = (O − E) ÷ √O. "
             "MI3 = log₂(O³/E). logDice = 14 + log₂(2O ÷ (hits + collocate frequency)). Log-likelihood uses a 2×2 table of the collocate "
             "inside and outside the windows (signed + when it occurs more than expected), with p from χ² at 1 degree of freedom. "
             "MI favours rare words and T-score frequent ones; logDice sits between. Frequencies count words in the chosen scope; "
             "the window stops at the scope's edge, and at the sentence's edge if chosen.")


def collocates(view, query, mode="simple", settings=None, scope=None, left=5, right=5, unit="word",
               min_freq=3, min_range=1, within_sentence=False, sort="mi", limit=3000, flt=None):
    """Words that occur near the search term more (or less) often than chance, with association measures.
    `flt` (see `token_test`) lists only collocates of the chosen word types. The figures of a collocate that passes are the same as
    without the filter, except that its corpus frequency counts only the tokens that pass too (so "run" as a verb is compared with
    all uses of "run" as a verb); the windows themselves are not changed."""
    settings = settings or {}
    m = Matcher(view, query, mode, settings)
    sc = as_scope(view, scope)
    total, per_book, _, N = counts(view, view.books, sc, unit, settings, flt=flt, dispersion=False)
    seen, seen_left, seen_right, rng = Counter(), Counter(), Counter(), defaultdict(set)
    nhits, wtok = 0, 0
    for b in view.books:
        bd = view.bd[b]
        isword = cindex(bd)["isword"]
        keep = token_test(bd, flt)
        stream = stream_of(view, b, settings)
        mask = sc.mask(b)
        inside = None if mask is None else (lambda j, e, mask=mask, stream=stream: all(mask[x] for x in stream[j:e]))
        for j, e, _ln in m.hits(b, stream, accept=inside):
            nhits += 1
            lw, rw = _window(bd, stream, j, e, left, right, mask, within_sentence)
            for win, side in ((lw, seen_left), (rw, seen_right)):
                for x in win:
                    t = stream[x]
                    if not isword[t]:
                        continue                                   # windows only count words
                    wtok += 1
                    if keep is not None and not keep(t):
                        continue                                   # a word of another type: in the window, but not listed
                    it = item_of(bd, t, unit, settings.get("case"))
                    seen[it] += 1
                    side[it] += 1
                    rng[it].add(b)
    window = left + right
    rows = []
    for it, o in seen.items():
        if o < min_freq or len(rng[it]) < min_range:
            continue
        fc = total.get(it, o)                                      # the collocate's frequency in the whole text
        E = nhits * fc * window / N if N else 0                    # how often chance would put it in the windows
        r = {"item": it, "n": o, "left": seen_left[it], "right": seen_right[it], "freq": fc, "range": len(rng[it])}
        r["mi"] = math.log2(o / E) if E > 0 else None
        r["mi3"] = math.log2(o ** 3 / E) if E > 0 else None
        r["t"] = (o - E) / math.sqrt(o) if o else None
        r["logdice"] = 14 + math.log2(2 * o / (nhits + fc)) if (nhits + fc) else None
        a, b_, c = o, max(0, fc - o), max(0, wtok - o)
        d = max(0, N - a - b_ - c)
        r["ll"] = _ll4(a, b_, c, d)
        r["p"] = stats.p_chi1(abs(r["ll"]))
        rows.append(r)
    key = sort if sort in COLL_MEASURES else "mi"
    rows.sort(key=lambda r: (r[key] if r[key] is not None else -1e9, r["n"]), reverse=True)
    for k, r in enumerate(rows):
        r["rank"] = k + 1
    return {"rows": rows[:limit], "hits": nhits, "tokens": N, "window_tokens": wtok, "listed": len(rows)}


def _ll4(a, b, c, d):
    """Signed log-likelihood of a 2×2 table (positive when cell a is larger than expected)."""
    n = a + b + c + d
    if n == 0:
        return 0.0
    cells = [(a, (a + b) * (a + c) / n), (b, (a + b) * (b + d) / n), (c, (c + d) * (a + c) / n), (d, (c + d) * (b + d) / n)]
    g = 2 * sum(o * math.log(o / e) for o, e in cells if o > 0 and e > 0)
    return g if a >= cells[0][1] else -g


# ---------- keywords ----------
def keywords(view, ref, scope=None, unit="word", settings=None, kw=None, min_range=1, ref_view=None, ref_counts=None):
    """Words more (or, with direction "both", also less) frequent in the target than in a reference:
    other books (`ref_view`, with `ref["scope"]`) or a reference file's counts (`ref_counts`)."""
    settings = settings or {}
    tgt, per_book, _, N = counts(view, view.books, scope, unit, settings, dispersion=False)
    if ref_counts is not None:
        rc = ref_counts
    elif ref_view is not None:
        rc, _, _, _ = counts(ref_view, ref_view.books, ref.get("scope") or scope, unit, settings, dispersion=False)
    else:
        raise QueryError("Choose a reference: other books or a reference file.")
    rows, summary = stats.keyness(tgt, rc, **dict(kw or {}))
    for r in rows:
        r["range"] = sum(1 for c in per_book.values() if r["item"] in c)
    rows = [r for r in rows if r["range"] >= min_range]
    for k, r in enumerate(rows):
        r["rank"] = k + 1
    summary.update(target_tokens=N, reference_tokens=sum(rc.values()), target_types=len(tgt), reference_types=len(rc))
    return {"rows": rows[:3000], "summary": summary}


# ---------- reference files ----------
CLITICS = ("n't", "'s", "'ll", "'re", "'ve", "'d", "'m")     # split off words, to match BookNLP's tokens


def tokenize(text):
    """Split plain text into lowercased words, splitting clitics (didn't -> did n't) like BookNLP does."""
    out = []
    for w in re.findall(r"[^\W_]+(?:[-'’][^\W_]+)*", text.replace("’", "'")):
        lw = w.lower()
        for c in CLITICS:
            if lw.endswith(c) and len(lw) > len(c):
                out.extend([lw[: -len(c)], c])
                break
        else:
            out.append(lw)
    return out


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?|\.\d+")


def _num(x):
    """A number from text with thousands commas, or None. Only digits count: "nan", "inf" and "1e5" are words, not numbers."""
    return float(x.replace(",", "")) if NUMBER.fullmatch(x) else None


def parse_wordlist(text):
    """Word list in AntConc's or a similar format (a word and a frequency per line, tab, comma or space
    separated, with or without a header) -> Counter, or None if the text isn't such a list."""
    lines = [l.rstrip("\r") for l in text.splitlines() if l.strip() and not l.startswith("#")]
    if not lines:
        return None
    sep = "\t" if "\t" in lines[0] else ("," if lines[0].count(",") >= 1 and len(lines[0].split(",")) <= 6 else None)
    split = (lambda l: [x.strip().strip('"') for x in l.split(sep)]) if sep else (lambda l: l.split())
    head = [h.lower() for h in split(lines[0])]
    word_col = freq_col = None
    word_names = ("type", "word", "item", "lemma", "token", "types")
    if any("freq" in h for h in head) and any(h in word_names for h in head):        # a header row
        word_col = next(k for k, h in enumerate(head) if h in word_names)
        freq_col = next(k for k, h in enumerate(head) if h.startswith("freq") or h == "frequency")
        lines = lines[1:]
    if word_col is None:                                                             # no header: most lines must be "word number(s)"
        rows = [split(l) for l in lines[:200]]
        good = sum(1 for r in rows if 2 <= len(r) <= 6 and any(_num(x) is not None for x in r)
                   and len(r) - sum(_num(x) is not None for x in r) == 1)
        if good < 0.9 * len(rows):
            return None
    out = Counter()
    for l in lines:
        r = split(l)
        if word_col is not None:
            if max(word_col, freq_col) >= len(r):
                continue
            w, f = r[word_col], _num(r[freq_col])
        else:
            words = [x for x in r if _num(x) is None]
            nums = [_num(x) for x in r if _num(x) is not None]
            if len(words) != 1 or not nums:
                continue
            w, f = words[0], nums[1] if len(nums) >= 2 else nums[0]      # "rank freq word": the second number is the frequency
        if f is not None and re.search(r"[^\W\d_]", w):          # an entry needs a letter, so "!!! 12345" isn't a list
            out[w.lower()] += int(f)
    return out or None


def make_reference(name, files):
    """Combine uploaded files (word lists or plain texts) into one reference: {name, files, kinds, tokens, types, counts}."""
    total, kinds = Counter(), Counter()
    for f in files:
        wl = parse_wordlist(f["text"])
        if wl is not None:
            total.update(wl)
            kinds["word list"] += 1
        else:
            total.update(tokenize(f["text"]))
            kinds["text"] += 1
    return {"name": name, "files": [f["name"] for f in files], "kinds": dict(kinds),
            "tokens": sum(total.values()), "types": len(total), "counts": dict(total)}
