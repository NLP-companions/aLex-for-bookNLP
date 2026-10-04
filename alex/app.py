"""aLex, a BookNLP analyser: explore the books BookNLP has processed (its output files, or exports from the companion editor).

    alex                       start and open the browser (the same as `python -m alex`)
    alex --books FOLDER        also look for books in FOLDER (kept for next time; can be repeated)
    alex --data FOLDER         keep the analyser's own files in FOLDER (default: `alex-data` in the folder you start it from)
    alex --port 8770           use another port
    alex --no-browser          don't open the browser
    alex --workspace X         open the workspace called X (it is also the one opened next time)

This file only wires things together: it builds the web application (`build_app`), turns errors into
readable messages and starts the server. The work is in `core/` (analysis) and `api/` (routes).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from alex import api
from alex.api.context import Context
from alex.core.library import Library, LibraryError, data_home
from alex.core.workspaces import DEFAULT_ID, Workspaces
from alex.localonly import LocalOnly

try:                      # numpy and scikit-learn are only needed for topics; the rest works without them
    from alex.core import topics
    import sklearn  # noqa: F401  (imported only to find out whether it is installed)
except ImportError:
    topics = None

STATIC = Path(__file__).resolve().parent / "static"
log = logging.getLogger("alex")


class NoCacheStaticFiles(StaticFiles):
    """Static files that the browser re-checks on every load, so an updated script or style sheet is never stale."""

    async def get_response(self, path, scope):
        """Serve a file with `Cache-Control: no-cache`."""
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


def build_app(lib: Library, topics_module=topics, workspaces: Workspaces | None = None) -> FastAPI:
    """The web application for a library. `topics_module=None` switches the topic tools off (as if scikit-learn were missing).
    `workspaces`: the list of workspaces `lib` is the active one of (default: a list beside the library's data folder, with that
    folder as the Default workspace, which is what tests want)."""
    if workspaces is None:
        workspaces = Workspaces(lib.data_dir.parent / "workspaces.json", default_data=lib.data_dir)
    if topics_module is not None:
        topics_module.configure(lib.data_dir / "topics")
    ctx = Context(lib)
    app = FastAPI(title="BookNLP analyser")
    app.add_middleware(LocalOnly)           # only requests for this computer, and changes only from our own page (see localonly.py)

    # ---------- errors become messages the interface can show ----------
    def error(status, message):
        """A JSON error response with a `detail` message."""
        return JSONResponse({"detail": message}, status_code=status)

    @app.exception_handler(ValueError)
    async def bad_value(request: Request, exc: ValueError):
        """Something the user asked can't be done (a bad search, too little text…): the message says why."""
        return error(400, str(exc) or "That request can't be carried out.")

    @app.exception_handler(KeyError)
    async def bad_key(request: Request, exc: KeyError):
        """An id or field that doesn't exist (a book that was removed, a missing field)."""
        return error(400, f"Not found: {exc.args[0] if exc.args else 'something the request refers to'}.")

    @app.exception_handler(Exception)
    async def crash(request: Request, exc: Exception):
        """A bug: log it in the terminal and tell the interface something went wrong (with the reason, for bug reports)."""
        log.exception("Error in %s %s", request.method, request.url.path)
        return error(500, f"Something went wrong ({type(exc).__name__}: {exc}). Details are in the terminal.")

    for router in api.routers(ctx, topics_module, workspaces):
        app.include_router(router)

    @app.get("/")
    def index():
        """The page itself, with the id of the open workspace written in (the browser keeps its remembered settings per workspace)."""
        html = (STATIC / "index.html").read_text(encoding="utf-8").replace(
            "window.WORKSPACE = null;", f"window.WORKSPACE = {json.dumps(workspaces.active)};", 1)
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    app.mount("/static", NoCacheStaticFiles(directory=STATIC), name="static")
    return app


def main():
    """Start the analyser: read the library, then serve it on this computer only (127.0.0.1) and open the browser."""
    parser = argparse.ArgumentParser(prog="alex", description="aLex: explore books processed by BookNLP.")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--books", action="append", default=[], metavar="FOLDER",
                        help="a folder of BookNLP output to look for books in; it is added to the open workspace's folders (repeat for several)")
    parser.add_argument("--workspace", help="open this workspace (its id or name) and keep it as the one to open next time")
    parser.add_argument("--data", metavar="FOLDER", help="keep the analyser's own files here (default: the ALEX_DATA variable, else `alex-data` in the current folder)")
    args = parser.parse_args()
    for folder in args.books:
        if not Path(folder).expanduser().is_dir():
            sys.exit(f"\n--books: “{folder}” is not a folder.\n")
    import uvicorn

    try:
        home = Path(args.data).expanduser().resolve() if args.data else data_home()
        workspaces = Workspaces(home / "workspaces.json", default_data=home)
        if args.workspace:
            wanted = workspaces.find(args.workspace)
            workspaces.openable(wanted)
            workspaces.activate(wanted)
        if workspaces.active != DEFAULT_ID and not workspaces.folder().is_dir():
            print(f"Note: the folder of the workspace “{workspaces.get(workspaces.active)['name']}” is gone; opening Default instead.")
            workspaces.activate(DEFAULT_ID)
        lib = Library(data_dir=workspaces.folder())
    except (LibraryError, ValueError) as e:
        sys.exit(f"\n{e}\n")
    lib.add_sources(args.books)
    found, problems = lib.scan()
    for p in problems:
        print("Note:", p)
    print(f"\nData folder: {home}")
    print(f"Workspace “{workspaces.get(workspaces.active)['name']}”: {len(found)} book(s) found. Open http://127.0.0.1:{args.port}/ — press Ctrl+C to stop.\n")
    if not found:
        print("No books yet: add a folder of BookNLP output under Library in the browser, or restart with --books FOLDER.\n")
    threading.Thread(target=lib.warm, daemon=True).start()          # read the books while the browser opens
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(f"http://127.0.0.1:{args.port}/")).start()
    uvicorn.run(build_app(lib, workspaces=workspaces), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
