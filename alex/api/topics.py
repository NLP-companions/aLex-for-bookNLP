"""Topic models: fitting and storing them, the model overview, a topic's page, comparisons, and their use on entity pages."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException

from .context import Context, need, unit_target, whole


def router(ctx: Context, topics) -> APIRouter:
    """Routes for topic models."""
    r = APIRouter()

    def ready():
        """The topics package, or a readable error if scikit-learn isn't installed."""
        if topics is None:
            raise HTTPException(400, "Topic modelling needs scikit-learn. Run: pip install scikit-learn")
        return topics

    @r.get("/api/topics/models")
    def models():
        """The stored models."""
        return {"models": ready().list_models()}

    @r.post("/api/topics/fit")
    def fit(body: dict = Body(...)):
        """Fit a model of the selected books and store it -> its id."""
        t = ready()
        v = ctx.of(body)
        cfg = t.clean_cfg(body.get("cfg"))
        name = str(body.get("name") or "").strip()[:80] or f"{cfg['method'].upper()}, {cfg['k']} topics, {len(t.list_models()) + 1}"
        return {"id": t.build(v, cfg, name)["id"]}

    @r.post("/api/topics/scan")
    def scan(body: dict = Body(...)):
        """Fit one model per number of topics and report quality, to help choosing how many."""
        t = ready()
        v = ctx.of(body)
        cfg = t.clean_cfg(body.get("cfg"))
        ks = sorted({max(2, min(60, int(k))) for k in body.get("ks", [])})[:20]
        if not ks:
            raise HTTPException(400, "Choose at least one number of topics.")
        return t.scan(v, cfg, ks)

    @r.post("/api/topics/model")
    def model(body: dict = Body(...)):
        """A model's overview."""
        return ready().overview(ctx.lib, need(body, "id"))

    @r.post("/api/topics/page")
    def page(body: dict = Body(...)):
        """One part of a topic's page: words, where, groups, passages, entities or speech."""
        t = ready()
        mid, topic, part = need(body, "id"), whole(body, "topic", 0), body.get("part")
        if part == "words":
            return t.part_words(mid, topic)
        v = ctx.view(t.load(mid)["books"], body.get("plural"))
        if part == "where":
            return t.part_where(v, mid, topic, body.get("seg"))
        if part == "groups":
            return t.part_groups(v, ctx.lib, mid, topic)
        if part == "passages":
            return t.part_passages(v, mid, topic, whole(body, "n", 8, 1, 30), body.get("book") or None)
        if part == "entities":
            return t.part_entities(v, mid, topic)
        if part == "speech":
            return t.part_speech(v, mid, topic)
        raise HTTPException(400, "Unknown part.")

    @r.post("/api/topics/compare")
    def compare(body: dict = Body(...)):
        """Comparisons between the topics of one model: map, pair, groups (topic × book etc.) or items (topic × character/speaker)."""
        t = ready()
        mid, part = need(body, "id"), body.get("part")
        if part == "map":
            return t.compare_map(mid)
        if part == "groups":
            return t.grid_groups(ctx.lib, mid, body.get("by", "book"))
        v = ctx.view(t.load(mid)["books"], body.get("plural"))
        if part == "pair":
            return t.compare_pair(v, mid, whole(body, "a", 0), whole(body, "b", 1), body.get("seg"))
        if part == "items":
            return t.grid_items(v, mid, body.get("kind", "mentions"), body.get("types") or None, whole(body, "min", 10, 1), whole(body, "limit", 40, 1, 200))
        raise HTTPException(400, "Unknown part.")

    @r.post("/api/topics/entity")
    def entity(body: dict = Body(...)):
        """The topics of one entity's (or a group's) mentions or speech, for the entity page."""
        v = ctx.of(body)
        ref = {"id": body.get("unit"), "ids": body.get("ids"), "group": body.get("group"), "name": body.get("name")}   # `id` here is the model's
        return ready().entity_topics(v, need(body, "id"), unit_target(v, ref), body.get("kind", "mentions"))

    @r.post("/api/topics/rename")
    def rename(body: dict = Body(...)):
        """Rename a model or one of its topics."""
        ready().rename(need(body, "id"), body.get("name"), body.get("topic"), body.get("label"))
        return {"ok": True}

    @r.post("/api/topics/delete")
    def delete(body: dict = Body(...)):
        """Delete a model."""
        ready().delete(need(body, "id"))
        return {"ok": True}

    return r
