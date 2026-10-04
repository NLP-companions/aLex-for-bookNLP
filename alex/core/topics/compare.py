"""Comparing the topics of one model: a similarity map, two topics side by side, and grids
(topic × book or group, topic × character or speaker)."""
from __future__ import annotations

import math

import numpy as np

from ..narrative import _cluster
from ..stats import compare
from .errors import TopicError
from .model import relevance
from .page import Topic, arc_of, entity_counts, share_of, speech_counts


def model_topics(T):
    """A short description of every topic (label, share, top words, most distinctive words), for headings and menus."""
    rel = relevance(T.phi, T.freq)
    return [{"id": t, "label": T.m["labels"][t], "share": float(T.share_all[t]),
             "words": [T.vocab[j] for j in np.argsort(-T.phi[t])[:8]],
             "distinctive": [{"w": T.vocab[j]} for j in np.argsort(-rel[t])[:6]]} for t in range(T.k)]


# ---------- the map ----------
def _classical_mds(D):
    """Place items in two dimensions so that distances approximate the matrix D (classical / Torgerson scaling)
    -> (coordinates, share of the variation kept by each axis)."""
    n = len(D)
    if n < 3:
        return [[float(i), 0.0] for i in range(n)], [1.0, 0.0]
    J = np.eye(n) - 1.0 / n
    vals, vecs = np.linalg.eigh(-0.5 * J @ (D ** 2) @ J)
    order = np.argsort(-vals)[:2]
    lam = np.maximum(vals[order], 0)
    positive = np.maximum(vals, 0).sum()
    return (vecs[:, order] * np.sqrt(lam)).tolist(), (lam / positive).tolist() if positive > 0 else [0.0, 0.0]


def compare_map(mid):
    """Topic similarity two ways: by shared words (cosine of the word weights) and by appearing together
    (correlation of the document weights). For each: the similarity matrix, a cluster tree and 2-D coordinates.
    Also every pair with both similarities and the top words they share."""
    T = Topic(mid, 0)
    unit = T.phi / np.maximum(np.linalg.norm(T.phi, axis=1, keepdims=True), 1e-12)
    with np.errstate(all="ignore"):
        corr = np.nan_to_num(np.corrcoef(T.theta.T))
    np.fill_diagonal(corr, 1.0)
    bases = {}
    for name, S in (("words", unit @ unit.T), ("docs", corr)):
        D = np.clip(1 - S, 0, None)
        np.fill_diagonal(D, 0.0)
        D = (D + D.T) / 2
        coords, variance = _classical_mds(D)
        bases[name] = {"sim": np.round(S, 4).tolist(), "tree": _cluster(D.tolist(), "average"), "coords": coords, "variance": variance}
    tops = [set(np.argsort(-T.phi[t])[:20]) for t in range(T.k)]
    pairs = [{"a": a, "b": b, "words": bases["words"]["sim"][a][b], "docs": bases["docs"]["sim"][a][b],
              "shared": [T.vocab[j] for j in sorted(tops[a] & tops[b], key=lambda j: -min(T.phi[a, j], T.phi[b, j]))][:8]}
             for a in range(T.k) for b in range(a + 1, T.k)]
    return {"topics": model_topics(T), "bases": bases, "pairs": pairs}


# ---------- two topics side by side ----------
def pair_assoc(TA, TB, per_item, exposure):
    """Compare each item's rate in topic A's text with its rate in topic B's text (a document counts towards both
    by its weights) -> rows with the share and rate under each topic, their ratio, and a signed log-likelihood
    (positive: more in A's text)."""
    n1, n2 = float((TA.w * exposure).sum()), float((TB.w * exposure).sum())
    rows = []
    for item, cnt in per_item.items():
        total = sum(cnt.values())
        a = float(sum(TA.w[i] * c for i, c in cnt.items()))
        b = float(sum(TB.w[i] * c for i, c in cnt.items()))
        r = compare(a, b, n1, n2)
        rows.append({"id": item, "count": total, "share_a": a / total if total else 0.0, "share_b": b / total if total else 0.0,
                     "rate_a": 1000 * a / n1 if n1 else 0.0, "rate_b": 1000 * b / n2 if n2 else 0.0,
                     "ratio": (a / n1) / (b / n2) if n1 and n2 and a > 0 and b > 0 else None, "ll": r["ll"]})
    return rows


