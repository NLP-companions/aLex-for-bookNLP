"""Linking the same person or place across books."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from alex.core import links

from .context import Context, need, whole


def router(ctx: Context) -> APIRouter:
    """Routes for linking entities across books."""
    r = APIRouter()
    lib = ctx.lib

    @r.get("/api/links/suggestions")
    def suggestions():
        """Possible matches between books, best first."""
        rows, total = links.suggest(lib)
        return {"rows": rows, "total": total}

    @r.get("/api/links/search")
    def search(q: str = ""):
        """Find entities by name in every book, for linking by hand (with no name: the most mentioned ones)."""
        return {"rows": links.search(lib, q)}

    @r.get("/api/links/persons")
    def persons():
        """The persons linked so far."""
        return {"rows": links.persons(lib)}

    @r.get("/api/links/narrator_links")
    def get_narrator_links():
        """The narrator roles linked so far (see /api/narrators/link, /api/narrators/unlink[_all] for changing them)."""
        return {"rows": links.narrator_links(lib)}

    @r.post("/api/links/auto")
    def auto():
        """Automatically link entities with an exact name, type and (for people) pronoun match, across the whole library."""
        return {"linked": links.auto_link(lib)}

    def person(uid):
        """The person id inside a `p:<n>` unit id."""
        uid = str(uid)
        if not uid.startswith("p:") or uid[2:] not in lib.state["persons"]:
            raise HTTPException(404, "That linked entity doesn't exist.")
        return uid[2:]

    @r.post("/api/links/link")
    def link(body: dict = Body(...)):
        """Link two entities (or a person and an entity) as one."""
        a, b = need(body, "a"), need(body, "b")
        if a == b:
            raise HTTPException(400, "Choose two different entities")
        for u in (a, b):
            if str(u).startswith("p:"):
                person(u)
        return {"id": lib.link(a, b, body.get("name"))}

    @r.post("/api/links/reject")
    def reject(body: dict = Body(...)):
        """Remember that two entities are not the same."""
        lib.reject(need(body, "a"), need(body, "b"))
        return {"ok": True}

    @r.post("/api/links/unlink")
    def unlink(body: dict = Body(...)):
        """Take one book's entity out of a linked person."""
        lib.unlink(person(need(body, "id")), need(body, "book"), whole(body, "coref", 0))
        return {"ok": True}

    @r.post("/api/links/unlink_all")
    def unlink_all(body: dict = Body(...)):
        """Dissolve a linked person entirely: every member becomes its own entity again."""
        lib.unlink_all(person(need(body, "id")))
        return {"ok": True}

    return r
