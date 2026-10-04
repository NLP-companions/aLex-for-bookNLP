"""The parsed-book cache: a parsed book is saved to a file so that the next start doesn't have to parse it again (see `Library._parsed`).

The cache is a Python pickle, and a pickle can be made to run any code when it is opened. The files in `alex-data/cache` are our own, but a
data folder can be copied from someone else, so `loads` opens a pickle only if it asks for nothing but the few classes a parsed book is made of
(`ALLOWED`). Anything else raises `pickle.UnpicklingError`, which `Library._parsed` treats like any damaged cache: it is ignored and rebuilt
from the book's files. When `BookData` gains a field of another kind, add its class here (a test fails until you do).
"""
from __future__ import annotations

import io
import pickle

ALLOWED = {
    ("alex.core.bookdata", "BookData"), ("alex.core.bookdata", "Group"),
    ("array", "array"), ("array", "_array_reconstructor"),
    ("collections", "Counter"), ("collections", "defaultdict"),
    ("builtins", "list"), ("builtins", "set"), ("builtins", "dict"), ("builtins", "tuple"), ("builtins", "frozenset"),
    ("pathlib", "PosixPath"), ("pathlib", "WindowsPath"),
    ("pathlib._local", "PosixPath"), ("pathlib._local", "WindowsPath"),          # where Python 3.13 keeps them
}


class _Unpickler(pickle.Unpickler):
    """An unpickler that looks up only the classes in `ALLOWED`."""

    def find_class(self, module, name):
        """The class `module.name`, if a parsed book may contain one; otherwise refuse the whole file."""
        if (module, name) not in ALLOWED:
            raise pickle.UnpicklingError(f"the cache asks for {module}.{name}, which a parsed book never contains")
        return super().find_class(module, name)


def dumps(book) -> bytes:
    """A parsed book as bytes, to be saved in the cache."""
    return pickle.dumps(book, protocol=pickle.HIGHEST_PROTOCOL)


def loads(data: bytes):
    """The parsed book in `data` (what `dumps` made). Raises an exception (`pickle.UnpicklingError` for anything unexpected) if it can't be read."""
    return _Unpickler(io.BytesIO(data)).load()
