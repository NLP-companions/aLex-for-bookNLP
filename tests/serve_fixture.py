"""Serve the synthetic corpus, for the browser tests (and for trying the analyser without your own books).

    python tests/serve_fixture.py            # http://127.0.0.1:8799, data in a temporary folder
    python tests/serve_fixture.py --port 8800 --keep /tmp/analyser-demo
    python tests/serve_fixture.py --many 60  # sixty small generated books instead of three, to see how the pages cope

Nothing outside the chosen folder is touched.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]

import fixture  # noqa: E402


def make_library(folder: Path, many: int = 0):
    """Write the corpus (the three books, or `many` generated ones) and open a library over it (its own data folder inside `folder`)."""
    from alex.core.library import Library
    if many:
        fixture.build_many(folder / "exports", many)
    else:
        fixture.build(folder / "exports")
    lib = Library(data_dir=folder / "data", sources=[folder / "exports"])
    lib.save()                    # keep the sources in library.json, so the library still finds its books after switching workspace and back
    return lib


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8799)
    parser.add_argument("--keep", help="use this folder (created if needed) instead of a temporary one")
    parser.add_argument("--many", type=int, default=0, help="serve this many small generated books instead of the usual three")
    args = parser.parse_args()
    import uvicorn

    from alex import app as app_module
    folder = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="analyser-fixture-"))
    folder.mkdir(parents=True, exist_ok=True)
    print(f"Serving the synthetic corpus from {folder} at http://127.0.0.1:{args.port}/")
    uvicorn.run(app_module.build_app(make_library(folder, args.many)), host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
