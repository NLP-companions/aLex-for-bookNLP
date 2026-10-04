"""Where fitted models are kept: one JSON file per model, `<data folder>/topics/<id>.json`.

A model file holds the settings it was fitted with, its documents (book, first and last token),
the vocabulary, the topic–word and document–topic matrices, quality figures and your topic labels.
Files are written atomically, and the most recently read model is kept in memory.
The folder is set once at start-up with `configure` (tests give each run its own).
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from .errors import TopicError

_folder: Path | None = None
_lock = threading.RLock()
_cache: dict = {}          # model id -> (file modification time, model); at most one entry
_summaries: dict = {}      # model file -> (file modification time, its row in `list_models`): reading a model file takes a while


def configure(folder):
    """Use `folder` for models (created on first save)."""
    global _folder
    with _lock:
        _folder = Path(folder)
        _cache.clear()
        _summaries.clear()


def topics_dir() -> Path:
    """The models folder: the configured one, else `topics` inside the default data folder."""
    if _folder is not None:
        return _folder
    from ..library import DATA
    return DATA / "topics"


def path(mid) -> Path:
    """The file of model `mid`. Ids are lowercase letters, digits and hyphens, so no id can point outside the folder."""
    if not isinstance(mid, str) or not re.fullmatch(r"[a-z0-9-]+", mid):
        raise TopicError("Unknown model.")
    return topics_dir() / f"{mid}.json"


def save(model):
    """Write a model (compact JSON, atomically)."""
    with _lock:
        folder = topics_dir()
        folder.mkdir(parents=True, exist_ok=True)
        p = path(model["id"])
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(model, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        tmp.replace(p)


def load(mid):
    """Read a model. Do not modify the result: it is shared with other readers."""
    p = path(mid)
    with _lock:
        if not p.exists():
            raise TopicError("That model no longer exists.")
        stamp = p.stat().st_mtime_ns
        hit = _cache.get(mid)
        if hit and hit[0] == stamp:
            return hit[1]
        try:
            model = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise TopicError(f"The model file {p.name} can't be read ({e}). Delete it under Topics and fit the model again.") from None
        _cache.clear()
        _cache[mid] = (stamp, model)
        return model


def delete(mid):
    """Remove a model (no error if it is already gone)."""
    with _lock:
        path(mid).unlink(missing_ok=True)
        _cache.pop(mid, None)


def _summary(p):
    """The `list_models` row of the model file `p` (a model file can be large; this reads it whole)."""
    m = json.loads(p.read_text(encoding="utf-8"))
    c, me = m["cfg"], m["metrics"]
    stab = me["stability"]
    return {"id": m["id"], "name": m["name"], "created": m["created"], "books": m["books"],
            "titles": [m["titles"].get(b, b) for b in m["books"]], "method": c["method"], "k": me["k"],
            "docs": len(m["docs"]), "unit": c["unit"], "coherence": me["mean_coherence"], "diversity": me["diversity"],
            "stable": sum(1 for s in stab if s["recurs"] / s["of"] >= 0.6) if stab and stab[0]["of"] > 1 else None}


def list_models():
    """One summary row per model, newest first; unreadable files are skipped. A model's row is kept until its file changes."""
    folder = topics_dir()
    rows = []
    files = sorted(folder.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.exists() else []
    with _lock:
        for gone in [p for p in _summaries if p not in files]:
            del _summaries[gone]
        for p in files:
            try:
                stamp = p.stat().st_mtime_ns
                if p not in _summaries or _summaries[p][0] != stamp:
                    _summaries[p] = (stamp, _summary(p))
                rows.append(_summaries[p][1])
            except (OSError, ValueError, KeyError, TypeError):
                continue
    return rows


def rename(mid, name=None, topic=None, label=None):
    """Change a model's name, and/or the label of one topic (topic index and its new label)."""
    with _lock:
        m = json.loads(json.dumps(load(mid)))          # a copy: the loaded model is shared
        if name is not None:
            m["name"] = str(name).strip()[:80]
        if topic is not None:
            try:
                topic = int(topic)
            except (TypeError, ValueError):
                raise TopicError("Unknown topic.") from None
            if not 0 <= topic < len(m["labels"]):
                raise TopicError("Unknown topic.")
            m["labels"][topic] = str(label or "").strip()[:60]
        save(m)
