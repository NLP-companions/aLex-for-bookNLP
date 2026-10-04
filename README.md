# aLex — BookNLP analyser

aLex lets you explore books that [BookNLP](https://github.com/booknlp/booknlp) has processed, in your browser: who and what is in them (people, places, organisations…), how they are referred to, what they do, who they appear with and speak to, what is distinctive about them, and how they are linked. It runs on your own computer; nothing is uploaded anywhere.

- **Entities:** a profile for every character, place and organisation, linked across books, grouped, tagged and compared.
- **Dialogue:** who speaks, how quotes are introduced, speaking style, conversations and estimated addressees.
- **Corpus tools:** concordance (KWIC), word lists, n-grams, collocates and keywords, with pattern queries over BookNLP's layers.
- **Narrative:** arcs, style measures, stylometry, sentiment and emotion, narrators, and a chapter editor.
- **Topics:** topic models (NMF or LDA) with comparison tools.
- **Networks** of who appears with or speaks to whom, exportable to Gephi.
- A **text view** of each book with entities, quotes and topics marked, **collections** of books, and separate **workspaces** for separate corpora.

What each figure means and how it is calculated is in [docs/MEASURES.md](docs/MEASURES.md).

## What you need

- **Python 3.10 or newer.**
- **BookNLP output for your books.** aLex does not run BookNLP and does not need it installed; it reads the files BookNLP writes. For each book it needs `<book>.tokens` and `<book>.entities`, and uses `<book>.quotes`, `<book>.supersense` and `<book>.book` when they are there. Put the files of each book in a folder (several books can share one folder, or each book can have its own).

aLex is developed and tested on macOS.

## Install

In a terminal:

```bash
python3 -m venv alex-env
source alex-env/bin/activate        # on Windows: alex-env\Scripts\activate
python -m pip install --upgrade pip
pip install git+https://github.com/sapphophonic/aLex.git
```

That creates a separate Python environment so aLex doesn't disturb anything else, brings its installer (pip) up to date, and installs aLex and what it needs (FastAPI, uvicorn, networkx, vaderSentiment, scikit-learn). To update later, run the `pip install` line again with `--upgrade`.

Prefer to work from a copy of the code? Clone the repository and run `pip install .` inside it (or `pip install -e .` if you want to change the code).

## Start it

With the environment active, in the folder where you want aLex to keep its files:

```bash
alex --books /path/to/folder/with/booknlp/output
```

It opens <http://127.0.0.1:8766/> in your browser. aLex answers only your own computer: other computers can't reach it, and neither can other web pages you have open (it refuses requests that don't come from its own page). `--books` is remembered, so next time `alex` alone is enough; you can also add folders later under **Library → Where to find books**. Stop it with Ctrl+C.

Other options: `--port` (default 8766), `--no-browser`, `--workspace NAME` (open a particular workspace) and `--data FOLDER` (see below). `python -m alex` does the same as `alex`.

### Where aLex keeps its files

aLex only reads your books. Its own files (your book details, collections, links, tags, corrections, topic models and a cache that makes the next start fast) are kept in a folder called **`alex-data`**, made in the folder you start aLex from. **Start it from the same folder each time** to find your work again, or choose the place once and for all with `--data FOLDER` or the `ALEX_DATA` environment variable. The start-up message tells you which data folder is in use. The whole of your work, with the books, can be saved as one `.zip` under **Library → Export selected books**, and opened as a workspace on another computer.

## Next steps

- **[User guide](docs/guide.md):** books and collections, workspaces, and every view in detail.
- **[How the numbers are made](docs/MEASURES.md)** and **[technical documentation](docs/DOCUMENTATION.md)** (how it is built, the web API, how to change it).

## Companion editor

aLex works with any BookNLP output. A separate companion editor (link to follow) can be used to clean and correct BookNLP's output before analysis; its dated export folders are read directly, and the newest export of each book is used.

## Development

From a clone of the repository:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
cd tests/js && npm install     # optional: the browser tests, which need Node
cd ../.. && pytest
```

The tests use their own generated books and temporary folders and never touch your data.

## Licence

[MIT](LICENSE)
