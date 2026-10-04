"""The in-text view: one chapter or slice of a book, paragraph by paragraph, with entities, quotes
(speaker and addressees), narrators, events, supersenses and topics marked.

`read` returns each paragraph's text with marks in the control-character form of
`BookData.span_text` (`\\x01class|data\\x02 … \\x03`); the browser turns them into <mark> elements:

    e <TYPE> <PROP|NOM|PRON> [in]|unit id    an entity mention ("in": the entity is counted, so it has a profile)
    q|<quote index>                          a quote (details in the response's `quotes`)
    ev|event, ss|<supersense>                events and supersenses
    tw|<topic id>                            a topic's top word
    sn|<sentence number>                     the first word of a sentence (the "sentences" layer: numbers from 1 in reading order)
    hit|                                     the place you jumped to
"""
from __future__ import annotations

import bisect

from . import dialogue as dl
from .corpus import cindex
from .narrative import book_segments


def read(view, b, cfg, index=None, tok=None, end=None, layers=None, topics=None, mark=True):
    """One segment of book b.

    index / tok   which segment: its number, or (with `tok`, and `end` for a span) the one holding that token, which is also marked
                  (unless `mark` is off: then the segment is just found, and `anchor` names the paragraph to scroll to);
    layers        any of entities, quotes, narrators, events, supersenses, sentences, topics (default: the first three); [] gives plain text;
    topics        {"model": id, "focus": topic id or None} for the topics layer.
    -> {book, title, index, mode, info, segments (label, words, and for chapters `pid` of the heading paragraph and its `source`),
        paragraphs (each with `no`, its number from 1 in reading order, and `tok`, its first token), anchor, quotes, topic_layer, default_narrator…}"""
    layers = set(layers if layers is not None else ["entities", "quotes", "narrators"])
    bd = view.bd[b]
    segs, info = book_segments(view, b, cfg)
    if tok is not None and not 0 <= tok < bd.n_tokens:
        tok = None                                     # a position outside the book: just show the segment asked for
    if tok is not None:
        # A paragraph is shown in the segment where it starts (a slice can end mid-paragraph), so find the token's segment
        # by its paragraph's first token; otherwise a jump into the tail of such a paragraph would land where it isn't shown.
        anchor = bd.para_bounds[bd.para[tok]][0]
        index = next((k for k, sg in enumerate(segs) if sg["start"] <= anchor <= sg["end"]), 0)
    index = max(0, min(len(segs) - 1, index or 0))
    sg = segs[index]
    s0, e0 = sg["start"], sg["end"]

    tl = None                                           # the topics layer, or its error
    if "topics" in layers and topics and topics.get("model"):
        try:
            from . import topics as topic_tools
            tl = topic_tools.reader_layer(view, b, topics["model"], topics.get("focus"), s0, e0)
        except Exception as e:  # noqa: BLE001 - scikit-learn missing, or a model that was deleted: the text still shows
            tl = {"error": str(e) or "Topics aren't available."}

    d = dl.bdlg(view, b)
    recs = [r for r in d["recs"] if r["end"] >= s0 and r["start"] <= e0]
    quotes = {}                                         # quote index -> what the side panel needs
    for r in recs:
        su = dl.unit_of(view, b, r["speaker"])
        addrs, method = dl.addressees(view, b, r)
        conv = d["convs"][r["conv"]]
        quotes[r["qi"]] = {"qi": r["qi"], "speaker": view.name_of(su) if su else None, "speaker_id": su,
                           "addressees": [{"id": a, "name": view.name_of(a)} for a in addrs], "method": method,
                           "conv": r["conv"], "first": conv[0]["qi"] == r["qi"], "verb": r["verb"]}

    ci = cindex(bd)
    mention_starts = bd.mention_starts
    para_no = {pid: k + 1 for k, pid in enumerate(sorted(bd.para_bounds))}
    sent_starts = sorted((bd.sent_bounds[sid][0], k + 1) for k, sid in enumerate(sorted(bd.sent_bounds)))      # (first token, sentence number)
    paras, last_doc, anchor = [], None, None
    for pid in sorted(p for p, (ps, pe) in bd.para_bounds.items() if s0 <= ps <= e0):
        ps, pe = bd.para_bounds[pid]
        marks = []
        if "sentences" in layers:
            i = bisect.bisect_left(sent_starts, (ps, 0))
            while i < len(sent_starts) and sent_starts[i][0] <= pe:
                marks.append((sent_starts[i][0], sent_starts[i][0], f"sn|{sent_starts[i][1]}"))
                i += 1
        if "quotes" in layers:
            for r in recs:
                a, z = max(ps, r["start"]), min(pe, r["end"])
                if a <= z:
                    marks.append((a, z, f"q|{r['qi']}"))
        if "entities" in layers:
            i = bisect.bisect_left(mention_starts, (ps, -1))
            while i < len(mention_starts) and mention_starts[i][0] <= pe:
                m = bd.mentions[mention_starts[i][1]]
                if m[2] <= pe:
                    u = view.member_unit.get((b, m[0]))
                    marks.append((m[1], m[2], f"e {m[4]} {m[3]}{' in' if u else ''}|{u or dl.unit_of(view, b, m[0])}"))
                i += 1
        if "events" in layers:
            marks += [(t, t, "ev|event") for t in range(ps, pe + 1) if bd.event[t]]
        if "supersenses" in layers:
            for t in range(ps, pe + 1):
                c = bd.ss.get(t)
                if c and bd.ss.get(t - 1) != c:                  # mark a supersense once, at its first token
                    marks.append((t, t, f"ss|{c}"))
        topic_info = None
        if tl and not tl["error"]:
            marks += [(t, t, f"tw|{tl['tok_topic'][t]}") for t in range(ps, pe + 1) if t in tl["tok_topic"]]
            di = tl["doc_at"](b, ps)                              # the topic model's document this paragraph starts in
            if di is not None and di in tl["docs"]:
                focus = tl["focus"]
                dom = int(focus if focus is not None else tl["docs"][di][0][0])
                topic_info = {"doc": di, "dom": dom, "w": float(tl["theta"][di, dom]), "first": di != last_doc}
                last_doc = di
        if tok is not None and ps <= tok <= pe:
            anchor = pid
            if mark:
                marks.append((tok, min(pe, end if end is not None else tok), "hit|"))
        rid, exception = dl.narrator_of(view, b, pid)
        has_narration = any(ci["isword"][t] and not ci["in_quote"][t] for t in range(ps, pe + 1))
        paras.append({"topic": topic_info, "pid": pid, "no": para_no[pid], "tok": ps, "text": bd.span_text(ps, pe, _nest(marks)),
                      "narrator": dl.role_name(view, rid) if has_narration else None,
                      "narrator_id": rid if has_narration else None, "exception": exception and has_narration,
                      "hit": mark and tok is not None and ps <= tok <= pe})

    ann = view.lib.ann["books"].get(b, {})
    topic_layer = None
    if tl:
        topic_layer = {"error": tl["error"]} if tl["error"] else {"error": None, "model": tl["model"], "focus": tl["focus"], "topics": tl["topics"],
                                                                    "docs": {str(i): v for i, v in tl["docs"].items()}}
    default_role = "nar:" + ann["narrator"] if ann.get("narrator") else "nar:anon:" + b
    return {"topic_layer": topic_layer, "book": b, "title": view.title(b), "index": index, "mode": info.get("mode"), "info": info,
            "segments": [{"label": x["label"], "words": x["words"], "source": x.get("source"), "pid": bd.para[x["head"]] if x.get("head") is not None else None} for x in segs],
            "paragraphs": paras, "anchor": anchor, "quotes": quotes, "default_narrator": ann.get("narrator"),
            "default_narrator_name": dl.role_name(view, default_role)}


def _nest(marks):
    """Keep marks properly nested (dropping any that would cross another), outermost first, so the markup is well formed."""
    marks.sort(key=lambda m: (m[0], -(m[1] - m[0])))
    out, stack = [], []
    for a, z, c in marks:
        while stack and stack[-1][1] < a:
            stack.pop()
        if stack and z > stack[-1][1]:
            continue                                # would cross the enclosing mark
        out.append((a, z, c))
        stack.append((a, z))
    return out
