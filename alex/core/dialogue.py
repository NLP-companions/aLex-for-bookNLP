"""Dialogue: who speaks, how speech is introduced, how characters speak, conversations and
estimated addressees, and who narrates.

Per book, every quote becomes a **record** (`book_dialogue`); records are combined across the
selected books through the view, so your minimum-mention settings and links apply as elsewhere.

A record is a dict:
    qi, start, end     the quote's index in `bd.quotes` and its first and last token
    speaker            the speaker's coreference group (None if BookNLP found none)
    speakers           the groups the speaker stands for: (speaker,), or with the book read with plural groups on, a plural
                       speaker and its members (`BookData.stands_for`); () for none. Counts per speaker use these
    n, tokens, words, lemmas   the words inside the quote (punctuation and quotation marks left out)
    question, exclaim  the quote contains ? or !
    verb, verb_tok, verb_method, adverbs   the verb that introduces the quote ("said") and its manner adverbs
    vocative           coreference groups addressed by name inside the quote
    conv, addressee, addr_method   the conversation the quote belongs to, and who it is (estimated) addressed to
    key, fixed         a stable key for the quote, and your correction of its addressees (if any)

Sections: helpers · per-book dialogue · speech verb and vocatives · across books · statistics ·
lists (overview, verbs, voice, conversations, quotes, entity) · narration and narrators.

Your corrections (annotations.json) are keyed by opening words rather than token numbers, so
they survive a re-export that shifts positions; see `keys`.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from statistics import median

from . import stats
from .bookdata import QUOTE_MARKS, ekey
from .corpus import cindex

BOUNDARY_BEFORE = {",", ";", ":", "—", "--", "-", "!", "?", "."}
VOC_LEAD = {"my", "dear", "o", "oh", "ah", "well", "yes", "no", "now", "look", "listen", "sir", "madam"}
AFTER_VOC = {",", "!", "?", ".", ";", "—", "--", ":"}
STOP_ADV = {"then", "again", "now", "so", "also", "still", "there", "here", "too", "just", "even", "only", "back", "up",
            "down", "out", "away", "on", "off", "in", "once", "at", "all", "not", "n't", "never", "ever", "yet", "however"}
SPEECH_VERBS = {"say", "ask", "reply", "answer", "cry", "exclaim", "whisper", "shout", "mutter", "murmur", "add", "continue", "observe",
                "remark", "explain", "repeat", "respond", "call", "declare", "insist", "protest", "suggest", "admit", "inquire", "enquire",
                "demand", "retort", "laugh", "sigh", "groan", "snap", "growl", "gasp", "stammer", "whimper", "sob", "scream", "yell", "roar",
                "bellow", "hiss", "breathe", "begin", "resume", "interrupt", "agree", "rejoin", "return", "ejaculate", "state", "announce",
                "report", "tell", "go", "chuckle", "grumble", "plead", "urge", "warn", "object", "query", "question", "confess", "concede",
                "comment", "note", "mumble", "drawl", "chirp", "squeak", "shriek", "thunder", "wail", "moan", "sneer", "scoff", "cry out"}
QUESTION_VERBS = {"ask", "inquire", "enquire", "query", "question", "demand", "wonder"}          # imply a question even without a "?"
EXCLAIM_VERBS = {"exclaim", "cry", "cry out", "shout", "scream", "yell", "roar", "bellow", "shriek", "gasp", "ejaculate", "thunder", "wail"}
SENTENCE_TYPES = ("question", "exclaim", "statement")
FIRST_SG = {"i", "me", "my", "mine", "myself"}
SECOND = {"you", "your", "yours", "yourself", "yourselves", "thee", "thou", "thy", "thine", "ye"}
FIRST_PL = {"we", "us", "our", "ours", "ourselves"}
ADDR_METHODS = {
    "named": "Named in the quote",
    "reply": "Reply to the previous speaker",
    "continues": "Speaker keeps talking to the same person",
    "next": "The next speaker (opening line)",
    "yours": "Set by you",
    "yours_all": "Set by you: everyone present",
}
VERB_METHODS = {"subject": "Speaker is the verb's subject", "near": "Nearest verb outside the quote"}
NOTES = {
    "words": "Words spoken are the tokens inside a quote other than punctuation and quotation marks. Share of dialogue divides them by all words inside quotes in the same books, including quotes BookNLP didn't attribute.",
    "verbs": ("The verb that introduces a quote is found from the mention BookNLP used to attribute it (in .quotes): when that mention "
              "is the subject of a verb, as in “said Holmes” or “he cried”, that verb is taken. Otherwise the nearest verb "
              "within 8 tokens after the quote, or before it, is taken if it is a speech verb (say, ask, whisper…) or BookNLP gives it the communication supersense. Adverbs are the -ly words and other manner adverbs attached to that verb "
              "(“said quietly”), leaving out words like then, again and now."),
    "addressee": ("You can correct any quote's addressees (one or several, or everyone present in the conversation); your corrections replace the estimate and are marked as yours. "
                  "Otherwise: BookNLP doesn't record who a quote is addressed to, so it is estimated, in this order: a person named inside the quote "
                  "as a form of address, either a name at the start, after a comma or after my/dear/O (“Watson, come here”, “Come here, Watson.”) "
                  "or a description after my/dear/O or closing the quote after a comma (“My dear fellow, …”, “…, sir.”); otherwise, within a conversation, the previous speaker "
                  "if someone else; if the speaker simply continues, the same person as before; for an opening line, the next speaker. "
                  "Quotes with none of these have no addressee. Each estimate keeps its method, so you can check and filter them."),
    "conversations": ("A conversation is a run of quotes with no more than the set number of narration words between one quote and the next, "
                      "unless you start a new conversation at a quote or join a conversation to the one before. Its participants are its speakers, "
                      "plus any listeners you add, minus any you remove."),
    "style": ("Words per quote is the mean. Questions and exclamations count quotes containing ? or !, per 100 quotes. "
              "I, you and we are per 1,000 words spoken (I/me/my/mine/myself, you/your…/thee/thou, we/us/our…). "
              "Word length is the mean in letters. MATTR is the moving-average type-token ratio over windows of 100 words "
              "(Covington & McFall 2010), a vocabulary-variety measure that, unlike the plain ratio, doesn't fall as more is said. "
              "Speakers with fewer than 100 words spoken get the plain type-token ratio, shown in brackets."),
}


def keys(bd):
    """Stable keys for quotes and paragraphs, from their opening words, so your
    corrections survive re-exports that shift token numbers."""
    cache = bd.cache("keys")
    if cache:
        return cache
    qk, seen = {}, Counter()
    for qi in sorted(range(len(bd.quotes)), key=lambda i: bd.quotes[i]["start"]):
        q = bd.quotes[qi]
        t = " ".join(bd.word[i].lower() for i in range(q["start"], min(q["end"] + 1, q["start"] + 30, bd.n_tokens))
                     if bd.word[i] not in QUOTE_MARKS)[:120]
        seen[t] += 1
        qk[qi] = f"{t}#{seen[t]}"
    pk, seen = {}, Counter()
    for pid, (s, e) in sorted(bd.para_bounds.items()):
        t = " ".join(bd.word[i].lower() for i in range(s, min(e + 1, s + 15)))[:80]
        seen[t] += 1
        pk[pid] = f"{t}#{seen[t]}"
    cache.update(q=qk, q_rev={v: i for i, v in qk.items()}, p=pk, p_rev={v: i for i, v in pk.items()})
    return cache


def ann_sig(ann):
    """A string identifying a set of corrections, for cache keys ("" when there are none)."""
    return json.dumps(ann, sort_keys=True) if ann else ""


def book_dialogue(bd, gap_words=100, ann=None):
    """All of one book's dialogue: {recs, convs, words, dlg_words, time, bins_w, starts}.

    `convs` groups the records into conversations: a new one starts when more than `gap_words`
    narration words lie between two quotes, unless you joined or split there. Each quote then gets an
    estimated addressee, in this order: a person named inside the quote (`named`); the previous
    speaker if someone else (`reply`); the same person as before if the speaker carries on
    (`continues`); for an opening line, the next speaker (`next`). `time` is the share of words in
    quotes in each fiftieth of the book; `bins_w` is that fiftieth's own word count, the denominator
    `scoped_time` reuses to find one scope's own share of the same slices. Results are cached on the
    book per (gap, corrections)."""
    cache = bd.cache("dialogue")
    ck = (gap_words, ann_sig({k: ann.get(k) for k in ("splits", "merges", "addressees")} if ann else None))
    hit = cache.get(ck)                    # .get, not `in` then []: another request may empty the cache in between
    if hit is not None:
        return hit
    if len(cache) >= 3:              # the records hold a copy of every quote's words: keep few settings' worth
        cache.clear()
    ann = ann or {}
    splits, merges = set(ann.get("splits", [])), set(ann.get("merges", []))
    fixed = ann.get("addressees", {})
    qkeys = keys(bd)["q"]
    n = bd.n_tokens
    isw = cindex(bd)["isword"]
    pref = [0]
    for f in isw:
        pref.append(pref[-1] + f)
    order = sorted(range(len(bd.quotes)), key=lambda i: bd.quotes[i]["start"])
    recs = []
    for qi in order:
        q = bd.quotes[qi]
        s, e = q["start"], q["end"]
        toks = [i for i in range(s, e + 1) if isw[i]]
        words = [bd.word[i].lower() for i in toks]
        verb, vmethod = _speech_verb(bd, q)
        adv = []
        if verb is not None:
            adv = [bd.lemma[x].lower() for x in bd.children.get(verb, [])
                   if bd.dep[x] == "advmod" and bd.pos[x] == "ADV" and bd.word[x].lower() not in STOP_ADV and not (s <= x <= e)]
        recs.append({
            "qi": qi, "start": s, "end": e, "speaker": q["char"], "speakers": bd.stands_for(q["char"]), "n": len(toks), "tokens": toks,
            "words": words, "lemmas": [bd.lemma[i].lower() for i in toks],
            "question": any(bd.word[i] == "?" for i in range(s, e + 1)),
            "exclaim": any(bd.word[i] == "!" for i in range(s, e + 1)),
            "verb": bd.lemma[verb].lower() if verb is not None else None, "verb_tok": verb, "verb_method": vmethod,
            "adverbs": adv, "mention": q.get("mstart"),
            "vocative": _vocative(bd, qi, q),
            "para": bd.para[s], "pos": s / max(1, n),
        })
    # conversations and addressees
    conv, prev = -1, None
    convs = []
    for r in recs:
        r["key"] = qkeys[r["qi"]]
        r["fixed"] = fixed.get(r["key"])
        gap = pref[r["start"]] - pref[prev["end"] + 1] if prev else None
        if prev is None or (gap > gap_words and r["key"] not in merges) or r["key"] in splits:
            conv += 1
            convs.append([])
        r["conv"] = conv
        convs[conv].append(r)
        prev = r
    for cq in convs:
        for i, r in enumerate(cq):
            sp = r["speaker"]
            r["addressee"], r["addr_method"] = None, None
            voc = [c for c in r["vocative"] if c != sp]
            if voc:
                r["addressee"], r["addr_method"] = voc[0], "named"
                continue
            if sp is None:
                continue
            if i > 0:
                p = cq[i - 1]
                if p["speaker"] is not None and p["speaker"] != sp:
                    r["addressee"], r["addr_method"] = p["speaker"], "reply"
                    continue
                if p["speaker"] == sp and p.get("addressee") is not None:
                    r["addressee"], r["addr_method"] = p["addressee"], "continues"
                    continue
            nxt = next((x["speaker"] for x in cq[i + 1:] if x["speaker"] is not None and x["speaker"] != sp), None) if i == 0 else None
            if nxt is not None:
                r["addressee"], r["addr_method"] = nxt, "next"
    # dialogue share across the book, in 50 slices
    bins_w, bins_d = [0] * 50, [0] * 50
    inq = [False] * n
    for r in recs:
        for t in r["tokens"]:
            inq[t] = True
    for i in range(n):
        if isw[i]:
            b = min(49, int(50 * i / max(1, n)))
            bins_w[b] += 1
            bins_d[b] += inq[i]
    out = {"recs": recs, "convs": convs, "words": pref[-1], "dlg_words": sum(r["n"] for r in recs),
           "time": [100 * d / w if w else 0 for d, w in zip(bins_d, bins_w)], "bins_w": bins_w, "starts": [r["start"] for r in recs]}
    cache[ck] = out
    return out


def _speech_verb(bd, q):
    """The verb that introduces a quote -> (token, method) or (None, None).

    method "subject": BookNLP's attributing mention is the subject of a verb ("said Holmes", "he cried");
    "near": otherwise the nearest verb within 8 tokens after the quote, or before it, in the same paragraph, if it
    is a speech verb or has the communication supersense."""
    s, e = q["start"], q["end"]
    ms, me = q.get("mstart"), q.get("mend")
    if ms is not None and me is not None and 0 <= ms < bd.n_tokens and not (s <= ms <= e):
        h = bd._mention_head(ms, min(me, bd.n_tokens - 1))
        for _ in range(4):
            if bd.dep[h] == "conj" and bd.head[h] != h:
                h = bd.head[h]
            else:
                break
        g = bd.head[h]
        if bd.dep[h] in ("nsubj", "nsubjpass") and g != h and bd.pos[g] == "VERB":
            return g, "subject"
    for rng in (range(e + 1, min(e + 9, bd.n_tokens)), range(s - 1, max(s - 9, -1), -1)):
        for i in rng:
            if i in bd.quote_at or bd.para[i] != bd.para[s]:
                break
            if bd.pos[i] == "VERB":
                if bd.lemma[i].lower() in SPEECH_VERBS or bd.ss.get(i) == "verb.communication":
                    return i, "near"
                break
    return None, None


def _vocative(bd, qi, q):
    """Coreference groups addressed by name inside quote qi: a person mentioned as a form of address,
    either a name at the start, after a comma or after my/dear/O, or a description after my/dear/O or
    closing the quote after a comma ("My dear fellow, …", "…, sir.")."""
    s, e = q["start"], q["end"]
    first = next((i for i in range(s, e + 1) if bd.word[i] not in QUOTE_MARKS), s)
    out = []
    for c, prop, mi in bd.quote_mentions.get(qi, ()):
        m = bd.mentions[mi]
        if prop == "PRON" or m[4] != "PER":
            continue
        ms, me = m[1], m[2]
        b, a = ms - 1, me + 1
        led = b >= s and bd.word[b].lower() in VOC_LEAD
        after_comma = b >= s and bd.word[b] == ","
        after_ok = a > e or bd.word[a] in AFTER_VOC or bd.word[a] in QUOTE_MARKS
        if not after_ok:
            continue
        if prop == "PROP" and (ms <= first or led or after_comma):
            out.append(c)
        elif prop == "NOM" and bd.word[ms].lower() not in ("a", "an", "the", "this", "that", "these", "those", "some", "any") and (led or (after_comma and (a > e or bd.word[a] in QUOTE_MARKS or bd.word[a] in (".", "!", "?")))):
            out.append(c)
    return out


# ---------- across the selected books ----------
def bdlg(view, b):
    """Book b's dialogue under the view's settings and your corrections (cached on the view)."""
    cache = view.cache.setdefault("dialogue", {})
    if b not in cache:
        cache[b] = book_dialogue(view.bd[b], view.lib.state["settings"].get("conv_gap", 100), view.lib.ann["books"].get(b))
    return cache[b]


def all_recs(view):
    """Every quote record of the view's books, as (book, record)."""
    for b in view.books:
        for r in bdlg(view, b)["recs"]:
            yield b, r


