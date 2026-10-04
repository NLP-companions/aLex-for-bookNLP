"""Reading a stored model: the model overview and the parts of one topic's page.

`overview` summarises a whole model. `Topic` wraps one topic of a stored model with the arrays
every per-topic tool needs, and `part_words` … `part_speech` compute the sections of a topic's
page. The helpers at the top (`share_of`, `group_rows`, `assoc`, `arc_of`, and the count
functions) are shared with `compare.py` and `uses.py`.

Two ideas recur:

* A document's **weight** for a topic is its share `theta[d, t]` (0…1). A topic's share of a
  group of documents is the average weight, weighted by the words each document keeps.
* To ask which entities or speakers a topic "draws in", each document counts as topic text to the
  extent of its weight: `assoc` compares an item's rate per 1,000 words in topic text with its
  rate elsewhere, and ranks by a log-likelihood. It is a ranking, not a significance test,
  because the weights are not independent observations.
"""
from __future__ import annotations

import operator
import re
from bisect import bisect_right
from collections import Counter

import numpy as np

from .. import dialogue as dl
from ..corpus import cindex
from ..narrative import _locate, _para_text, _seg_index, all_segments
from ..stats import compare
from . import store
from .errors import TopicError
from .model import dropped_tokens, kept_tokens, relevance, stop_set


# ---------- the model overview ----------
def overview(lib, mid):
    """Everything the model overview shows: settings, quality, and for each topic (biggest first) its words,
    share, share in each book, stability and strongest passages. `stale` lists books that changed since fitting."""
    m = store.load(mid)
    phi, theta = np.array(m["phi"]), np.array(m["theta"])
    vocab, freq = m["vocab"], np.array(m["freq"], float)
    docs, k = m["docs"], phi.shape[0]
    kept = np.array([d["kept"] for d in docs], float)
    share = (theta * kept[:, None]).sum(0) / max(kept.sum(), 1)
    rel = relevance(phi, freq)
    stale, books = [], {}
    for b in m["books"]:
        try:
            books[b] = lib.book(b)
            if books[b].n_tokens != m["tokens"].get(b):
                stale.append(m["titles"].get(b, b))
        except Exception:  # noqa: BLE001 - a book that is gone or unreadable is as good as changed
            stale.append(m["titles"].get(b, b))
    by_book = {}
    for b in m["books"]:
        idx = [i for i, d in enumerate(docs) if d["book"] == b]
        w = kept[idx]
        by_book[b] = ((theta[idx] * w[:, None]).sum(0) / max(w.sum(), 1)).tolist() if idx else [0.0] * k
    topics = []
    for t in range(k):
        passages = []
        for i in np.argsort(-theta[:, t])[:3]:
            d = docs[i]
            text = ""
            if d["book"] in books and not stale:                 # passages are only shown against unchanged books
                text = re.sub(r"\s+", " ", _para_text(books[d["book"]], d["start"], d["end"])).strip()
            passages.append({"book": d["book"], "title": m["titles"].get(d["book"], d["book"]), "start": d["start"], "end": d["end"],
                             "pos": d["pos_pct"], "weight": float(theta[i, t]), "text": text[:420] + ("…" if len(text) > 420 else "")})
        topics.append({
            "id": t, "label": m["labels"][t], "share": float(share[t]),
            "words": [{"w": vocab[j], "p": float(phi[t, j])} for j in np.argsort(-phi[t])[:30]],
            "distinctive": [{"w": vocab[j], "p": float(phi[t, j]), "n": int(freq[j])} for j in np.argsort(-rel[t])[:30]],
            "coherence": m["metrics"]["coherence"][t], "stability": m["metrics"]["stability"][t],
            "by_book": {b: float(v[t]) for b, v in by_book.items()}, "passages": passages,
            "top_docs": int((theta[:, t] >= 0.5).sum()),
        })
    order = sorted(range(k), key=lambda t: -topics[t]["share"])
    return {"id": m["id"], "name": m["name"], "created": m["created"], "cfg": m["cfg"], "books": m["books"], "titles": m["titles"],
            "docs": len(docs), "vocab": len(vocab), "words": int(kept.sum()),
            "metrics": {key: v for key, v in m["metrics"].items() if key not in ("coherence", "stability")},
            "stale": stale, "topics": [topics[t] for t in order]}


