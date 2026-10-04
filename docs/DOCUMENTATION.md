# aLex - BookNLP analyser — technical documentation

This file explains how the analyser is built, so you can find your way around the code, change it, and trust it.
The [user guide](guide.md) is for *using* aLex (the README for installing it); this is for *working on* it. Every module, function and script also carries
its own comments; this file is the map that connects them.

Contents: 1 Overview · 2 Folder layout · 3 Data (what is read, what is written) · 4 How a request flows ·
5 The analysis code (`core/`) · 6 Definitions and methods · 7 The web API · 8 The browser code (`static/`) ·
9 Testing · 10 Extending the analyser · 11 Large libraries · 12 Robustness decisions · 13 Troubleshooting

What each figure means, how it is calculated and where in the code: [MEASURES.md](MEASURES.md).

---

## 1. Overview

aLex (the analyser) reads books processed by BookNLP (its output files, or exports from the companion editor) and offers views of them in the browser:
entities (with narrators and groups of entities), dialogue, corpus tools, arcs and style, topics, a text view with a chapter editor,
and tools for linking entities across books. Books can be organised in collections.

* It is a **Python** program (FastAPI + uvicorn) that serves one HTML page and a JSON API on `127.0.0.1` only.
* The browser side is **plain JavaScript** (no build step, no framework): a set of scripts that draw pages from JSON.
* Nothing is written to your books' folders. The analyser writes only under its own data folder, `alex-data` (see section 3).
* Python packages: `fastapi`, `uvicorn`, `networkx`, `vaderSentiment` (sentiment), `scikit-learn` (topics; brings numpy and scipy).
  All of them are installed with the package (`pyproject.toml`); the code still copes if scikit-learn or vaderSentiment is missing: the Topics tab
  and the sentiment page then explain what to install.

## 2. Folder layout

```
pyproject.toml         the package: name, version, Python version, dependencies, the `alex` command, test settings
README.md  LICENSE     what it is and how to install it (README); MIT licence
docs/                  the user guide (guide.md), this file and MEASURES.md
alex/                  the package (everything below this line in this block is inside it)
  app.py               start-up (`alex` / `python -m alex`): builds the web app, error handling, static files
  localonly.py         middleware: answers only requests for this computer, and changes only from our own page (section 12)
  api/                 the web API: one router per area (routes only; no analysis)
  core/                the analysis: reads books, computes, no web code
    topics/            topic modelling (a package)
  static/              index.html, app.css and js/ (the browser code)
tests/                 the test suite (pytest) and its browser tests (tests/js)
alex-data/             the analyser's own files, made in the folder you start it from (git-ignored; see section 3)
```

Paths such as `core/…`, `api/…` and `static/…` in the rest of this file are inside the `alex/` folder. `core/` never imports
from `api/` or `app.py`, and `api/` contains no analysis: a route validates its input, calls one
function in `core/` and returns the result. That split is what lets the tests exercise the analysis without a web server.

## 3. Data

### What is read (BookNLP files)

A book is a folder with files named after its id (`houn` → `houn.tokens`, …). The editor writes each export in a dated
folder (`houn-20260924-124729`); the newest export of each book is used unless you pin an earlier one.

