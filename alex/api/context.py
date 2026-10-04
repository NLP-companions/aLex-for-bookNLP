"""What every route needs: the library, the cache of views, the folders for the analyser's own files, and
helpers for reading request bodies."""
from __future__ import annotations

import threading
from collections import OrderedDict

from fastapi import HTTPException

from alex.core.view import View


class Context:
    """Shared state of one running analyser (one per `build_app`)."""

    MAX_VIEWS = 6           # views kept in memory; a view holds the combined entities of a selection of books

    def __init__(self, lib):
        self.lib = lib
        self._views: OrderedDict = OrderedDict()
        self._remembered: OrderedDict = OrderedDict()               # last few concordance searches, so paging doesn't search again
        self._lock = threading.Lock()
        self.refs_dir, self.lexicon_path = self._folders()

    def _folders(self):
        """The reference-file folder and the emotion lexicon file of the library's data folder (both made if missing)."""
        refs, lexicon = self.lib.data_dir / "references", self.lib.data_dir / "lexicons" / "emotion.json"
        refs.mkdir(parents=True, exist_ok=True)
        lexicon.parent.mkdir(parents=True, exist_ok=True)
        return refs, lexicon

    def switch(self, data_dir):
        """Work in another data folder (a workspace): the library re-opens it (`Library.reopen`, which raises `LibraryError` and
        changes nothing if it can't be read), and everything kept from the old folder is dropped. Routes must read `refs_dir` and
        `lexicon_path` from here on each request, not keep them."""
        self.lib.reopen(data_dir)
        self.refs_dir, self.lexicon_path = self._folders()
        with self._lock:
            self._views.clear()
            self._remembered.clear()

    def selected(self, books) -> list:
        """The ids in a request's `books` that are in the library, each once, in the order given. A request that names
        no books, or none that exist, is a 400."""
        if not books or not isinstance(books, list):
            raise HTTPException(400, "No books selected")
        found = self.lib.found()
        books = [b for b in dict.fromkeys(books) if b in found]
        if not books:
            raise HTTPException(400, "None of the selected books were found")
        return books

    def view(self, books, plural=None) -> View:
        """The `View` of the given books (unknown ids are ignored), from the cache when nothing has changed since it
        was built: your settings, links and corrections (`lib.version`) and the books' files (`lib.book_key`).
        `plural` (a page's own choice, sent with its requests) overrides your setting for counting plural groups'
        mentions for their members; None uses the setting."""
        books = self.selected(books)
        plural = bool(self.lib.state["settings"].get("plural", False) if plural is None else plural)
        sig = (tuple(books), plural, self.lib.version, tuple(self.lib.book_key(b) for b in books))
        with self._lock:
            if sig in self._views:
                self._views.move_to_end(sig)
                return self._views[sig]
        view = View(self.lib, books, plural)                                # built outside the lock: it can take a while
        with self._lock:
            self._views[sig] = view
            while len(self._views) > self.MAX_VIEWS:
                self._views.popitem(last=False)
        return view

    def of(self, body) -> View:
        """The `View` a request asks about: its `books` and its page's `plural` choice (see `view`)."""
        return self.view(body.get("books"), body.get("plural"))

    @staticmethod
    def signature(view) -> tuple:
        """What a result computed from a view depends on, for keeping results: the view's books and plural setting, your settings,
        links and corrections (`lib.version`), and the books' files."""
        return (tuple(view.books), view.plural, view.lib.version, tuple(view.lib.book_key(b) for b in view.books))

    MAX_REMEMBERED = 4

    def remember(self, key, make):
        """The result `make()` gives for `key`, from the last few kept if there is one (the least recently used is forgotten)."""
        with self._lock:
            if key in self._remembered:
                self._remembered.move_to_end(key)
                return self._remembered[key]
        result = make()                                                       # outside the lock: it can take a while
        with self._lock:
            self._remembered[key] = result
            while len(self._remembered) > self.MAX_REMEMBERED:
                self._remembered.popitem(last=False)
        return result


# ---------- reading request bodies ----------
def whole(body, key, default, low=None, high=None):
    """body[key] as a whole number (default if absent), held between low and high; a readable error if it isn't a number."""
    value = body.get(key, default)
    try:
        value = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"“{key}” should be a whole number.") from None
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def real(body, key, default, low=None, high=None):
    """Like `whole`, for numbers with decimals."""
    value = body.get(key, default)
    try:
        value = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"“{key}” should be a number.") from None
    if low is not None:
        value = max(low, value)
    if high is not None:
        value = min(high, value)
    return value


def need(body, key):
    """body[key], or a readable error saying what is missing."""
    if key not in body or body[key] is None:
        raise ValueError(f"“{key}” is missing.")
    return body[key]


def is_group(body):
    """Whether a request names several entities (`ids`, or a saved `group`) rather than one (`id`)."""
    return body.get("ids") is not None or bool(body.get("group"))


def unit_target(view, body):
    """The unit (or virtual group unit) a request asks about, or None if it isn't in the selection; a readable error if the body names none."""
    if not is_group(body):
        need(body, "id")
    return view.target_unit(body)