def scoped_time(view, pairs):
    """Like `book_dialogue`'s "time" (the dialogue-share curve, 50 slices per book), but only the given (book, record)
    pairs' own words count towards it, as a share of each slice's total words (`bdlg`'s "bins_w") — one scope's own
    dialogue share across each book, for In-Depth Who Speaks' Search and Compare. Books the scope never speaks in
    are left out."""
    by_book = defaultdict(list)
    for b, r in pairs:
        by_book[b].append(r)
    out = []
    for b, recs in by_book.items():
        n = view.bd[b].n_tokens
        bins_d = [0] * 50
        for r in recs:
            for t in r["tokens"]:
                bins_d[min(49, int(50 * t / max(1, n)))] += 1
        bins_w = bdlg(view, b)["bins_w"]
        out.append({"book": b, "title": view.title(b), "values": [100 * d / w if w else 0 for d, w in zip(bins_d, bins_w)]})
    return out


def participants(view, b, conv):
    """Speakers in the conversation, plus listeners you added, minus those you removed."""
    d = bdlg(view, b)
    cq = d["convs"][conv]
    sp = []
    for r in cq:
        for u in speaker_units(view, b, r):
            if u not in sp:
                sp.append(u)
    edit = view.lib.ann["books"].get(b, {}).get("participants", {}).get(cq[0]["key"], {})
    out = [u for u in sp if u not in edit.get("remove", [])] + [u for u in edit.get("add", []) if u not in sp]
    return out, sp, edit


