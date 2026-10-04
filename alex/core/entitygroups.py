"""Saved groups of entities: a set of entities you analyse together (Entities → select several → "Save as group").

A group is `{"name", "ids"}` in `library.json` under `groups` (next free number in `next_group`); `ids` are unit ids
(`e:<book>:<coref>` or `p:<n>`, see `library.py`). A group only lists entities, it doesn't copy their figures, so it follows
your minimum-mentions setting, the selected books and your links: `View.group_of` looks the ids up again each time.
The functions take the `Library`, change its state under its lock and save it; `ValueError` means input that can't be used
(a blank or repeated name, nothing to group), `KeyError` an unknown group.
"""
from __future__ import annotations


def _clean(ids):
    """Unit ids as a list of unique strings, in order."""
    return list(dict.fromkeys(str(i) for i in (ids or []) if str(i).startswith(("e:", "p:"))))


def _check_name(lib, name, own=None):
    """The trimmed name, if it is given and not already used by another group."""
    name = str(name or "").strip()
    if not name:
        raise ValueError("Give the group a name.")
    if any(g["name"].lower() == name.lower() for gid, g in lib.state["groups"].items() if gid != own):
        raise ValueError(f"There is already a group called “{name}”.")
    return name


def get(lib, gid):
    """A saved group's (name, unit ids); KeyError if there is none."""
    g = lib.state["groups"][str(gid)]
    return g["name"], list(g["ids"])


def create(lib, name, ids):
    """Save a group of entities -> its id."""
    ids = _clean(ids)
    if not ids:
        raise ValueError("Select at least one entity to group.")
    with lib.lock:
        name = _check_name(lib, name)
        gid = str(lib.state["next_group"])
        lib.state["next_group"] += 1
        lib.state["groups"][gid] = {"name": name, "ids": ids}
        lib.save()
        return gid


def update(lib, gid, name=None, ids=None):
    """Rename a group and/or replace its entities."""
    with lib.lock:
        g = lib.state["groups"][str(gid)]
        if name is not None:
            g["name"] = _check_name(lib, name, own=str(gid))
        if ids is not None:
            new = _clean(ids)
            if not new:
                raise ValueError("A group needs at least one entity; delete it instead.")
            g["ids"] = new
        lib.save()


def delete(lib, gid):
    """Remove a group (the entities are untouched)."""
    with lib.lock:
        del lib.state["groups"][str(gid)]
        lib.save()


def listing(lib):
    """Every group for the browser, by name: `{id, name, ids}`."""
    return sorted(({"id": gid, "name": g["name"], "ids": list(g["ids"])} for gid, g in lib.state["groups"].items()), key=lambda g: g["name"].lower())
