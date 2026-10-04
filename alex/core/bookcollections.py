"""Collections: the folders you organise your books in.

A collection has a name, may sit inside another collection (so they nest like folders), and holds any books you put in it.
A book can be in several collections at once (like tags, unlike files), and belongs to none until you add it.
Removing a collection never touches books: it only removes the grouping, and its sub-collections move up one level.

Stored in `library.json` under `collections`: `{id: {"name", "parent": id or None, "books": [book id]}}`, with the next free
number in `next_collection`. The functions here take the `Library`, change its state under its lock and save it; they raise
`ValueError` for input that can't be used (a blank or repeated name, a move into itself) and `KeyError` for an unknown id.
"""
from __future__ import annotations


def _get(lib, cid):
    """One collection's record (KeyError if there is none)."""
    return lib.state["collections"][cid]


def _siblings(lib, parent):
    """Names (lowercase) of the collections directly inside `parent` (None = the top level)."""
    return {c["name"].lower(): cid for cid, c in lib.state["collections"].items() if c["parent"] == parent}


def descendants(lib, cid):
    """A collection and everything nested inside it, as a set of ids."""
    found, todo = set(), [cid]
    while todo:
        c = todo.pop()
        if c in found:
            continue
        found.add(c)
        todo += [k for k, v in lib.state["collections"].items() if v["parent"] == c]
    return found


def books_in(lib, cid, deep=True):
    """Book ids in a collection; with `deep`, also those in the collections nested inside it (each book once)."""
    ids = descendants(lib, cid) if deep else {cid}
    members = {b for c in ids for b in lib.state["collections"][c]["books"]}
    return [b for b in lib.found() if b in members]


def create(lib, name, parent=None):
    """Make a collection (at the top level, or inside `parent`) -> its id."""
    name = str(name or "").strip()
    if not name:
        raise ValueError("Give the collection a name.")
    with lib.lock:
        if parent is not None:
            _get(lib, parent)
        if name.lower() in _siblings(lib, parent):
            raise ValueError(f"There is already a collection called “{name}” here.")
        cid = str(lib.state["next_collection"])
        lib.state["next_collection"] += 1
        lib.state["collections"][cid] = {"name": name, "parent": parent, "books": []}
        lib.save()
        return cid


def update(lib, cid, name=None, parent=..., add=(), remove=()):
    """Rename a collection, move it (`parent` None = to the top level; leave it out to keep it where it is), and add or remove books."""
    with lib.lock:
        c = _get(lib, cid)
        new_name = c["name"] if name is None else str(name).strip()
        new_parent = c["parent"] if parent is ... else parent
        if not new_name:
            raise ValueError("Give the collection a name.")
        if new_parent is not None:
            _get(lib, new_parent)
            if new_parent in descendants(lib, cid):
                raise ValueError("A collection can't be moved into itself or into one of its own sub-collections.")
        clash = _siblings(lib, new_parent).get(new_name.lower())
        if clash not in (None, cid):
            raise ValueError(f"There is already a collection called “{new_name}” there.")
        c["name"], c["parent"] = new_name, new_parent
        known = lib.found()
        c["books"] = [b for b in dict.fromkeys(list(c["books"]) + [b for b in add if b in known]) if b not in set(remove)]
        lib.save()


def delete(lib, cid):
    """Remove a collection. Its books are untouched and its sub-collections move up to its parent (renamed if that would clash)."""
    with lib.lock:
        c = _get(lib, cid)
        for k, v in lib.state["collections"].items():
            if v["parent"] == cid:
                v["parent"] = c["parent"]
                names = _siblings(lib, c["parent"])
                base, n = v["name"], 2
                while names.get(v["name"].lower(), k) != k:
                    v["name"], n = f"{base} ({n})", n + 1
        del lib.state["collections"][cid]
        lib.save()


def listing(lib):
    """Every collection for the browser: id, name, parent, `books` (directly in it) and `deep` (also in those nested inside it),
    parents before children and siblings by name. Books no longer in the library are left out."""
    found = set(lib.found())
    rows = []

    def walk(parent):
        for cid, c in sorted(((k, v) for k, v in lib.state["collections"].items() if v["parent"] == parent), key=lambda kv: kv[1]["name"].lower()):
            rows.append({"id": cid, "name": c["name"], "parent": parent, "books": [b for b in c["books"] if b in found], "deep": books_in(lib, cid)})
            walk(cid)
    walk(None)
    return rows
