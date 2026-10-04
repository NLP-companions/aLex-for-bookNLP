"""Entity networks for a selection of books.

A network of a whole library can have thousands of entities, far more than can be read on a page (and betweenness and the layout
take minutes on them), so `build` keeps the `max_nodes` entities with the strongest links and records how many there were.
"""
from __future__ import annotations

import io
from collections import Counter
from itertools import combinations

import networkx as nx

from .dialogue import addressee_edges

MAX_NODES = 300          # entities shown by default; the browser can ask for up to LIMIT_NODES
LIMIT_NODES = 1000
KINDS = {
    "sentence": "Appear in the same sentence",
    "paragraph": "Appear in the same paragraph",
    "dialogue": "Speaker mentions them in a quote",
    "addressed": "Speaker talks to them (estimated)",
}
NOTES = {
    "sentence": "An edge joins two entities that are mentioned in the same sentence. Its weight is the number of sentences they share, summed over the selected books.",
    "paragraph": "An edge joins two entities that are mentioned in the same paragraph. Its weight is the number of paragraphs they share, summed over the selected books.",
    "dialogue": "A directed edge runs from a speaker to each entity mentioned inside one of their quotes (by name, description or pronoun). Its weight is the number of quotes. A speaker mentioning themselves is not counted.",
    "addressed": ("A directed edge runs from a speaker to the person each quote is estimated to be addressed to. Its weight is the number of quotes. "
                  "BookNLP doesn't record addressees; see the Dialogue page for how they are estimated."),
    "measures": ("Degree: number of neighbours. Strength: sum of edge weights. Betweenness and closeness treat 1 ÷ weight as the distance, "
                 "so frequent pairs count as close; betweenness is normalised to 0–1. Eigenvector centrality uses weights on the undirected graph. "
                 "Clustering is the weighted clustering coefficient (undirected). Communities come from the Louvain method on weights, with a fixed seed so results repeat. "
                 "For dialogue networks, in- and out- versions count incoming and outgoing edges separately. "
                 "Because distances are 1 ÷ weight, closeness can be above 1; compare values within one network rather than across networks. "
                 "Eigenvector centrality is only meaningful within a connected part, and is near zero outside the largest one. "
                 "Separate connected parts are drawn side by side, largest first."),
}


def build(view, kind="sentence", types=("PER",), min_weight=1, keep_isolated=False, focus=None, focus_top=15, max_nodes=MAX_NODES):
    """An entity network of the view -> networkx graph. kind: entities that share a sentence or paragraph (undirected, weight = how
    often), a speaker mentioning someone inside a quote, or a speaker talking to someone (directed). Edges weaker than
    `min_weight` are dropped, unlinked nodes too unless `keep_isolated`; `focus` keeps one entity and its `focus_top` strongest neighbours.
    At most `max_nodes` entities are kept (those with the greatest total link weight, then the most mentions); `G.graph["total_nodes"]`
    is how many there were before that."""
    types = set(types)
    directed = kind in ("dialogue", "addressed")
    G = nx.DiGraph() if directed else nx.Graph()
    for u in view.units.values():
        if u.type in types:
            G.add_node(u.id)
    nodes = set(G)                                  # the entities that may appear in the network
    w = Counter()
    for b, bd in view.bd.items():
        mu = lambda c: view.member_unit.get((b, c))
        if kind in ("sentence", "paragraph"):
            groups = bd.sent_members if kind == "sentence" else bd.para_members
            for cs in groups.values():
                us = {mu(c) for c in cs}
                us = sorted(x for x in us if x in nodes)
                # a plural group ("Holmes and Watson") and its own members always share its sentences: no edge for that
                same = {frozenset((mu(p), mu(m))) for p in cs for m in bd.groups[p].members}
                for a, c in combinations(us, 2):
                    if frozenset((a, c)) not in same:
                        w[(a, c)] += 1
        elif kind == "dialogue":
            for qi, q in enumerate(bd.quotes):
                if q["char"] is None:
                    continue
                sources = {mu(c) for c in bd.stands_for(q["char"])} & nodes      # with plural groups on, its members speak too
                targets = {mu(c) for c, prop, mi in bd.quote_mentions.get(qi, ()) for c in bd.mention_groups(mi)}
                for s in sources:
                    for t in targets:
                        if t in nodes and t not in sources:
                            w[(s, t)] += 1
    if kind == "addressed":
        for (a, c), n in addressee_edges(view).items():
            if a in nodes and c in nodes:
                w[(a, c)] += n
    for (a, c), n in w.items():
        if n >= min_weight:
            G.add_edge(a, c, weight=n)
    if focus and focus in G:
        nb = sorted(set(G.predecessors(focus)) | set(G.successors(focus)) if directed else G.neighbors(focus),
                    key=lambda x: -(G[focus][x]["weight"] if G.has_edge(focus, x) else G[x][focus]["weight"]))
        G = G.subgraph([focus] + nb[:focus_top]).copy()
    if not keep_isolated:
        G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n) == 0])
    G.graph["total_nodes"] = G.number_of_nodes()
    if G.number_of_nodes() > max_nodes:
        strength = dict(G.degree(weight="weight"))
        keep = sorted(G.nodes, key=lambda n: (-strength[n], -view.units[n].mentions, n))[:max_nodes]
        G = G.subgraph(keep).copy()
        G.graph["total_nodes"] = len(strength)
        if not keep_isolated:                      # nodes whose only partners were cut are alone now
            G.remove_nodes_from([n for n in list(G.nodes) if G.degree(n) == 0])
    return G