# ---------- one topic of a model ----------
def _check_overlap(view, m):
    """For tools that work on whichever of the model's books are selected: those must be unchanged."""
    if not any(b in view.bd for b in m["books"]):
        raise TopicError("None of the model's books are in the selected books.")
    changed = [m["titles"].get(b, b) for b in m["books"] if b in view.bd and view.bd[b].n_tokens != m["tokens"].get(b)]
    if changed:
        raise TopicError(", ".join(changed) + " changed since the model was fitted. Fit it again.")


def _check_all_books(view, m):
    """For tools that need every book of the model, unchanged."""
    missing = [m["titles"].get(b, b) for b in m["books"] if b not in view.bd]
    changed = [m["titles"].get(b, b) for b in m["books"] if b in view.bd and view.bd[b].n_tokens != m["tokens"].get(b)]
    if missing or changed:
        raise TopicError("The model can't be read against the books: " + ", ".join(missing + changed)
                         + (" not found." if missing and not changed else " changed since it was fitted. Fit the model again."))


class Topic:
    """One topic (`t`) of a stored model, with the arrays every per-topic tool uses:
    phi, theta, docs, vocab, freq; `w` the topic's weight in each document; `kept` the counted words per document;
    `share_all` each topic's share of the whole model; `by_book` book -> document indexes.
    Given a `view`, the books it needs are checked against the model (`strict`: all of the model's books must be in the
    view; otherwise only those that are must be unchanged)."""

    def __init__(self, mid, t=0, view=None, strict=True):
        self.m = m = store.load(mid)
        self.phi, self.theta = np.array(m["phi"]), np.array(m["theta"])
        try:
            t = operator.index(t)                       # accepts numpy integers, refuses 1.5 and "2"
        except TypeError:
            raise TopicError("Unknown topic.") from None
        if not 0 <= t < self.phi.shape[0]:
            raise TopicError("Unknown topic.")
        self.t, self.k = t, self.phi.shape[0]
        self.docs, self.cfg = m["docs"], m["cfg"]
        self.vocab, self.freq = m["vocab"], np.array(m["freq"], float)
        self.kept = np.array([d["kept"] for d in self.docs], float)
        self.w = self.theta[:, t]
        self.share_all = (self.theta * self.kept[:, None]).sum(0) / max(self.kept.sum(), 1)
        self.view = view
        if view is not None:
            (_check_all_books if strict else _check_overlap)(view, m)
        self.by_book, self._starts = {}, {}
        for i, d in enumerate(self.docs):
            self.by_book.setdefault(d["book"], []).append(i)

    def words(self):
        """The topic's 30 most probable words."""
        return {self.vocab[j] for j in np.argsort(-self.phi[self.t])[:30]}

    def doc_at(self, b, tok):
        """Index of the model's document holding token `tok` of book `b`, or None."""
        if b not in self._starts:
            idx = self.by_book.get(b, [])
            self._starts[b] = ([self.docs[i]["start"] for i in idx], idx)
        starts, idx = self._starts[b]
        pos = bisect_right(starts, tok) - 1
        if pos < 0:
            return None
        return idx[pos] if tok <= self.docs[idx[pos]]["end"] else None


# ---------- shared computations ----------
def share_of(w, kept, idx):
    """A topic's share of the documents `idx`: weights `w` averaged, weighted by the words kept."""
    idx = list(idx)
    if not idx:
        return 0.0
    return float((w[idx] * kept[idx]).sum() / max(kept[idx].sum(), 1))