| File | One row per | Columns used |
|---|---|---|
| `.tokens` (required) | token | `paragraph_ID`, `sentence_ID`, `token_ID_within_document`, `word`, `lemma`, `byte_onset`, `byte_offset`, `POS_tag`, `fine_POS_tag`, `dependency_relation`, `syntactic_head_ID`, `event` |
| `.entities` (required) | mention | `COREF` (the group), `start_token`, `end_token`, `prop` (PROP name / NOM description / PRON pronoun), `cat` (PER, LOC…), `text` |
| `.quotes` | quote | `quote_start`, `quote_end`, `mention_start`, `mention_end` (the mention BookNLP used to attribute it), `char_id` (speaker's group), `quote` |
| `.supersense` | span | `start_token`, `end_token`, `supersense_category` |
| `.book` | (JSON) | `characters[].id / name / g.argmax` (BookNLP's names and pronouns) |
| `.txt` | (the whole text) | optional; the original text the export was made from. Found the same way as the other optional files (in the book's own folder), not in a BookNLP input folder. Used for exact inter-token spacing in `BookData.span_text` (falls back to a single-space guess without it) and offered for download on the Library page (`/api/books/{bid}/text`). |

Everything in the analyser addresses tokens by their **position** in `.tokens` (0, 1, 2 …). A parse problem is reported by
name, file and line; mentions or quotes outside the book are skipped with a note on the Library page, and so are lines of `.entities`, `.quotes`
or `.supersense` that can't be read at all (a missing field, a number that isn't one: the note says how many). A byte-order mark and Windows
line endings are fine; a file that isn't UTF-8 text is refused with a message that says so. Optional columns of `.tokens` (`fine_POS_tag`,
`event`, `byte_onset`, `byte_offset`) may be missing.

`byte_onset`/`byte_offset`, despite the name, are **character offsets** into the original text (Unicode codepoints), not true UTF-8 byte offsets: a
multi-byte character (curly quotes, em dashes, £…) is one unit there but two or three bytes in a UTF-8 file. `BookData._original_text` decodes `.txt`
once to a `str` (`raw_text`) for exactly this reason, so `span_text` indexes it by character position; slicing the raw bytes instead corrupts every
token after the first multi-byte character in the book (a real bug this project hit once — see `test_span_text_handles_multibyte_characters_in_the_original_text`).

### What is written (`alex-data/`)

| Path | Contents |
|---|---|
| `library.json` | your settings and work: `sources` (folders; none in a fresh library, see below), `books` (title, author, year, series, tags, pinned export), `settings` (`min` per type, `count_mode`, `conv_gap`, `plural`: count plural groups' mentions for their members by default), `persons` (entities you linked: `{id: {members: [[book, coref]], tags, name, note}}`), `entity_tags`, `entity_names` (a name you gave a single, unlinked entity) and `entity_notes` (its description), `rejected` (pairs you said are different), `next_person`, `collections` (`{id: {name, parent, books}}`, nested; a book may be in several) and `next_collection`, `groups` (saved groups of entities: `{id: {name, ids}}`) and `next_group`, `plurals` (plural groups: `{unit id: [member unit ids]}`) and `plural_rejected` (suggestions you dismissed), `narrator_links` (narrator roles linked into one: `{id: {members: [role id, ...], name}}`) and `next_narrator_link` |
| `annotations.json` | your corrections, per book: `narrator`, `para_narrators` (paragraph key → unit or `"anon"`), `chapter_narrators` (chapter key, or `narrative.OPENING_KEY`, → unit or `"anon"`; see below), `addressees` (quote key → units or `["*"]`), `splits`, `merges`, `participants` (`add`/`remove`), `narr_rejected`, `chapters` (`add` / `remove`: paragraph keys, `names`: paragraph key → title) |
| `cache/<book>-<hash>.pkl` | a parsed book (parsing takes seconds; the hash covers the files' modification times and `CACHE_VERSION`; the file is about twice the size of the book's own files). Safe to delete. Opened only by `bookcache.loads`, which refuses code in a pickle (a copied-in cache folder can't run anything). (The way with plural groups counted for their members is made from it in memory, see below.) |
| `topics/<id>.json` | one fitted topic model (settings, documents, vocabulary, topic–word and document–topic matrices, quality figures, your labels) |
| `references/<id>.json` | a reference file for keywords: `{name, files, kinds, tokens, types, counts}` |
| `lexicons/emotion.json` | the loaded emotion lexicon `{name, cats: {category: [words]}}` |

All JSON is written atomically (a temporary file, then a rename). A damaged `library.json` or `annotations.json` stops start-up
with a message naming the file, and is never overwritten. The data folder is `alex-data` in the folder you start the analyser from, unless `--data FOLDER`, the `ALEX_DATA`
environment variable (`library.data_home`) or `Library(data_dir=…)` says otherwise; start-up prints which one is in use.

A fresh library has **no source folders** (nothing is assumed about where your books are). The Library page then shows "Where to find books" first, with
guidance; a folder is added there, with `alex --books FOLDER` (`Library.add_sources`: full paths, repeats skipped, saved; a path that
isn't a folder stops start-up with a message), or in a new workspace's folder box.

Your corrections (including chapter edits) are keyed by the *opening words* of a quote or paragraph (`dialogue.keys`), not by token
numbers, so they survive a re-export that shifts positions. Collections and saved groups store only book and entity ids: a group
follows your minimum, your links and the selected books, because `View.group_of` looks its entities up again each time.

### Identifiers

* **Book id**: the file stem (`houn`).  **Coref**: BookNLP's group number, unique within a book.
* **Unit id**: an entity of the selection: `e:<book>:<coref>` for one book's group, or `p:<n>` for a person you linked. `bookdata.ekey` makes
  the first kind and `bookdata.parse_ekey` reads it back (the coref is what follows the *last* colon, and a damaged id gives `None` rather than an error).
* **Member**: `(book, coref)`. A unit has one or more members (a linked person has one per book).
* **Spec**: how the API names a set of units: `{"kind": "unit", "id"}`, `{"kind": "group", "ids"}` or `{"kind": "group", "group"}` (a saved group),
  `{"kind": "tag", "tag", "type"}`, `{"kind": "type", "type"}`, `{"kind": "others", "types"}`, `{"kind": "book", "book"}` (everyone counted in one
  book) or `{"kind": "gender", "pron"}` (every PER entity of one BookNLP-predicted gender, `UNKNOWN_GENDER` for none predicted), optionally with
  `"books"`; dialogue also accepts `{"kind": "narration", "id"}`.
* **Group**: several units analysed as one. `View.group_unit` makes a virtual `Unit` (id `"group"`, its `parts` are the real unit ids), so profiles,
  speech and topics work on it exactly as on one entity. A request names it with `ids` (a temporary group) or `group` (a saved one).
  `book_profile` and `gender_profile` pool a book's or a gender's own units the same way (`View._pooled_profile`), for their own pages
  (`book:<id>` / `gender:<pron>`, addressed like a narrator role) — everyone counted in a book, or every PER entity BookNLP predicted a
  gender for, as one page: mentions, relations, dialogue style, kinds of action, what's distinctive. Speech and Topics are left out there
  (they need an `id`/`ids`/`group` ref a pool doesn't have), and so is Appears with (a pool already contains almost everyone who could
  "appear with" it). `View.book_grid` compares two books "split into characters": every PER entity in either, with its mentions in each.
  `View.pool_unit(spec)` is the general form of this for unit/group/tag/gender specs: a `group_unit` pooling everyone a spec matches (None
  if it matches nobody), for a view that needs a real `Unit`'s worth of figures for a scope — `dialogue.entity()`'s per-book breakdown and
  narrating figures, via `/api/dialogue/scope` — rather than just `resolve`'s flat member set. It doesn't handle `book`/`others`/`narration`
  (not needed by that route) or apply a spec's own `"books"` (the view is already scoped to your book selection).
* **Plural group**: an entity whose mentions ("Holmes and Watson", "they") stand for several entities together, declared in the analyser
  (`plurals.py`: `library.json → plurals`, keyed by unit id, so a linked entity's declaration applies in all its books; one made on a
  group before you linked it counts as the linked entity's, and the checks go by group). Pages change a declaration by adding and removing
  members (`change_members`), so members a page doesn't show (other books, below the minimum) are kept. `.entities` gives
  the mentions to the plural group only. `Library.book` applies the declarations to each book (`BookData.set_members`: `Group.members`,
  `Group.member_of`; cheap, nothing is recounted). Whether the mentions also count for the members is the **plural setting**:
  `settings.plural` is the default, and every request may carry its page's own `plural` (true/false), which `Context.view` passes to
  `View(lib, books, plural)`; the page choices reset when you choose other books. With plural on, `Library.book(bid, True)` gives
  `BookData.plural_copy()`, made in memory from the parsed book and kept until the declarations or files change, which credits a plural mention to each member not named inside it (`credit`, `mention_groups`: mentions, forms, relations, co-occurrence), and
  a plural speaker or addressee stands for its members too (`stands_for`; dialogue records carry `speakers`, see `dialogue.speaker_units` /
  `said_by`). Off, every group has only its own. A plural group and its own members are never counted as appearing with each other
  (`BookData.plural_pair`: networks, "appears with"); the plural group always keeps its own profile.
* **Narrator role**: `nar:<unit id>` (a character narrating) or `nar:anon:<book>` (an unnamed narrator). Roles are listed on the Entities page
  as type `NARR` and have their own profile; they are not units and never appear in `View.units`. A paragraph's role
  (`dialogue.narrator_of`) is, in order: a paragraph exception (`para_narrators`), else a chapter exception (`chapter_narrators`,
  found by `narrative.chapter_key_of` from any paragraph in it — always the book's real chapters at the default detection settings
  plus your chapter edits, `{"mode": "chapters"}`, regardless of what the current page happens to be showing, so "chapter" means one
  stable thing), else the book's own narrator, else anonymous. **Linking narrator roles** (`nl:<n>`, `library.json → narrator_links`,
  `Library.link_narrators` / `unlink_narrator` / `unlink_narrators_all`, mirroring `link`/`unlink` for persons but as its own store,
  since a role isn't `(book, coref)`-shaped and an anonymous one has no unit at all) pools two or more roles' narration into one —
  Watson narrating one book and Watson narrating another as a single voice, or two anonymous narrators, or a mix. Unlike linking
  entities, nothing else about them merges. `View.narrator_link_of` (a role id → its link id, built once per view) is substituted
  in inside `narrator_of`, so every other narrator function (`narrator_rows`, `narrator_profile`, `narrators`, `narration_recs`) only
  ever sees the already-canonical id. Unlinking down to one member dissolves the link and that member goes back to its own id.

### Workspaces

A **workspace** is one data folder, the unit you switch between (`core/workspaces.py`; no merging, no links across workspaces). The
**Default** workspace is the data folder itself (`alex-data`) and points at the folders its books are in. A workspace
you **create** (`POST /api/workspaces`) gets a folder under `alex-data/workspaces/` and the source folders you give it; one you **import** from an
export zip gets a folder with a copy of the books in `books/` as its only source. The list and the active workspace are in
`alex-data/workspaces.json`, so a separate data folder (`--data`, tests, experiments) never touches the real list. `app.py` opens the active
workspace at start (Default, with a note, if its folder has gone).

Switching (`POST /api/workspaces/activate`, `Context.switch`) re-opens the data folder **in place**: `Library.reopen` replaces the library's
state and annotations (reading both first, so a damaged file leaves the current workspace open and the error names the file), bumps
`version` (nothing cached for the old folder can be hit again) and stops a running `Library.warm`; `Context` drops its cached views and
remembered searches, and its reference-file folder and emotion lexicon follow, so routes read `ctx.refs_dir` / `ctx.lexicon_path` on every
request rather than keeping them. `topics.configure` points the topics store at the new folder. The browser reloads after a switch (`reloadPage()`). Each workspace has its own settings,
links, groups, collections, corrections, topic models, reference files, lexicon and parse cache. A request still running while you switch may
end with an error message (it was started on the other workspace); `test_switching_while_the_analyser_is_in_use` checks the analyser serves
the right workspace afterwards.

**In the browser.** The server writes the open workspace's id into the page it serves (`window.WORKSPACE`, in `index()` in `app.py`), so the
page always agrees with the server and no reload can loop. `core.js` keeps remembered settings (`localStorage`) per workspace: the Default
workspace keeps the plain key names (so what was saved before workspaces existed is still found), another gets `key@<id>`, and the theme is
shared (`storageKey`, `GLOBAL_KEYS`). The picker in the top bar and the Library page's *Workspaces* section are in `static/js/workspaces.js`;
an import sends the zip as the raw request body (`api()` passes a `Blob` or `File` through unchanged). `alex --workspace NAME`
opens a workspace by id or name (`Workspaces.find`) and keeps it as the one opened next time.

**Deleting** (`Workspaces.delete`) removes a workspace's whole folder, including the books copied in by an import, and is guarded three ways:
only folders the analyser made (`owns`: inside `workspaces/`, after resolving links), never the active workspace or Default, and only when the
exact name of the workspace is typed. *Forget* just takes it off the list. Books in folders a workspace merely points at are never touched.

### The export zip

The Library page's *Export selected books (.zip)* button (`POST /api/export`, `core/export.py`) packs the selected books and your work on them:

```
manifest.json            format (export.FORMAT, now 1), when it was made, the export folder each book came from
books/<book>/<book>.*    the BookNLP files of the export in use: .tokens .entities .quotes .supersense .book .txt (those that exist)
state/library.json       library.json cut down to the selected books
state/annotations.json   annotations.json for the selected books
topics/<id>.json         topic models whose documents all come from the selected books
references/<id>.json     the keyword reference files (they belong to no book, so all of them)
```

`scoped_state` is a plain filter: nothing is renamed or merged, so an id in the zip means what it meant in the library. Details that matter:
`sources` and each book's `pinned` export are left out (the zip holds only the export in use); a linked person or narrator link keeps only its
members in the selected books and **stays even with one member left**, so ids that corrections refer to (`p:17`) stay valid (it goes only when
no member is left); tags, names, notes, saved groups, plural groups, rejected pairs and `plural_rejected` keep what touches a selected book
(a unit touches the books of its groups, a linked person those of all its members); a collection stays if it, or one inside it, holds a
selected book, and lists only the selected books; the `next_*` counters are kept. The emotion lexicon is not included. The zip is written
to a temporary file (deleted after it is sent), so a large corpus never has to fit in memory twice. The zip can be unpacked and read with
the analyser as it is: `books/` is a source folder (`Library(sources=[…/books])`).

## 4. How a request flows

0. `LocalOnly` (`localonly.py`) looks at every request first: wrong `Host`, or a change that names another `Origin`, is refused with 403 (section 12).
1. The browser (`static/js/*.js`) calls `api("/api/…", body)`; every analysis call carries `books` (the selected book ids).
2. A route in `api/` asks the shared `Context` for a **`View`** of those books. Views are cached (six at a time), keyed by the books,
   the library's `version` (bumped by every change to your settings, links or corrections) and each book's file signature,
   so a view is rebuilt exactly when something it depends on changed. `Context.signature(view)` is the same idea for results kept
   outside a view: a concordance search is kept (`Context.remember`, the last four) so that "Show more" pages through it without searching again.
3. The route calls a function in `core/` and returns its dict as JSON.
4. Errors: a `ValueError` (something the user asked can't be done) becomes `400 {"detail": message}`, a missing id or field
   `400`, `HTTPException` its own status, and anything else `500` with the exception's name, logged in the terminal.
   The browser shows `detail` as a message and replaces the "Loading…" line that was waiting for that request.

## 5. The analysis code (`core/`)

| Module | Job |
|---|---|
| `bookdata.py` | `BookData`: parses one book and builds its indexes: tokens, sentences and paragraphs, mentions, coreference `Group`s, quotes, supersenses, each group's grammatical relations (section 6), and the original `.txt` if there is one. `span_text` rebuilds text with marks, using the original text for exact spacing when available. To keep a book small in memory equal strings are shared (`shared`) and whole-number columns are arrays; `BookData.cache(owner)` is where other modules keep what they derive from a book; `plural_copy` shares the tokens with the book and copies only the groups. `ekey` / `parse_ekey` build and read unit ids. |
| `library.py` | `Library`: the books on disk (`scan`, `book` with the cache), your book details, tags, links ("persons") and corrections; both JSON files. `reopen` switches it to another data folder in place (workspaces). |
| `bookcache.py` | Saving and opening the parsed-book cache. It is a pickle, so `loads` accepts only the classes in `ALLOWED` (a parsed book's own) and refuses anything else, which `Library` treats as a damaged cache and rebuilds. |
| `bookcollections.py` | Collections of books: nested, a book may be in several (`create`, `update`, `delete`, `listing`). Named so as not to shadow Python's `collections`. |
| `export.py` | The export zip: `write_zip` writes the selected books' files and your state cut down to them (`scoped_state`, `scoped_annotations`), plus topic models and reference files (section 3). |
| `workspaces.py` | Workspaces: separate libraries (each one data folder) you switch between. `Workspaces` keeps the list and the active one in `workspaces.json`, and can `create`, `rename`, `activate`, `forget` (never deletes files) and `import_zip` (an export zip becomes a workspace with its own copy of the books). Wired to the web by `api/workspaces.py` (section 7); see "Workspaces" in section 3. |
| `entitygroups.py` | Saved groups of entities (`create`, `update`, `delete`, `get`, `listing`). |
| `plurals.py` | Plural groups: declaring them (`set_members`, checked; `change_members` adds and removes, keeping the rest), what they mean in one book (`book_map`), suggestions from names (`suggestions`, `reject`). |
| `view.py` | `View`: the selected books combined. Applies your minimum-mentions rule, merges linked entities into units, and computes profiles (of one unit or of a group), distinctive words, group summaries, book-by-book tables and evidence sentences. `group_of` / `group_unit` / `target_unit` turn a request's `ids` or `group` into a virtual unit. `self.books` is ordered by publication year ascending (undated books last, by title), regardless of the order requested, so every "several books together" view (book by book, stylometry, arcs, network) is consistent; a unit's own `books` (`Unit.as_row`) follows the same order. |
| `stats.py` | Keyness and other statistics: log-likelihood, chi-squared, log ratio, %DIFF, odds ratio, `across` (chi-squared over several books), with their own p-values (no SciPy needed). |
| `corpus.py` | Concordance (KWIC, with sort levels and a context search: `kwic_search` finds, filters and sorts the hits, `kwic_lines` makes the text of the lines shown, `kwic` does both), word lists (also word+POS+lemma), n-grams, collocates, keywords, reference files; the word-type filter (`token_test`, `filter_options`); the query language (simple and pattern), including batch queries (`Matcher`, below); `Scope`, the part of the text a tool may use. |
| `dialogue.py` | Per-book quote records, speech verbs and adverbs, vocatives, conversations, estimated addressees, speaking style, speaker/narrator tables; your corrections applied. Also narrators as entities: `narrator_rows`, `narrator_profile`. `sentence_type` classifies a quote (or a narration paragraph) as a question, exclamation or statement, optionally weighing in its speech verb; `quotes`, `style_table`, `voice` and `entity` all take `types`/`weigh_verb` to filter or scope by it. |
| `narrative.py` | Segments (slices or chapters, with your chapter edits: `book_segments`, `edit_chapters`), arcs, style figures, stylometry (Delta, tree, PCA), sentiment (VADER), emotion (lexicon). `all_segments` combines every selected book's segments in book order; with equal slices and `cfg["scope"] == "corpus"` it shares one total slice count across the books by their words, instead of giving each book the same count (the "Whole corpus" timeline). |
| `narrators.py` | Suggests each book's narrator and stretches narrated by someone else, from the "I" outside quotes. |
| `network.py` | Entity networks (networkx), measures, layout, GEXF/GraphML export. A network keeps the `max_nodes` (300; at most 1,000) entities with the strongest links and says how many there were (`G.graph["total_nodes"]`). |
| `links.py` | Suggests entities of different books of the same series that may be the same (`suggest`), and `auto_link`, which links exact name/type/pronoun matches across the whole library outright. Both start from `_units`, one summary per entity of the whole library, which is kept on the `Library` until something it depends on changes. |
| `reader.py` | The text view: one segment as paragraphs (with their numbers) with marks for entities, quotes, narrators, events, supersenses, sentence numbers and topics. |
| `topics/` | Topic modelling (below). |

**`core/topics/`**: `model.py` (settings, documents, words, NMF/LDA fit, quality figures, `build`), `store.py` (models on disk),
`page.py` (model overview; `Topic`; the parts of a topic's page), `compare.py` (map, side by side, grids), `uses.py` (topics in Arcs,
on entity pages and in the text view), `notes.py` (explanatory texts), `errors.py` (`TopicError`).

Layers of memory: a parsed book lives in the library (and the pickle cache); per-book lookup tables (`cindex`, dialogue records,
quote keys, style figures, sentence sentiment) are built on first use and kept on the `BookData` (`BookData.cache(owner)`: they are never
saved with the book or copied into its plural copy, and each owner keeps few of them); a `View` is cached by the API context (six at a time;
a view itself is light, it points into the books). At start-up `Library.warm` reads every book in the background so that the first page
doesn't wait for them.

## 6. Definitions and methods

**Mentions and entities.** BookNLP groups mentions of the same thing into a coreference group. A group's *type* is its most
common category. It is *counted* if it reaches your minimum for that type, in each book separately or across the selected
books combined (`count_mode`). Linked groups form one unit; its name is the one you gave, else the most frequent name. Any
unit — linked or not — can be renamed and given a short description from its profile (`Library.name_of`/`set_name`,
`note_of`/`set_note`; `/api/name`, `/api/note`); a linked person's live in `persons[pid]`, a single entity's in
`entity_names`/`entity_notes`, keyed like `entity_tags`. Linking or unlinking carries a plain entity's name, note and tags
along with it the same way (`Library.link`/`unlink`).

**Relations** (`BookData._relations`), from the dependency parse, per mention head: subject of a verb → *agent*; object,
indirect object or passive subject → *patient*; possessor → *poss*; adjective modifier, apposition or complement of "to be" →
*mod*; object of a preposition → *prep* ("went to"). Extensions to BookNLP's rules: a conjoined mention takes the first
conjunct's role, a subject is also the agent of verbs coordinated with its verb, and *prep* is recorded for every type. Each
finding keeps the tokens to highlight, which is where "click a row for the sentences" comes from.

**Keyness** (`stats.compare`): for an item with counts *a* (target) and *b* (reference) in texts of size *c* and *d*, log-likelihood
G² = 2(a·ln(a/E₁) + b·ln(b/E₂)) with E from the pooled rate (Rayson & Garside 2000), chi-squared for the 2×2 table, log ratio,
%DIFF and odds ratio; p from chi-squared with 1 degree of freedom. `across` tests one item over several books. Bonferroni divides
the level by the number of items tested.

**Dialogue** (`dialogue.py`). Each quote becomes a record. The *speech verb* is the verb the attributing mention is the subject of, else
the nearest speech verb within 8 tokens. *Vocatives* are people named as a form of address inside the quote. *Conversations* are runs of
quotes with at most `conv_gap` narration words between them (unless you split or join). *Addressees* are estimated in this order: a
named person, the previous speaker, the same person as before, the next speaker (for an opening line); your corrections replace the
estimate. MATTR is the moving-average type–token ratio over 100-word windows. *Sentence type* (`dialogue.sentence_type`) is question,
exclaim or statement, from the record's own `?`/`!` (also true for a narration paragraph: see `narration_recs`); with `weigh_verb`, a
speech verb in `QUESTION_VERBS`/`EXCLAIM_VERBS` (asked, exclaimed…) decides it instead when the record's own punctuation doesn't already.
`book_dialogue`'s "time" (the whole book's dialogue-share curve, 50 slices) exposes its per-slice word count as `bins_w` alongside the
ratio itself, so `scoped_time(view, pairs)` can reuse the exact same denominator for one scope's own curve — the given pairs' own words,
sliced the same way, as a share of each slice's total words — rather than recomputing it from scratch or (wrongly) reusing `bdlg`'s
dialogue-word bins as the denominator, which would be everyone's dialogue, not the whole slice.

**Segments** (`narrative.segments`): equal slices by token count, or chapters found from heading paragraphs (12 words or fewer, starting
with a heading word or numeral, optionally in capitals or without closing punctuation); a heading too close to the previous one is ignored;
fewer than two headings falls back to slices. The text view shows a paragraph in the segment where it *starts*. Across several books
(`narrative.all_segments`), Arcs and style offers two timelines: "Book by book" (each book's own slices or chapters, plotted as its own line) and
"Whole corpus" (one continuous line over every selected book; with equal slices, the slice count is shared across the books by their words, so a
short book gets fewer than a long one, rather than the same count each).
**Your chapter edits** (`narrative.edit_chapters`, stored per book in `annotations.json`) sit on top of the automatic chapters: the found
headings minus those you removed, plus paragraphs you made chapter starts, with the titles you gave; the text before the first start becomes an
"Opening". With edits a book needs only one start to be split into chapters, and the minimum-length rule no longer drops your starts. Edits name
paragraphs by their opening words. Every place that uses chapters (Arcs and style, topic documents, the text view) goes through `book_segments`,
so they all see your chapters.

**Stylometry**: z-scores of the most frequent words' relative frequencies; Burrows' Delta, Cosine Delta or Euclidean distance;
average/complete/Ward linkage; a principal-component map. At most 400 texts.

**Topics** (`core/topics`). 1) *Documents*: chunks of about N words ending at sentence boundaries, groups of paragraphs, chapters or
slices, or whole books. 2) *Words*: the chosen parts of speech, as lemmas or forms; tokens inside proper-name (or person, or any entity)
mentions are dropped using BookNLP's mentions; general words and your own stop-words are removed; words in too few or too many
documents are removed. 3) *Fit*: NMF on tf–idf (default; random start with a fixed seed) or batch LDA. 4) *Quality*: NPMI coherence of
each topic's ten top words over documents, diversity of top words, and *stability*: re-fit with other seeds and count how often each topic
returns (a re-run's matched topic shares at least 40% of its top 20 words). 5) *Topic page*: relevance ranking of words
(Sievert & Shirley 2014), where the topic occurs, its strongest passages, and *association*: each document counts as topic text to the
extent of its share, and an entity's (or speaker's) rate per 1,000 words in topic text is compared with its rate elsewhere with a
log-likelihood. That ranks; it is not a significance test, because the weights are not independent observations. Book and group
comparisons use Mann–Whitney U on documents. 6) *Compare*: similarity by shared words (cosine) or appearing together (correlation of
document shares), classical multidimensional scaling for the map, average-linkage tree.
The one function that decides which words a model counts is `model.kept_tokens`; passages and the text view use it too, so a
highlighted word is always a counted word.

**Groups and narrators as entities.** A group counts several entities as one: its members are all their coreference groups, so mentions,
forms, relations, supersenses and presence add up. A sentence counts once for a group however many of its entities it holds (co-occurrence,
"appears with"), members are never counted as outsiders (who names the group in dialogue, who it talks to), and the Speech section adds the
quotes between members. Groups of mixed types have no "share of type". A narrator role has no mentions or relations: its profile (`dialogue.narrator_profile`)
is the words outside quotes that belong to it, with style figures against all narration and against the same character's dialogue, a row per book, and
vocabulary distinctive of its narration (`dialogue.voice` with a narration target).

**Word-type filters** (`corpus.token_test`): a filter is `{pos, tag, ent}`; a token passes when it matches one value of every non-empty list
(POS: BookNLP's universal tags, tag: fine tags, ent: the category of a mention covering the token). In a word list only passing tokens are counted while
the total, per-1,000 rates and the tenths used for dispersion still refer to all words in scope. In collocates the filter only decides which collocates
are listed: windows and hit counts are unchanged, and a collocate's corpus frequency counts only its passing tokens.

**Concordance sorting and context search** (`corpus.kwic`): up to three sort levels, each a position (the hit, one of five words left or right,
the book) and a `by` (word, lemma, POS, fine tag, or frequency of that word among the hits), optionally reversed; each level is one stable sort applied
from the least to the most important, ties keep the order of the text. The context search (`_ctx_test`) runs a second query (simple or pattern) over the
book (all its matches, however many) and keeps the hits with a match wholly inside their window (left/right words, not counting the hit; stopping at the
scope's edge and, if chosen, the sentence's), or, inverted, those without. **Limits apply last**: the scope, the near-word filter and the context
search reach `Matcher.hits` as its `accept` function, so a candidate they turn down is neither counted towards the 20,000-hit limit nor blocks
the text it covers; searching a common word in dialogue only therefore still reaches the later books. A pattern with repeated parts (`[]* []*
"x"`) remembers the outcome of each (line, item, position) it has tried, which cannot change, so it costs no more than its length times the
repeat limit (without that, a few `[]*` could take minutes). The search and the lines are made apart (`kwic_search`, `kwic_lines`) so a page of
500 lines only builds those 500; the plot gets 200 counts per book (`bins`), not a position per hit.

**Networks** (`network.py`). Nodes are the units of the chosen types; an edge counts shared sentences or paragraphs, a speaker mentioning
someone in a quote, or a speaker talking to someone (directed). Edges below the minimum strength go, then unlinked nodes (unless shown), then,
if more than `max_nodes` remain, all but the strongest (the greatest sum of edge weights, then the most mentions); measures and layout are of
what is left. Without that cut a network of a whole library (thousands of people) took a minute to build and was unreadable.

**Batch queries** (`corpus.Matcher`): a query string may hold several complete queries, one per line ("say", "ask" and "shout" each on their own line,
or a pattern per line), each parsed independently. `Matcher.hits` tries every line's parsed items at each candidate position, in the order given, and
takes the first that matches, so the lines behave as alternatives (unlike `a|b` inside one simple word, a batch line can be a whole multi-token pattern).
Each hit carries the line that matched it (`"matched"` in `kwic`'s output; `collocates` just pools every line's hits). `kwic`'s result also carries
`"batch"` (more than one line), which the browser uses to decide whether to offer the "Matched" column at all.

**Link suggestions** (`links.suggest`) are only made between books that share a series (compared case-insensitively; books without a series get none).
Candidates come from names that share a word or a three-letter start (no group of more than 400 is compared with itself, so a name like
"Holmes" in sixty books is still tried: 60 entities), and the per-entity summaries they are made from are kept (`links._units`) until your
settings, links or the books change.
**Auto-link** (`links.auto_link`, the "Auto-link exact matches" button) instead links outright, across the whole library, whenever two entities agree
exactly on name (titles set aside), type, and — the safeguard against merging two different same-named people — BookNLP's pronouns; an entity with
no pronoun evidence (almost everything that isn't a person) is never auto-linked this way, and a pair you've rejected never is either. It's an
ordinary link once made, so it shows on the Links page and undoes like any other.

**Marks in text.** Anywhere the server returns text with highlighting, it uses control characters instead of HTML:
`\x01class|data\x02 … \x03` (see `BookData.span_text`); `markup()` in `core.js` turns them into `<mark>` elements (sentence numbers are marks `sn|<n>`
shown with CSS). Text is never
inserted as HTML, and the browser code has no way to set `innerHTML`.

## 7. The web API

All routes take and return JSON (`POST` unless noted). Bodies carry `books` (selected book ids) wherever a route analyses text.
Generated from the running application:

| Method | Path | What it does |
|---|---|---|
| GET | `/` | The page itself. |
| POST | `/api/annot/addressees` | Set a quote's addressees (["*"] = everyone present), or clear your correction (null). |
| POST | `/api/annot/chapter_narrator` | Assign a narrator to a whole chapter (found from any paragraph in it), or, with no `pid`, the Opening. |
| POST | `/api/annot/conversation` | Start a new conversation at a quote ("split"), join it to the previous one ("merge"), or undo either. |
| POST | `/api/annot/narrator` | Set (or clear) a book's narrator. |
| GET | `/api/annot/narrator_options` | People and things that can be a book's narrator. |
| POST | `/api/annot/paragraphs` | Give paragraphs to a narrator other than the book's (or, with no narrator, take the exception away). |
| POST | `/api/annot/participants` | Add a listener to a conversation, remove a participant, or put one back. |
| POST | `/api/annot/quote` | Everything the quote editor shows: speaker, addressees (yours or estimated), conversation and its participants. |
| POST | `/api/books/{bid}` | Change a book's title, author, year, series, tags or pinned export. |
| GET | `/api/books/{bid}/text` | The original `.txt` the book was exported from, for download; 404 if none was found. |
| POST | `/api/bybook` | How a target's figures and words change from book to book. |
| POST | `/api/collections` | Make a collection, at the top level or inside another. |
| POST | `/api/collections/delete` | Remove a collection (its books stay; its sub-collections move up). |
| POST | `/api/collections/{cid}` | Rename a collection, move it, or add and remove its books. |
| POST | `/api/compare` | Two entities or groups side by side. |
| POST | `/api/compare/books` | Two books split into characters: every PER entity in either, with its mentions in each. |
| POST | `/api/corpus/collocates` | Collocates of a search, with association measures, optionally only of some word types. |
| POST | `/api/corpus/context` | The paragraph around a concordance hit. |
| POST | `/api/corpus/filters` | The word classes, fine tags and entity types a word-type filter can choose from, with their counts. |
| POST | `/api/corpus/keywords` | Keywords of the selected books against other books or a reference file. |
| POST | `/api/corpus/kwic` | A concordance. The search is kept, so paging ("Show more") doesn't search again; `offset` and `limit` page it and only the lines of that page are made; `context` is the number of tokens each side. |
| POST | `/api/corpus/ngrams` | N-grams, optionally containing a word. |
| POST | `/api/corpus/wordlist` | A frequency list of words, lemmas, word+POS, word+POS+lemma or POS, optionally only of some word types. |
| POST | `/api/dialogue/conversations` | The conversations, optionally only those involving someone. |
| POST | `/api/dialogue/entity` | The Speech section of an entity's page. |
| POST | `/api/dialogue/narrators` | Narration per narrator role. |
| POST | `/api/dialogue/overview` | Dialogue per book and a row per speaker. |
| POST | `/api/dialogue/quotes` | Quotes matching a filter. |
| POST | `/api/dialogue/scope` | Dialogue-in-each-book, speaking and narrating figures pooled for a scope (entity, group, tag or gender); In-Depth Who Speaks. |
| POST | `/api/dialogue/style` | Speaking-style figures for every speaker. |
| POST | `/api/dialogue/verbs` | Speech verbs and adverbs, overall or for one speaker or group; `types`/`weigh_verb` filter by sentence type. |
| POST | `/api/dialogue/voice` | Speaking style and distinctive vocabulary of a target against a reference. |
| POST | `/api/distinctive` | Words markedly more typical of a target than of a reference. |
| POST | `/api/evidence` | The sentences behind a count. |
| POST | `/api/export` | The selected books and your work on them as one `.zip`, for download (`core/export.py`; section 3). |
| GET | `/api/groups` | The saved groups of entities. |
| POST | `/api/groups` | Save a group of entities under a name. |
| POST | `/api/plurals` | Declare an entity a plural group: `add` / `remove` members (keeping the others), or `members` to replace them all (none: an ordinary entity again). |
| POST | `/api/plurals/suggestions` | Entities named after two or more others ("Holmes and Watson"), with the members found. |
| POST | `/api/plurals/reject` | Don't suggest this plural group again. |
| POST | `/api/groups/delete` | Delete a saved group (the entities stay). |
| POST | `/api/groups/{gid}` | Rename a saved group or replace its entities. |
| GET | `/api/library` | The library page's data. |
| POST | `/api/links/auto` | Automatically link entities with an exact name, type and (for people) pronoun match, across the whole library. |
| POST | `/api/links/link` | Link two entities (or a person and an entity) as one. |
| GET | `/api/links/narrator_links` | The narrator roles linked so far (see `/api/narrators/link` etc. for changing them). |
| GET | `/api/links/persons` | The persons linked so far. |
| POST | `/api/links/reject` | Remember that two entities are not the same. |
| GET | `/api/links/search` | Find entities by name in every book, for linking by hand (with no name: the most mentioned ones). |
| GET | `/api/links/suggestions` | Possible matches between books, best first. |
| POST | `/api/links/unlink` | Take one book's entity out of a linked person. |
| POST | `/api/links/unlink_all` | Dissolve a linked person entirely: every member becomes its own entity again. |
| POST | `/api/name` | Rename an entity, linked person or narrator link (blank goes back to the name found in the books, or, for a narrator link, to its members' own names). |
| POST | `/api/note` | Give an entity or linked person a short free-text description (blank clears it). |
| POST | `/api/narrative/arcs` | Something counted per segment: entities, events, supersenses, dialogue or topics. |
| POST | `/api/narrative/chapters` | Edit a book's chapters: start one at a paragraph, remove or rename one, or go back to the ones found automatically. |
| POST | `/api/narrative/emotion` | Emotion-lexicon counts per segment. |
| GET | `/api/narrative/lexicons` | The lexicon status. |
| POST | `/api/narrative/lexicons` | Store an emotion lexicon from uploaded text. |
| POST | `/api/narrative/lexicons/delete` | Remove the stored emotion lexicon. |
| POST | `/api/narrative/segments` | The chapters or slices of the selected books. |
| POST | `/api/narrative/sentiment` | VADER sentiment per segment. |
| POST | `/api/narrative/style` | Style figures per book or per segment. |
| POST | `/api/narrative/stylometry` | Distances between texts, cluster tree and map. |
| POST | `/api/narrators/link` | Link two narrator roles (or a narrator link and a role) as one narrator; pools their narration only. |
| POST | `/api/narrators/reject` | Hide a suggested stretch told by someone else. |
| POST | `/api/narrators/suggestions` | Suggested narrators, from the "I" in the narration. |
| POST | `/api/narrators/unlink` | Take one narrator role out of a narrator link. |
| POST | `/api/narrators/unlink_all` | Dissolve a narrator link entirely: every role becomes its own narrator again. |
| POST | `/api/network` | A network as JSON (nodes with positions and measures, edges); `max_nodes` (10–1000, default 300) keeps the most strongly linked entities and `info.total_nodes` says how many there were. |
| POST | `/api/network/export` | A network as a GEXF or GraphML file (also limited by `max_nodes`). |
| POST | `/api/profile` | An entity's, narrator role's or narrator link's profile, a book's (`book:<id>`) or a gender's (`gender:<pron>`), or a group's (`ids`, or a saved `group`) as one; 404 if it isn't in the selection. |
| POST | `/api/read` | One chapter or slice of a book, with the layers asked for. The book may lie outside the selection. |
| GET | `/api/refs` | The stored reference files (damaged ones are skipped). |
| POST | `/api/refs` | Store uploaded files (word lists or texts) as a reference for keywords. |
| POST | `/api/refs/delete` | Delete a reference file. |
| POST | `/api/settings` | Minimum mentions, how to count them, the conversation gap and the source folders. |
| POST | `/api/tags` | Replace an entity's or linked person's tags. |
| POST | `/api/topics/compare` | Comparisons between the topics of one model: map, pair, groups (topic × book etc.) or items (topic × character/speaker). |
| POST | `/api/topics/delete` | Delete a model. |
| POST | `/api/topics/entity` | The topics of one entity's (or a group's) mentions or speech, for the entity page. |
| POST | `/api/topics/fit` | Fit a model of the selected books and store it -> its id. |
| POST | `/api/topics/model` | A model's overview. |
| GET | `/api/topics/models` | The stored models. |
| POST | `/api/topics/page` | One part of a topic's page: words, where, groups, passages, entities or speech. |
| POST | `/api/topics/rename` | Rename a model or one of its topics. |
| POST | `/api/topics/scan` | Fit one model per number of topics and report quality, to help choosing how many. |
| POST | `/api/units` | The entity list of the selected books, and the gender buckets among its PER entities (`genders`). |
| GET | `/api/workspaces` | The workspaces and which one is in use. |
| POST | `/api/workspaces` | Make an empty workspace (not opened), reading books from `sources`. |
| POST | `/api/workspaces/activate` | Switch to a workspace: the library re-opens its folder, caches are dropped, the topics folder follows. The browser reloads after it. |
| POST | `/api/workspaces/delete` | Delete a workspace's folder for good; `name` must be typed exactly. Only folders the analyser made; never Default or the one in use. |
| POST | `/api/workspaces/forget` | Take a workspace off the list; its files stay. |
| POST | `/api/workspaces/import` | Make a workspace from an export zip sent as the raw request body (`?name=`), streamed to a temporary file; not opened. |
| POST | `/api/workspaces/{wid}` | Rename a workspace. |

FastAPI also serves its interactive description of these routes at `/docs` while the analyser runs.

## 8. The browser code (`static/`)

`index.html` loads `app.css` and the scripts in `static/js/` **in order**; they share one global scope (no modules, no build).

| File | Contents |
|---|---|
| `core.js` | shared state `S`, `h()` (the element builder), formatting, remembered settings (`loadState`/`saveState`, kept per workspace: `storageKey`), `api()`, `table()`, charts, the evidence drawer, the book-selection pop-up, `picker()`, statistics controls |
| `entities.js`, `network.js`, `compare.js`, `links.js`, `books.js` | those pages (Entities also holds group, narrator, book and gender profiles; Library the collections and the export button). Compare adds a "Split into characters" section (`/api/compare/books`) when both sides are a book: every character in either, with mentions in each — for comparing two whole books without losing who's in them. |
| `dialogue.js`, `corpus.js`, `narrative.js` | those page groups |
| `reader.js`, `narrators.js` | the text view (a continuous scroll, with the quote and narrator editors, and the chapter editor) and the Narrators page |
| `topics.js`, `topic-page.js`, `topic-compare.js` | topic models: fit, overview, a topic's page, comparisons |
| `workspaces.js` | the workspace picker in the top bar and the Library page's Workspaces section (make, import by upload, rename, switch, remove from the list, delete by typing the name); switching reloads the page |
| `pagetools.js` | collapsible sections and the side menu |
| `main.js` | the router; must load last |

**Pages.** A page is `renderX(main, …)`: it builds DOM with `h()` and puts it in `#main`. The address is a hash route,
`#/<tab>/<sub>/…` (`#/entities/<unit id>`, `#/dialogue/verbs`, `#/read/<book>/<token>`, `#/topics/<model>/<topic>`,
`#/topics/<model>/compare/pair/<a>/<b>`). `render()` (in `main.js`) dispatches; renders never overlap (a newer request waits for the
running one).

**The text view** (`reader.js`) shows a book as one scroll. It asks `/api/read` for one chapter (or slice) at a time and adds the next or previous
one when you scroll near it (an `IntersectionObserver`, with "Load…" buttons as fallback); quotes, paragraphs and topic documents of the loaded chapters are kept
in small registries for the side panels. The settings bar (book, layers, legend) and, under it, the position bar are frozen together in `.read-head`; its height is published as the CSS variable `--read-head` (a `ResizeObserver` keeps it current) so jumps and the side panel stay clear of it. The position bar shows the chapter and paragraph at the top of the window (worked out from element positions on scroll)
and jumps between chapters. Paragraph numbers are `no` from the server (1-based reading order). The chapter editor (`#/chapters/<book>`) is the same page
with `edit` set: no layers, a "start a chapter here" button per paragraph and rename/remove buttons on chapter titles; after each edit the page reloads at the
paragraph. Take care with class names: `.seg` is the segmented button group, so chapters use `.chap`. Clicking a paragraph's narrator
pill (`.pn`) opens `narrPanel`: "Apply" corrects this paragraph (and optionally the next few), "Apply to this whole chapter" instead
posts to `/api/annot/chapter_narrator` with this paragraph's `pid` — the server works out which chapter it's in, so the panel needs
no chapter boundary of its own. Clicking a counted entity mark (`entPanel`) shows the mention's own text as a heading, then, once
`units()` resolves (the same cached `/api/units` call every entity list uses), "Attributed to `<name>`" linking to that entity's page
whenever its canonical name differs from what's actually on the page ("he" → Holmes, "the detective" → Holmes, or "Sherlock Holmes" →
Holmes) — "Open profile" instead when it doesn't (a mention that already reads as the canonical name). An uncounted mark (below the
minimum) never got a `units()` row, so it keeps the plain "no profile" message.

**Narrator profiles** (`entities.js`, `narratorProfileView`): a role or narrator-link page (`isNarr` in `renderEntities` also treats
an `nl:` id as a narrator page, matching `/api/profile`'s own check). `narratorLinkBox` shows the current members (each linked to its
own character's profile when it has one, via `role.members[].unit`, since the role id itself no longer resolves once linked — see
below) with an Unlink each and "Unlink all", and always a picker to link with another narrator role. Linking or unlinking can move
this role to a different id (a fresh `nl:…`, or, once a link of two dissolves, a member's own original id), so those actions navigate
there (`location.hash`) rather than just re-rendering — except when the id doesn't change, where a same-value hash assignment
wouldn't fire `hashchange`, so it calls `render()` directly instead.

**Network focus** (`networkSvg`): hovering a circle highlights it and its neighbours; a click pins that focus (`o.pinned`, `el.setPinned`, `o.onPin`), a click on
empty space releases it (a drag doesn't); a circle without a label gets one while hovered or pinned.

**Book and gender profiles** (`entities.js`): `bookProfileView` and `genderProfileView` are their own pages (`isBook`/`isGender` in
`renderEntities`, matching `/api/profile`'s `book:`/`gender:` dispatch), each with its own simple header (a book's facts; a gender's just
its name) plus the entities pooled into it (`poolTable`, read-only — no ticking or editing, unlike a hand-picked group) and, shared with an
entity's or a hand-picked group's page, `profileBody` (`profileView`'s relations/how-referred-to/book-by-book/kinds-of-action/appears-with/
distinctive sections, extracted so both can use them; `opts.noSpeechTopics` and `opts.noCooccur` turn off the two that a pool can't support).
A gender bucket is its own row in the Entities list (type `"GENDER"`, built client-side from `/api/units`'s `genders`, since it isn't a real
entity type); a book's page is linked from its row on the Library page ("Overview"), not from the Entities list.

`.ent-list` (`app.css`) is a sticky flex column (`.head` for the search/filter controls, `.items` for the scrolling rows). `.items` needs
`min-height: 0` (with `.head` set to `flex: 0 0 auto`): without it, a flex child with `overflow: auto` won't shrink below its content's own
intrinsic height, so a `.head` that grows tall (many selected-entity chips, wrapped over several lines) pushed `.items` past `.ent-list`'s
bottom border instead of scrolling inside it.

`.filters-grid` (Quotes, `dialogue.js`) has the same class of gotcha for CSS Grid: `grid-template-columns: repeat(auto-fill, minmax(200px,
1fr))` sizes every column from the widest content ever placed in it, across every row, because a grid item's default `min-width: auto`
lets its own unbreakable content (a `<select>`'s longest option string) inflate the *track*, not just overflow past its own cell. One
field with a long option — "Addressee found by", from `dialogue.ADDR_METHODS`'s "Speaker keeps talking to the same person" — was enough
to widen column 1 past 200px, squeezing the other columns in the row above it and pushing "Book" to overlap "Containing". Fixed with
`min-width: 0` on `.filters-grid label` and its `select`/`input`, so a track never grows past its `minmax()`; an over-long selected value
just clips inside its own box (native `<select>` behaviour) instead of resizing the grid.

**Pickers.** `picker()` chooses an entity, a group (`groupPicker`: search, chosen entities shown as removable tags outside the list, saved groups, the Entities
selection), a tag group, "everyone else", a narrator, a book or a gender (`opts.book`/`opts.gender`; the same spec kinds `View.resolve` accepts,
so Compare, Dialogue's speaker/narrator pickers and an entity's "Compared with" all take one without further plumbing). `typeFilter()` (corpus.js) is the word-type filter. Requests that can be superseded by a newer one
(corpus searches) keep a counter so only the newest may fill the page. A chosen entity is drawn by `gtag()`: a compact pill (`.gtag`) with its type as small
text and a colour bar (an inset box-shadow) rather than a separate badge, so it reads as one shape; used by `groupPicker` (including on the Compare page) and a
group profile's member list (`entities.js`'s `groupHeader`). Its book label (`booksLabel`) is truncated with an ellipsis (`.gtag small`, 90px) to keep the chip
compact; the full label is the chip's own `title`, so it shows on hover.

**Many books.** Charts and lists that draw one thing per book stay readable and light with sixty: a line chart with more than `MANY_LINES`
(12) lines names them by tooltip instead of at their right-hand ends (`timeChart`), x-axis labels are thinned to about sixteen (`lineChart`), book
titles over an arc chart are left out beyond twelve books, "Kinds of action, book by book" shows the eight books with most actions and says
so, the concordance plot is drawn from 200 counts per book (`plotChart`), and the Network page's "Show at most" box sends `max_nodes`. Entities
remembered from an earlier visit (Arcs, Sentiment) are dropped if they no longer exist (linked since, or below the minimum now) rather
than leaving an empty chart. `tests/js/many.mjs` opens the pages over forty books to keep it so.

**Corpus tools** (`corpus.js`). The tool tabs (`.corp-tabs`) are a sibling of the settings panel, not nested inside it — both are direct
children of `main` — so `position: sticky` keeps them below the top nav across the whole page (settings and results alike), not just
while their own short panel is in view; nesting it inside the panel was tried first and only stuck for that panel's own height. Search
settings (word forms/lemmas, case, regex, wildcards, ignore punctuation) are always shown, not behind a collapsed `<details>`. Wildcards
(`S.corp.settings.wildcards`, default on) is disabled whenever regex is on (regex already gives you the same power); switching it off makes
`*`, `?`, `|` and `#` literal characters instead of Simple/Pattern search wildcards, so you can search for punctuation like `?` or `!` —
`corpus.value_matcher`'s new `wildcards` param does `re.escape()` instead of interpreting them when off, and `parse_simple`'s `#` (any
word) marker is likewise only special when wildcards are on. `queryBar` swaps
between a single-line `<input>` and a `<textarea>` (`S.corp.batch`) for a batch query — one term or pattern per line, Ctrl/Cmd+Enter to
search since Enter alone adds a line — passed to the server as-is (a batch is just a multi-line query string: see `corpus.Matcher`).
`corpKwic` shows a "Matched" checkbox (`S.corp.showMatch`) only when the result says `batch: true`; on, each `kwicLine` gets a `.kl-m`
column naming which line matched (`.kl.with-match` changes the row's grid columns to fit it).

**Independent controls.** A control must never change what another one shows (a user rule, after two reports: Speech verbs' two filters,
and Book by book / What's distinctive's significance settings). Two kinds of sharing exist, and only the second is allowed to stay:
(1) *same-page coupling* — two panels on one page reading one state — is a bug; (2) *a documented global setting* that is drawn once
and visibly applies to a whole page or tool group is intended. The intended ones: the Corpus scope, search settings and query (drawn once
at the top of the five Corpus tools, `S.corp`); the Arcs-and-style slice/chapter timeline setting (`S.nar.seg`, shared by Arcs, Style,
Stylometry, Sentiment and the topic pages); the book selection and the conversation-gap setting; the significance settings (below).

**Sentence type** (`dialogue.js`, `sentenceTypeFilter(st, onChange, compact)`): a "Sentence type" select (All/Questions/Exclamations/Statements)
and a "Weigh the speech verb too" checkbox, for filtering or scoping by `dialogue.sentence_type`. Every place that shows it has its own
state object `{type, weigh}` in `S.dlg.sf` (`quotes`, `verbs` = "How speech is introduced", `verbsTarget` = "One speaker or group",
`style` = Speaking style, `voice` = Distinctive vocabulary) and the entity Speech panel keeps one local to the panel, so changing one
changes nothing else, on that page or any other. `typeArgs(st)` turns a state into the request's `types`/`weigh_verb`. The entity Speech
panel (`speechPanel`) uses the same function in its compact form: the same control on one small line. `entity()`'s `vb = verbs(view, spec, None, types,
weigh_verb)` call used to pass `None` for `types`/`weigh_verb` even when the caller asked for a filter, so the entity Speech panel's
Speech-verbs/Adverbs tables silently ignored it while the other figures (from `style(pairs)`) obeyed it — fixed by threading the same
`types`/`weigh_verb` through.

**Significance settings** (`S.stat`: ranking measure, test, minimum frequency, p-level, Bonferroni, show non-significant; `statControls`)
are one global set, saved in localStorage and used by every comparison panel (entity Book by book and What's distinctive, Compare,
Corpus Keywords, Speech verbs' distinctive verbs, Distinctive vocabulary, narrator vocabulary). Because an entity's page shows two of
those panels at once, `saveStat(origin)` announces a change with a `statchange` event and `syncStat(el, run, refresh)` makes a panel
re-run (and, for What's distinctive, rebuild its controls) when the *other* one changes them, so the two never disagree; `origin` is the
changing panel's own re-run function, which `syncStat` skips.

**In-Depth Who Speaks** (`dialogue.js`'s sixth Dialogue tab, `dlgIndepth`): "Who speaks"'s three sections — "Dialogue in each book",
"Speakers", "Narrators" — filterable and comparable by entity, group, tag or gender. `wholeSpeakersPanels()` (the first two sections'
markup, extracted from `dlgSpeakers` so both share it) and `narratorsPanel()` give the unfiltered, whole-selection view when Search mode
has nothing chosen — the same content "Who speaks" shows. Choosing a scope pools everyone it matches into one `/api/dialogue/scope` call
(`scopedSpeakerPanels(spec)`): "Dialogue in each book" becomes that pool's own `entity()`-style per-book breakdown plus its own dialogue-
share-over-time chart (`E.time`, from `dialogue.scoped_time`), "Speakers" its pooled `style()` figures as a `.facts-inline` card (mirroring
`speechPanel`'s), "Narrators" its pooled `narrating` figures if any of it narrates. A `seg()` (Search/Compare, mirroring Corpus's Simple/
Pattern toggle) chooses one scope or two. The scope picker uses `picker(value, onChange, {group: true, gender: true})`, which is Entity +
Group + Tag (always) + Gender — no `book`/`narration`/`others` modes, since those aren't among the four axes asked for. Because switching
Search/Compare must also show or hide the "Compared with" field and relabel "Scope" to "Target", `drawControls()` rebuilds the whole
controls row on every change (mode, target or reference) — simpler and more robust than patching it in place, and cheap since `picker()`'s
`onChange` only fires on a completed selection, not per keystroke. `core.view.View.pool_unit(spec)` is the server-side piece: see the
Group entry above.

Compare mode (`compareSpeakerPanels`) stacks target and reference as rows rather than two side-by-side columns, one colour per side
(`PALETTE[0]`/`PALETTE[1]`) throughout, on the reasoning that a reader compares figures more easily aligned than split left/right:
"Dialogue in each book" becomes one `hbarChart` of quotes per book, a paired bar (target's colour above reference's) for each book,
rather than two tables; its dialogue-share chart becomes one `timeChart` combining both sides' `E.time` series (each book's line still its
own name/colour pair, `"<book> · <side>"`, since it's the side — not the book — that carries the meaningful colour here); "Speakers"
becomes a `cmpRow` per figure — a label and two small `.bar-cell` bars, sized relative to whichever side is larger, reusing the same class
`barFmt` uses in tables but with an explicit two-colour `background` (its default CSS only sets one, `var(--accent)`); "Narrators" becomes
two coloured-left-border lines instead of two `.facts-inline` cards. Two independent `/api/dialogue/scope` calls via `Promise.all`, not a
single merged endpoint — each side's figures come back in exactly the shape `scopedSpeakerPanels` already uses, so Compare only has to
pick a different way to lay them out, not recompute them differently.

**The Links page** (`links.js`) shows one card per character throughout: `.link-card` for each side of a suggested pair (`sideView`), and `.person-card`
(laid out several to a row by `.people-grid`, filled the same `--panel-2` as a suggestion card) for each already-linked person, with every book appearance
it was made from listed inside the card (`personCard`), each with its own Unlink. A card's head has its type (`typeChip`, from `links.persons`'s
`type`: its members' most-mentioned category) and name on the left, "Open profile" and a checkbox (unrelated to its appearances) on the right, for
batch work: the toolbar above the grid dissolves every ticked person at once, one `/api/links/unlink_all` call per card (`Library.unlink_all`, which — like
`unlink` taking one member out — gives every departing member a copy of the tags, name and description the linked person had).

Linked narrators (the same narrator role linked across books, e.g. an anonymous narrator carried from one book to the next) get their own
"Linked narrators" subsection below the people grid, in their own `narratorLinkCard`s — the same shape as `personCard` but for narrator roles:
no book appearances or tags (a role isn't an entity), each member its own possibly-anonymous role with its own Unlink, and "Unlink all" to
dissolve the whole link. They're kept out of the person batch-unlink toolbar and use `/api/narrators/*` (not `/api/links/*`) since it's a
different kind of link. `core.links.narrator_links`/`_unit_name` resolve a narrator link's members and display name directly from `lib.state`,
mirroring `persons`'s own View-free pattern (this listing has to work library-wide, regardless of which books are selected or the minimum-mentions
setting) rather than reusing the View-dependent `dialogue.role_name`. Both iterate a `list(...)` snapshot of `lib.state`'s dict, not the
dict itself: FastAPI runs each request in its own thread pool worker, so a concurrent request that mutates `lib.state["persons"]` or
`["narrator_links"]` (an unlink, say) while one of these is mid-loop would otherwise raise "dictionary changed size during iteration".

**Sort direction.** A "most/least" style sort `<select>` that has no direction of its own gets a `reverseBtn()` beside it: ↓ for the normal order, ↑ once
reversed, matching the concordance sort's own reverse arrow. It flips whatever the current sort key's normal order is (most-first for a count, A–Z for a
name), rather than meaning "ascending" globally. Used by the Entities list (`entSort` / `entSortRev`) so far.

**Several books together.** `bookLabel(id)` names a book for a list of several (the server already orders these by year, see `view.py`); it adds "(publication
date missing)" for one with no year, since that is why it sorts last. `bookLink(id, label?)` wraps that in a link that "drills down": clicking sets the
selection to just that book (`setSel([id])`) and redraws the current page, so a table or chart of several books can jump to any one of them (the "Book by book"
overview table on an entity's page does this for its Book column; add it to a page's own book-labelled cells the same way as they are touched). It also
pushes the wider selection it narrowed from onto `S.selHistory`, for `viewingBar()`'s "Back" button.

**The viewing bar** (`#viewSlot`, a sibling of `#main` so it sits above a page's own layout regardless of whether that page has a side panel or a ToC).
`renderPage()` fills it on every render except the Library page (which shows the selection in its own table): `viewingLabel()` names what the selection amounts
to — a single book's title; a whole collection's or series' name when the selection is exactly that; `Various for "X"` for several books all from one
collection or series but not all of it (the smallest enclosing collection wins over a series, if both match); else `Various`. `viewingBar()` adds a "Back"
button when `S.selHistory` isn't empty, popping it and restoring that wider selection.

**State.** `S` holds what the interface remembers. Parts are saved in `localStorage` under `analyser.*` keys through
`loadState(key, defaults)` (defaults merged with what was saved, key by key, and only if the saved value is the same kind of thing) and
`saveState`. (Keys include `analyser.libview` for the Library page, `analyser.read`, `analyser.corp`, `analyser.nar`, `analyser.net`, and
`analyser.plural`: each page's own plural-group choice, page key -> true/false, see `pageKey` / `pluralMode` / `pluralBox`; and `analyser.theme`: "auto" (the default, follows the system), "light" or "dark", set by the button at the top right (`setTheme`, `#themeBtn`) as `<html data-theme>`, which `app.css`'s custom properties key off. `index.html` sets it from storage in a small inline script before the stylesheet loads, so there is no flash of the wrong theme.) Damaged or unavailable storage falls back to defaults and never stops a page.

**Talking to the server.** `api(path, body)` posts JSON, adding the page's plural-group choice (`plural`) unless the body sets it. On failure it shows a message, replaces the "Loading…" line that request was
going to fill (see `loading()`), and throws an error marked `handled`, so an unawaited call doesn't add console noise.

**Building DOM.** `h(tag, props, ...children)`: props starting `on` are listeners, `class`, `style` (object); children may be nested
arrays; `null`/`false` are skipped; strings are text. `svg:circle` builds SVG; style keys starting `--` are set with `setProperty` (custom properties). Charts are functions returning `<svg>`; `chartBox()`
adds SVG/PNG download buttons; `table()` gives sortable, limited, CSV-exportable tables. A chart's own text, axis lines and halos are plain SVG attributes, not stylesheet rules, so they can't pick up
`app.css`'s custom properties through CSS alone: they read the current theme's colour at draw time with `cssVar("--ink")` and the like. Downloaded SVG/PNG charts always use the light-theme colours on a white
backing rectangle regardless of the screen's theme (`prepSvg` swaps them back), since a saved file has no theme of its own. Categorical colours (entity types, series, topics) don't change with the theme.

**Page tools** (`pagetools.js`). A MutationObserver watches `#main`; after any change `enhancePage()` adds a fold arrow to every
top-level panel with a heading (or a `data-toc` label) and to `h3` sub-headings (the heading plus what follows it up to the next heading),
re-applies remembered folds (`analyser.collapsed`, keyed by page and heading), and builds the sticky menu when there are three or more
top-level sections (on the right for the Entities page, where the list takes the left; topic pages have their own menu).
Give a panel `data-toc="Label"` to name it in the menu when it has no heading; put `data-cx-head` on a row to fold by it.

**Styling.** One `app.css`; colours and fonts are custom properties on `:root`. Light is the default; dark values are set in a
`@media (prefers-color-scheme: dark)` block (for "Auto") and again under `:root[data-theme="dark"]` (for the toggle's explicit
"Dark", which also blocks the media query from applying when it is explicitly "Light"). `--chrome` is a surface that stays dark
in both themes (the top bar, toast and tooltips), since it always carries white text.

## 9. Testing

Setup, once (from the project folder, with your environment active):

```
pip install -e ".[dev]"                    # the package itself (editable), pytest and httpx
cd tests/js && npm install                 # jsdom, for the browser tests (needs Node); optional
```

Run:

```
pytest                       # everything (Python tests, and the browser tests if Node and jsdom are installed)
pytest tests/test_view.py    # one file
pytest -k topics             # by name
```

The suite never touches your real data: every test uses a generated corpus and its own temporary data folder.

**Continuous integration.** `.github/workflows/tests.yml` runs the whole suite (browser tests included) on every push and pull request, on Ubuntu and
macOS with Python 3.10 and 3.13, from a fresh `pip install -e ".[dev]"` and `npm ci --prefix tests/js`, so the newest library versions are tried
as well as the oldest supported Python. A failure there that you can't see locally is usually a newer library: reproduce it in a new virtual environment.

**A large library** is tested two ways. `tests/test_scale.py` generates sixty small books (`fixture.build_many`: each its own mix of themes
and characters) and checks figures and limits; it runs in a few seconds. `tests/benchmark.py` times every analysis over a whole library of
real books:

```
python tests/benchmark.py                                   # sixty generated books
python tests/benchmark.py --sources /path/to/your/books # your own books (only read); add --data some/folder to keep the parsed-book cache
```

It prints each request's time and size, marks anything slower than `--slow` seconds (default 2) and any rise of peak memory, and ends with the
peak memory in use. `python tests/serve_fixture.py --many 60` serves sixty generated books in a browser.

**The test corpus** (`tests/fixture.py`) generates three small "books" in BookNLP's file layout, from a seeded random generator, with
hand-written dependency parses, entities and quotes, a first-person narrator (alpha), chapter headings and four vocabulary themes
(moor, goose, room, case). While generating, it counts the truth: mentions per character, quotes and words per speaker, the verbs a
character does, possessions, prepositions, vocatives. Tests compare the analyser's numbers with these counts, so they check
*correctness*, not just that code runs. `tests/serve_fixture.py` serves the same corpus in a browser.

| File | What it covers |
|---|---|
| `test_bookdata.py` | parsing against the truth; damaged and partial files; spacing and marks in rebuilt text |
| `test_library.py` | scanning, versions and pinning, the pickle cache, atomic saving, tags, links (entities and narrator roles), rejections, corrections |
| `test_stats.py` | p-values and effect sizes against SciPy and by hand; keyness filtering |
| `test_view.py` | minimums and counting modes, linking, profiles, distinctiveness, evidence, book by book, book and gender pools |
| `test_corpus.py` | the query languages, batch queries (merging, the matched line, patterns too), concordance counts against the truth, scopes, near-word filter, sort levels, context search, lists, word-type filters (counted straight from the files), collocates, keywords, reference files |
| `test_dialogue.py` | quotes, verbs, conversations (against an independent count), addressees, your corrections, style, narrators, sentence type (by punctuation and by speech verb) and its filter in quotes/style/voice/entity |
| `test_narrative.py` | segments, your chapter edits, arcs adding up to the totals, style figures, stylometry, sentiment, emotion |
| `test_narrators_network_links.py` | narrator suggestions (including a stretch told by someone else), networks and exports, link suggestions |
| `test_reader.py` | the text view: balanced marks, layers, jumping to a token, narrators, topics, paragraph and sentence numbers, finding a place without marking it |
| `test_export.py` | the export zip: what goes in, the state cut down to the selected books (persons, collections, groups, plurals, narrator links), topic models and references, the books readable again |
| `test_localonly.py` | Host and Origin checks: foreign names, forged and null origins, other ports, our own page, scripts, reading |
| `test_bookcache.py` | the cache round trip, a real cache fully allowed, code in a cache refused and not run, a poisoned cache rebuilt |
| `test_workspaces.py` | the list of workspaces and the active one, creating/renaming/forgetting, deleting (the typed name, only folders the analyser made), importing an export zip (and refusing bad ones without leaving anything), and the routes: switching between workspaces keeps their work apart, a damaged one is refused, switching under load |
| `test_bookcollections.py` | collections: nesting, several per book, names, moving without cycles, deleting, saving, routes |
| `test_groups.py` | groups pooled against the entities' figures, members not counted as outsiders, saved groups following links and the selection, narrators as entities, group and narrator routes |
| `test_topics.py` | settings, documents, words, fitting and its reproducibility, recovery of the four themes, storage, every part of a topic's page, comparisons, uses elsewhere |
| `test_edge_cases.py` | books with no quotes, no entities, or one sentence, through every analysis |
| `test_robustness.py` | damaged and unusual files: byte-order marks, Windows line endings, other encodings, missing columns, numbers that aren't numbers, lines outside the book, an unreadable book among good ones |
| `test_scale.py` | sixty generated books: the right figures over many books, a limited search still reaching the later books, a network cut to the strongest entities, link suggestions and patterns in good time, strings shared |
| `test_api.py` | every route (the export download included), its errors, your corrections end to end, paging, concurrent requests, topics switched off |
| `test_frontend.py` | runs `tests/js` (below) against a live server: the three-book corpus, forty generated books, and a library with no books |

**Browser tests** (`tests/js`, Node + jsdom; the page is loaded from a live server in a simulated browser): `smoke.mjs` visits every
page; `interactions.mjs` clicks and types through the main features (editing books, collections and search, exporting a zip, workspaces (make, rename, switch, remove, delete by typing the name), filtering, narrators (including
linking them and assigning one to a whole chapter), select several and groups, Compare groups and two books split into characters, book and
gender overview pages, opening profiles, correcting a quote, searching with sort levels, a context search, word-type filters and a batch
query with its Matched column, the sentence-type filter in Quotes/How they speak/an entity's Speech, the scrolling
text view and the chapter editor, the network focus, fitting a topic model, folding sections…); `units.mjs` tests the helper functions;
`many.mjs` opens the main pages over many books and checks that charts stay a bounded size; `empty.mjs` opens every page of a library with no
books (a new install) and checks that none breaks and that the Library page leads with where to find books.
`harness.mjs` holds the shared helpers.
Run one by hand against a server:

```
python tests/serve_fixture.py --port 8799 &
cd tests/js && node smoke.mjs http://127.0.0.1:8799
```

## 10. Extending the analyser

*A new analysis.* 1) Write the function in a `core/` module, taking a `View` (or `Library`) and plain arguments, returning a dict of
JSON-friendly values, raising `ValueError` (or a subclass) with a helpful message for input that can't be used. 2) Add a route in the
matching `api/` router: read the body with `whole`/`real`/`need` (they give readable errors), call the function, return it; give the route
a one-line docstring (it appears in the table above). 3) Add a `renderX` page or a section in the matching `static/js` file; use
`api()`, `withBooks()`, `table()`, `note()`. 4) Register the tab in `index.html` and the router in `main.js` if it is a new page.
5) Add tests: the function against the fixture (add a counted truth to `tests/fixture.py` if you need one), the route in `test_api.py`,
the page in `tests/js/smoke.mjs` (and `interactions.mjs` if it has controls).

*A new kind of value in `BookData`* (a class other than a list, set, dict, tuple, `Counter`, `defaultdict`, `array`, `Path`, `BookData`, `Group`): add it to
`bookcache.ALLOWED`, or the cache silently stops working (`test_bookcache.py` catches it) and every start re-parses the books.

*A new part of a topic's page.* Add `part_x` in `core/topics/page.py` (use `Topic`, `assoc`, `group_rows`), a branch in `api/topics.py`'s
`page` route, a section in `static/js/topic-page.js`, and its explanatory text in `notes.py`.

*A new explanatory note.* Put the text next to the code it describes (`NOTES` dictionaries); `api/library.py` sends them to the browser.

## 11. Large libraries

Built and measured on 60 books made from real BookNLP output (four novels and 56 short stories, 760,000 tokens, 8,400 entities at a minimum of one
mention; the words of copies shuffled within their part of speech so that the books are not repeats of each other). `tests/benchmark.py` reproduces
the figures on any set of books. Memory is the main cost of size; time is mostly spent once, the first time something is asked.

| | 60 books (760,000 tokens) |
|---|---|
| Reading every book the first time | about 5 s (parsing); about 1.2 s afterwards, from the cache |
| Memory with every book loaded | about 700 MB (540 bytes a token; a book's files are ~80 bytes a token). Plural-group counting adds ~15% |
| Memory after using every page | 1.5–1.7 GB at the most (per-book lookup tables, dialogue records, a topic model fitting) |
| A page of results | under 0.5 s for most; the slowest first-time requests (style figures per book, sentiment, a pattern with many optional parts) take 1–4 s |
| The cache folder | about twice the size of the books' own files |

What keeps it that way, and what to keep doing when adding something:

* **Cut before you count.** Anything that pairs things up across the whole library (a network, link suggestions, n-grams) has a limit that is
  applied early: `network.build`'s `max_nodes`, link candidates only from shared name parts, n-gram rows made only for the ones shown (`heapq.nlargest`).
  Lists returned to the browser are cut to a size a page can show (5,000 word-list and n-gram rows, 20,000 concordance hits and 500 lines a page, 300 link suggestions).
* **Never rebuild a whole structure inside a loop** (`set(G)` per quote made a dialogue network take three seconds instead of a tenth).
* **Keep what is derived from a book on the book** (`BookData.cache(owner)`), keyed by what it depends on, and keep few of them.
* **Keep dense matrices out of topics**: documents × words are sparse (`npmi_coherence` takes a sparse matrix; a dense one for thousands of documents would run to gigabytes).
* **Memoise what cannot change within a call** (`Matcher.hits` for repeated pattern parts) and **read only what is shown**
  (`kwic_lines`, rows of lists).
* **Write a test with many books** (`tests/test_scale.py`) when a new feature compares or combines books.

## 12. Robustness decisions

* **No crash on bad input.** Numbers from the browser are read with `whole`/`real` (a readable 400 if they aren't numbers); searches
  that can't run (`QueryError`) and topic requests that can't be met (`TopicError`) say why.
* **Books are read defensively**: blank lines skipped, missing optional files and columns fine, byte-order marks and Windows line endings fine, a file that
  isn't UTF-8 refused with a message, out-of-range positions and unreadable lines skipped and reported (a supersense span can't run past the
  book), and one unreadable book never stops the others (`View.problems`, the Library page).
* **Limits protect the server**: a pattern search can't blow up (memoised repeats); a network, a list or a search that could grow without bound is cut and says so.
* **Sources and ids from the browser are checked**: a correction to a book that doesn't exist is a 404 and invents nothing; statistics options
  that don't exist are refused with the list of those that do; `sources` must be a list; a damaged unit id is "not found", not a crash.
* **Writes are atomic**; a damaged settings file is reported, never replaced.
* **Concurrency**: requests run in a thread pool. The view cache and the file writes are locked; per-book caches are idempotent and
  read with `.get`; corrections take the library lock.
* **Overlapping requests**: pages whose settings change quickly (corpus searches) let only the newest request fill the page.
* **Stale files**: browsers are told never to cache the scripts and style sheet (`Cache-Control: no-cache`), so an update shows at once.
* **Topic models** record each book's token count; a book that changed afterwards is flagged and passages are withheld rather than shown wrongly.
* **Text safety**: server text never becomes HTML in the browser.
* **Only you can reach it** (`localonly.py`). The server listens on 127.0.0.1, but a web page in your browser can still talk to it, so two things
  are checked on every request: `Host` must be `127.0.0.1` or `localhost` (otherwise a page on another domain could reach it by "DNS rebinding"), and a
  request that changes something (anything but GET/HEAD/OPTIONS) that carries an `Origin` must carry exactly our own (`http://<Host>`), so a form or
  script on another site, or a program on another local port, can't make your browser change your library. Requests with no `Origin`
  (`curl`, scripts) are allowed; reading requests are checked for `Host` only, since no CORS headers are sent. Test clients must therefore use
  `base_url="http://127.0.0.1"` (`fixture.LOCAL`).
* **The cache can't run code.** A pickle can execute anything when opened, so `bookcache.loads` accepts only a parsed book's classes. When a
  new kind of value goes into `BookData`, add its class to `bookcache.ALLOWED`: `test_bookcache.py` opens a real cache and fails until you do.
* **Newer libraries**: the tests run in CI on Python 3.10 and 3.13 with the newest versions pip finds, which has caught real breaks (a GEXF export that newer
  networkx refused because of mixed number types, a Mann–Whitney `nan`, Python 3.13 pickling `Path` under another name).

## 13. Troubleshooting

* *"Something went wrong (…)" on a page*: the message names the error; the terminal has the traceback. Re-run with the failing action
  and look for a line starting `Error in POST /api/…`.
* *A book doesn't appear*: it needs `.tokens` and `.entities` in a folder listed under Library → Where to find books.
* *Numbers look stale after re-exporting*: switch to the window (the analyser re-checks on focus) or reload; the parsed-book cache is keyed by
  file modification times, and deleting `alex-data/cache` is always safe.
* *Topics tab asks for scikit-learn*: `pip install -e .` again (or `pip install scikit-learn`), then restart.
* *Browser tests are skipped*: install Node, then `cd tests/js && npm install`.
* *Slow or heavy with many books*: the first start parses every book (a few seconds each for a novel; later starts read the cache). Run
  `python tests/benchmark.py --sources <your folder>` to see which request is slow and how much memory the books take, and see section 11. A network
  shows at most 300 entities (raise "Show at most", or raise the minimum link strength); the concordance stops at 20,000 hits.