def addressees(view, b, r):
    """(list of unit ids, method) for a quote: your correction if any, else the estimate (a plural addressee with its members
    when plural groups count for them)."""
    if r.get("fixed") is not None:
        if r["fixed"] == ["*"]:
            sus = speaker_units(view, b, r)
            return [u for u in participants(view, b, r["conv"])[0] if u not in sus], "yours_all"
        return list(r["fixed"]), "yours"
    return list(dict.fromkeys(unit_of(view, b, a) for a in view.bd[b].stands_for(r["addressee"]))), r["addr_method"]


def unit_of(view, b, coref):
    """The unit id of a coreference group: its counted unit, else the single-book id; None for no speaker."""
    if coref is None:
        return None
    return view.member_unit.get((b, coref)) or ekey(b, coref)


def speaker_units(view, b, r):
    """The unit ids a quote counts for as speaker: its speaker's, and a plural speaker's members' when plural groups count
    for them (see `speakers`); [] for an unattributed quote."""
    return list(dict.fromkeys(unit_of(view, b, c) for c in r["speakers"]))


def said_by(mem, b, r):
    """Whether a quote of book b counts as spoken by one of the members `mem` ((book, coref) pairs)."""
    return any((b, c) in mem for c in r["speakers"])


def sentence_type(r, weigh_verb=False):
    """A quote's sentence type, one of `SENTENCE_TYPES`: "question" or "exclaim" from its own `?`/`!` (`r["question"]`/
    `r["exclaim"]`), else "statement" — unless `weigh_verb`, when a speech verb that implies one (asked, exclaimed…)
    decides it instead, for a quote whose own punctuation doesn't already say so."""
    if r["question"]:
        return "question"
    if r["exclaim"]:
        return "exclaim"
    if weigh_verb and r.get("verb") in QUESTION_VERBS:
        return "question"
    if weigh_verb and r.get("verb") in EXCLAIM_VERBS:
        return "exclaim"
    return "statement"


