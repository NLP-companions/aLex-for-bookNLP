"""Export: the selected books and your work on them, as one .zip.

The zip holds, for the books you select:

    manifest.json              `format` (FORMAT), when it was made and the export folder each book came from
    books/<book>/<book>.*      the BookNLP files of the export in use (`Library.folder_for`): .tokens, .entities, .quotes,
                               .supersense, .book and the original .txt, whichever exist
    state/library.json         your settings and work, cut down to the selected books (`scoped_state`)
    state/annotations.json     your corrections for the selected books (`scoped_annotations`)
    topics/<id>.json           fitted topic models whose documents all come from the selected books
    references/<id>.json       the keyword reference files (they belong to no book, so all of them)

Nothing is written outside the zip, and the book folders are only read. `scoped_state` is a plain filter: nothing is renamed
or merged, so every id in the zip means what it meant in the library. It differs from `library.json` in these ways:

* `sources` (folders on this computer) and each book's `pinned` export (the zip has only the one in use) are left out;
* a linked person (`persons`) or narrator link keeps only the members in the selected books, and stays even if one is left
  (so ids like `p:17` that corrections refer to remain valid); one with no member left is dropped;
* tags, names, notes, saved groups, plural groups, rejected pairs and collections keep what touches a selected book, and
  a collection also stays when only a collection inside it does (so the folders nest as before);
* the counters for the next free id (`next_person`…) are kept, so a later import can't hand out an id twice.
"""
from __future__ import annotations

import json
import time
import zipfile
from pathlib import Path

from . import bookcollections
from .library import EXTS, Library
from .plurals import groups_of

FORMAT = 1                    # bump when the layout above changes, so an import can tell what it is reading
ANON_ROLE = "nar:anon:"       # an unnamed narrator's role id is this followed by the book id (see dialogue.narrator_of)


# ---------- the state, cut down to the selected books ----------
def _touches(lib: Library, uid: str, keep: set) -> bool:
    """Whether a unit id (`e:<book>:<coref>` or `p:<n>`) has a group in one of the books in `keep`."""
    return any(book in keep for book, _ in groups_of(lib, uid))


def _role_touches(lib: Library, role: str, keep: set) -> bool:
    """Whether a narrator role id (`nar:<unit id>` or `nar:anon:<book>`) belongs to one of the books in `keep`."""
    if role.startswith(ANON_ROLE):
        return role[len(ANON_ROLE):] in keep
    return _touches(lib, role[len("nar:"):], keep)


def _collections(lib: Library, keep: set) -> dict:
    """The collections that hold a selected book, directly or through a collection inside them, listing only selected books."""
    found = {}
    for cid, c in lib.state["collections"].items():
        deep = {b for d in bookcollections.descendants(lib, cid) for b in lib.state["collections"][d]["books"]}
        if deep & keep:
            found[cid] = {**c, "books": [b for b in c["books"] if b in keep]}
    return found


def scoped_state(lib: Library, keep: set) -> dict:
    """`library.json` as it stands, cut down to the book ids in `keep` (see the module docstring for what that means).
    Reads the live state: call it with `lib.lock` held, and serialise the result before releasing it."""
    s = lib.state
    touch = lambda uid: _touches(lib, uid, keep)         # noqa: E731
    persons = {pid: {**p, "members": [m for m in p["members"] if m[0] in keep]} for pid, p in s["persons"].items()}
    groups = {gid: {**g, "ids": [i for i in g["ids"] if touch(i)]} for gid, g in s["groups"].items()}
    plurals = {uid: [m for m in members if touch(m)] for uid, members in s["plurals"].items() if touch(uid)}
    links = {lid: {**k, "members": [m for m in k["members"] if _role_touches(lib, m, keep)]} for lid, k in s["narrator_links"].items()}
    return {
        "books": {b: {k: v for k, v in m.items() if k != "pinned"} for b, m in s["books"].items() if b in keep},
        "settings": s["settings"],
        "persons": {pid: p for pid, p in persons.items() if p["members"]},
        "entity_tags": {u: v for u, v in s["entity_tags"].items() if touch(u)},
        "entity_names": {u: v for u, v in s["entity_names"].items() if touch(u)},
        "entity_notes": {u: v for u, v in s["entity_notes"].items() if touch(u)},
        "rejected": [pair for pair in s["rejected"] if all(touch(u) for u in pair)],
        "collections": _collections(lib, keep),
        "groups": {gid: g for gid, g in groups.items() if g["ids"]},
        "plurals": {uid: ms for uid, ms in plurals.items() if ms},
        "plural_rejected": [u for u in s["plural_rejected"] if touch(u)],
        "narrator_links": {lid: k for lid, k in links.items() if k["members"]},
        "next_person": s["next_person"], "next_collection": s["next_collection"], "next_group": s["next_group"],
        "next_narrator_link": s["next_narrator_link"],
    }


def scoped_annotations(lib: Library, keep: set) -> dict:
    """`annotations.json` as it stands, with only the selected books' corrections (call it with `lib.lock` held, like `scoped_state`)."""
    return {"books": {b: a for b, a in lib.ann["books"].items() if b in keep}}


# ---------- the files ----------
def book_files(lib: Library, bid: str) -> list[Path]:
    """The BookNLP files of the export in use for a book (the ones that exist)."""
    folder = lib.folder_for(bid)
    return [folder / f"{bid}.{ext}" for ext in EXTS if (folder / f"{bid}.{ext}").exists()]


def topic_files(lib: Library, keep: set) -> list[Path]:
    """The topic model files whose documents all come from the books in `keep`. A damaged file is skipped, as the Topics page does."""
    found = []
    for p in sorted((lib.data_dir / "topics").glob("*.json")):
        try:
            books = json.loads(p.read_text(encoding="utf-8"))["books"]
        except (OSError, ValueError, KeyError):
            continue
        if books and set(books) <= keep:
            found.append(p)
    return found


def reference_files(lib: Library) -> list[Path]:
    """The keyword reference files."""
    return sorted((lib.data_dir / "references").glob("*.json"))


def write_zip(lib: Library, books: list[str], dest) -> dict:
    """Write the zip for the given book ids (all must be in the library) to the path `dest`. Returns the manifest."""
    keep = set(books)
    with lib.lock:                        # one consistent copy of your work, even if you change something meanwhile
        state = json.dumps(scoped_state(lib, keep), indent=1, ensure_ascii=False)
        annotations = json.dumps(scoped_annotations(lib, keep), indent=1, ensure_ascii=False)
        files = {b: book_files(lib, b) for b in books}
        exports = {b: lib.folder_for(b).name for b in books}
    manifest = {"format": FORMAT, "created": time.strftime("%Y-%m-%d %H:%M:%S"), "books": exports}
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, indent=1, ensure_ascii=False))
        z.writestr("state/library.json", state)
        z.writestr("state/annotations.json", annotations)
        for bid, paths in files.items():
            for p in paths:
                z.write(p, f"books/{bid}/{p.name}")
        for p in topic_files(lib, keep):
            z.write(p, f"topics/{p.name}")
        for p in reference_files(lib):
            z.write(p, f"references/{p.name}")
    return manifest
