"""Books, settings, the entity list, tags and the export zip."""
from __future__ import annotations

import hashlib
import os
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from alex.core import bookcollections, corpus, dialogue, entitygroups, export, narrative, network, stats
from alex.core.bookdata import RELATIONS, TYPES
from alex.core.view import REL_LABELS

from .context import Context, need, whole


def library_info(ctx: Context, topics):
    """The whole library page: books with their details and sizes, settings, and the explanatory texts and option lists
    the browser needs (sent once, so the interface never has to hard-code them)."""
    lib = ctx.lib
    found, problems = lib.scan()
    order = lambda b: (lib.meta(b)["series"].lower(), str(lib.meta(b)["year"]), lib.meta(b)["title"].lower())
    books = []
    for bid in sorted(found, key=order):
        row = {"id": bid, **lib.meta(bid), "folder": str(lib.folder_for(bid)), "versions": found[bid]}
        try:
            bd = lib.book(bid)
            row.update(tokens=bd.n_tokens, words=bd.n_words, sentences=bd.n_sents, paragraphs=bd.n_paras, mentions=len(bd.mentions),
                       groups=len(bd.groups), quotes=len(bd.quotes), problems=bd.problems, has_text=bd.has_original,
                       signature=hashlib.sha1(repr(lib.book_key(bid)).encode()).hexdigest()[:12])   # changes when a new export arrives
        except Exception as e:  # noqa: BLE001 - show the book with its error instead of failing the whole page
            row.update(error=str(e))
        books.append(row)
    topic_notes = {}
    if topics:
        topic_notes = {**topics.NOTES, **{"page_" + k: v for k, v in topics.PAGE_NOTES.items()},
                       **{"cmp_" + k: v for k, v in topics.COMPARE_NOTES.items()}}
    return {"books": books, "collections": bookcollections.listing(lib), "groups": entitygroups.listing(lib), "sources": lib.state["sources"], "problems": problems,
            "settings": lib.state["settings"], "types": TYPES, "tags": lib.all_tags(),
            "relations": [{"id": r, "label": REL_LABELS[r]} for r in RELATIONS],
            "measures": stats.MEASURES, "tests": stats.TESTS, "stat_notes": stats.NOTES, "across_note": stats.ACROSS_NOTE,
            "network_kinds": network.KINDS, "network_notes": network.NOTES,
            "dialogue_notes": dialogue.NOTES, "addr_methods": dialogue.ADDR_METHODS, "verb_methods": dialogue.VERB_METHODS,
            "corpus_attrs": corpus.ATTRS, "sort_by": corpus.SORT_BY, "coll_measures": corpus.COLL_MEASURES, "coll_note": corpus.COLL_NOTE,
            "narrative_notes": narrative.NOTES,
            "topics_ready": topics is not None, "topic_notes": topic_notes, "topic_defaults": topics.DEFAULTS if topics else {}}