def mann_whitney(x, y):
    """Two-sided Mann–Whitney U p-value for weights x against y; None when either side has fewer than five documents.
    Identical values throughout are no difference at all: p = 1 (newer scipy says nan, older says 1)."""
    if len(x) < 5 or len(y) < 5:
        return None
    try:
        from scipy.stats import mannwhitneyu
        p = float(mannwhitneyu(x, y, alternative="two-sided").pvalue)
        return 1.0 if p != p else p
    except ValueError:                                           # all values identical
        return None


def group_rows(T, groups):
    """For groups of documents (label -> document indexes): the topic's share in each, against all books, with a
    Mann–Whitney p of the group's weights against the rest -> (rows, overall share)."""
    overall = share_of(T.w, T.kept, range(len(T.docs)))
    rows = []
    for label, idx in groups.items():
        if not idx:
            continue
        inside = set(idx)
        rest = [i for i in range(len(T.docs)) if i not in inside]
        share = share_of(T.w, T.kept, idx)
        rows.append({"group": label, "docs": len(idx), "share": share, "ratio": share / overall if overall else None,
                     "mean": float(T.w[idx].mean()), "p": mann_whitney(T.w[idx], T.w[rest]) if rest else None,
                     "words": int(T.kept[idx].sum())})
    return rows, overall


def assoc(T, per_item, exposure):
    """Rank items by how much more (or less) often they occur in this topic's text than elsewhere.
    per_item: item -> {document index: count}; exposure: the words each document offers (per document).
    -> rows {id, count, in_topic, share, rate_in, rate_out, ratio, ll}; `ll` is a signed log-likelihood."""
    n1 = float((T.w * exposure).sum())                 # exposure in topic text
    n2 = float(((1 - T.w) * exposure).sum())           # ...and elsewhere
    rows = []
    for item, cnt in per_item.items():
        total = sum(cnt.values())
        a = float(sum(T.w[i] * c for i, c in cnt.items()))
        r = compare(a, total - a, n1, n2)
        rows.append({"id": item, "count": total, "in_topic": a, "share": a / total if total else 0.0,
                     "rate_in": 1000 * a / n1 if n1 else 0.0, "rate_out": 1000 * (total - a) / n2 if n2 else 0.0,
                     "ratio": (a / n1) / ((total - a) / n2) if n1 and n2 and total - a > 1e-9 and a > 0 else None, "ll": r["ll"]})
    return rows


