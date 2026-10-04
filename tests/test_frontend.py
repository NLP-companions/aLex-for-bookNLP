"""The browser code, run in a simulated browser (jsdom) against a live server over the synthetic books.

Five scripts in tests/js do the work: smoke.mjs visits every page, interactions.mjs clicks and types through the main
features, units.mjs tests the helper functions, many.mjs opens the pages over a library of forty books, and empty.mjs
opens them with no books at all. They need Node and jsdom; if either is missing these tests are skipped.
To set up once:  cd tests/js && npm install
"""
from __future__ import annotations

import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest

JS_DIR = Path(__file__).resolve().parent / "js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(
    not NODE or not (JS_DIR / "node_modules" / "jsdom").exists(),
    reason="the browser tests need Node and jsdom: run `npm install` in tests/js")


def serve(lib):
    """Serve a library on a free port in this process -> (the address, a function that stops the server)."""
    import uvicorn

    from alex import app as app_module
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app_module.build_app(lib), host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    assert srv.started, "the test server didn't start"

    def stop():
        srv.should_exit = True
        thread.join(timeout=10)
    return f"http://127.0.0.1:{port}", stop


@pytest.fixture(scope="module")
def server(tmp_path_factory, corpus):
    """The analyser serving the synthetic books on a free port, in this process."""
    from alex.core.library import Library

    root = tmp_path_factory.mktemp("live")
    lib = Library(data_dir=root / "data", sources=[corpus[0]])
    lib.save()                      # keep the sources, so the library still finds its books after switching workspace and back
    address, stop = serve(lib)
    yield address
    stop()


@pytest.fixture(scope="module")
def many_books(tmp_path_factory):
    """The analyser serving forty generated books."""
    import fixture
    from alex.core.library import Library

    root = tmp_path_factory.mktemp("many")
    fixture.build_many(root / "exports", 40)
    lib = Library(data_dir=root / "data", sources=[root / "exports"])
    lib.save()
    address, stop = serve(lib)
    yield address
    stop()


@pytest.fixture(scope="module")
def empty_library(tmp_path_factory):
    """The analyser serving a library with no books and no source folders: what a new install starts with."""
    from alex.core.library import Library

    address, stop = serve(Library(data_dir=tmp_path_factory.mktemp("empty") / "data"))
    yield address
    stop()


def run_script(name, url, timeout=600):
    """Run one Node script against the server -> its JSON result (the last line it prints)."""
    proc = subprocess.run([NODE, name, url], cwd=JS_DIR, capture_output=True, text=True, timeout=timeout)
    lines = [l for l in proc.stdout.strip().splitlines() if l.strip()]
    assert lines, f"{name} printed nothing.\nstderr: {proc.stderr[-1500:]}"
    try:
        return json.loads(lines[-1])
    except ValueError:
        pytest.fail(f"{name} didn't finish cleanly:\n{proc.stdout[-1500:]}\n{proc.stderr[-1500:]}")


def test_every_page_loads(server):
    r = run_script("smoke.mjs", server)
    assert r["problems"] == [] and r["errorsAtEnd"] == []
    assert len(r["visited"]) >= 28


def test_the_main_features_work_when_used(server):
    r = run_script("interactions.mjs", server)
    assert r["failures"] == [] and r["errorsAtEnd"] == []
    assert len(r["passed"]) >= 12


def test_the_helper_functions(server):
    r = run_script("units.mjs", server)
    assert r["failures"] == [] and r["errorsAtEnd"] == []
    assert len(r["passed"]) >= 25


def test_the_pages_cope_with_forty_books(many_books):
    r = run_script("many.mjs", many_books)
    assert r["failures"] == [] and r["errorsAtEnd"] == []
    assert len(r["passed"]) >= 8


def test_a_new_install_with_no_books_opens_every_page_and_says_what_to_do(empty_library):
    r = run_script("empty.mjs", empty_library)
    assert r["problems"] == [] and r["errorsAtEnd"] == []
    assert len(r["visited"]) >= 20