def router(ctx: Context, topics) -> APIRouter:
    """Routes for the library: books, settings, the entity list and tags."""
    r = APIRouter()
    lib = ctx.lib

    @r.get("/api/library")
    def library():
        """The library page's data."""
        return library_info(ctx, topics)

    @r.post("/api/books/{bid}")
    def set_book(bid: str, body: dict = Body(...)):
        """Change a book's title, author, year, series, tags or pinned export."""
        if bid not in lib.found():
            raise HTTPException(404, "That book isn't in the library.")
        patch = dict(body)
        if patch.get("year") not in ("", None):
            try:
                patch["year"] = int(patch["year"])
            except (TypeError, ValueError):
                raise HTTPException(400, "Year must be a number") from None
        if "tags" in patch:
            patch["tags"] = sorted({str(t).strip() for t in patch["tags"] if str(t).strip()})
        lib.set_meta(bid, patch)
        return lib.meta(bid)

    @r.get("/api/books/{bid}/text")
    def book_text(bid: str):
        """The original .txt the book was exported from, for download; 404 if none was found next to its other files."""
        if bid not in lib.found():
            raise HTTPException(404, "That book isn't in the library.")
        bd = lib.book(bid)
        if not bd.has_original:
            raise HTTPException(404, "No original text file was found for this book.")
        return Response(bd.raw_bytes, media_type="text/plain; charset=utf-8",
                         headers={"Content-Disposition": f'attachment; filename="{bid}.txt"'})

    @r.post("/api/export")
    def export_zip(body: dict = Body(...)):
        """The selected books and your work on them as one .zip, for download (see core/export.py for what it holds)."""
        books = ctx.selected(body.get("books"))
        handle, path = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        try:
            export.write_zip(lib, books, path)
        except BaseException:
            os.unlink(path)
            raise
        return FileResponse(path, media_type="application/zip", filename=time.strftime("analyser-export-%Y%m%d-%H%M%S.zip"),
                            background=BackgroundTask(os.unlink, path))          # the temporary file goes once it has been sent

    def collection_reply(cid=None):
        """What every collection route returns: the collections as they are now (and the id of the one just made)."""
        return {"collections": bookcollections.listing(lib), "id": cid}

    def in_collection(action, *args, **kw):
        """Run a change to collections, turning an unknown id into a 404 and unusable input (ValueError) into the usual 400."""
        try:
            return action(lib, *args, **kw)
        except KeyError:
            raise HTTPException(404, "That collection doesn't exist.") from None

    @r.post("/api/collections")
    def collection_new(body: dict = Body(...)):
        """Make a collection, at the top level or inside another."""
        return collection_reply(in_collection(bookcollections.create, body.get("name"), body.get("parent")))

    @r.post("/api/collections/delete")
    def collection_delete(body: dict = Body(...)):
        """Remove a collection (its books stay; its sub-collections move up)."""
        in_collection(bookcollections.delete, str(need(body, "id")))
        return collection_reply()

    @r.post("/api/collections/{cid}")
    def collection_change(cid: str, body: dict = Body(...)):
        """Rename a collection, move it, or add and remove its books."""
        kw = {k: body[k] for k in ("name", "parent", "add", "remove") if k in body}
        in_collection(bookcollections.update, cid, **kw)
        return collection_reply(cid)

    @r.post("/api/settings")
    def settings(body: dict = Body(...)):
        """Minimum mentions, how to count them, whether plural groups' mentions count for their members, the conversation gap
        and the source folders."""
        with lib.lock:
            s = lib.state["settings"]
            for t, n in (body.get("min") or {}).items():
                if t in TYPES:
                    s["min"][t] = whole({"n": n}, "n", 2, 1)
            if "conv_gap" in body:
                s["conv_gap"] = whole(body, "conv_gap", 100, 0)
            if body.get("count_mode") in ("per_book", "combined"):
                s["count_mode"] = body["count_mode"]
            if isinstance(body.get("plural_default"), bool):     # not "plural": every request carries that (a page's own choice)
                s["plural"] = body["plural_default"]
            if "sources" in body:
                if not isinstance(body["sources"], list):
                    raise ValueError("“sources” should be a list of folders.")
                sources = [str(Path(x).expanduser()) for x in body["sources"] if str(x).strip()]
                lib.state["sources"] = list(dict.fromkeys(sources))
                lib.reset_scan()
            lib.save()
        return library_info(ctx, topics)

    @r.post("/api/units")
    def units(body: dict = Body(...)):
        """The entity list of the selected books."""
        v = ctx.of(body)
        return {"rows": v.unit_rows(body.get("type")), "type_counts": v.type_counts(), "narrators": dialogue.narrator_rows(v),
                "genders": v.genders(), "problems": v.problems, "words": sum(bd.n_words for bd in v.bd.values())}

    @r.post("/api/tags")
    def tags(body: dict = Body(...)):
        """Replace an entity's or linked person's tags."""
        uid = need(body, "id")
        try:
            lib.set_tags(uid, body.get("tags", []))
        except KeyError:
            raise HTTPException(404, "That entity or person doesn't exist.") from None
        return {"tags": lib.tags_of(uid), "all": lib.all_tags()}

    @r.post("/api/name")
    def name(body: dict = Body(...)):
        """Rename an entity or linked person (blank goes back to the name found in the books)."""
        uid = need(body, "id")
        try:
            lib.set_name(uid, body.get("name", ""))
        except KeyError:
            raise HTTPException(404, "That entity or person doesn't exist.") from None
        return {"name": lib.name_of(uid)}

    @r.post("/api/note")
    def note(body: dict = Body(...)):
        """Give an entity or linked person a short free-text description (blank clears it)."""
        uid = need(body, "id")
        try:
            lib.set_note(uid, body.get("note", ""))
        except KeyError:
            raise HTTPException(404, "That entity or person doesn't exist.") from None
        return {"note": lib.note_of(uid)}

    return r
