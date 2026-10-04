"""Shared fixtures. The synthetic corpus is written once per session; every test that changes
anything gets its own data folder, so tests never touch your real data."""
from __future__ import annotations

import pytest

import fixture
from alex.core.library import Library
from alex.core.view import View

BOOKS = ["alpha", "beta", "gamma"]


@pytest.fixture(scope="session")
def corpus(tmp_path_factory):
    """(folder with the exports, {book id: Truth})."""
    exports = tmp_path_factory.mktemp("exports")
    return exports, fixture.build(exports)


@pytest.fixture(scope="session")
def truth(corpus):
    return corpus[1]


@pytest.fixture
def lib(tmp_path, corpus):
    """A library over the synthetic books with its own empty data folder."""
    return Library(data_dir=tmp_path / "data", sources=[corpus[0]])


@pytest.fixture
def view(lib):
    """All three books."""
    return View(lib, BOOKS)


@pytest.fixture
def alpha(lib):
    return lib.book("alpha")


@pytest.fixture
def client(lib):
    """The web API over the synthetic books, as a test client."""
    from fastapi.testclient import TestClient

    from alex import app as app_module
    return TestClient(app_module.build_app(lib), base_url=fixture.LOCAL, raise_server_exceptions=False)
