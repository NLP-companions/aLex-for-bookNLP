"""The analyser's own state, and the books it reads.

Two things live here:

* **Where the books are.** `Library.scan()` looks through the source folders for BookNLP
  exports; `Library.book()` loads one (parsing is slow, so the result is saved in the
  cache folder (`bookcache.py`) and reused until the files change). The book folders are only ever read.
* **What you have added.** Book details, collections of books (`bookcollections.py`), tags, links between entities of different
  books ("persons"), saved groups of entities (`entitygroups.py`), plural groups (`plurals.py`), settings and rejected link
  suggestions are kept in `library.json`; your
  corrections to narrators, addressees and conversations are kept in `annotations.json`.
  Both files are written atomically (write a temporary file, then rename it).

Everything is stored under one data folder (`alex-data` in the folder the analyser is started from unless another is given, or the
`ALEX_DATA` environment variable is set), so tests and experiments can use a separate one.

Entity ids ("units") used across the analyser:

* `e:<book>:<coref>`  one BookNLP coreference group in one book;
* `p:<n>`             a person/place you linked across books (see `Library.link`).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from . import bookcache, plurals
from .bookdata import TYPES, BookData, ekey, parse_ekey



def data_home() -> Path:
    """The analyser's data folder: `ALEX_DATA` if that is set, else `alex-data` in the current folder (as a full path)."""
    return Path(os.environ.get("ALEX_DATA") or "alex-data").expanduser().resolve()
STAMP = re.compile(r"-(\d{8}-\d{6})$")                            # "<book>-20260924-201753": the editor's export folders
EXTS = ("tokens", "entities", "quotes", "supersense", "book", "txt")     # the files that make up a book
CACHE_VERSION = 12   # bump when BookData's structure changes, so old caches are ignored


class LibraryError(Exception):
    """The analyser's own files can't be read (for example a damaged library.json)."""


def default_state():
    """A fresh library.json: no source folders, book details, links, tags or collections (folders are added on the Library page or with `--books`)."""
    return {
        "sources": [],
        "books": {},
        "settings": {"min": {t: 2 for t in TYPES}, "count_mode": "per_book", "conv_gap": 100, "plural": False},
        "persons": {},
        "entity_tags": {},
        "entity_names": {},
        "entity_notes": {},
        "rejected": [],
        "next_person": 1,
        "collections": {},
        "next_collection": 1,
        "groups": {},
        "next_group": 1,
        "plurals": {},
        "plural_rejected": [],
        "narrator_links": {},
        "next_narrator_link": 1,
    }