def measures(G):
    """Node measures (degree, strength, betweenness, closeness, eigenvector, clustering, Louvain community) and network figures; see NOTES["measures"]."""
    if G.number_of_nodes() == 0:
        return {}, {}
    U = G.to_undirected() if G.is_directed() else G
    for a, b, d in G.edges(data=True):
        d["distance"] = 1 / d["weight"]
    if G.is_directed():
        for a, b, d in U.edges(data=True):
            d["weight"] = (G[a][b]["weight"] if G.has_edge(a, b) else 0) + (G[b][a]["weight"] if G.has_edge(b, a) else 0)
            d["distance"] = 1 / d["weight"]
    m = {n: {} for n in G}
    for n in G:
        m[n]["degree"] = U.degree(n)
        m[n]["strength"] = U.degree(n, weight="weight")
        if G.is_directed():
            m[n]["in_degree"], m[n]["out_degree"] = G.in_degree(n), G.out_degree(n)
            m[n]["in_strength"], m[n]["out_strength"] = G.in_degree(n, weight="weight"), G.out_degree(n, weight="weight")
    for name, fn in (("betweenness", lambda: nx.betweenness_centrality(G, weight="distance", normalized=True)),
                     ("closeness", lambda: nx.closeness_centrality(G, distance="distance")),
                     ("eigenvector", lambda: nx.eigenvector_centrality(U, weight="weight", max_iter=2000)),
                     ("clustering", lambda: nx.clustering(U, weight="weight"))):
        try:
            vals = fn()
        except Exception:  # noqa: BLE001 - e.g. eigenvector not converging
            vals = {}
        for n in G:
            m[n][name] = vals.get(n)
    comm = {}
    try:
        for i, c in enumerate(sorted(nx.community.louvain_communities(U, weight="weight", seed=42), key=len, reverse=True)):
            for n in c:
                comm[n] = i + 1
    except Exception:  # noqa: BLE001
        pass
    for n in G:
        m[n]["community"] = comm.get(n)
    info = {"nodes": G.number_of_nodes(), "edges": G.number_of_edges(), "density": nx.density(G),
            "components": nx.number_connected_components(U), "communities": len(set(comm.values())),
            "total_nodes": G.graph.get("total_nodes", G.number_of_nodes())}
    return m, info


def _spring(U, nodes):
    """A spring layout of one connected part, scaled to 0…1 in both directions."""
    n = len(nodes)
    if n == 1:
        return {nodes[0]: (0.5, 0.5)}
    raw = nx.spring_layout(U.subgraph(nodes), weight="weight", seed=42, k=1.6 / n ** 0.5, iterations=200)
    xs = [p[0] for p in raw.values()]
    ys = [p[1] for p in raw.values()]
    sx, sy = (max(xs) - min(xs)) or 1, (max(ys) - min(ys)) or 1
    return {v: ((p[0] - min(xs)) / sx, (p[1] - min(ys)) / sy) for v, p in raw.items()}


