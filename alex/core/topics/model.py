"""Fitting a topic model: from the selected books to a stored model.

The steps, in order (`prepare` runs the first four, `build` all of them):

1. **settings**  `clean_cfg` turns whatever the browser sent into valid settings;
2. **documents** `make_docs` cuts every book into documents (chunks of about N words, groups of
   paragraphs, chapters or slices, or whole books);
3. **words**     `tokenize` keeps, per document, the words of the chosen parts of speech, dropping
   names (using BookNLP's mentions), general words and very rare or very common words;
4. **counts**    `matrix` builds the documents × words count matrix;
5. **fit**       `fit` runs NMF (on tf–idf) or LDA with a fixed seed -> document–topic shares
   (theta) and topic–word weights (phi), each row summing to 1;
6. **quality**   `npmi_coherence`, `diversity` and `stability` (re-fits with other seeds);
7. **store**     `build` saves everything as one JSON model (see store.py).

A document is `{book, start, end, words, pos_pct, [label], kept}`: `start`/`end` are token
positions in the book, `words` the words in it, `kept` the words the model actually counts.
"""
from __future__ import annotations

import hashlib
import math
import re
import time
import warnings

import numpy as np
from scipy import sparse

from ..corpus import cindex
from ..narrative import book_segments
from . import store
from .errors import TopicError

POS_CHOICES = ["NOUN", "VERB", "ADJ", "ADV", "PROPN"]
RECUR = 0.4   # a topic "recurs" when a re-run has a topic sharing at least 40% of its top 20 words
WORD = re.compile(r"^[^\W\d_][\w'’-]*$")     # what counts as a word: starts with a letter
# Very general words that swamp topics in fiction; can be switched off.
GENERIC = set("""thing things way ways time times day days moment moments sort kind lot bit side part sir mr mrs miss madam
one two something anything nothing everything someone anyone nobody man men woman women people fellow gentleman lady
be have do say go get make see know come take think look tell seem let give find want ask answer use put keep turn
begin leave call try hear feel show mean stand run hold bring appear help seem may might must shall will can could
would should good great little old new own last first other much many more most such same well ill right long
""".split())

DEFAULTS = {
    "unit": "chunk", "chunk_words": 300, "paras": 10, "seg": {"mode": "chapters", "n": 10, "min_words": 500, "rules": {}},
    "text": "all", "pos": ["NOUN"], "form": "lemma", "drop": "names", "generic": True, "extra_stop": "",
    "min_df": 3, "max_df": 0.5, "min_len": 3,
    "method": "nmf", "k": 8, "seed": 1, "runs": 5, "alpha": None, "beta": 0.01,
}


# ---------- settings ----------
def _number(cfg, key, cast, low, high):
    """cfg[key] as a number of type `cast`, held between low and high; a clear error if it isn't a number."""
    try:
        value = cast(cfg[key])
    except (TypeError, ValueError):
        raise TopicError(f"“{key}” should be a number.") from None
    return max(low, min(high, value))


def clean_cfg(cfg):
    """Complete and validate topic settings: unknown keys are dropped, missing ones take the defaults,
    numbers are held inside sensible limits and choices fall back to their default if unrecognised."""
    c = {**DEFAULTS, **{k: v for k, v in (cfg or {}).items() if k in DEFAULTS}}
    c["unit"] = c["unit"] if c["unit"] in ("chunk", "paras", "segments", "book") else "chunk"
    c["chunk_words"] = _number(c, "chunk_words", int, 50, 5000)
    c["paras"] = _number(c, "paras", int, 1, 200)
    c["text"] = c["text"] if c["text"] in ("all", "narration", "dialogue") else "all"
    c["pos"] = [p for p in (c["pos"] if isinstance(c["pos"], (list, tuple)) else []) if p in POS_CHOICES] or ["NOUN"]
    c["form"] = "word" if c["form"] == "word" else "lemma"
    c["drop"] = c["drop"] if c["drop"] in ("none", "names", "people", "entities") else "names"
    c["generic"] = bool(c["generic"])
    c["extra_stop"] = str(c["extra_stop"] or "")
    c["min_df"] = _number(c, "min_df", int, 1, 10 ** 6)
    c["max_df"] = _number(c, "max_df", float, 0.05, 1.0)
    c["min_len"] = _number(c, "min_len", int, 1, 30)
    c["method"] = "lda" if c["method"] == "lda" else "nmf"
    c["k"] = _number(c, "k", int, 2, 60)
    c["seed"] = _number(c, "seed", int, 0, 2 ** 31 - 1)
    c["runs"] = _number(c, "runs", int, 1, 20)
    c["alpha"] = None if c["alpha"] in (None, "") else _number(c, "alpha", float, 1e-4, 100.0)
    c["beta"] = 0.01 if c["beta"] in (None, "") else _number(c, "beta", float, 1e-4, 100.0)
    return c


