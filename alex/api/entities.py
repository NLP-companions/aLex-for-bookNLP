"""Entity profiles, comparisons between entities or groups, evidence sentences and networks."""
from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Response

from alex.core import dialogue, entitygroups, network, plurals, stats
from alex.core.bookdata import RELATIONS

from .context import Context, is_group, need, real, whole


def stat_options(body):
    """The statistics options every comparison shares (measure, test, minimum frequency, significance level…). A measure or test
    the analyser doesn't have is refused with the list of those it has."""
    measure, test = body.get("measure", "ll"), body.get("test", "ll")
    if measure not in stats.MEASURES:
        raise ValueError(f"Unknown measure “{measure}”. Choose one of: {', '.join(stats.MEASURES)}.")
    if test not in stats.TESTS:
        raise ValueError(f"Unknown significance test “{test}”. Choose one of: {', '.join(stats.TESTS)}.")
    return dict(measure=measure, test=test,
                min_freq=whole(body, "min_freq", 3, 1), alpha=real(body, "alpha", 0.05, 1e-12, 1),
                bonferroni=bool(body.get("bonferroni", False)),
                direction=body.get("direction", "target"), show_all=bool(body.get("show_all", False)))


def router(ctx: Context) -> APIRouter:
    """Routes for entity profiles, saved groups, plural groups, comparisons, evidence and networks."""
    r = APIRouter()
    lib = ctx.lib

    @r.post("/api/profile")
    def profile(body: dict = Body(...)):
        """An entity's, narrator role's, book's or gender's profile, or a group's (`ids`, or a saved `group`) as one;
        404 if it isn't in the selection."""
        v = ctx.of(body)
        if is_group(body):
            p = v.group_profile(body)
        else:
            id_ = str(need(body, "id"))
            if id_.startswith(("nar:", "nl:")):
                p = dialogue.narrator_profile(v, id_)
            elif id_.startswith("book:"):
                p = v.book_profile(id_[len("book:"):])
            elif id_.startswith("gender:"):
                p = v.gender_profile(id_[len("gender:"):])
            else:
                p = v.profile(id_)
        if p is None:
            raise HTTPException(404, "This entity doesn't meet the minimum in the selected books.")
        return p

    # ---------- saved groups of entities ----------
    def group_reply(gid=None):
        """What every group route returns: the saved groups as they are now (and the id of the one just made)."""
        return {"groups": entitygroups.listing(lib), "id": gid}

    def in_group(action, *args, **kw):
        """Run a change to saved groups, turning an unknown id into a 404 (unusable input is a ValueError, hence a 400)."""
        try:
            return action(lib, *args, **kw)
        except KeyError:
            raise HTTPException(404, "That group doesn't exist.") from None

    @r.get("/api/groups")
    def groups():
        """The saved groups of entities."""
        return group_reply()

    @r.post("/api/groups")
    def group_new(body: dict = Body(...)):
        """Save a group of entities under a name."""
        return group_reply(in_group(entitygroups.create, body.get("name"), body.get("ids")))

    @r.post("/api/groups/delete")
    def group_delete(body: dict = Body(...)):
        """Delete a saved group (the entities stay)."""
        in_group(entitygroups.delete, str(need(body, "id")))
        return group_reply()

    @r.post("/api/groups/{gid}")
    def group_change(gid: str, body: dict = Body(...)):
        """Rename a saved group or replace its entities."""
        in_group(entitygroups.update, gid, **{k: body[k] for k in ("name", "ids") if k in body})
        return group_reply(gid)

    # ---------- plural groups ----------
    @r.post("/api/plurals")
    def plural_set(body: dict = Body(...)):
        """Declare an entity (`id`) a plural group: `add` and `remove` change its members (unit ids) and keep those a page
        doesn't show; `members` replaces them all (none makes it an ordinary entity again)."""
        uid = str(need(body, "id"))
        if "members" in body:
            return {"id": uid, "members": plurals.set_members(lib, uid, body.get("members") or [])}
        return {"id": uid, "members": plurals.change_members(lib, uid, body.get("add") or [], body.get("remove") or [])}

    @r.post("/api/plurals/suggestions")
    def plural_suggestions(body: dict = Body(...)):
        """People of the selected books named after two or more others ("Holmes and Watson"), with the members found."""
        return {"items": plurals.suggestions(ctx.view(body.get("books"), False))}

    @r.post("/api/plurals/reject")
    def plural_reject(body: dict = Body(...)):
        """Remember that a suggested plural group isn't one."""
        plurals.reject(lib, str(need(body, "id")))
        return {"ok": True}

    @r.post("/api/distinctive")
    def distinctive(body: dict = Body(...)):
        """Words markedly more typical of a target than of a reference."""
        v = ctx.of(body)
        rows, summary = v.distinctive(need(body, "target"), body.get("reference", {"kind": "others"}), body.get("rel", "agent"), **stat_options(body))
        return {"rows": rows[:300], "summary": summary}

    @r.post("/api/compare")
    def compare(body: dict = Body(...)):
        """Two entities or groups side by side."""
        v = ctx.of(body)
        a, b = need(body, "a"), need(body, "b")
        kw = stat_options({**body, "direction": "both"})
        a_members = frozenset(v.resolve(a)[0])
        out = {"a": v.group_summary(a), "b": v.group_summary(b, exclude=a_members), "distinctive": {}}
        for rel in RELATIONS:
            rows, summary = v.distinctive(a, b, rel, **kw)
            out["distinctive"][rel] = {"rows": rows[:200], "summary": summary}
        return out

    @r.post("/api/compare/books")
    def compare_books(body: dict = Body(...)):
        """Two books split into characters: every PER entity in either, with its mentions in each."""
        v = ctx.of(body)
        return {"rows": v.book_grid(need(body, "a"), need(body, "b"), whole(body, "top", 25, 1, 200))}

    @r.post("/api/bybook")
    def bybook(body: dict = Body(...)):
        """How a target's figures and words change from book to book."""
        v = ctx.of(body)
        kw = stat_options(body)
        return v.by_book(need(body, "target"), body.get("rel", "mod"), min_freq=kw["min_freq"], alpha=kw["alpha"], bonferroni=kw["bonferroni"])

    @r.post("/api/evidence")
    def evidence(body: dict = Body(...)):
        """The sentences behind a count."""
        return ctx.of(body).evidence(need(body, "target"), need(body, "kind"), body.get("key"), body.get("other"))

    # ---------- networks ----------
    def graph(body):
        """Build the network asked for -> (view, graph)."""
        v = ctx.of(body)
        kind = body.get("kind", "sentence")
        if kind not in network.KINDS:
            raise HTTPException(400, "Unknown network kind")
        G = network.build(v, kind, body.get("types") or ["PER"], whole(body, "min_weight", 1, 1), bool(body.get("keep_isolated")),
                          body.get("focus"), whole(body, "focus_top", 15, 1), whole(body, "max_nodes", network.MAX_NODES, 10, network.LIMIT_NODES))
        return v, G

    @r.post("/api/network")
    def net(body: dict = Body(...)):
        """A network as JSON (nodes with positions and measures, edges)."""
        v, G = graph(body)
        return network.as_json(v, G)

    @r.post("/api/network/export")
    def net_export(body: dict = Body(...)):
        """A network as a GEXF or GraphML file."""
        v, G = graph(body)
        fmt = "gexf" if body.get("format") == "gexf" else "graphml"
        return Response(network.export(v, G, fmt), media_type="application/xml",
                        headers={"Content-Disposition": f'attachment; filename="network-{body.get("kind", "sentence")}.{fmt}"'})

    return r
