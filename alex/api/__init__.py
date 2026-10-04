"""The web API: one router per area, built around a shared `Context`.

    library.py    books, settings, entity list, tags, the export zip
    entities.py   profiles, comparisons, evidence, networks
    dialogue.py   dialogue views and your corrections
    corpus.py     concordance, word lists, n-grams, collocates, keywords, reference files
    narrative.py  arcs, style, stylometry, sentiment, emotion; the text view
    topics.py     topic models
    links.py      linking entities across books
    workspaces.py workspaces: list, create, switch, import a zip, delete

Every route takes and returns JSON. A route that is given something it can't use answers 400 with
`{"detail": "…"}`, which the browser shows as a message (see the handlers in app.py).
"""
from . import context, corpus, dialogue, entities, library, links, narrative
from . import topics as topics_api
from . import workspaces as workspaces_api


def routers(ctx, topics, workspaces):
    """All routers for a running analyser. `topics` is the topic-modelling package, or None if scikit-learn is missing;
    `workspaces` is the core.workspaces.Workspaces list."""
    return [library.router(ctx, topics), entities.router(ctx), dialogue.router(ctx), corpus.router(ctx),
            narrative.router(ctx, topics), topics_api.router(ctx, topics), links.router(ctx),
            workspaces_api.router(ctx, topics, workspaces)]


__all__ = ["context", "routers"]
