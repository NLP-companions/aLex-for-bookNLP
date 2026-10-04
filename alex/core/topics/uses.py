"""Topics used elsewhere in the analyser: as series in Arcs, on an entity's page, and in the text view."""
from __future__ import annotations

import numpy as np

from ..stats import compare
from .compare import model_topics
from .errors import TopicError
from .model import dropped_tokens, kept_tokens, stop_set
from .page import Topic, arc_of, speech_counts, unit_counts


def _name(t):
    """A topic's name: your label, else its three most distinctive words."""
    return t["label"] or " · ".join(w["w"] for w in t["distinctive"][:3])


def arc_series(view, mid, ids, seg):
    """Topics as series for Arcs: each chosen topic's share of the words in every chapter or slice of the selected books
    (the five biggest topics if none are chosen). Works on whichever of the model's books are selected.
    -> {segments, series: [{id, name, values, counts}], info: {topics, model}}."""
    T0 = Topic(mid, 0, view, strict=False)
    listing = model_topics(T0)
    by_id = {t["id"]: t for t in listing}
    ids = [i for i in (ids or []) if i in by_id] or [t["id"] for t in sorted(listing, key=lambda t: -t["share"])[:5]]
    series, segs, info = [], [], {}
    for t in ids:
        segs, info, values, counts = arc_of(Topic(mid, t, view, strict=False), view, seg)
        series.append({"id": t, "name": _name(by_id[t]), "values": values, "counts": counts})
    info = {**info, "topics": [{"id": t["id"], "name": _name(t), "share": t["share"]} for t in sorted(listing, key=lambda t: -t["share"])],
            "model": {"id": T0.m["id"], "name": T0.m["name"], "books": [T0.m["titles"][b] for b in T0.m["books"] if b in view.bd]}}
    return {"segments": segs, "series": series, "info": info}


def entity_topics(view, mid, target, kind="mentions"):
    """Which topics an entity is mentioned in (`kind` "mentions") or speaks in ("speech"): for each topic the share of the
    entity's mentions (words) in its text, that against the topic's share of the whole model (lift), and a signed
    log-likelihood to rank by. `target` is a unit id or a `Unit`, which may be a group (counts are pooled over its entities)."""
    T = Topic(mid, 0, view, strict=False)
    u = view.units.get(target) if isinstance(target, str) else target
    if u is None:
        raise TopicError("This entity isn't in the selected books.")
    if kind == "speech":
        _, D, spk, _ = speech_counts(T, view)
        cnt, exposure = {}, D
        for part in u.parts:
            for i, c in spk.get(part, {}).items():
                cnt[i] = cnt.get(i, 0) + c
    else:
        cnt, exposure = unit_counts(T, view, u), np.array([d["words"] for d in T.docs], float)
    total = sum(cnt.values())
    if not total:
        return {"model": T.m["name"], "count": 0, "rows": [], "kind": kind}
    vec = np.zeros(len(T.docs))
    for i, c in cnt.items():
        vec[i] = c
    in_topic = T.theta.T @ vec                          # the entity's weighted count under each topic
    n1 = T.theta.T @ exposure                           # the words each topic's text offers
    n2 = exposure.sum() - n1
    listing = model_topics(T)
    rows = []
    for t in range(T.k):
        r = compare(float(in_topic[t]), float(total - in_topic[t]), float(n1[t]), float(n2[t]))
        share = float(in_topic[t] / total)
        rows.append({"id": t, "label": listing[t]["label"], "distinctive": listing[t]["distinctive"], "words": listing[t]["words"],
                     "topic_share": float(T.share_all[t]), "share": share,
                     "lift": share / float(T.share_all[t]) if T.share_all[t] else None, "ll": r["ll"]})
    rows.sort(key=lambda r: -r["ll"])
    return {"model": T.m["name"], "count": total, "rows": rows, "kind": kind, "books": [T.m["titles"][b] for b in T.m["books"] if b in view.bd]}


def reader_layer(view, b, mid, focus, s0, e0):
    """What the text view needs to show topics in tokens s0..e0 of book b: the topic of each counted top word
    (`tok_topic`), and the shares of the documents in view (`docs`). With `focus` a topic, only its top words are marked;
    otherwise each top word goes to the topic it mostly belongs to. Returns {"error": …} if the book isn't in the model or changed."""
    T = Topic(mid, 0)
    if b not in T.m["books"]:
        return {"error": "This book isn't in the model."}
    bd = view.bd[b]
    if T.m["tokens"].get(b) != bd.n_tokens:
        return {"error": "This book changed since the model was fitted. Fit it again."}
    focus = int(focus) if focus not in (None, "", "all") else None
    if focus is not None and not 0 <= focus < T.k:
        focus = None
    top_words = [{T.vocab[j] for j in np.argsort(-T.phi[t])[:30]} for t in range(T.k)]
    if focus is not None:
        wordmap = {w: focus for w in top_words[focus]}
    else:
        weight = T.phi * T.share_all[:, None]
        wordmap = {}
        for t in range(T.k):
            for j in np.argsort(-T.phi[t])[:30]:
                if int(np.argmax(weight[:, j])) == t:
                    wordmap[T.vocab[j]] = t
    stop, dropped = stop_set(T.cfg), dropped_tokens(bd, T.cfg["drop"])
    tok_topic, docs = {}, {}
    for i in T.by_book.get(b, []):
        d = T.docs[i]
        if d["end"] < s0 or d["start"] > e0:
            continue
        docs[i] = [[int(t), float(T.theta[i, t])] for t in np.argsort(-T.theta[i]) if T.theta[i, t] >= 0.02]
        for j, w in kept_tokens(bd, d, T.cfg, stop, dropped):
            if s0 <= j <= e0 and w in wordmap:
                tok_topic[j] = wordmap[w]
    return {"error": None, "model": {"id": T.m["id"], "name": T.m["name"]}, "focus": focus, "topics": model_topics(T), "docs": docs,
            "tok_topic": tok_topic, "doc_at": T.doc_at, "theta": T.theta}