def _read_json(path: Path, what: str):
    """Read a JSON file, turning a damaged or unreadable one into a `LibraryError` that says which file and why."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise LibraryError(f"{what} ({path}) can't be read: {e}. Fix or move the file and start again; nothing has been changed.") from e


def _write_json(path: Path, data):
    """Write JSON so that a crash never leaves a half-written file: write beside it, then rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class Library:
    """The analyser's books and your own settings, under one data folder.
    `state` is library.json (see default_state), `ann` is annotations.json; both are saved on every change.
    Books are found by `scan`, loaded by `book`, and described by `meta`. One lock guards the files and the book cache."""
    def __init__(self, data_dir=None, sources=None):
        self.lock = threading.RLock()          # guards the two json files and the book cache
        self.version = 0         # bumped on every change to either file (and by `reopen`, so nothing cached for another folder is reused)
        self.ann_version = 0     # bumped when corrections change, so cached results that depend on them are rebuilt
        self._generation = 0     # bumped by `reopen`, so a `warm` still running for the old folder stops
        self._open(data_dir, sources)

    def _open(self, data_dir, sources):
        """Read a data folder into this library. Everything is read before anything is replaced, so a folder that can't be read
        (`LibraryError`) leaves the library as it was."""
        data_dir = Path(data_dir) if data_dir else data_home()
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "cache").mkdir(exist_ok=True)
        state_path, annot_path = data_dir / "library.json", data_dir / "annotations.json"
        state = default_state()
        if state_path.exists():
            saved = _read_json(state_path, "The analyser's settings file")
            saved_settings = saved.pop("settings", {})
            state.update(saved)
            settings = state["settings"]
            settings.update({k: v for k, v in saved_settings.items() if k != "min"})
            settings["min"] = {**settings["min"], **saved_settings.get("min", {})}
        if sources is not None:
            state["sources"] = [str(s) for s in sources]
        ann = _read_json(annot_path, "Your corrections file") if annot_path.exists() else {"books": {}}
        ann.setdefault("books", {})
        with self.lock:
            self.data_dir = data_dir
            self.cache_dir = data_dir / "cache"
            self.state_path, self.annot_path = state_path, annot_path
            self.state, self.ann = state, ann
            self._loaded: dict[tuple, BookData] = {}       # book key -> the parsed book
            self._plural: dict[tuple, BookData] = {}       # (book key, declarations applied) -> its plural_copy
            self._found: dict = {}
            self.link_units: dict = {}                     # links.py's per-entity summaries of the whole library: minimum mentions -> (stamp, units)

    def reopen(self, data_dir, sources=None):
        """Switch to another data folder (a workspace, see workspaces.py) without making a new `Library`, so everything that holds
        this one sees the new folder. Raises `LibraryError` and changes nothing if the folder's files can't be read. Callers
        should also drop what they cached from the old folder (the API `Context` does)."""
        with self.lock:
            self._open(data_dir, sources)
            self._generation += 1
            self.version += 1
            self.ann_version += 1

    # ---------- persistence ----------
    def save(self):
        """Write library.json."""
        with self.lock:
            _write_json(self.state_path, self.state)
            self.version += 1

    def ann_book(self, bid):
        """One book's corrections, created empty on first use."""
        return self.ann["books"].setdefault(bid, {"narrator": None, "para_narrators": {}, "addressees": {},
                                                  "splits": [], "merges": [], "participants": {}})

    def save_ann(self):
        """Write annotations.json."""
        with self.lock:
            _write_json(self.annot_path, self.ann)
            self.ann_version += 1
            self.version += 1

    # ---------- discovery ----------
    def scan(self):
        """Find every book in the source folders -> ({book id: [versions, newest first]}, [problems]).

        A source can be a folder of exports (one dated subfolder per export) or a folder that
        holds BookNLP files directly. A book needs at least `.tokens` and `.entities`."""
        found, problems, seen = {}, [], set()
        for src in self.state["sources"]:
            root = Path(src).expanduser()
            if not root.is_dir():
                problems.append(f"Folder not found: {root}")
                continue
            for folder in [root] + sorted(p for p in root.iterdir() if p.is_dir()):
                for tok in folder.glob("*.tokens"):
                    bid = tok.stem
                    if not (folder / f"{bid}.entities").exists():
                        continue
                    if (bid, os.path.realpath(folder)) in seen:       # the same folder reached through two sources (a folder and its parent)
                        continue
                    seen.add((bid, os.path.realpath(folder)))
                    m = STAMP.search(folder.name)
                    stamp = m.group(1) if m else time.strftime("%Y%m%d-%H%M%S", time.localtime(tok.stat().st_mtime))
                    found.setdefault(bid, []).append({"folder": str(folder), "stamp": stamp, "exported": bool(m)})
        for versions in found.values():
            versions.sort(key=lambda v: v["stamp"], reverse=True)
        self._found = found
        return found, problems

    def add_sources(self, folders) -> list[str]:
        """Add folders to look for books in (full paths; ones already listed are skipped) and save -> the folders that were added."""
        with self.lock:
            new = []
            for folder in folders:
                path = str(Path(folder).expanduser().resolve())
                if path not in self.state["sources"] and path not in new:
                    new.append(path)
            if new:
                self.state["sources"] += new
                self.reset_scan()
                self.save()
            return new

    def reset_scan(self):
        """Forget the last scan (after the source folders changed)."""
        self._found = {}

    def found(self):
        """The books found by the last scan, scanning first if there hasn't been one."""
        return self._found or self.scan()[0]

    def folder_for(self, bid):
        """The folder of the export used for a book: the one you pinned, else the newest."""
        versions = self._found.get(bid) or self.scan()[0].get(bid)
        if not versions:
            return None
        pinned = self.state["books"].get(bid, {}).get("pinned")
        if pinned and any(v["folder"] == pinned for v in versions):
            return Path(pinned)
        return Path(versions[0]["folder"])

    # ---------- loading ----------
    def _signature(self, bid, folder):
        """Modification times of a book's files: changes whenever a new export replaces them."""
        return tuple((folder / f"{bid}.{e}").stat().st_mtime if (folder / f"{bid}.{e}").exists() else 0 for e in EXTS)

    def book_key(self, bid):
        """Identifies the current version of a book's data; changes when the export used or its files change."""
        folder = self.folder_for(bid)
        if folder is None:
            raise KeyError(bid)
        return (bid, str(folder), self._signature(bid, folder))

    def book(self, bid, plural=False) -> BookData:
        """Load a book (from memory, else from the cache, else by parsing its files), with your plural-group declarations
        applied (plurals.py). `plural`: the book counted the "include plural-group mentions" way, made from the parsed book
        (`BookData.plural_copy`) and kept in memory until the declarations or the files change."""
        key = self.book_key(bid)
        folder = Path(key[1])
        with self.lock:
            bd = self._loaded.get(key)
            if bd is None:
                bd = self._parsed(bid, folder, key)
                for k in [k for k in self._loaded if k[0] == bid]:              # the book's files changed
                    del self._loaded[k]
                self._plural = {k: v for k, v in self._plural.items() if k[0][0] != bid}
                self._loaded[key] = bd
            bd.set_members(plurals.book_map(self, bid))
            if not plural:
                return bd
            pk = (key, bd.members_sig)
            if pk not in self._plural:
                self._plural = {k: v for k, v in self._plural.items() if k[0] != key}
                self._plural[pk] = bd.plural_copy()
            return self._plural[pk]

    def warm(self):
        """Load every book now (from the cache, else by parsing it), so the first page doesn't have to wait for them. A book that can't
        be read is skipped here and reported by the page that needs it."""
        generation = self._generation
        for bid in list(self.found()):
            if generation != self._generation:         # the library was switched to another folder meanwhile
                return
            try:
                self.book(bid)
            except Exception:  # noqa: BLE001
                continue

    def _parsed(self, bid, folder, key):
        """The parsed book from the cache, else parsed from its files and cached (outdated caches of it are removed)."""
        digest = hashlib.sha1(repr((CACHE_VERSION,) + key).encode()).hexdigest()[:16]
        cache_file = self.cache_dir / f"{bid}-{digest}.pkl"
        if cache_file.exists():
            try:
                return bookcache.loads(cache_file.read_bytes())
            except Exception:  # noqa: BLE001 - a damaged, outdated or unexpected cache is simply rebuilt
                pass
        bd = BookData(bid, folder)
        for old in self.cache_dir.glob(f"{bid}-*.pkl"):     # not another book whose id starts "<bid>-"
            if re.fullmatch(re.escape(bid) + r"-[0-9a-f]{16}(-p)?\.pkl", old.name):
                old.unlink(missing_ok=True)
        tmp = cache_file.with_suffix(".tmp")
        tmp.write_bytes(bookcache.dumps(bd))
        tmp.replace(cache_file)
        return bd

    def meta(self, bid):
        """A book's details as shown in the interface (title falls back to the id)."""
        m = self.state["books"].get(bid, {})
        return {"title": m.get("title") or bid, "author": m.get("author", ""), "year": m.get("year", ""),
                "series": m.get("series", ""), "tags": m.get("tags", []), "pinned": m.get("pinned")}

    def set_meta(self, bid, patch):
        """Change some of a book's details (title, author, year, series, tags, pinned)."""
        with self.lock:
            m = self.state["books"].setdefault(bid, {})
            for k in ("title", "author", "year", "series", "tags", "pinned"):
                if k in patch:
                    m[k] = patch[k]
            self.save()

    # ---------- units: entities and the persons you link across books ----------
    ekey = staticmethod(ekey)      # the unit id of one coreference group in one book (see bookdata.ekey)

    def person_of(self):
        """(book, coref) -> person id, for every entity you have linked."""
        return {(bid, int(c)): pid for pid, p in self.state["persons"].items() for bid, c in p["members"]}

    def tags_of(self, uid):
        """Tags of an entity or linked person."""
        if uid.startswith("p:"):
            return self.state["persons"].get(uid[2:], {}).get("tags", [])
        return self.state["entity_tags"].get(uid, [])

    def set_tags(self, uid, tags):
        """Replace an entity's or person's tags (sorted, blanks dropped)."""
        tags = sorted({t.strip() for t in tags if t.strip()})
        with self.lock:
            if uid.startswith("p:"):
                if uid[2:] not in self.state["persons"]:
                    raise KeyError(uid)
                self.state["persons"][uid[2:]]["tags"] = tags
            elif tags:
                self.state["entity_tags"][uid] = tags
            else:
                self.state["entity_tags"].pop(uid, None)
            self.save()

    def name_of(self, uid):
        """Your name for an entity, linked person or narrator link, if you gave one; else None (the page falls back to
        the name found in the books, or, for a narrator link, to its members' own names)."""
        if uid.startswith("p:"):
            return self.state["persons"].get(uid[2:], {}).get("name")
        if uid.startswith("nl:"):
            return self.state["narrator_links"].get(uid[3:], {}).get("name")
        return self.state["entity_names"].get(uid)

    def set_name(self, uid, name):
        """Give an entity, linked person or narrator link a name (blank goes back to the one found in the books)."""
        name = name.strip() or None
        with self.lock:
            if uid.startswith("p:"):
                if uid[2:] not in self.state["persons"]:
                    raise KeyError(uid)
                self.state["persons"][uid[2:]]["name"] = name
            elif uid.startswith("nl:"):
                if uid[3:] not in self.state["narrator_links"]:
                    raise KeyError(uid)
                self.state["narrator_links"][uid[3:]]["name"] = name
            elif name:
                self.state["entity_names"][uid] = name
            else:
                self.state["entity_names"].pop(uid, None)
            self.save()

    def note_of(self, uid):
        """Your short description of an entity or linked person, or ""."""
        if uid.startswith("p:"):
            return self.state["persons"].get(uid[2:], {}).get("note") or ""
        return self.state["entity_notes"].get(uid, "")

    def set_note(self, uid, note):
        """Give an entity or linked person a short free-text description (blank clears it)."""
        note = note.strip()
        with self.lock:
            if uid.startswith("p:"):
                if uid[2:] not in self.state["persons"]:
                    raise KeyError(uid)
                if note:
                    self.state["persons"][uid[2:]]["note"] = note
                else:
                    self.state["persons"][uid[2:]].pop("note", None)
            elif note:
                self.state["entity_notes"][uid] = note
            else:
                self.state["entity_notes"].pop(uid, None)
            self.save()

    def all_tags(self):
        """Every tag in use, case-insensitively sorted."""
        tags = set()
        for p in self.state["persons"].values():
            tags.update(p.get("tags", []))
        for t in self.state["entity_tags"].values():
            tags.update(t)
        return sorted(tags, key=str.lower)

    def link(self, a, b, name=None):
        """Treat two units (entity or person ids) as the same. Their members, tags, name and description are
        merged into one person, which is returned as `p:<n>`."""
        with self.lock:
            persons = self.state["persons"]

            def parts(u):
                """A unit's (members, tags, name, note); a single entity's tags, name and note move with it, taken
                out of `entity_tags` / `entity_names` / `entity_notes`."""
                if u.startswith("p:"):
                    p = persons[u[2:]]
                    return list(p["members"]), list(p.get("tags", [])), p.get("name"), p.get("note")
                key = parse_ekey(u)
                if key is None:
                    raise KeyError(u)
                bid, c = key
                return ([[bid, c]], self.state["entity_tags"].pop(u, []),
                        self.state["entity_names"].pop(u, None), self.state["entity_notes"].pop(u, None))

            ma, ta, na, oa = parts(a)
            mb, tb, nb, ob = parts(b)
            if a.startswith("p:"):
                pid = a[2:]
            elif b.startswith("p:"):
                pid = b[2:]
            else:
                pid = str(self.state["next_person"])
                self.state["next_person"] += 1
                persons[pid] = {"members": [], "tags": [], "name": None}
            for u in (a, b):                      # a person that is absorbed disappears
                if u.startswith("p:") and u[2:] != pid:
                    persons.pop(u[2:], None)
            members = []
            for m in ma + mb:
                if m not in members:
                    members.append(m)
            person = persons[pid]
            person["members"] = members
            person["tags"] = sorted(set(ta) | set(tb) | set(person.get("tags", [])))
            person["name"] = name or person.get("name") or na or nb
            note = person.get("note") or oa or ob
            if note:
                person["note"] = note
            self.save()
            return "p:" + pid

    def unlink(self, pid, bid, coref):
        """Take one book's entity out of a linked person, taking a copy of the person's tags, name and description
        with it (as tags already did). A person left with one member dissolves the same way."""
        with self.lock:
            p = self.state["persons"][pid]
            p["members"] = [m for m in p["members"] if not (m[0] == bid and int(m[1]) == int(coref))]
            tags, name, note = list(p.get("tags") or []), p.get("name"), p.get("note")
            key = self.ekey(bid, coref)
            if tags:
                self.state["entity_tags"][key] = tags
            if name:
                self.state["entity_names"][key] = name
            if note:
                self.state["entity_notes"][key] = note
            if len(p["members"]) <= 1:
                for m in p["members"]:
                    mkey = self.ekey(m[0], m[1])
                    if tags:
                        self.state["entity_tags"][mkey] = tags
                    if name:
                        self.state["entity_names"][mkey] = name
                    if note:
                        self.state["entity_notes"][mkey] = note
                del self.state["persons"][pid]
            self.save()

    def unlink_all(self, pid):
        """Dissolve a linked person entirely: every member becomes its own entity again, each taking a copy of the
        person's tags, name and description, the same way one member does when taken out with `unlink`."""
        with self.lock:
            p = self.state["persons"][pid]
            tags, name, note = list(p.get("tags") or []), p.get("name"), p.get("note")
            for bid, c in p["members"]:
                key = self.ekey(bid, c)
                if tags:
                    self.state["entity_tags"][key] = tags
                if name:
                    self.state["entity_names"][key] = name
                if note:
                    self.state["entity_notes"][key] = note
            del self.state["persons"][pid]
            self.save()

    def rename_person(self, pid, name):
        """Give a linked person a name (blank goes back to the name found in the books)."""
        with self.lock:
            self.state["persons"][pid]["name"] = name.strip() or None
            self.save()

    # ---------- linking narrator roles ----------
    # A narrator role (nar:<unit id> or nar:anon:<book>, see dialogue.py) isn't a unit, so it can't go through
    # `link`/`unlink` above (those expect a (book, coref) member); this is the same idea, kept separate, for roles.
    # A narrator link pools narration only — the underlying characters (if any), their mentions, relations, tags
    # and so on stay exactly as they were; only which role a paragraph's narration counts as "the same narrator" changes.
    def link_narrators(self, a, b, name=None):
        """Treat two narrator roles as the same narrator, merged into one narrator link, returned as `nl:<n>`."""
        with self.lock:
            links = self.state["narrator_links"]

            def parts(u):
                if u.startswith("nl:"):
                    link = links[u[3:]]
                    return list(link["members"]), link.get("name")
                return [u], None

            ma, na = parts(a)
            mb, nb = parts(b)
            if a.startswith("nl:"):
                lid = a[3:]
            elif b.startswith("nl:"):
                lid = b[3:]
            else:
                lid = str(self.state["next_narrator_link"])
                self.state["next_narrator_link"] += 1
                links[lid] = {"members": [], "name": None}
            for u in (a, b):                      # a narrator link that is absorbed disappears
                if u.startswith("nl:") and u[3:] != lid:
                    links.pop(u[3:], None)
            members = []
            for m in ma + mb:
                if m not in members:
                    members.append(m)
            link = links[lid]
            link["members"] = members
            link["name"] = name or link.get("name") or na or nb
            self.save()
            return "nl:" + lid

    def unlink_narrator(self, lid, role):
        """Take one narrator role out of a narrator link. A link left with one member dissolves."""
        with self.lock:
            link = self.state["narrator_links"][lid]
            link["members"] = [m for m in link["members"] if m != role]
            if len(link["members"]) <= 1:
                del self.state["narrator_links"][lid]
            self.save()

    def unlink_narrators_all(self, lid):
        """Dissolve a narrator link entirely: every role becomes its own narrator again."""
        with self.lock:
            del self.state["narrator_links"][lid]
            self.save()

    def narrator_link_of(self):
        """Narrator role id -> its narrator-link id (`nl:<n>`), for every role you've linked."""
        return {role: "nl:" + lid for lid, link in self.state["narrator_links"].items() for role in link["members"]}

    # ---------- rejected link suggestions ----------
    def entity_keys(self, u):
        """The single-book entity ids inside a unit (a person's members, or the entity itself)."""
        if u.startswith("p:"):
            return [self.ekey(b, c) for b, c in self.state["persons"].get(u[2:], {}).get("members", [])]
        return [u]

    def rejected_set(self):
        """The rejected pairs as a set of sorted tuples: pass it to `is_rejected` when checking many pairs in a row."""
        return {tuple(p) for p in self.state["rejected"]}

    def is_rejected(self, a, b, rejected=None):
        """Whether you said a and b are different (checked member by member, so it survives later links).
        `rejected`: the result of `rejected_set()`, if the caller already has it (it is rebuilt from the list otherwise)."""
        rejected = self.rejected_set() if rejected is None else rejected
        return any(tuple(sorted((x, y))) in rejected for x in self.entity_keys(a) for y in self.entity_keys(b))

    def reject(self, a, b):
        """Remember that a and b are different, as pairs of single-book entities."""
        with self.lock:
            rejected = self.rejected_set()
            for x in self.entity_keys(a):
                for y in self.entity_keys(b):
                    pair = tuple(sorted((x, y)))
                    if pair not in rejected:
                        self.state["rejected"].append(list(pair))
                        rejected.add(pair)
            self.save()