def layout(G, aspect=1.56):
    """Lay out each connected part on its own. The largest part fills most of the
    canvas; smaller parts are packed in rows in a column on the right."""
    if G.number_of_nodes() == 0:
        return {}
    U = G.to_undirected() if G.is_directed() else G
    parts = sorted((list(c) for c in nx.connected_components(U)), key=len, reverse=True)
    main = _spring(U, parts[0])
    if len(parts) == 1:
        return {v: (0.03 + 0.94 * x, 0.03 + 0.94 * y) for v, (x, y) in main.items()}
    rest_n = sum(len(p) for p in parts[1:])
    f = min(0.8, max(0.55, len(parts[0]) / (len(parts[0]) + rest_n)))
    out = {v: (0.02 + (f - 0.04) * x, 0.03 + 0.94 * y) for v, (x, y) in main.items()}
    # shelf-pack the other parts into the right-hand column, in canvas units (width = aspect, height = 1)
    x0, width = (f + 0.02) * aspect, (1 - f - 0.03) * aspect
    sides = [len(p) ** 0.5 for p in parts[1:]]
    scale = 0.12
    for _ in range(40):
        x = y = row = 0.0
        placed = []
        for side in sides:
            w = max(0.05, side * scale)
            if x > 0 and x + w > width:
                x, y, row = 0.0, y + row + 0.03, 0.0
            placed.append((x, y, w))
            x += w + 0.03
            row = max(row, w)
        if y + row <= 0.94 or scale < 0.01:
            break
        scale *= 0.85
    for nodes, (px, py, w) in zip(parts[1:], placed):
        pos = _spring(U, nodes)
        inner = w * (0.8 if len(nodes) > 1 else 0.3)
        off = (w - inner) / 2
        for v, (a, b) in pos.items():
            out[v] = ((x0 + px + off + a * inner) / aspect, 0.03 + py + off + b * inner)
    return {v: (min(0.98, max(0.02, x)), min(0.98, max(0.02, y))) for v, (x, y) in out.items()}


def as_json(view, G):
    """The network for the browser: nodes (with name, type, position and measures) and edges."""
    m, info = measures(G)
    pos = layout(G)
    nodes = []
    for n in G:
        u = view.units[n]
        nodes.append({"id": n, "name": u.name, "type": u.type, "tags": u.tags, "mentions": u.mentions,
                      "books": len(u.books), "x": pos[n][0], "y": pos[n][1], **m[n]})
    edges = [{"source": a, "target": b, "weight": d["weight"]} for a, b, d in G.edges(data=True)]
    return {"nodes": nodes, "edges": edges, "info": info, "directed": G.is_directed()}


WHOLE_MEASURES = ("degree", "in_degree", "out_degree", "community")      # the measures that are counts; the others are written as decimals


def export(view, G, fmt):
    """The network as GEXF or GraphML bytes, with attributes (as plain Python numbers, one type per attribute) and positions."""
    m, _ = measures(G)
    pos = layout(G)
    H = G.__class__()
    for n in G:
        u = view.units[n]
        attrs = {"label": u.name, "type": u.type, "tags": "; ".join(u.tags), "mentions": int(u.mentions),
                 "books": "; ".join(view.title(b) for b in sorted(u.books)), "x": float(pos[n][0]) * 1000, "y": float(pos[n][1]) * 1000}
        for k, v in m[n].items():
            if v is not None:
                attrs[k] = int(v) if k in WHOLE_MEASURES else float(v)   # plain numbers, one type per attribute (newer networkx refuses a mix)
        H.add_node(n, **attrs)
    for a, b, d in G.edges(data=True):
        H.add_edge(a, b, weight=d["weight"])
    buf = io.BytesIO()
    if fmt == "gexf":
        for n, d in H.nodes(data=True):
            d["viz"] = {"position": {"x": d["x"], "y": d["y"], "z": 0.0}}
        nx.write_gexf(H, buf)
    else:
        nx.write_graphml(H, buf)
    return buf.getvalue()
