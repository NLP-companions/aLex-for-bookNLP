"""Corpus tools (concordance, word lists, n-grams, collocates, keywords) and the reference files keywords use."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, Body, HTTPException

from alex.core import corpus

from .context import Context, need, whole
from .entities import stat_options


def router(ctx: Context) -> APIRouter:
    """Routes for the corpus tools and reference files."""
    r = APIRouter()

    @r.post("/api/corpus/kwic")
    def kwic(body: dict = Body(...)):
        """A concordance. The search is kept, so paging ("Show more") doesn't search again; `offset` and `limit` page it, and only
        the lines of the page are made."""
        v = ctx.of(body)
        key = json.dumps([body.get(k) for k in ("query", "mode", "settings", "scope", "sort", "near", "ctx")] + [ctx.signature(v)], sort_keys=True, default=str)
        search = ctx.remember(key, lambda: corpus.kwic_search(v, body.get("query", ""), body.get("mode", "simple"), body.get("settings") or {},
                                                              body.get("scope"), tuple(body.get("sort") or ("R1", "R2", "R3")), body.get("near"),
                                                              ctx=body.get("ctx")))
        offset, limit = whole(body, "offset", 0, 0), whole(body, "limit", 500, 1, 100000)
        out = {k: x for k, x in search.items() if k != "found"}
        out["hits"] = corpus.kwic_lines(v, search["found"][offset:offset + limit], whole(body, "context", 10, 1, 60))
        out["offset"] = offset
        if offset:                                   # the per-book figures only go with the first page
            out.pop("per_book")
            out.pop("speakers")
        return out

    @r.post("/api/corpus/context")
    def context(body: dict = Body(...)):
        """The paragraph around a concordance hit."""
        return corpus.context(ctx.of(body), need(body, "book"), whole(body, "tok", 0), body.get("end"))

    @r.post("/api/corpus/filters")
    def filters(body: dict = Body(...)):
        """The word classes, fine tags and entity types a word-type filter can choose from, with their counts."""
        return corpus.filter_options(ctx.of(body))

    @r.post("/api/corpus/wordlist")
    def wordlist(body: dict = Body(...)):
        """A frequency list of words, lemmas, word+POS, word+POS+lemma or POS, optionally only of some word types."""
        return corpus.wordlist(ctx.of(body), body.get("scope"), body.get("unit", "word"), body.get("settings") or {},
                               whole(body, "min_freq", 1, 1), whole(body, "min_range", 1, 1), flt=body.get("filter"))

    @r.post("/api/corpus/ngrams")
    def ngrams(body: dict = Body(...)):
        """N-grams, optionally containing a word."""
        return corpus.ngrams(ctx.of(body), whole(body, "n_min", 2, 1, 10), whole(body, "n_max", 3, 1, 10), body.get("scope"),
                             body.get("unit", "word"), body.get("settings") or {}, whole(body, "min_freq", 2, 1), whole(body, "min_range", 1, 1),
                             body.get("contains") or None, body.get("position", "any"), bool(body.get("within_sentence", True)))

    @r.post("/api/corpus/collocates")
    def collocates(body: dict = Body(...)):
        """Collocates of a search, with association measures, optionally only of some word types."""
        return corpus.collocates(ctx.of(body), body.get("query", ""), body.get("mode", "simple"), body.get("settings") or {}, body.get("scope"),
                                 whole(body, "left", 5, 0, 20), whole(body, "right", 5, 0, 20), body.get("unit", "word"), whole(body, "min_freq", 3, 1),
                                 whole(body, "min_range", 1, 1), bool(body.get("within_sentence", False)), body.get("sort", "mi"), flt=body.get("filter"))

    @r.post("/api/corpus/keywords")
    def keywords(body: dict = Body(...)):
        """Keywords of the selected books against other books or a reference file."""
        v = ctx.of(body)
        reference = body.get("reference") or {}
        unit = body.get("unit", "word")
        options = stat_options(body)
        options["direction"] = "both" if body.get("negative") else "target"
        min_range = whole(body, "min_range", 1, 1)
        if reference.get("kind") == "file":
            path = ctx.refs_dir / f"{re.sub(r'[^a-z0-9-]', '', str(reference.get('id')))}.json"
            if not path.exists():
                raise HTTPException(404, "That reference file is no longer available.")
            if unit != "word":
                raise HTTPException(400, "Reference files only have word forms. Choose Word forms, or use books as the reference.")
            counts = corpus.Counter(json.loads(path.read_text(encoding="utf-8"))["counts"])
            return corpus.keywords(v, reference, body.get("scope"), unit, body.get("settings") or {}, options, min_range, ref_counts=counts)
        if not reference.get("books"):
            raise HTTPException(400, "Choose at least one reference book.")
        return corpus.keywords(v, reference, body.get("scope"), unit, body.get("settings") or {}, options, min_range, ref_view=ctx.view(reference["books"], body.get("plural")))

    # ---------- reference files ----------
    @r.get("/api/refs")
    def list_refs():
        """The stored reference files (damaged ones are skipped)."""
        rows = []
        for p in sorted(ctx.refs_dir.glob("*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                rows.append({"id": p.stem, "name": d["name"], "files": d["files"], "kinds": d["kinds"], "tokens": d["tokens"], "types": d["types"]})
            except (OSError, ValueError, KeyError):
                continue                             # a damaged file must not hide the others
        return {"rows": rows}

    @r.post("/api/refs")
    def add_ref(body: dict = Body(...)):
        """Store uploaded files (word lists or texts) as a reference for keywords."""
        files = [f for f in body.get("files", []) if isinstance(f, dict) and f.get("text")]
        if not files:
            raise HTTPException(400, "Choose one or more text files.")
        d = corpus.make_reference(body.get("name") or files[0]["name"], files)
        if not d["tokens"]:
            raise HTTPException(400, "No words found in those files.")
        base = re.sub(r"[^a-z0-9]+", "-", d["name"].lower()).strip("-")[:40] or "reference"
        rid, k = base, 1
        while (ctx.refs_dir / f"{rid}.json").exists():
            k += 1
            rid = f"{base}-{k}"
        (ctx.refs_dir / f"{rid}.json").write_text(json.dumps(d), encoding="utf-8")
        return {"id": rid, "name": d["name"], "kinds": d["kinds"], "tokens": d["tokens"], "types": d["types"]}

    @r.post("/api/refs/delete")
    def del_ref(body: dict = Body(...)):
        """Delete a reference file."""
        (ctx.refs_dir / f"{re.sub(r'[^a-z0-9-]', '', str(body.get('id', '')))}.json").unlink(missing_ok=True)
        return {"ok": True}

    return r