def _filter_type(pairs, types, weigh_verb):
    """Keep only (book, record) pairs of one of `types` (see `sentence_type`); `pairs` unchanged if `types` is empty."""
    if not types:
        return pairs
    types = set(types)
    return [(b, r) for b, r in pairs if sentence_type(r, weigh_verb) in types]


def recs_for(view, spec):
    """Quotes spoken by the members of spec, or, for {"kind": "narration", "id": ...},
    the narration of that narrator (a role id, a unit id, or "all")."""
    if spec.get("kind") == "narration":
        rid = spec.get("id", "all")
        books = set(spec.get("books") or [])
        want = rid if rid.startswith("nar:") or rid == "all" else "nar:" + rid
        pairs = [(b, r) for b, r in narration_recs(view) if (want == "all" or r["role"] == want) and (not books or b in books)]
        label = "all narration" if want == "all" else role_name(view, want)
        if books:
            label += " in " + view.books_label(books)
        return pairs, label
    mem, label, _ = view.resolve(spec)
    return [(b, r) for b, r in all_recs(view) if said_by(mem, b, r)], label


def mattr(words, window=100):
    """Moving-average type-token ratio (Covington & McFall 2010) -> (value, reliable).
    Averages the type-token ratio of every window of `window` words, so it doesn't fall as more is
    said. Under `window` words it is the plain ratio, marked not reliable (False)."""
    if not words:
        return None, False
    if len(words) < window:
        return len(set(words)) / len(words), False
    counts = Counter(words[:window])
    total = len(counts)
    for i in range(window, len(words)):
        counts[words[i]] += 1
        counts[words[i - window]] -= 1
        if counts[words[i - window]] == 0:
            del counts[words[i - window]]
        total += len(counts)
    return total / ((len(words) - window + 1) * window), True


def style(pairs):
    """How the given (book, record) pairs speak: words per quote, questions, exclamations, I/you/we per 1,000 words, word length and MATTR."""
    words = [w for b, r in pairs for w in r["words"]]
    nq, nw = len(pairs), len(words)
    m, ok = mattr(words)
    wc = Counter(words)
    per = lambda s: 1000 * sum(wc[w] for w in s) / nw if nw else 0
    return {"quotes": nq, "words": nw, "per_quote": nw / nq if nq else 0,
            "median_quote": median([r["n"] for b, r in pairs]) if pairs else 0,
            "questions": 100 * sum(r["question"] for b, r in pairs) / nq if nq else 0,
            "exclaims": 100 * sum(r["exclaim"] for b, r in pairs) / nq if nq else 0,
            "i": per(FIRST_SG), "you": per(SECOND), "we": per(FIRST_PL),
            "wordlen": sum(len(w) for w in words) / nw if nw else 0, "mattr": m, "mattr_ok": ok}


def overview(view):
    """The Dialogue page's overview: figures per book, the dialogue-share curves and a row per speaker."""
    gap = view.lib.state["settings"].get("conv_gap", 100)
    books, time = [], []
    all_dlg = 0
    for b in view.books:
        d = bdlg(view, b)
        recs = d["recs"]
        att = sum(r["speaker"] is not None for r in recs)
        books.append({"book": b, "title": view.title(b), "words": d["words"], "dialogue": d["dlg_words"],
                      "share": 100 * d["dlg_words"] / d["words"] if d["words"] else 0, "quotes": len(recs),
                      "attributed": 100 * att / len(recs) if recs else 0, "conversations": len(d["convs"]),
                      "speakers": len({c for r in recs for c in r["speakers"]}),
                      "addressed": 100 * sum(bool(addressees(view, b, r)[0]) for r in recs) / len(recs) if recs else 0})
        time.append({"book": b, "title": view.title(b), "values": d["time"]})
        all_dlg += d["dlg_words"]
    by_unit = defaultdict(list)
    addressed = Counter()
    for b, r in all_recs(view):
        for u in speaker_units(view, b, r) or [None]:
            by_unit[u].append((b, r))
        for a in addressees(view, b, r)[0]:
            addressed[a] += 1
    rows = []
    for u, pairs in by_unit.items():
        if u is None or u not in view.units:
            continue
        st = style(pairs)
        verbs = Counter(r["verb"] for b, r in pairs if r["verb"])
        nv = sum(verbs.values())
        rows.append({"id": u, "name": view.units[u].name, "type": view.units[u].type, "tags": view.units[u].tags,
                     "books": len({b for b, r in pairs}), "quotes": st["quotes"], "words": st["words"],
                     "share": 100 * st["words"] / all_dlg if all_dlg else 0, "per_quote": st["per_quote"],
                     "addressed": addressed.get(u, 0),
                     "said": 100 * verbs.get("say", 0) / nv if nv else None,
                     "top_verbs": ", ".join(v for v, _ in verbs.most_common(4))})
    rows.sort(key=lambda r: -r["words"])
    unatt = by_unit.get(None, [])
    below = sum(len(p) for u, p in by_unit.items() if u is not None and u not in view.units)
    return {"books": books, "time": time, "speakers": rows, "dialogue_words": all_dlg,
            "unattributed": {"quotes": len(unatt), "words": sum(r["n"] for b, r in unatt)},
            "below_min": below, "gap": gap}


