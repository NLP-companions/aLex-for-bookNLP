"""Workspaces: separate libraries you can switch between.

A **workspace** is one data folder (`Library(data_dir=…)`): its settings and source folders, your links, groups, collections and
corrections, topic models, reference files and the parse cache (see library.py). Nothing is shared between workspaces, so there is
nothing to merge; entities can't be linked across them. The workspace you work in is the *active* one.

* The **Default** workspace is the analyser's data folder itself (`alex-data`, see `library.data_home`), which points at the folders its books are in.
* A workspace you **create** gets its own folder under `workspaces/` and points at the source folders you give it.
* A workspace you **import** from an export zip (export.py) gets its own folder too, with a copy of the books in `books/`
  (its only source), so the zip works as it is on any computer.

The list of workspaces and the active one are kept in `workspaces.json` in the data folder (so experiments with a separate data
folder never touch the real list), the folders of created and imported workspaces beside it in `workspaces/`. Removing a workspace from the list (`forget`) never deletes files; `delete` does, but only for folders the analyser
made, never the active workspace, and only when its name is typed. Like the other stores, `Workspaces` raises `ValueError` for
input that can't be used (a blank or repeated name, a damaged zip) and `KeyError` for an unknown id.
"""
from __future__ import annotations

import json
import re
import shutil
import threading
import zipfile
from pathlib import Path

from . import export
from .library import Library, LibraryError, _read_json, _write_json, data_home

# the only files an import takes from a zip (anything else in it is ignored): export.py's layout
IMPORTED = re.compile(r"books/[^/]+/[^/]+|topics/[^/]+\.json|references/[^/]+\.json")
DEFAULT_ID = "default"


def default_registry() -> Path:
    """Where the list of workspaces is kept: `workspaces.json` in the data folder."""
    return data_home() / "workspaces.json"


