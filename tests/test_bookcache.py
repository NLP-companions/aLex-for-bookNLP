"""The parsed-book cache is opened only if it holds nothing but a parsed book, and a refused or damaged cache is rebuilt."""
from __future__ import annotations

import os
import pickle

import pytest

from alex.core import bookcache
from alex.core.library import Library


def cache_files(lib):
    """The cache files the library has written so far."""
    return sorted(lib.cache_dir.glob("*.pkl"))


class Evil:
    """Something a pickle could carry to run a command when it is opened."""
    marker = None

    def __reduce__(self):
        return (os.system, (f"touch {self.marker}",))


@pytest.fixture
def evil(tmp_path):
    """Pickled bytes that would create a file called `marker` if they were ever executed -> (bytes, marker)."""
    Evil.marker = tmp_path / "executed"
    return pickle.dumps(Evil()), Evil.marker


def test_a_parsed_book_survives_a_round_trip_and_everything_in_the_real_cache_is_allowed(lib):
    """If `BookData` gains a field of another kind, this fails until its class is added to `bookcache.ALLOWED`."""
    first = lib.book("alpha")
    files = cache_files(lib)
    assert files, "parsing a book should write its cache"
    for f in files:
        again = bookcache.loads(f.read_bytes())                     # raises if the file holds a class that isn't allowed
        assert again.book_id == first.book_id and again.n_tokens == first.n_tokens and set(again.groups) == set(first.groups)


def test_code_inside_a_cache_file_is_refused_not_run(evil):
    data, marker = evil
    with pytest.raises(pickle.UnpicklingError, match="posix.system|nt.system|os.system"):
        bookcache.loads(data)
    assert not marker.exists()


def test_a_library_with_a_poisoned_cache_ignores_it_and_rebuilds_the_book(lib, corpus, evil, tmp_path):
    data, marker = evil
    expected = lib.book("alpha").n_tokens
    for f in cache_files(lib):
        f.write_bytes(data)                                         # someone else's cache folder, copied in
    fresh = Library(data_dir=lib.data_dir, sources=[corpus[0]])
    book = fresh.book("alpha")
    assert book.n_tokens == expected and not marker.exists()
    assert all(bookcache.loads(f.read_bytes()) for f in cache_files(fresh))   # and the cache was rewritten with a real book