def verbs(view, spec=None, kw=None, types=None, weigh_verb=False):
    """Speech verbs and adverbs overall, or for one speaker/group with what's distinctive.
    `types` keeps only quotes of the given sentence types (see `sentence_type`), on every side."""
    pairs = _filter_type(list(all_recs(view)), types, weigh_verb)
    allv, alla, spk = Counter(), Counter(), defaultdict(set)
    manner = Counter()
    for b, r in pairs:
        if r["verb"]:
            allv[r["verb"]] += 1
            spk[r["verb"]].update(speaker_units(view, b, r))
            for a in r["adverbs"]:
                alla[a] += 1
                manner[f"{r['verb']} {a}"] += 1
    nq = len(pairs)
    out = {"quotes": nq, "with_verb": sum(allv.values()),
           "methods": dict(Counter(r["verb_method"] for b, r in pairs if r["verb_method"])),
           "verbs": [{"item": v, "n": n, "pct": 100 * n / nq if nq else 0, "speakers": len(spk[v] - {None})} for v, n in allv.most_common(200)],
           "adverbs": [{"item": a, "n": n} for a, n in alla.most_common(100)],
           "manner": [{"item": a, "n": n} for a, n in manner.most_common(100)]}
    if spec:
        mem, label, _ = view.resolve(spec)
        tv, rv, ta = Counter(), Counter(), Counter()
        for b, r in pairs:
            if not r["verb"]:
                continue
            if said_by(mem, b, r):
                tv[r["verb"]] += 1
                for a in r["adverbs"]:
                    ta[a] += 1
            elif r["speakers"]:
                rv[r["verb"]] += 1
        rows, summary = stats.keyness(tv, rv, **(kw or {}))
        summary.update(target=label, reference="all other speakers")
        tot = sum(tv.values())
        out["target"] = {"label": label, "verbs": [{"item": v, "n": n, "pct": 100 * n / tot} for v, n in tv.most_common(100)],
                         "adverbs": [{"item": a, "n": n} for a, n in ta.most_common(50)], "total": tot,
                         "distinctive": rows[:200], "summary": summary}
    return out


def voice(view, target, reference, unit="word", kw=None, types=None, weigh_verb=False):
    """Compare the vocabulary of a target (speaker, group or narrator) with a reference ("others" = all other speakers): -> style figures for both and keywords.
    `types` keeps only quotes (or narration paragraphs) of the given sentence types (see `sentence_type`) on both sides."""
    tp, tlabel = recs_for(view, target)
    record = lambda b, r: (b, r["qi"], r.get("para"))         # a quote, or a paragraph of narration: what the two sides must not share
    tset = {record(b, r) for b, r in tp}
    if reference.get("kind") == "others":
        rp = [(b, r) for b, r in all_recs(view) if record(b, r) not in tset
              and any(u in view.units for u in speaker_units(view, b, r))]
        rlabel = "all other speakers"
    else:
        rp, rlabel = recs_for(view, reference)
        rp = [(b, r) for b, r in rp if record(b, r) not in tset]
    tp, rp = _filter_type(tp, types, weigh_verb), _filter_type(rp, types, weigh_verb)
    key = "lemmas" if unit == "lemma" else "words"
    tc = Counter(w for b, r in tp for w in r[key])
    rc = Counter(w for b, r in rp for w in r[key])
    rows, summary = stats.keyness(tc, rc, **(kw or {}))
    summary.update(target=tlabel, reference=rlabel, unit=unit)
    return {"target": {"label": tlabel, **style(tp)}, "reference": {"label": rlabel, **style(rp)},
            "rows": rows[:300], "summary": summary}


def _quotes_by_speaker(view, types=None, weigh_verb=False):
    """{counted speaker unit: [(book, record)]} for the quotes (of the given sentence types, see `sentence_type`) whose speaker is
    in the selection."""
    by_unit = defaultdict(list)
    for b, r in _filter_type(list(all_recs(view)), types, weigh_verb):
        for u in speaker_units(view, b, r):
            if u in view.units:
                by_unit[u].append((b, r))
    return by_unit


def _each_once(by_unit):
    """The (book, record) pairs of a `_quotes_by_speaker` table, each quote once however many speakers it counts for."""
    return list({(b, r["qi"]): (b, r) for ps in by_unit.values() for b, r in ps}.values())


def style_table(view, min_words=0, types=None, weigh_verb=False):
    """The speaking-style figures for every speaker with at least `min_words` words, and for all speakers together.
    `types` keeps only quotes of the given sentence types (see `sentence_type`)."""
    by_unit = _quotes_by_speaker(view, types, weigh_verb)
    rows = []
    for u, pairs in by_unit.items():
        st = style(pairs)
        if st["words"] < min_words:
            continue
        rows.append({"id": u, "name": view.units[u].name, "type": view.units[u].type, **st})
    rows.sort(key=lambda r: -r["words"])
    return {"rows": rows, "all": style(_each_once(by_unit))}