def arc_of(T, view, seg):
    """The topic's share of the words in each chapter or slice of the view's books; each document goes to the segment
    holding its middle -> (segments, info, values in %, number of documents per segment). Books of the view
    that aren't in the model, and segments without a document, give None."""
    segs, info = all_segments(view, seg)
    idx = _seg_index(segs)
    num, den, cnt = {}, {}, {}
    for i, d in enumerate(T.docs):
        k = _locate(idx, d["book"], (d["start"] + d["end"]) // 2)
        if k is not None:
            num[k] = num.get(k, 0) + T.w[i] * T.kept[i]
            den[k] = den.get(k, 0) + T.kept[i]
            cnt[k] = cnt.get(k, 0) + 1
    return segs, info, [100 * num[k] / den[k] if den.get(k) else None for k in range(len(segs))], [cnt.get(k, 0) for k in range(len(segs))]


def unit_counts(T, view, u):
    """Mentions of one entity (a `Unit`) in each of the model's documents: {document index: count}."""
    cnt = {}
    for b, co in u.members:
        bd = view.bd[b]
        for mi in bd.groups[co].mentions:
            i = T.doc_at(b, bd.mentions[mi][1])
            if i is not None:
                cnt[i] = cnt.get(i, 0) + 1
    return cnt


def entity_counts(T, view, min_mentions=5, types=None):
    """Mentions of every entity (of the given types) in each document: unit id -> {document index: count},
    keeping entities with at least `min_mentions` in the model's documents."""
    per = {}
    for uid, u in view.units.items():
        if types and u.type not in types:
            continue
        cnt = unit_counts(T, view, u)
        if sum(cnt.values()) >= min_mentions:
            per[uid] = cnt
    return per


def speech_counts(T, view):
    """Words per document (W) and dialogue words per document (D), spoken words per speaker unit and narration
    words per narrator role, each as {document index: count} -> (W, D, speakers, narrators)."""
    n = len(T.docs)
    W, D = np.zeros(n), np.zeros(n)
    speakers, narrators = {}, {}
    for b in T.m["books"]:
        if b not in view.bd:
            continue
        bd = view.bd[b]
        ci = cindex(bd)
        roles = {}                                        # paragraph -> narrator role
        for i in T.by_book.get(b, []):
            d = T.docs[i]
            for j in range(d["start"], d["end"] + 1):
                if not ci["isword"][j]:
                    continue
                W[i] += 1
                if ci["in_quote"][j]:
                    D[i] += 1
                    u = dl.unit_of(view, b, ci["speaker"][j])
                    if u:
                        speakers.setdefault(u, {})
                        speakers[u][i] = speakers[u].get(i, 0) + 1
                else:
                    pid = bd.para[j]
                    if pid not in roles:
                        roles[pid] = dl.narrator_of(view, b, pid)[0]
                    narrators.setdefault(roles[pid], {})
                    narrators[roles[pid]][i] = narrators[roles[pid]].get(i, 0) + 1
    return W, D, speakers, narrators


# ---------- the parts of a topic's page ----------
def part_words(mid, t):
    """The 300 most probable words with what the relevance slider needs: probability p, the word's overall
    probability pw, its count n, and its exclusive share (how much of the word's weight in the model is this topic's)."""
    T = Topic(mid, t)
    weight = T.phi * T.share_all[:, None]                 # topics × words: the weight of each word in each topic
    excl = weight[t] / np.maximum(weight.sum(0), 1e-12)
    pw = T.freq / T.freq.sum()
    return {"form": T.cfg["form"], "words": [{"w": T.vocab[j], "p": float(T.phi[t, j]), "pw": float(pw[j]), "n": int(T.freq[j]),
                                            "excl": float(excl[j])} for j in np.argsort(-T.phi[t])[:300]]}


def part_where(view, mid, t, seg):
    """Where the topic occurs: a strip of document weights per book, its arc over chapters or slices, and per-book shares."""
    T = Topic(mid, t, view)
    strips = []
    for b in T.m["books"]:
        n = max(1, T.m["tokens"][b])
        strips.append({"book": b, "title": T.m["titles"][b],
                       "docs": [{"a": 100 * T.docs[i]["start"] / n, "b": 100 * (T.docs[i]["end"] + 1) / n, "w": float(T.w[i]),
                                 "start": T.docs[i]["start"], "end": T.docs[i]["end"]} for i in T.by_book.get(b, [])]})
    segs, info, values, counts = arc_of(T, view, seg)
    rows, overall = group_rows(T, {T.m["titles"][b]: T.by_book.get(b, []) for b in T.m["books"]})
    return {"strips": strips, "max": float(T.w.max()), "segments": segs, "info": info,
            "arc": {"name": "Share of the words (%)", "values": values, "counts": counts}, "books": rows, "overall": overall}


def part_groups(view, lib, mid, t):
    """The topic's share by series, author, year and tag (a book with several tags counts in each)."""
    T = Topic(mid, t, view)
    fields = {"series": {}, "author": {}, "year": {}, "tag": {}}
    for b in T.m["books"]:
        meta = lib.meta(b)
        for f in ("series", "author", "year"):
            fields[f].setdefault(str(meta[f]) or "(none)", []).append(b)
        for tag in meta["tags"] or ["(no tag)"]:
            fields["tag"].setdefault(tag, []).append(b)
    out = {}
    for f, groups in fields.items():
        rows, _ = group_rows(T, {label: [i for b in bs for i in T.by_book.get(b, [])] for label, bs in sorted(groups.items())})
        out[f] = [{**r, "books": [T.m["titles"][b] for b in groups[r["group"]]]} for r in rows]
    return {"fields": out, "overall": share_of(T.w, T.kept, range(len(T.docs)))}


def part_passages(view, mid, t, n=8, book=None):
    """The documents where the topic is strongest (optionally in one book), with the topic's top words marked `tw`
    (marks as in BookData.span_text)."""
    T = Topic(mid, t, view)
    stop, words = stop_set(T.cfg), T.words()
    order = [i for i in np.argsort(-T.w) if not book or T.docs[i]["book"] == book][:max(1, min(30, n))]
    out, drops = [], {}
    for i in order:
        d = T.docs[i]
        b = d["book"]
        bd = view.bd[b]
        if b not in drops:
            drops[b] = dropped_tokens(bd, T.cfg["drop"])
        marks = [(j, j, "tw") for j, w in kept_tokens(bd, d, T.cfg, stop, drops[b]) if w in words]
        text = re.sub(r"[ \n\t]+", " ", bd.span_text(d["start"], d["end"], marks)).strip()
        out.append({"book": b, "title": T.m["titles"][b], "start": d["start"], "end": d["end"], "pos": d["pos_pct"],
                    "weight": float(T.w[i]), "marked": len(marks), "text": text})
    return {"passages": out, "words": sorted(words)}


def part_entities(view, mid, t, min_mentions=5):
    """Entities ranked by how much more (or less) often they are mentioned in this topic's text (see `assoc`)."""
    T = Topic(mid, t, view)
    rows = assoc(T, entity_counts(T, view, min_mentions), np.array([d["words"] for d in T.docs], float))
    for r in rows:
        u = view.units[r["id"]]
        r.update(name=u.name, type=u.type, linked=u.linked)
    rows.sort(key=lambda r: -r["ll"])
    return {"rows": rows, "min": min_mentions}


def part_speech(view, mid, t, min_words=50):
    """Dialogue against narration in the topic's text, where its top words fall, and the speakers and narrators it draws in."""
    T = Topic(mid, t, view)
    W, D, spk, nar = speech_counts(T, view)
    top_words, stop = T.words(), stop_set(T.cfg)
    cfg_all = {**T.cfg, "text": "all"}                   # where the vocabulary occurs, whatever text the model used
    uses = [0, 0]                                        # top-word uses in narration, in dialogue
    for b in T.m["books"]:
        bd = view.bd[b]
        in_quote = cindex(bd)["in_quote"]
        drop = dropped_tokens(bd, T.cfg["drop"])
        for i in T.by_book.get(b, []):
            for j, w in kept_tokens(bd, T.docs[i], cfg_all, stop, drop):
                if w in top_words:
                    uses[1 if in_quote[j] else 0] += 1
    spk = {u: c for u, c in spk.items() if sum(c.values()) >= min_words}
    nar = {r: c for r, c in nar.items() if sum(c.values()) >= min_words}
    speakers = assoc(T, spk, D)
    for r in speakers:
        r["name"] = view.name_of(r["id"])
        r["linked"] = r["id"] in view.units
    narrators = assoc(T, nar, W - D)
    for r in narrators:
        r["unit"] = None if r["id"].startswith("nar:anon:") else r["id"][4:]
        r["name"] = dl.role_name(view, r["id"])
    for rows, key in ((speakers, "id"), (narrators, "unit")):
        seen = Counter(r["name"] for r in rows)
        for r in rows:            # tell apart people who share a name only because they aren't linked across books
            uid = r[key] or ""
            if seen[r["name"]] > 1 and uid.startswith("e:"):
                r["name"] += f" ({view.title(uid.split(':')[1])})"
        rows.sort(key=lambda r: -r["ll"])
    return {"dialogue": {"strong": float((T.w * D).sum() / max((T.w * W).sum(), 1e-9)), "base": float(D.sum() / max(W.sum(), 1)),
                         "vocab_dialogue": uses[1], "vocab_narration": uses[0], "vocab_share": uses[1] / max(1, sum(uses))},
            "speakers": speakers, "narrators": narrators, "min": min_words}