# ---------- documents ----------
def _merge_short(docs, minimum):
    """Fold a too-short last document into the one before it."""
    if len(docs) >= 2 and docs[-1]["words"] < minimum:
        last = docs.pop()
        docs[-1]["end"] = last["end"]
        docs[-1]["words"] += last["words"]
    return docs


def make_docs(view, cfg):
    """Cut every book of the view into documents (see the module docstring for the four ways)."""
    docs = []
    for b in view.books:
        bd = view.bd[b]
        iw = cindex(bd)["isword"]

        def words(s, e):
            """Words in tokens s..e."""
            return sum(iw[s:e + 1])

        part = []
        if cfg["unit"] == "book":
            part = [{"start": 0, "end": bd.n_tokens - 1, "words": words(0, bd.n_tokens - 1)}]
        elif cfg["unit"] == "segments":
            segs, _ = book_segments(view, b, cfg["seg"])
            part = [{"start": s["start"], "end": s["end"], "words": s["words"], "label": s["label"]} for s in segs]
        elif cfg["unit"] == "paras":
            items = sorted(bd.para_bounds.items())
            for i in range(0, len(items), cfg["paras"]):
                group = items[i:i + cfg["paras"]]
                s, e = group[0][1][0], group[-1][1][1]
                part.append({"start": s, "end": e, "words": words(s, e)})
            _merge_short(part, 0.5 * sum(p["words"] for p in part[:-1]) / max(1, len(part) - 1))
        else:                                               # chunks: whole sentences until N words are reached
            cur, n = None, 0
            for _, (s, e) in sorted(bd.sent_bounds.items()):
                if cur is None:
                    cur, n = {"start": s, "end": e}, 0
                cur["end"] = e
                n += words(s, e)
                if n >= cfg["chunk_words"]:
                    part.append({**cur, "words": n})
                    cur = None
            if cur is not None:
                part.append({**cur, "words": n})
            _merge_short(part, cfg["chunk_words"] / 2)
        for d in part:
            d["book"] = b
            d["pos_pct"] = round(100 * d["start"] / max(1, bd.n_tokens), 1)
        docs += [d for d in part if d["words"] > 0]
    return docs


# ---------- words ----------
def dropped_tokens(bd, drop):
    """Token positions to leave out because they lie inside a mention: "names" (proper-name mentions),
    "people" (any mention of a person), "entities" (any mention) or "none"."""
    if drop == "none":
        return set()
    out = set()
    for c, s, e, prop, cat, *_ in bd.mentions:
        if drop == "names" and prop != "PROP":
            continue
        if drop == "people" and cat != "PER":
            continue
        out.update(range(s, e + 1))
    return out


def stop_set(cfg):
    """Words never counted: the built-in general words (unless switched off) plus your own."""
    stop = set(GENERIC) if cfg["generic"] else set()
    return stop | {w.strip().lower() for w in re.split(r"[\s,;]+", cfg["extra_stop"]) if w.strip()}


def kept_tokens(bd, d, cfg, stop, dropped):
    """(token position, word) for every token of document d that the model counts. The one place that
    decides this: the model, the passages and the text view all use it, so a highlighted word is always a counted word."""
    form = bd.lemma if cfg["form"] == "lemma" else bd.word
    in_quote = cindex(bd)["in_quote"]
    pos = set(cfg["pos"])
    for i in range(d["start"], d["end"] + 1):
        if bd.pos[i] not in pos or i in dropped:
            continue
        if cfg["text"] != "all" and in_quote[i] != (cfg["text"] == "dialogue"):
            continue
        w = form[i].lower()
        if len(w) < cfg["min_len"] or not WORD.match(w) or w in stop:
            continue
        yield i, w


def tokenize(view, docs, cfg):
    """The counted words of each document, as lists."""
    stop = stop_set(cfg)
    drops = {b: dropped_tokens(view.bd[b], cfg["drop"]) for b in view.books}
    return [[w for _, w in kept_tokens(view.bd[d["book"]], d, cfg, stop, drops[d["book"]])] for d in docs]


