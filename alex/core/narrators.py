"""Suggest narrators from "I" in the narration: who narrates each book, and runs of
paragraphs whose "I" belongs to someone else."""
from __future__ import annotations

from collections import Counter, defaultdict

from . import dialogue as dl
from .bookdata import parse_ekey
from .corpus import cindex

FIRST = {"i", "me", "my", "mine", "myself"}
NOTE = ("Only first-person pronouns outside quotes are counted (I, me, my, mine, myself), each belonging to whichever character "
        "BookNLP grouped it with. The book's suggestion is the character behind most of them. A suggested exception is a run of "
        "paragraphs whose “I” belongs to someone other than the book's narrator. Paragraphs without any “I” can sit inside a run "
        "if no more than the set number of them come in a row; a paragraph whose “I” is the book's narrator ends it. "
        "Strength is the share of the run's “I” that belongs to the suggested narrator. “We” isn't counted.")


def _unnamed(view, uid):
    """Whether a unit is a group with neither a name nor a description (only pronouns)."""
    key = parse_ekey(uid)
    g = view.bd[key[0]].groups.get(key[1]) if key and key[0] in view.bd else None
    return bool(g) and not g.forms["PROP"] and not g.forms["NOM"]


def _label(view, uid):
    """A unit's name for display, marking groups that have no name."""
    name = view.name_of(uid)
    if _unnamed(view, uid):
        return f"“{name}” (group {parse_ekey(uid)[1]}, no name)"
    return name


def book_suggestions(view, b, max_gap=3, min_evidence=2):
    """Who narrates book b and which stretches are told by someone else, from the "I" outside quotes.
    The suggested narrator is the character behind most of them. A run is a stretch of paragraphs whose "I" belongs to
    someone other than the narrator (paragraphs with no "I" can sit inside it, up to `max_gap` in a row); runs with fewer
    than `min_evidence` "I" or that you rejected are left out, and a run is `done` once you have assigned its paragraphs."""
    bd = view.bd[b]
    ci = cindex(bd)
    ann = view.lib.ann["books"].get(b, {})
    pkeys = dl.keys(bd)["p"]
    per_para = defaultdict(Counter)
    marks_by_para = defaultdict(list)
    total = Counter()
    for m in bd.mentions:
        c, s, e, prop, cat, text, h = m
        if prop != "PRON" or text.lower() not in FIRST or ci["in_quote"][s]:
            continue
        u = dl.unit_of(view, b, c)
        pid = bd.para[s]
        per_para[pid][u] += 1
        marks_by_para[pid].append((s, e, u))
        total[u] += 1
    n_fp = sum(total.values())
    candidates = [{"id": u, "name": _label(view, u), "n": n, "share": 100 * n / n_fp, "unnamed": _unnamed(view, u)}
                  for u, n in total.most_common(6)]
    current = ann.get("narrator")
    narrator = current or (candidates[0]["id"] if candidates else None)
    # runs of paragraphs told by someone else
    rejected = set(ann.get("narr_rejected", []))
    exceptions = ann.get("para_narrators", {})
    paras = [pid for pid, (s, e) in sorted(bd.para_bounds.items())
             if any(ci["isword"][t] and not ci["in_quote"][t] for t in range(s, e + 1))]
    runs, cur, gap = [], None, []
    for pid in paras:
        votes = per_para.get(pid)
        top = votes.most_common(1)[0][0] if votes else None
        if top is None:
            if cur:
                gap.append(pid)
                if len(gap) > max_gap:
                    runs.append(cur)
                    cur, gap = None, []
            continue
        if top == narrator:
            if cur:
                runs.append(cur)
            cur, gap = None, []
            continue
        if cur and cur["unit"] == top:
            cur["pids"] += gap + [pid]
            gap = []
        else:
            if cur:
                runs.append(cur)
            cur, gap = {"unit": top, "pids": [pid]}, []
    if cur:
        runs.append(cur)
    out = []
    for r in runs:
        u, pids = r["unit"], r["pids"]
        votes = Counter()
        for pid in pids:
            votes.update(per_para.get(pid, {}))
        ev = votes[u]
        if ev < min_evidence:
            continue
        key = f"{pkeys[pids[0]]}|{pkeys[pids[-1]]}|{u}"
        if key in rejected:
            continue
        done = all(exceptions.get(pkeys[p]) == u for p in pids)
        samples = []
        for pid in pids:
            if len(samples) >= 3:
                break
            ms = [(s, e) for s, e, uu in marks_by_para.get(pid, []) if uu == u]
            if not ms:
                continue
            sid = bd.sent[ms[0][0]]
            a, z = bd.sent_bounds[sid]
            samples.append({"tok": ms[0][0], "text": bd.span_text(a, z, [(s, e, "m") for s, e in ms if a <= s <= z])})
        s0, e1 = bd.para_bounds[pids[0]][0], bd.para_bounds[pids[-1]][1]
        out.append({"key": key, "unit": u, "name": _label(view, u), "unnamed": _unnamed(view, u), "pids": pids,
                    "paragraphs": len(pids), "evidence": ev, "against": sum(votes.values()) - ev,
                    "narrator_votes": votes.get(narrator, 0), "strength": ev / max(1, sum(votes.values())),
                    "from": round(100 * s0 / max(1, bd.n_tokens), 1), "to": round(100 * e1 / max(1, bd.n_tokens), 1),
                    "tok": s0, "words": sum(1 for t in range(s0, e1 + 1) if ci["isword"][t] and not ci["in_quote"][t]),
                    "done": done, "samples": samples})
    return {"book": b, "title": view.title(b), "first_person": n_fp, "candidates": candidates,
            "current": {"id": current, "name": _label(view, current)} if current else None,
            "suggested": candidates[0] if candidates else None, "narrator": narrator,
            "narrator_name": _label(view, narrator) if narrator else None, "runs": out}


def suggestions(view, max_gap=3, min_evidence=2):
    """Narrator suggestions for every book of the view."""
    return {"books": [book_suggestions(view, b, max_gap, min_evidence) for b in view.books], "note": NOTE}