def conversations(view, spec=None, limit=2000):
    """One row per conversation (optionally only those involving the spec's members) -> (rows, total)."""
    mem = view.resolve(spec)[0] if spec else None
    mem_units = {view.member_unit.get(m) for m in mem} if mem is not None else None
    out = []
    for b in view.books:
        d = bdlg(view, b)
        for ci, cq in enumerate(d["convs"]):
            spk = Counter(u for r in cq for u in speaker_units(view, b, r) or [None])
            parts, _, edit = participants(view, b, ci)
            if mem is not None and not (any(said_by(mem, b, r) for r in cq) or any(u in mem_units for u in parts)):
                continue
            names = [view.name_of(u) for u in parts]
            first = cq[0]
            out.append({"book": b, "title": view.title(b), "conv": ci, "pos": round(100 * first["pos"], 1), "tok": first["start"], "qi": first["qi"],
                        "quotes": len(cq), "words": sum(r["n"] for r in cq), "speakers": len([u for u in spk if u]),
                        "listeners": len([u for u in edit.get("add", [])]), "edited": bool(edit) or any(r["fixed"] is not None for r in cq),
                        "participants": ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else ""),
                        "unattributed": spk.get(None, 0),
                        "opening": " ".join(first["words"][:14]) + ("…" if first["n"] > 14 else "")})
    return out[:limit], len(out)


def quotes(view, f, limit=400):
    """Filtered quote records with text. f: speaker (spec), addressee (unit id, or a list of them), verb, word, lemma,
    book, conv, q (text contains), attributed ('yes'/'no'), addr_method, types (sentence types to keep, see
    `sentence_type`) and weigh_verb (let a speech verb decide a quote's type too, not only its own punctuation)."""
    mem = view.resolve(f["speaker"])[0] if f.get("speaker") else None
    q = (f.get("q") or "").lower().strip()
    types, weigh_verb = f.get("types"), bool(f.get("weigh_verb"))
    out, total = [], 0
    for b, r in all_recs(view):
        if f.get("book") and b != f["book"]:
            continue
        if f.get("conv") is not None and (b != f.get("book") or r["conv"] != f["conv"]):
            continue
        if mem is not None and not said_by(mem, b, r):
            continue
        if types and sentence_type(r, weigh_verb) not in types:
            continue
        if f.get("attributed") == "yes" and r["speaker"] is None or f.get("attributed") == "no" and r["speaker"] is not None:
            continue
        addrs, meth = addressees(view, b, r)
        want = f.get("addressee")                                  # one unit id, or a list of them (any of them will do)
        if want and not any(a in addrs for a in ([want] if isinstance(want, str) else want)):
            continue
        if f.get("addr_method") and meth != f["addr_method"] and not (f["addr_method"] == "yours" and meth == "yours_all"):
            continue
        if f.get("verb") and r["verb"] != f["verb"]:
            continue
        if f.get("adverb") and f["adverb"] not in r["adverbs"]:
            continue
        if f.get("word") and f["word"] not in r["words"]:
            continue
        if f.get("lemma") and f["lemma"] not in r["lemmas"]:
            continue
        bd = view.bd[b]
        if q and q not in bd.span_text(r["start"], r["end"]).lower():
            continue
        total += 1
        if len(out) >= limit:
            continue
        # context: the sentences from the quote (and its verb/speaker mention) outwards
        pts = [r["start"], r["end"]] + [x for x in (r["verb_tok"], r["mention"])
                                        if x is not None and (abs(x - r["start"]) < 60 or abs(x - r["end"]) < 60)]
        s0 = bd.sentence_of(min(pts))[0]
        e0 = bd.sentence_of(max(pts))[1]
        marks = [(r["start"], r["end"], "q")]
        if r["mention"] is not None and not (r["start"] <= r["mention"] <= r["end"]):
            for mi in bd.mentions_in(r["mention"], r["mention"]):
                m = bd.mentions[mi]
                marks.append((m[1], m[2], "m"))
                break
        if r["verb_tok"] is not None:
            marks.append((r["verb_tok"], r["verb_tok"], "k"))
        hl = f.get("word") or f.get("lemma")
        if hl:
            key = "words" if f.get("word") else "lemmas"
            for t, w in zip(r["tokens"], r[key]):
                if w == hl:
                    marks.append((t, t, "o"))
        marks.sort(key=lambda m: (m[0], -(m[1] - m[0])))
        su = unit_of(view, b, r["speaker"])
        out.append({"book": b, "title": view.title(b), "pos": round(100 * r["pos"], 1), "conv": r["conv"], "qi": r["qi"], "tok": r["start"],
                    "speaker": view.name_of(su) if su else None, "speaker_id": su,
                    "addressee": "; ".join(view.name_of(a) for a in addrs) or None, "addressees": [{"id": a, "name": view.name_of(a)} for a in addrs],
                    "addr_method": meth, "verb": r["verb"], "adverbs": ", ".join(r["adverbs"]), "type": sentence_type(r, weigh_verb),
                    "words": r["n"], "text": bd.span_text(s0, e0, marks), "quote": bd.span_text(r["start"], r["end"])})
    return {"total": total, "shown": len(out), "items": out}