def matrix(tokens, cfg):
    """Documents × words count matrix and the vocabulary; words in too few or too many documents are left out."""
    from sklearn.feature_extraction.text import CountVectorizer
    if len(tokens) < 4:
        raise TopicError(f"Only {len(tokens)} documents. Use smaller documents or select more books.")
    cv = CountVectorizer(analyzer=lambda t: t, min_df=min(cfg["min_df"], max(1, len(tokens) // 2)), max_df=cfg["max_df"])
    try:
        X = cv.fit_transform(tokens)
    except ValueError:
        raise TopicError("No words are left after filtering. Lower the minimum document count or keep more parts of speech.") from None
    vocab = list(cv.get_feature_names_out())
    if len(vocab) < 20:
        raise TopicError(f"Only {len(vocab)} words are left after filtering. Lower the minimum document count, raise the maximum, or keep more parts of speech.")
    return X.tocsr(), vocab


# ---------- fitting ----------
def fit(X, cfg, seed):
    """Fit the model -> (theta: documents × topics, phi: topics × words), both with rows summing to 1.
    NMF factorises tf–idf weights (random start, so the seed matters); LDA is scikit-learn's batch variant.
    The number of topics is held below the number of documents and words."""
    k = min(cfg["k"], X.shape[0] - 1, X.shape[1] - 1)
    if k < 2:
        raise TopicError("Too few documents or words for that many topics.")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")               # scikit-learn's convergence chatter
        if cfg["method"] == "nmf":
            from sklearn.decomposition import NMF
            from sklearn.feature_extraction.text import TfidfTransformer
            tfidf = TfidfTransformer(sublinear_tf=True).fit_transform(X)
            model = NMF(n_components=k, init="random", random_state=seed, max_iter=500, tol=1e-4)
            W = model.fit_transform(tfidf)
        else:
            from sklearn.decomposition import LatentDirichletAllocation
            model = LatentDirichletAllocation(n_components=k, learning_method="batch", max_iter=80, random_state=seed,
                                              doc_topic_prior=cfg["alpha"] or 1.0 / k, topic_word_prior=cfg["beta"])
            W = model.fit_transform(X)
        H = model.components_

    def rows(M):
        """Normalise each row to sum to 1."""
        return M / np.maximum(M.sum(1, keepdims=True), 1e-12)

    theta = rows(W)
    theta[W.sum(1) <= 0] = 1.0 / k                     # a document NMF gave no topic to: spread evenly
    return theta, rows(H)


# ---------- quality ----------
def npmi_coherence(X, phi, top=10):
    """Mean normalised PMI of each topic's `top` words, from how often they occur in the same documents
    (-1…1, higher is better). X is the documents × words matrix, dense or sparse, of counts or 0/1: only whether a word occurs
    in a document matters. A pair that never co-occurs scores -1. (Kept sparse: a dense matrix of many documents × many words
    would fill the memory.)"""
    B = sparse.csc_matrix(X, dtype=float)
    B.eliminate_zeros()
    B.data[:] = 1.0
    n = B.shape[0]
    df = np.asarray(B.sum(0)).ravel()
    out = []
    for t in range(phi.shape[0]):
        idx = np.argsort(-phi[t])[:top]
        cols = B[:, idx]
        co = (cols.T @ cols).toarray()
        vals = []
        for a in range(len(idx)):
            for b in range(a + 1, len(idx)):
                p12 = co[a, b] / n
                if p12 <= 0:
                    vals.append(-1.0)
                    continue
                p1, p2 = df[idx[a]] / n, df[idx[b]] / n
                vals.append(math.log(p12 / (p1 * p2)) / -math.log(p12) if p12 < 1 else 1.0)
        out.append(float(np.mean(vals)) if vals else 0.0)
    return out


def diversity(phi, top=10):
    """Share of distinct words among all topics' top words (1 = no topic shares a top word with another)."""
    flat = [i for r in phi for i in np.argsort(-r)[:top]]
    return len(set(flat)) / max(1, len(flat))


def match(phi_a, phi_b, top=20):
    """For each topic of A, the share of its top words found in its best one-to-one match in B (Hungarian matching)."""
    from scipy.optimize import linear_sum_assignment

    def top_sets(phi):
        """Each topic's top words as a 0/1 matrix."""
        M = np.zeros(phi.shape)
        for t in range(phi.shape[0]):
            M[t, np.argsort(-phi[t])[:top]] = 1
        return M

    sim = top_sets(phi_a) @ top_sets(phi_b).T / top
    rows, cols = linear_sum_assignment(-sim)
    out = np.zeros(phi_a.shape[0])
    out[rows] = sim[rows, cols]
    return out


def stability(X, cfg, phi, runs):
    """Re-fit with other seeds and see how often each topic comes back -> per topic {recurs, of, similarity}
    (`recurs` counts the main run too; `of` is the number of runs)."""
    sims = [match(phi, fit(X, cfg, cfg["seed"] + r)[1]) for r in range(1, runs)]
    if not sims:
        return [{"recurs": 1, "of": 1, "similarity": None} for _ in range(phi.shape[0])]
    S = np.array(sims)
    return [{"recurs": 1 + int((S[:, t] >= RECUR).sum()), "of": runs, "similarity": float(S[:, t].mean())} for t in range(phi.shape[0])]


def relevance(phi, freq, lam=0.6):
    """Topic–word relevance (Sievert & Shirley 2014): λ·log p(w|t) + (1−λ)·log(p(w|t)/p(w)); higher for words that are
    both probable in the topic and much more probable there than overall. `freq` are the words' counts in the model."""
    pw = np.maximum(freq / freq.sum(), 1e-12)
    p = np.maximum(phi, 1e-12)
    return lam * np.log(p) + (1 - lam) * np.log(p / pw)


# ---------- the pipeline ----------
def prepare(view, cfg):
    """Documents, counts and vocabulary for the view -> (docs, X, vocab). Documents left with no counted word are dropped."""
    docs = make_docs(view, cfg)
    tokens = tokenize(view, docs, cfg)
    X, vocab = matrix(tokens, cfg)
    keep = np.flatnonzero(np.asarray(X.sum(1)).ravel() > 0)
    if len(keep) < len(docs):
        docs = [docs[i] for i in keep]
        X = X[keep]
    for d, n in zip(docs, np.asarray(X.sum(1)).ravel()):
        d["kept"] = int(n)
    return docs, X, vocab


def scan(view, cfg, ks):
    """Fit one model for each number of topics in `ks` and report quality, to help choosing k
    -> {docs, vocab, words, rows: [{k, coherence, diversity, stability}]}. Stability uses at most three runs."""
    docs, X, vocab = prepare(view, cfg)
    out = []
    for k in ks:
        c = {**cfg, "k": k}
        _, phi = fit(X, c, cfg["seed"])
        stab = stability(X, c, phi, max(1, min(cfg["runs"], 3)))
        out.append({"k": phi.shape[0], "coherence": float(np.mean(npmi_coherence(X, phi))), "diversity": diversity(phi),
                    "stability": float(np.mean([s["recurs"] / s["of"] for s in stab])) if stab[0]["of"] > 1 else None})
    return {"docs": len(docs), "vocab": len(vocab), "words": int(X.sum()), "rows": out}


def build(view, cfg, name=""):
    """Fit and store a model of the view's books -> the model dict (with its new `id`)."""
    t0 = time.time()
    docs, X, vocab = prepare(view, cfg)
    theta, phi = fit(X, cfg, cfg["seed"])
    coherence = npmi_coherence(X, phi)
    freq = np.asarray(X.sum(0)).ravel().astype(float)
    k = phi.shape[0]

    def rounded(M, digits):
        """Round for compact storage."""
        return [[float(f"{x:.{digits}g}") for x in row] for row in M]

    model = {
        "name": name, "created": time.strftime("%Y-%m-%d %H:%M"), "cfg": cfg, "books": list(view.books),
        "titles": {b: view.title(b) for b in view.books}, "tokens": {b: view.bd[b].n_tokens for b in view.books},
        "docs": [{key: d[key] for key in ("book", "start", "end", "words", "kept", "pos_pct", "label") if key in d} for d in docs],
        "vocab": vocab, "freq": [int(f) for f in freq], "phi": rounded(phi, 5), "theta": rounded(theta, 4),
        "metrics": {"coherence": coherence, "diversity": diversity(phi), "stability": stability(X, cfg, phi, cfg["runs"]),
                    "seconds": round(time.time() - t0, 1), "mean_coherence": float(np.mean(coherence)), "k": k},
        "labels": [""] * k,
    }
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "model").lower()).strip("-")[:30] or "model"
    model["id"] = f"{slug}-{hashlib.sha1(f'{time.time()}{name}'.encode()).hexdigest()[:6]}"
    store.save(model)
    return model
