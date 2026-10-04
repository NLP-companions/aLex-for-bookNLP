"""Arcs, style, stylometry, sentiment and emotion; and the text view."""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, HTTPException

from alex.core import narrative, reader

from .context import Context, need, real, whole


def router(ctx: Context, topics) -> APIRouter:
    """Routes for arcs, style, stylometry, sentiment, emotion and the text view."""
    r = APIRouter()

    @r.post("/api/narrative/segments")
    def segments(body: dict = Body(...)):
        """The chapters or slices of the selected books."""
        segs, info = narrative.all_segments(ctx.of(body), body.get("seg"))
        return {"segments": segs, "info": info}

    @r.post("/api/narrative/arcs")
    def arcs(body: dict = Body(...)):
        """Something counted per segment: entities, events, supersenses, dialogue or topics."""
        v = ctx.of(body)
        if body.get("kind") == "topics":
            if topics is None:
                raise HTTPException(400, "Topic modelling needs scikit-learn. Run: pip install scikit-learn")
            return topics.arc_series(v, body.get("model"), [int(i) for i in body.get("ids") or []], body.get("seg"))
        return narrative.arcs(v, body.get("seg"), body.get("kind", "entities"), body.get("ids"), body.get("cats"))

    @r.post("/api/narrative/style")
    def style(body: dict = Body(...)):
        """Style figures per book or per segment."""
        return narrative.style(ctx.of(body), body.get("seg"), body.get("by", "book"))

    @r.post("/api/narrative/stylometry")
    def stylometry(body: dict = Body(...)):
        """Distances between texts, cluster tree and map."""
        return narrative.stylometry(ctx.of(body), body.get("seg"), body.get("units", "books"), whole(body, "mfw", 100, 2, 5000),
                                    real(body, "culling", 0, 0, 100), body.get("measure", "cosine"), body.get("linkage", "average"),
                                    body.get("scope", "all"), bool(body.get("exclude_pronouns")))

    # ---------- sentiment and emotion ----------
    def lexicon_info():
        """Whether VADER is installed and which emotion lexicon (if any) is loaded."""
        lex = narrative.load_lexicon(ctx.lexicon_path)
        return {"vader": narrative.vader_available(),
                "emotion": {"name": lex["name"], "cats": {c: len(w) for c, w in lex["cats"].items()}} if lex else None}

    @r.get("/api/narrative/lexicons")
    def lexicons():
        """The lexicon status."""
        return lexicon_info()

    @r.post("/api/narrative/lexicons")
    def add_lexicon(body: dict = Body(...)):
        """Store an emotion lexicon from uploaded text."""
        cats = narrative.parse_lexicon(body.get("text", ""))
        if not cats:
            raise HTTPException(400, "No word–category pairs found. The file should have a word and a category on each line (and optionally 0/1), separated by tabs or commas.")
        ctx.lexicon_path.write_text(json.dumps({"name": body.get("name") or "Emotion lexicon", "cats": cats}), encoding="utf-8")
        return lexicon_info()

    @r.post("/api/narrative/lexicons/delete")
    def delete_lexicon():
        """Remove the stored emotion lexicon."""
        ctx.lexicon_path.unlink(missing_ok=True)
        return lexicon_info()

    @r.post("/api/narrative/sentiment")
    def sentiment(body: dict = Body(...)):
        """VADER sentiment per segment."""
        if not narrative.vader_available():
            raise HTTPException(400, "Sentiment needs the vaderSentiment package: pip install vaderSentiment")
        return narrative.sentiment(ctx.of(body), body.get("seg"), body.get("ids"))

    @r.post("/api/narrative/emotion")
    def emotion(body: dict = Body(...)):
        """Emotion-lexicon counts per segment."""
        lex = narrative.load_lexicon(ctx.lexicon_path)
        if not lex:
            raise HTTPException(400, "Load an emotion lexicon first.")
        return narrative.emotion(ctx.of(body), body.get("seg"), lex, body.get("cats"))

    # ---------- the text view ----------
    @r.post("/api/read")
    def read(body: dict = Body(...)):
        """One chapter or slice of a book, with the layers asked for. The book may lie outside the selection."""
        books = body.get("books") or []
        b = need(body, "book")
        v = ctx.view(books if b in books else books + [b], body.get("plural"))
        if b not in v.bd:
            raise HTTPException(404, "That book isn't available.")
        return reader.read(v, b, body.get("seg"), body.get("index"), body.get("tok"), body.get("end"), body.get("layers"), body.get("topics"),
                           mark=bool(body.get("mark", True)))

    @r.post("/api/narrative/chapters")
    def chapters(body: dict = Body(...)):
        """Edit a book's chapters: start one at a paragraph, remove or rename one, or go back to the ones found automatically."""
        b = need(body, "book")
        if b not in ctx.lib.found():
            raise HTTPException(404, "That book isn't in the library.")
        pid = whole(body, "pid", 0) if body.get("action") != "reset" else None
        return {"edited": narrative.edit_chapters(ctx.lib, b, need(body, "action"), pid, body.get("name"))}

    return r
