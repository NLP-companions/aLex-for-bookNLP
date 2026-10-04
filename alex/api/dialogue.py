"""Dialogue views, and the corrections you make to quotes, conversations and narrators."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from alex.core import dialogue, narrative, narrators

from .context import Context, need, unit_target, whole
from .entities import stat_options


def router(ctx: Context) -> APIRouter:
    """Routes for the dialogue views and for your corrections to quotes, conversations and narrators."""
    r = APIRouter()
    lib = ctx.lib

    def known_book(body):
        """The `book` a correction is about, if it is in the library (404 otherwise: a correction must not invent a book)."""
        book = need(body, "book")
        if book not in lib.found():
            raise HTTPException(404, "That book isn't in the library.")
        return book

    def book_view(body, book):
        """A view of the selected books plus `book` (corrections can concern a book outside the selection)."""
        return ctx.view(list(dict.fromkeys((body.get("books") or []) + [book])), body.get("plural"))

    # ---------- the views ----------
    @r.post("/api/dialogue/overview")
    def overview(body: dict = Body(...)):
        """Dialogue per book and a row per speaker."""
        return dialogue.overview(ctx.of(body))

    @r.post("/api/dialogue/verbs")
    def verbs(body: dict = Body(...)):
        """Speech verbs and adverbs, overall or for one speaker or group."""
        return dialogue.verbs(ctx.of(body), body.get("target"), stat_options(body),
                              body.get("types"), bool(body.get("weigh_verb")))

    @r.post("/api/dialogue/voice")
    def voice(body: dict = Body(...)):
        """Speaking style and distinctive vocabulary of a target against a reference."""
        return dialogue.voice(ctx.of(body), need(body, "target"), body.get("reference", {"kind": "others"}),
                              body.get("unit", "word"), stat_options(body), body.get("types"), bool(body.get("weigh_verb")))

    @r.post("/api/dialogue/style")
    def style(body: dict = Body(...)):
        """Speaking-style figures for every speaker."""
        return dialogue.style_table(ctx.of(body), whole(body, "min_words", 0, 0),
                                    body.get("types"), bool(body.get("weigh_verb")))

    @r.post("/api/dialogue/conversations")
    def conversations(body: dict = Body(...)):
        """The conversations, optionally only those involving someone."""
        rows, total = dialogue.conversations(ctx.of(body), body.get("target"))
        return {"rows": rows, "total": total}

    @r.post("/api/dialogue/quotes")
    def quotes(body: dict = Body(...)):
        """Quotes matching a filter."""
        return dialogue.quotes(ctx.of(body), body.get("filter") or {}, whole(body, "limit", 400, 1, 5000))

    @r.post("/api/dialogue/entity")
    def entity(body: dict = Body(...)):
        """The Speech section of an entity's page."""
        v = ctx.of(body)
        result = dialogue.entity(v, unit_target(v, body), body.get("types"), bool(body.get("weigh_verb")))
        if result is None:
            raise HTTPException(404, "Not in the selected books")
        return result

    @r.post("/api/dialogue/narrators")
    def narration(body: dict = Body(...)):
        """Narration per narrator role."""
        return dialogue.narrators(ctx.of(body))

    @r.post("/api/dialogue/scope")
    def scope(body: dict = Body(...)):
        """The pooled Dialogue-in-each-book, speaking and narrating figures for a scope (an entity, a saved or
        hand-picked group, a tag or a gender) all at once, for In-Depth Who Speaks; None if the scope matches nobody."""
        v = ctx.of(body)
        u = v.pool_unit(need(body, "target"))
        return dialogue.entity(v, u) if u else None

    # ---------- your corrections ----------
    def quote_key(v, b, qi):
        """The stable key of quote `qi` (see dialogue.keys)."""
        key = dialogue.keys(v.bd[b])["q"].get(int(qi))
        if key is None:
            raise HTTPException(404, "Quote not found.")
        return key

    @r.post("/api/annot/quote")
    def annot_quote(body: dict = Body(...)):
        """Everything the quote editor shows: speaker, addressees (yours or estimated), conversation and its participants."""
        b, qi = need(body, "book"), whole(body, "qi", 0)
        v = book_view(body, b)
        d = dialogue.bdlg(v, b)
        rec = next((x for x in d["recs"] if x["qi"] == qi), None)
        if rec is None:
            raise HTTPException(404, "Quote not found.")
        speaker = dialogue.unit_of(v, b, rec["speaker"])
        addressees, method = dialogue.addressees(v, b, rec)
        estimate = dialogue.unit_of(v, b, rec["addressee"])
        participants, speakers, edit = dialogue.participants(v, b, rec["conv"])
        conv = d["convs"][rec["conv"]]
        ann = lib.ann["books"].get(b, {})
        name = lambda u: {"id": u, "name": v.name_of(u)}
        return {"book": b, "qi": qi, "quote": v.bd[b].span_text(rec["start"], rec["end"]), "tok": rec["start"],
                "speaker": name(speaker) if speaker else None, "addressees": [name(a) for a in addressees], "method": method,
                "fixed": rec["fixed"], "estimate": name(estimate) if estimate else None, "estimate_method": rec["addr_method"],
                "conv": rec["conv"], "conv_quotes": len(conv), "first": conv[0]["qi"] == qi, "first_qi": conv[0]["qi"],
                "split": rec["key"] in ann.get("splits", []), "merged": conv[0]["key"] in ann.get("merges", []),
                "participants": [dict(name(u), speaker=u in speakers) for u in participants],
                "removed": [name(u) for u in edit.get("remove", [])], "methods": dialogue.ADDR_METHODS}

    @r.post("/api/annot/addressees")
    def annot_addressees(body: dict = Body(...)):
        """Set a quote's addressees (["*"] = everyone present), or clear your correction (null)."""
        b = need(body, "book")
        key = quote_key(book_view(body, b), b, need(body, "qi"))
        with lib.lock:
            fixed = lib.ann_book(b)["addressees"]
            if body.get("addressees") is None:
                fixed.pop(key, None)
            else:
                fixed[key] = list(dict.fromkeys(body["addressees"]))
            lib.save_ann()
        return {"ok": True}

    @r.post("/api/annot/conversation")
    def annot_conversation(body: dict = Body(...)):
        """Start a new conversation at a quote ("split"), join it to the previous one ("merge"), or undo either."""
        b = need(body, "book")
        key = quote_key(book_view(body, b), b, need(body, "qi"))
        with lib.lock:
            ab = lib.ann_book(b)
            ab["splits"] = [k for k in ab["splits"] if k != key]
            ab["merges"] = [k for k in ab["merges"] if k != key]
            if body.get("action") == "split":
                ab["splits"].append(key)
            elif body.get("action") == "merge":
                ab["merges"].append(key)
            lib.save_ann()
        return {"ok": True}

    @r.post("/api/annot/participants")
    def annot_participants(body: dict = Body(...)):
        """Add a listener to a conversation, remove a participant, or put one back."""
        b = need(body, "book")
        key = quote_key(book_view(body, b), b, need(body, "first_qi"))
        unit = need(body, "id")
        with lib.lock:
            edits = lib.ann_book(b)["participants"]
            p = edits.setdefault(key, {"add": [], "remove": []})
            p["add"] = [x for x in p["add"] if x != unit]
            p["remove"] = [x for x in p["remove"] if x != unit]
            if body.get("action") == "add":
                p["add"].append(unit)
            elif body.get("action") == "remove":
                p["remove"].append(unit)             # any other action ("restore") just clears the edit for this unit
            if not p["add"] and not p["remove"]:
                edits.pop(key, None)
            lib.save_ann()
        return {"ok": True}

    @r.post("/api/annot/narrator")
    def annot_narrator(body: dict = Body(...)):
        """Set (or clear) a book's narrator."""
        book = known_book(body)
        with lib.lock:
            lib.ann_book(book)["narrator"] = body.get("narrator") or None
            lib.save_ann()
        return {"ok": True}

    @r.post("/api/annot/paragraphs")
    def annot_paragraphs(body: dict = Body(...)):
        """Give paragraphs to a narrator other than the book's (or, with no narrator, take the exception away)."""
        b = need(body, "book")
        try:
            keys = dialogue.keys(lib.book(b))["p"]
        except KeyError:
            raise HTTPException(404, "That book isn't in the library.") from None
        with lib.lock:
            exceptions = lib.ann_book(b)["para_narrators"]
            for pid in body.get("pids", []):
                key = keys.get(int(pid))
                if key is None:
                    continue
                if body.get("narrator"):
                    exceptions[key] = body["narrator"]
                else:
                    exceptions.pop(key, None)
            lib.save_ann()
        return {"ok": True}

    @r.post("/api/annot/chapter_narrator")
    def annot_chapter_narrator(body: dict = Body(...)):
        """Assign a narrator to a whole chapter (found from any paragraph in it), on top of the book's default and
        any paragraph exceptions inside it; with no pid, the Opening before the first chapter start."""
        b = known_book(body)
        pid = body.get("pid")
        key = narrative.chapter_key_of(book_view(body, b), b, whole(body, "pid", 0)) if pid is not None else narrative.OPENING_KEY
        with lib.lock:
            exceptions = lib.ann_book(b).setdefault("chapter_narrators", {})
            if body.get("narrator"):
                exceptions[key] = body["narrator"]
            else:
                exceptions.pop(key, None)
            lib.save_ann()
        return {"ok": True}

    @r.get("/api/annot/narrator_options")
    def narrator_options(book: str):
        """People and things that can be a book's narrator."""
        v = ctx.view([book])
        return {"rows": [x for x in v.unit_rows() if x["type"] in ("PER", "VAR")][:300], "current": lib.ann["books"].get(book, {}).get("narrator")}

    @r.post("/api/narrators/suggestions")
    def suggestions(body: dict = Body(...)):
        """Suggested narrators, from the "I" in the narration."""
        return narrators.suggestions(ctx.of(body), whole(body, "max_gap", 3, 0, 50), whole(body, "min_evidence", 2, 1))

    @r.post("/api/narrators/reject")
    def reject(body: dict = Body(...)):
        """Hide a suggested stretch told by someone else."""
        book = known_book(body)
        with lib.lock:
            ab = lib.ann_book(book)
            rejected = ab.setdefault("narr_rejected", [])
            if need(body, "key") not in rejected:
                rejected.append(body["key"])
            lib.save_ann()
        return {"ok": True}

    def narrator_link(lid):
        """The narrator-link id inside an `nl:<n>` id."""
        lid = str(lid)
        if not lid.startswith("nl:") or lid[3:] not in lib.state["narrator_links"]:
            raise HTTPException(404, "That narrator link doesn't exist.")
        return lid[3:]

    @r.post("/api/narrators/link")
    def link_narrators(body: dict = Body(...)):
        """Link two narrator roles (or a narrator link and a role) as one narrator. Unlike linking entities, this
        only pools their narration; the underlying characters, if any, and everything else about them stay separate."""
        a, b = need(body, "a"), need(body, "b")
        if a == b:
            raise HTTPException(400, "Choose two different narrators")
        for u in (a, b):
            if str(u).startswith("nl:"):
                narrator_link(u)
        return {"id": lib.link_narrators(a, b, body.get("name"))}

    @r.post("/api/narrators/unlink")
    def unlink_narrator(body: dict = Body(...)):
        """Take one narrator role out of a narrator link."""
        lib.unlink_narrator(narrator_link(need(body, "id")), need(body, "role"))
        return {"ok": True}

    @r.post("/api/narrators/unlink_all")
    def unlink_narrators_all(body: dict = Body(...)):
        """Dissolve a narrator link entirely: every role becomes its own narrator again."""
        lib.unlink_narrators_all(narrator_link(need(body, "id")))
        return {"ok": True}

    return r