def compare_pair(view, mid, a, b, seg, min_mentions=5, min_words=50):
    """Two topics side by side: shared and exclusive words, similarity, arcs, per-book shares, and the entities and
    speakers that lean towards one or the other. A word is exclusive to a topic when it weighs more there, ranked by
    weight × log(ratio) so that both frequent and lopsided words count."""
    if a == b:
        raise TopicError("Choose two different topics.")
    TA, TB = Topic(mid, a, view), Topic(mid, b, view)
    pa, pb = TA.phi[a], TA.phi[b]
    candidates = sorted(set(np.argsort(-pa)[:80]) | set(np.argsort(-pb)[:80]))

    def lopsided(p, q, j):
        """How much more weight word j has under p than under q, times its weight (favours frequent and lopsided words)."""
        return p[j] * math.log(p[j] / max(q[j], 1e-12))

    def word(j, score):
        """A word with its weight in both topics."""
        return {"w": TA.vocab[j], "pa": float(pa[j]), "pb": float(pb[j]), "score": float(score)}

    only_a = sorted((j for j in candidates if pa[j] > pb[j]), key=lambda j: -lopsided(pa, pb, j))[:20]
    only_b = sorted((j for j in candidates if pb[j] > pa[j]), key=lambda j: -lopsided(pb, pa, j))[:20]
    shared = sorted(candidates, key=lambda j: -min(pa[j], pb[j]))[:20]
    words = {"shared": [word(j, min(pa[j], pb[j])) for j in shared],
             "a": [word(j, lopsided(pa, pb, j)) for j in only_a], "b": [word(j, lopsided(pb, pa, j)) for j in only_b]}
    with np.errstate(all="ignore"):
        corr = float(np.nan_to_num(np.corrcoef(TA.w, TB.w)[0, 1]))
    cosine = float(pa @ pb / max(np.linalg.norm(pa) * np.linalg.norm(pb), 1e-12))
    segs, info, values_a, counts_a = arc_of(TA, view, seg)
    _, _, values_b, counts_b = arc_of(TB, view, seg)
    books = [{"book": bk, "title": TA.m["titles"][bk], "a": share_of(TA.w, TA.kept, TA.by_book.get(bk, [])),
              "b": share_of(TB.w, TB.kept, TB.by_book.get(bk, []))} for bk in TA.m["books"]]
    entities = pair_assoc(TA, TB, entity_counts(TA, view, min_mentions), np.array([d["words"] for d in TA.docs], float))
    for r in entities:
        u = view.units[r["id"]]
        r.update(name=u.name, type=u.type)
    W, D, spk, _ = speech_counts(TA, view)
    speakers = pair_assoc(TA, TB, {u: c for u, c in spk.items() if sum(c.values()) >= min_words}, D)
    for r in speakers:
        r["name"] = view.name_of(r["id"])
        r["linked"] = r["id"] in view.units
    for rows in (entities, speakers):
        rows.sort(key=lambda r: -r["ll"])

    def dialogue_share(T):
        """The share of dialogue in the text where topic T is strong."""
        return float((T.w * D).sum() / max((T.w * W).sum(), 1e-9))

    return {"topics": model_topics(TA), "a": a, "b": b, "words": words,
            "similarity": {"words": cosine, "docs": corr, "overlap": len(set(np.argsort(-pa)[:20]) & set(np.argsort(-pb)[:20]))},
            "segments": segs, "info": info, "arc_a": {"values": values_a, "counts": counts_a}, "arc_b": {"values": values_b, "counts": counts_b},
            "books": books, "entities": entities, "speakers": speakers,
            "dialogue": {"a": dialogue_share(TA), "b": dialogue_share(TB), "base": float(D.sum() / max(W.sum(), 1))},
            "min_mentions": min_mentions, "min_words": min_words}


# ---------- grids ----------
GROUP_BY = ("book", "series", "author", "year", "tag")


def grid_groups(lib, mid, by="book"):
    """Every topic's share in each group of books (by book, series, author, year or tag): columns with a share per topic."""
    if by not in GROUP_BY:
        raise TopicError(f"Group by one of: {', '.join(GROUP_BY)}.")
    T = Topic(mid, 0)
    groups = {}
    for b in T.m["books"]:
        meta = lib.meta(b)
        labels = {"book": [T.m["titles"][b]], "series": [str(meta["series"]) or "(none)"], "author": [str(meta["author"]) or "(none)"],
                  "year": [str(meta["year"]) or "(none)"], "tag": meta["tags"] or ["(no tag)"]}[by]
        for lab in labels:
            g = groups.setdefault(lab, {"idx": [], "books": []})
            g["idx"] += T.by_book.get(b, [])
            g["books"].append(T.m["titles"][b])
    cols = []
    for lab, g in sorted(groups.items()):
        idx = g["idx"]
        w = T.kept[idx]
        cols.append({"label": lab, "docs": len(idx), "words": int(w.sum()), "books": g["books"],
                     "shares": ((T.theta[idx] * w[:, None]).sum(0) / max(w.sum(), 1)).tolist() if idx else [0.0] * T.k})
    return {"topics": model_topics(T), "columns": cols, "overall": T.share_all.tolist()}


def grid_items(view, mid, kind="mentions", types=None, min_count=10, limit=40):
    """For the most mentioned entities (or the speakers with most words): the share of each one's mentions (words)
    that falls in each topic's text. Every document's shares add up to 1, so each row adds up to 1 too."""
    T = Topic(mid, 0, view)
    if kind == "speakers":
        per = {u: c for u, c in speech_counts(T, view)[2].items() if sum(c.values()) >= min_count}
    else:
        per = entity_counts(T, view, min_count, set(types) if types else None)
    rows = []
    for u in sorted(per, key=lambda u: -sum(per[u].values()))[:max(1, min(200, int(limit)))]:
        unit = view.units.get(u)
        if kind == "speakers" and types and unit and unit.type not in types:
            continue
        vec = np.zeros(len(T.docs))
        for i, c in per[u].items():
            vec[i] = c
        rows.append({"id": u, "name": view.name_of(u), "type": unit.type if unit else None, "linked": unit is not None,
                     "count": int(vec.sum()), "shares": (vec @ T.theta / vec.sum()).tolist()})
    return {"topics": model_topics(T), "rows": rows, "overall": T.share_all.tolist(), "kind": kind}