def entity(view, target, types=None, weigh_verb=False):
    """Everything the entity page's Speech section shows for a unit, or for a group (a virtual unit from `View.group_unit`);
    `target` is that unit or a unit id. None if it isn't in the selection. For a group the entities' quotes are pooled, "talks to"
    and "spoken to by" leave out the group's own members, and `within` counts the quotes they address to each other.
    `types` keeps only quotes of the given sentence types (see `sentence_type`) in the style figures, presence and
    `time` (but not "talks to" / "spoken to by", nor the book totals "share" is measured against)."""
    u = view.units.get(target) if isinstance(target, str) else target
    if not u:
        return None
    parts = set(u.parts)
    spec = {"kind": "group", "ids": list(u.parts)}
    pairs, _ = recs_for(view, spec)
    pairs = _filter_type(pairs, types, weigh_verb)
    total_dlg = {b: bdlg(view, b)["dlg_words"] for b in view.books}          # words in quotes, per book
    dialogue_words = sum(total_dlg.values())
    st = style(pairs)
    per_book = []
    for b in view.books:
        bp = [(bb, r) for bb, r in pairs if bb == b]
        if not bp and b not in u.books:
            continue
        v = Counter(r["verb"] for _, r in bp if r["verb"])
        s = style(bp)
        per_book.append({"book": b, "title": view.title(b), "quotes": s["quotes"], "words": s["words"],
                         "share": 100 * s["words"] / total_dlg[b] if total_dlg.get(b) else 0, "per_quote": s["per_quote"],
                         "said": 100 * v.get("say", 0) / sum(v.values()) if v else None,
                         "top_verbs": ", ".join(x for x, _ in v.most_common(4))})
    to, by = Counter(), Counter()
    to_m = defaultdict(Counter)
    within = 0
    for b, r in all_recs(view):
        sus = speaker_units(view, b, r)
        mine = any(su in parts for su in sus)
        addrs, meth = addressees(view, b, r)
        for au in addrs:
            if au in sus:                                  # a plural speaker "talking to" one of its own members
                continue
            if mine and au in parts:
                within += 1
            elif mine:
                to[au] += 1
                to_m[au][meth] += 1
            elif au in parts:
                by.update(sus)
    presence = []
    for b in view.books:
        bins = view.bd[b].presence_bins(r["start"] for bb, r in pairs if bb == b)
        if any(bins):
            presence.append({"book": b, "title": view.title(b), "bins": bins})
    vb = verbs(view, spec, None, types, weigh_verb)
    roles = {"nar:" + p for p in parts}
    narr = [(b, r) for b, r in narration_recs(view) if r["role"] in roles]
    nst = style(narr) if narr else None
    return {"narrating": {"style": nst, "paragraphs": len(narr), "books": sorted({b for b, r in narr}),
                          "exceptions": sum(r["exception"] for b, r in narr)} if narr else None,
            "style": st, "all_style": style(_each_once(_quotes_by_speaker(view))), "per_book": per_book, "time": scoped_time(view, pairs),
            "share": 100 * st["words"] / dialogue_words if dialogue_words else 0,
            "talks_to": [{"id": k, "name": view.name_of(k), "n": n, "methods": dict(to_m[k])} for k, n in to.most_common(30)],
            "addressed_by": [{"id": k, "name": view.name_of(k), "n": n} for k, n in by.most_common(30)],
            "within": within if len(parts) > 1 else None,
            "verbs": vb["target"]["verbs"], "adverbs": vb["target"]["adverbs"], "presence": presence}


def addressee_edges(view, methods=None):
    """(speaker unit, addressee unit) -> quotes, for the network."""
    w = Counter()
    for b, r in all_recs(view):
        sus = [view.member_unit.get((b, c)) for c in r["speakers"]]
        addrs, meth = addressees(view, b, r)
        if methods and meth not in methods:
            continue
        for su in sus:
            for au in addrs:
                if su and au in view.units and au not in sus:
                    w[(su, au)] += 1
    return w


# ---------- narration and narrators ----------
def narrator_of(view, b, pid):
    """(role id, exception?) for a paragraph. Role ids: nar:<unit id> or nar:anon:<book>, translated to a
    narrator-link id (nl:<n>) if you've linked that role with another (`Library.link_narrators`).
    Precedence: a paragraph exception (`para_narrators`) first, then a chapter exception (`chapter_narrators`, the
    whole chapter the paragraph falls in — see `narrative.chapter_key_of`), then the book's default narrator, else
    anonymous."""
    from .narrative import chapter_key_of
    ann = view.lib.ann["books"].get(b, {})
    pkey = keys(view.bd[b])["p"].get(pid)
    exc = ann.get("para_narrators", {}).get(pkey)
    if not exc:
        exc = ann.get("chapter_narrators", {}).get(chapter_key_of(view, b, pid))
    if exc:
        rid, is_exc = ("nar:anon:" + b if exc == "anon" else "nar:" + exc), True
    else:
        d = ann.get("narrator")
        rid, is_exc = ("nar:" + d if d else "nar:anon:" + b), False
    return view.narrator_link_of.get(rid, rid), is_exc


def role_name(view, rid):
    """A narrator role's (or narrator link's) display name: "Watson, narrating", "Narrator of <book>", or, once
    you've linked two or more roles as one narrator (`Library.link_narrators`), your name for the link, else the
    first named member's own name, else "N narrators, linked"."""
    if rid.startswith("nl:"):
        link = view.lib.state["narrator_links"][rid[3:]]
        if link.get("name"):
            return link["name"]
        named = [m for m in link["members"] if not m.startswith("nar:anon:")]
        return role_name(view, named[0]) if named else f"{len(link['members'])} narrators, linked"
    if rid.startswith("nar:anon:"):
        return f"Narrator of {view.title(rid[9:])}"
    return f"{view.name_of(rid[4:])}, narrating"


def role_unit(rid):
    """The single unit id behind a narrator role, or None: an anonymous narrator, or a narrator link of several
    roles (`nl:<n>`), has no one underlying unit."""
    return None if rid.startswith("nar:anon:") or rid.startswith("nl:") else rid[4:]