def _slug(name: str) -> str:
    """A folder-name-safe version of a workspace name."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40] or "workspace"


class Workspaces:
    """The list of workspaces in one registry file, and which is active. `registry`: the file (default: `default_registry()`);
    `default_data`: the Default workspace's folder (default: the analyser's data folder). Changes are saved at once under one lock."""

    def __init__(self, registry=None, default_data=None):
        self.path = Path(registry) if registry else default_registry()
        self.root = self.path.parent / "workspaces"           # where created and imported workspaces get their folders
        self.lock = threading.RLock()
        default = {"name": "Default", "path": str(Path(default_data) if default_data else data_home())}
        self.state = {"active": DEFAULT_ID, "workspaces": {DEFAULT_ID: default}}
        if self.path.exists():
            saved = _read_json(self.path, "The list of workspaces")
            if isinstance(saved.get("workspaces"), dict):
                self.state.update(saved)
            self.state["workspaces"].setdefault(DEFAULT_ID, default)           # the Default workspace is always there
            if self.state["active"] not in self.state["workspaces"]:
                self.state["active"] = DEFAULT_ID

    def save(self):
        """Write the registry (atomically)."""
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            _write_json(self.path, self.state)

    # ---------- reading ----------
    @property
    def active(self) -> str:
        """The id of the workspace in use."""
        return self.state["active"]

    def get(self, wid) -> dict:
        """One workspace's record `{name, path}` (KeyError if there is none)."""
        return self.state["workspaces"][wid]

    def folder(self, wid=None) -> Path:
        """The data folder of a workspace (the active one by default)."""
        return Path(self.get(wid or self.active)["path"])

    def listing(self) -> list[dict]:
        """Every workspace, in the order they were made: `id`, `name`, `path`, `active`, `missing` (its folder is gone; never for
        Default, whose folder is made when it is opened), `own_books` (it holds its own copy of the books, as an imported one does) and
        `owned` (the analyser made its folder, so it can be deleted)."""
        return [{"id": wid, "name": w["name"], "path": w["path"], "active": wid == self.active,
                 "missing": wid != DEFAULT_ID and not Path(w["path"]).is_dir(),
                 "own_books": (Path(w["path"]) / "books").is_dir(), "owned": self.owns(wid)} for wid, w in self.state["workspaces"].items()]

    def find(self, ref) -> str:
        """The id of the workspace a person means by its id or its name (any case); ValueError, listing the names, if there is none."""
        ref = str(ref).strip().lower()
        for wid, w in self.state["workspaces"].items():
            if ref in (wid, w["name"].lower()):
                return wid
        raise ValueError(f"No workspace “{ref}”. The workspaces are: " + ", ".join(w["name"] for w in self.state["workspaces"].values()) + ".")

    # ---------- changing ----------
    def _name(self, name, own=None) -> str:
        """The trimmed name, if it is given and not already used by another workspace."""
        name = str(name or "").strip()
        if not name:
            raise ValueError("Give the workspace a name.")
        if any(w["name"].lower() == name.lower() for wid, w in self.state["workspaces"].items() if wid != own):
            raise ValueError(f"There is already a workspace called “{name}”.")
        return name

    def _free_id(self, name) -> str:
        """An id for a new workspace: the name as a slug, with a number if it is taken (by a workspace or by a folder)."""
        base = _slug(name)
        wid, n = base, 1
        while wid in self.state["workspaces"] or (self.root / wid).exists():
            n += 1
            wid = f"{base}-{n}"
        return wid

    def _add(self, wid, name, folder):
        """Put a workspace in the list and save."""
        self.state["workspaces"][wid] = {"name": name, "path": str(folder)}
        self.save()

    def create(self, name, sources=None) -> str:
        """Make an empty workspace in its own folder, reading books from `sources` (default: none; folders are added later) -> its id."""
        with self.lock:
            name = self._name(name)
            wid = self._free_id(name)
            Library(data_dir=self.root / wid, sources=sources).save()
            self._add(wid, name, self.root / wid)
            return wid

    def rename(self, wid, name):
        """Rename a workspace."""
        with self.lock:
            self.get(wid)["name"] = self._name(name, own=wid)
            self.save()

    def openable(self, wid) -> Path:
        """The data folder of a workspace, if it can be opened (ValueError if the folder is gone). Check this before switching to it."""
        folder = Path(self.get(wid)["path"])
        if wid != DEFAULT_ID and not folder.is_dir():              # (opening the Default workspace makes its folder if need be)
            raise ValueError("That workspace's folder no longer exists. Remove it from the list.")
        return folder

    def activate(self, wid):
        """Make a workspace the one in use (its folder must still exist). The next start opens it too."""
        with self.lock:
            self.openable(wid)
            self.state["active"] = wid
            self.save()

    def forget(self, wid):
        """Take a workspace off the list. Its folder and files stay where they are. The active one can't be removed."""
        with self.lock:
            self.get(wid)
            if wid == DEFAULT_ID:
                raise ValueError("The Default workspace can't be removed from the list.")
            if wid == self.active:
                raise ValueError("Switch to another workspace first: the one in use can't be removed.")
            del self.state["workspaces"][wid]
            self.save()

    def owns(self, wid) -> bool:
        """Whether the analyser made a workspace's folder (created or imported), so that `delete` may remove it. The Default
        workspace and any folder you pointed the analyser at are not."""
        folder = Path(self.get(wid)["path"]).resolve()
        return folder != self.root.resolve() and self.root.resolve() in folder.parents

    def delete(self, wid, typed_name):
        """Delete a workspace's folder and take it off the list. This removes its copied books, links, corrections, topic models and
        everything else in the folder, and can't be undone, so it is only for workspaces the analyser made (`owns`), never the active
        one, and only when `typed_name` is exactly the workspace's name. Books in folders it merely pointed at are never touched."""
        with self.lock:
            w = self.get(wid)
            if not self.owns(wid):
                raise ValueError("Only workspaces the analyser created or imported can be deleted; this one lives in a folder of your own. Remove it from the list instead.")
            if wid == self.active:
                raise ValueError("Switch to another workspace first: the one in use can't be deleted.")
            if typed_name != w["name"]:
                raise ValueError("The name you typed doesn't match, so nothing was deleted.")
            if Path(w["path"]).exists():
                shutil.rmtree(w["path"])
            del self.state["workspaces"][wid]
            self.save()

    # ---------- import ----------
    @staticmethod
    def _manifest(z: zipfile.ZipFile) -> dict:
        """The manifest of an export zip, checked: it must be one of ours, of a format this version reads, with books that are complete."""
        try:
            manifest = json.loads(z.read("manifest.json"))
            books = manifest["books"]
            z.getinfo("state/library.json")
        except (KeyError, ValueError, TypeError):
            raise ValueError("That isn't an export from the analyser (manifest.json or state/library.json is missing or unreadable).") from None
        if manifest.get("format") != export.FORMAT:
            raise ValueError(f"That export has format {manifest.get('format')}; this version of the analyser reads format {export.FORMAT}.")
        names = set(z.namelist())
        for bid in books:
            if not all(f"books/{bid}/{bid}.{ext}" in names for ext in ("tokens", "entities")):
                raise ValueError(f"The book “{bid}” in that export is incomplete (its .tokens or .entities file is missing).")
        if not books:
            raise ValueError("That export holds no books.")
        return manifest

    def import_zip(self, zip_path, name=None) -> str:
        """Make a workspace from an export zip (export.py) -> its id. The books are copied into the workspace's `books/` folder, which
        becomes its only source; your state, topic models and reference files come along. Nothing is merged with another workspace.
        The workspace is built in a temporary folder and moved into place only when complete, so a bad zip leaves nothing behind."""
        try:
            z = zipfile.ZipFile(zip_path)
        except (zipfile.BadZipFile, OSError):
            raise ValueError("That isn't a zip file.") from None
        with z, self.lock:
            manifest = self._manifest(z)
            name = self._name(name or f"Imported {manifest.get('created', '')[:10]}".strip())
            wid = self._free_id(name)
            folder, building = self.root / wid, self.root / f"{wid}.importing"
            shutil.rmtree(building, ignore_errors=True)
            try:
                for member in z.namelist():
                    if IMPORTED.fullmatch(member) and ".." not in member.split("/"):    # stream each file out; nothing else in the zip is touched
                        target = building / member
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
                state = self._json(z, "state/library.json")
                state["sources"] = [str(folder / "books")]
                _write_json(building / "library.json", state)
                if "state/annotations.json" in z.namelist():
                    _write_json(building / "annotations.json", self._json(z, "state/annotations.json"))
                building.rename(folder)
            except BaseException:
                shutil.rmtree(building, ignore_errors=True)
                raise
            self._add(wid, name, folder)
            return wid

    @staticmethod
    def _json(z, member) -> dict:
        """A JSON object from a zip member, or a `ValueError` naming it."""
        try:
            data = json.loads(z.read(member))
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise ValueError(f"{member} in that export can't be read.")
        return data