def narration_recs(view):
    """One record per paragraph that has narration (words outside quotes), with its narrator role -> [(book, record)]."""
    out = []
    for b in view.books:
        bd = view.bd[b]
        sig = ann_sig({"b": {k: view.lib.ann["books"].get(b, {}).get(k) for k in ("narrator", "para_narrators", "chapter_narrators", "chapters")},
                       "nl": view.lib.state.get("narrator_links")})
        cache = bd.cache("narration")
        recs = cache.get(sig)
        if recs is None:
            cache.clear()
            ci = cindex(bd)
            recs = []
            for pid, (s, e) in sorted(bd.para_bounds.items()):
                toks = [i for i in range(s, e + 1) if ci["isword"][i] and not ci["in_quote"][i]]
                if not toks:
                    continue
                rid, exc = narrator_of(view, b, pid)
                recs.append({"qi": None, "para": pid, "start": s, "end": e, "n": len(toks), "tokens": toks,
                             "words": [bd.word[i].lower() for i in toks], "lemmas": [bd.lemma[i].lower() for i in toks],
                             "question": any(bd.word[i] == "?" and not ci["in_quote"][i] for i in range(s, e + 1)),
                             "exclaim": any(bd.word[i] == "!" and not ci["in_quote"][i] for i in range(s, e + 1)),
                             "role": rid, "exception": exc, "pos": s / max(1, bd.n_tokens)})
            cache[sig] = recs
        out.extend((b, r) for r in recs)
    return out


def _by_role(view):
    """The narration records grouped by narrator role -> {role id: [(book, record)]}."""
    by = defaultdict(list)
    for b, r in narration_recs(view):
        by[r["role"]].append((b, r))
    return by


def narrator_rows(view):
    """The narrator roles as rows for the entity list, type "NARR", most narration first. Same fields as an entity's row; `mentions` is the
    words narrated, `paragraphs` and `share` (of all narration) are extra, and a character's tags are carried over."""
    by = _by_role(view)
    total = sum(r["n"] for ps in by.values() for b, r in ps)
    rows = []
    for rid, pairs in by.items():
        words = sum(r["n"] for b, r in pairs)
        uid = role_unit(rid)
        rows.append({"id": rid, "type": "NARR", "name": role_name(view, rid), "tags": list(view.units[uid].tags) if uid in view.units else [],
                     "linked": rid.startswith("nl:"), "mentions": words, "books": sorted({b for b, r in pairs}), "paragraphs": len(pairs),
                     "share": 100 * words / total if total else 0})
    rows.sort(key=lambda r: -r["mentions"])
    return rows


def narrator_profile(view, rid):
    """Everything the entity page shows for a narrator role (`nar:<unit id>`, `nar:anon:<book>`, or `nl:<n>` once
    linked): how much they narrate and where, their style against all narration, what the same character says in
    dialogue (a narrator link has no one character, so this is empty for one), and a row per book. None if that role
    narrates nothing in the selection."""
    by = _by_role(view)
    pairs = by.get(rid)
    if not pairs:
        return None
    every = [p for ps in by.values() for p in ps]
    uid = role_unit(rid)
    st, all_st = style(pairs), style(every)
    books = [b for b in view.books if any(bb == b for bb, r in pairs)]
    spoken = style(recs_for(view, {"kind": "group", "ids": [uid]})[0]) if uid in view.units else None
    per_book, presence = [], []
    for b in books:
        bp = [(bb, r) for bb, r in pairs if bb == b]
        s, book_narration = style(bp), sum(r["n"] for bb, r in every if bb == b)
        per_book.append({"book": b, "title": view.title(b), "paragraphs": len(bp), "words": s["words"], "per_para": s["per_quote"],
                         "share": 100 * s["words"] / book_narration if book_narration else 0, "exceptions": sum(r["exception"] for bb, r in bp)})
        presence.append({"book": b, "title": view.title(b), "bins": view.bd[b].presence_bins(r["start"] for bb, r in bp)})
    words_in_books = sum(view.bd[b].n_words for b in books)
    return {"role": {"id": rid, "name": role_name(view, rid), "unit": uid if uid in view.units else None,
                     "unit_name": view.name_of(uid) if uid else None, "anonymous": uid is None and not rid.startswith("nl:"),
                     "linked": rid.startswith("nl:"),
                     "members": [{"id": m, "name": role_name(view, m), "unit": role_unit(m)}
                                 for m in view.lib.state["narrator_links"][rid[3:]]["members"]] if rid.startswith("nl:") else None,
                     "books": books},
            "words": st["words"], "paragraphs": len(pairs), "exceptions": sum(r["exception"] for b, r in pairs),
            "share": 100 * st["words"] / all_st["words"] if all_st["words"] else 0,
            "per1k": 1000 * st["words"] / words_in_books if words_in_books else 0,
            "style": st, "all_style": all_st, "spoken": spoken if spoken and spoken["quotes"] else None,
            "per_book": per_book, "presence": presence}


def narrators(view):
    """One row per narrator role: paragraphs, words and style figures, and what the same character says in dialogue."""
    by = _by_role(view)
    total = sum(r["n"] for ps in by.values() for b, r in ps)
    rows = []
    spoken = Counter()
    for b, r in all_recs(view):
        for u in speaker_units(view, b, r):
            spoken[u] += r["n"]
    for rid, pairs in by.items():
        st = style(pairs)
        uid = role_unit(rid)
        rows.append({"id": rid, "unit": uid, "name": role_name(view, rid), "books": len({b for b, r in pairs}),
                     "paragraphs": len(pairs), "exceptions": sum(r["exception"] for b, r in pairs), "words": st["words"],
                     "share": 100 * st["words"] / total if total else 0, "per_para": st["per_quote"],
                     "questions": st["questions"], "i": st["i"], "you": st["you"], "we": st["we"], "mattr": st["mattr"],
                     "mattr_ok": st["mattr_ok"], "spoken": spoken.get(uid, 0) if uid else None})
    rows.sort(key=lambda r: -r["words"])
    return {"rows": rows, "narration_words": total}
