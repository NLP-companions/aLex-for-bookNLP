# aLex user guide

How to use aLex, the BookNLP analyser. Installing and starting it are in the [README](../README.md); this guide starts from the page in your browser.

aLex only reads your BookNLP files and never changes them. Its own settings, book collections, saved groups of entities, links and tags are kept in `alex-data/library.json`, fitted topic models in `alex-data/topics`, your corrections to addressees, conversations, narrators and chapters in `alex-data/annotations.json`, reference files for keywords in `alex-data/references`, and an emotion lexicon, if you load one, in `alex-data/lexicons`. `alex-data` is made in the folder you start aLex from (see the README for choosing another place).

The first time a book is opened it takes a few seconds to index; after that it loads from `alex-data/cache`. When aLex starts it reads all your books in the background, so a library of sixty books is ready within a few seconds (about five the first time, one or two afterwards).

## Where books come from

Under **Library → Where to find books**, add the folders aLex should look at (or start it with `alex --books FOLDER`). A folder can hold BookNLP's output files directly (`houn.tokens`, `houn.entities`, …), or hold exports in dated subfolders as the companion editor writes them, in which case the newest export of each book is used. Under **Library** you can:

- choose an earlier export of a book;
- add or remove folders of books;
- give each book a title, author, year, series and tags;
- **organise the library in collections**: make collections on the left of the table (a collection can sit inside another, like a folder, and a book can be in several at once), add books to them with the ＋ in the *Collections* column, and click a collection to list its books and those of the collections inside it. Deleting a collection never deletes books;
- **export** the selected books as one `.zip` (*Export selected books (.zip)*): their BookNLP files (the export in use) and your work on them — links between entities, names, tags, notes, groups, collections, plural groups, narrator links, corrections, settings — plus your topic models for those books and your keyword reference files;
- **search** by title, author, series, tag, year or id, and group the table by series or author; *Analyse the books shown* sets the book selection to whatever is listed, and *Add the books shown to…* files them all in a collection;
- open a book's own **Overview**: its facts (words, quotes, author, year…) and, pooling every entity counted in it as one, the same figures as an entity's page — "how does this book look" — minus Speech and Topics (which need one particular entity, not a pool) and Appears with (the pool already contains almost everyone who could appear with it).

When you export again from the companion editor, aLex picks up the new export when you return to its window.

If an export's folder also holds the original `.txt` (the companion editor copies it there), an **Original text** button appears under that book's export details, to download it; the analyser also uses it, when present, to get the exact spacing between words right in the text view (otherwise it guesses at a single space).

The button at the top right chooses which books to analyse. It has a search box and filters by collection, series, author, tag or year.

Every page (other than this one) names what that selection amounts to just above its own content: a single book's title, a whole collection's or series' name, "Various for…" for several books from the same one, or "Various". Clicking a book's name in a table or chart that lists several (such as "Book by book" on an entity's page) narrows the selection to just that book; a **← Back** button then appears there to return to the wider selection.

## Workspaces

A **workspace** is a separate library: its own folders of books, links between entities, groups, collections, corrections, topic models, reference files and settings. Nothing is shared or merged between workspaces, so you can keep one corpus apart from another. The workspace in use is shown in the picker at the top right; choosing another one opens it and reloads the page. What you saw before (book selection, search settings…) is remembered separately for each workspace. The analyser starts in the workspace you used last.

The library you start with is the **Default** workspace. Under **Library → Workspaces** you can:

- **make a workspace** (a name, and optionally the folder its books are in), then *Switch to* it; add more book folders to it under *Where to find books*;
- **import** one from a zip made with *Export selected books (.zip)*: the books are copied into the new workspace together with the links, groups, collections, corrections, topic models and reference files in the zip, so the zip works on any computer (and importing never touches another workspace);
- **rename** a workspace, or **remove it from the list** (its files stay where they are);
- **delete** a workspace the analyser made (an imported one, or one made here): this removes its folder with everything in it, including copied books, and can't be undone, so you must type its name first. The Default workspace and the one in use can't be removed or deleted, and books in folders a workspace merely points at are never touched.

The list of workspaces is kept in `alex-data/workspaces.json`, and the workspaces made or imported here in `alex-data/workspaces/`. The Default workspace is `alex-data` itself.

## Minimum mentions

Also under **Library**. There's one minimum per entity type (PER, LOC, FAC, GPE, VEH, ORG, and VAR for things you code by hand in the companion editor), and 2 matches BookNLP's rule for `.book`. You can count it in each book separately, or across the selected books combined.

## Light and dark mode

The button at the top right, next to the book selection, cycles Theme: Auto (follows your system) → Light → Dark. Your choice is remembered.

## Long pages: side menu and collapsing

- **Side menu.** A page with three or more sections (an entity's profile, Library, Links, Narrators, the topic pages, stylometry and so on) gets a sticky menu of them, which highlights the one you're reading. It sits at the left, or at the right on the Entities page, where the list takes the left. **Collapse all** and **Expand all** are under it. Topic pages have their own menu at the left. The menu is hidden on narrow windows.
- **Collapsing.** Click the arrow beside any section heading, or the heading itself, to fold the section away. Sub-headings (such as the blocks under stylometry) fold too, together with what follows them. Your choices are remembered by page and heading, so they stay after a reload.

## Many books

The analyser is built to work on a whole library: it has been run on sixty books (about 760,000 words, 8,400 entities) from real BookNLP output. All books together take about 700 MB of memory while it runs. Most pages answer in well under a second; a few things take a few seconds the first time (style figures, sentiment, link suggestions). To keep results readable and quick:

- a **network** shows the 300 most strongly linked entities (change **Show at most** on the Network page, up to 1,000; or raise the minimum link strength) and says how many there were;
- a **concordance** stops at 20,000 hits and shows 500 lines at a time (**Show more**); its plot shades each slice of a book by the number of hits;
- **word lists** and **n-grams** list the 5,000 most frequent;
- charts with many books name their lines by hover instead of at the line's end, and "Kinds of action, book by book" shows the eight books with most actions.

To see how your own library behaves, and which request is slow, run this from a clone of the repository (with the environment active):

```
python tests/benchmark.py --sources /path/to/your/books
```

It only reads your books; it prints each request's time and size and ends with the memory used.

## Tests and documentation

- **How it works, and how to change it:** [DOCUMENTATION.md](DOCUMENTATION.md) explains the folder layout, the data files, how a request flows, the methods used, the web API, the browser code and how to add a feature. The code carries comments on every function.
- **Tests:** a suite of about 530 tests checks the analysis against a small generated corpus with known answers, every web route, damaged and unusual files, a library of sixty generated books, and (in a simulated browser) every page and the main features, also with forty books and with none. To run it, from a clone of the repository:

  ```
  pip install -e ".[dev]"
  cd tests/js && npm install        # optional: adds the browser tests (needs Node)
  cd ../.. && pytest
  ```

  The tests use their own generated books and temporary folders; they never touch your data.

## Views

- **Entities.** One page per person, place, organisation and so on:
  - mentions and where they fall in each book;
  - names, descriptions and pronouns, and who names them in dialogue;
  - actions, what's done to them, possessions, modifiers, and prepositions ("went to London"), with events and supersenses;
  - who they appear with;
  - what's distinctive about them compared with others.
  Click any row to see the sentences behind it. Add tags here. **Rename** an entity (or a linked person) from its own name, and give it a short
  **description** — both shown everywhere that entity is, and undone by clearing them (a "Reset" link brings back the name found in the books).
  - **Narrators** are entities too: the **Narrators** chip lists one row per narrator role ("Watson, narrating", "Narrator of *book*"). A role's profile shows how much it narrates and where, its voice (questions, I/you/we, word length, MATTR) next to all narration and next to the same character's dialogue, a row per book, and the words that are distinctive of its narration. The character's own page is unchanged.
  - **Gender** is a pool too: the **Gender** chip lists one row per BookNLP-predicted gender (he/him/his, she/her, they/them/their…, plus "No BookNLP gender prediction" for anyone without one). Its page pools every entity of that gender as one — "how do the women in these books talk, act, appear" — the same figures as an entity's page, minus Speech and Topics (which need one particular entity, not a pool) and Appears with (a pool already contains almost everyone who could appear with it).
  - **Several entities as a group.** Switch on **Select several** under the search box: every row gets a checkbox (click the row or the box). *Select shown* ticks everything that matches the type chip and the filter, *Select by tag…* adds every entity with a tag, *Clear* empties the ticks. **Analyse together** opens one profile for the ticked entities: they are listed at the top as removable tags with each entity's share of the group, and every figure below is pooled (mentions, how they're referred to, actions and other relations, speech, topics, who they appear with, what is distinctive). *Save as a group…* keeps the group under a name (open it from *Saved groups…*, change it and *Update* it, or use it on the Compare page).
- **Book by book** (on an entity's page, when it's in two or more of the selected books). Each book's figures side by side, and a table of the entity's actions, possessions, modifiers and so on per book, with a χ² test of which words change between books. There are also charts of the most changed words and kinds of action per book. Books are listed by publication year (a book with none sorts last, marked "publication date missing" — set it under Library); click a book's name to switch to just that book.
- **Dialogue.** Six views:
  - **Who speaks:** dialogue per book and across each book, and a table of speakers with words spoken, share of dialogue, how often they're addressed and how their quotes are introduced.
  - **Speech verbs:** verbs and adverbs that introduce quotes ("said quietly", "cried"), overall and per speaker, and which are distinctive of a speaker; both the overall table and the one-speaker-or-group panel below it can be scoped to just questions, exclamations or statements, so you can see how, say, questions are introduced, down to one speaker.
  - **How they speak:** a speaking-style table (words per quote, questions, exclamations, I/you/we, word length, MATTR) and each speaker's distinctive vocabulary against other speakers, one speaker or a tag group. Both can be scoped to just questions, exclamations or statements.
  - **Conversations:** runs of quotes; click one to read it with speakers and estimated addressees.
  - **Quotes:** every quote, filtered by speaker, book, text, speech verb, attribution, how the addressee was found, or sentence type (questions, exclamations, statements).
  - **In-Depth Who Speaks:** Who speaks' three sections — Dialogue in each book (including its "Share of words in dialogue" chart), Speakers and Narrators — filtered or compared by **Entity**, **Group**, **Tag** or **Gender**, everyone the choice matches pooled as one (the same way the Gender and tag pages elsewhere pool a bucket into one profile). **Search** mode scopes all three sections, chart included, to one choice (or shows everyone, same as Who speaks, with nothing chosen). **Compare** mode (like Corpus's Simple/Pattern toggle) puts two choices' figures side by side as rows rather than columns — a paired bar per book for Dialogue in each book, a shared chart with one coloured line per side for the dialogue-share curve, and a paired bar per figure for Speakers and Narrators, target's colour above reference's throughout — so you can see, say, how women's dialogue volume compares with men's, book by book, or one tagged group against another.
  - **Sentence type** (Quotes, How they speak's Speaking style and Distinctive vocabulary, Speech verbs' overall table and its one-speaker-or-group panel, and an entity's Speech section): a quote is a question or exclamation if it contains `?` or `!`; tick **Weigh the speech verb too** to also count one like *asked* as a question or *exclaimed*/*cried* as an exclamation when the quote itself has neither mark. Every one of these has its own Sentence type and checkbox: setting one never changes what another shows.
- **Corpus.** Tools after AntConc, over the selected books. Each can be limited to narration, dialogue, or one character's or group's speech. The tool tabs stay in view as you scroll through results, and search settings (below) are always visible, not tucked behind a click.
  - **Concordance (KWIC):** sortable on three levels, each with a position (the hit, one of five words left or right of it, or the book) and what to compare there: the word, its lemma, its word class (POS), its fine tag, or how often that word occurs there among the hits; an arrow reverses a level. A plot shades each slice of every book by the number of hits, with hits per book, dispersion, and who says them. Click a line to read its paragraph. A search stops at 20,000 hits; scope, near-word and context filters are applied before that limit, so they never use it up.
  - **Search in the context** (under the search box): keep only hits that have, or do not have, a second search in the words around them. It takes a simple or pattern query like the main search, how many words to look at on the left and the right, and can stay within the sentence.
  - **Word list:** words, lemmas, word + POS, **word + POS + lemma** (three columns) or POS, with frequency, range and dispersion.
  - **Word types:** the word list and the collocates can be limited to word classes (POS), entity types and fine tags, several of each (words of any chosen value, and every group that has a choice must match). In a word list rates stay per 1,000 words of the whole text.
  - **N-grams:** a range of lengths, optionally containing a word first, last or anywhere, like AntConc's clusters.
  - **Collocates:** a window you choose, ranked by MI, T-score, logDice, MI3, log-likelihood or frequency; optionally only collocates of some word types.
  - **Keywords:** against other books (any of your library, with their own scope, such as dialogue against narration) or reference files. Reference files can be word lists (such as AntConc's exports) or plain texts.
  - **Searches are simple by default:** words with `*`, `?`, `a|b` and `#` for any word.
  - **Pattern queries** search BookNLP's layers, for example `[lemma="say"] [pos="ADV"]` or `[char="Holmes"] [lemma="look"]`. Attributes: word, lemma, pos, tag, dep, ent, prop, char, ss, event, quote, speaker. Quantifiers: `? * + {n,m}`.
  - **Batch search** (Concordance and Collocates): tick **Batch** to turn the search box into a list, one term or pattern per line — `said`, `asked`, `shouted`, or a pattern per line — searched together as alternatives and merged into one result. Quicker than typing `said|asked|shouted` by hand, and, unlike that, a line can be a whole phrase or pattern. Turn on the **Matched** checkbox under the results to see, in its own column, which line found each hit.
  - **Regular expressions** can be turned on under Search settings.
  - **Wildcards**, also under Search settings, are on by default (`*`, `?`, `a|b` and `#` as above). Turn them off to search for those characters literally instead — useful for finding punctuation like `?` or `!` — in either Simple or Pattern search; it's disabled while Regular expressions is on, since regex already gives you that.
- **Arcs and style.** Everything here can be measured over equal slices of each book or over chapters. Chapters are found from headings (Chapter, Adventure, numerals, lines in capitals, optionally short unpunctuated lines); check them under "Check the chapters found", and correct them in the text: **Edit chapters** opens the book like the text view, where you can start a chapter at any paragraph, rename a chapter or remove a chapter's start (its text joins the chapter before). Your changes are used everywhere chapters are (Arcs and style, topic documents, the text view) and can be undone with *Back to the automatic chapters*. With more than one book selected, **Timeline** chooses how Arcs, sentiment and emotion plot them: **Book by book** (the default) gives each book its own line, so a trend never seems to cross a book's end; **Whole corpus** draws one continuous line across every selected book instead, to follow a change across or between them, and (with equal slices) shares the slice count across the books by their length rather than giving each the same number.
  - **Arcs:** characters and places, events, supersenses and dialogue across each book, per 1,000 words, and topics (each topic's share of the words in every chapter or slice, from a topic model you choose).
  - **Style:** per book or per chapter or slice. Sentence and word length, MATTR, hapaxes, lexical density, dependency distance, tree depth, subordinate clauses, passives, questions, dialogue share, Flesch scores, and a parts-of-speech profile.
  - **Stylometry:** Burrows' Delta, Cosine Delta or Euclidean distance on the most frequent words, between books or between chapters or slices. Shown as a cluster tree, a principal-component map (coloured by book, author or series), nearest texts and a distance table.
  - **Sentiment and emotion:** a VADER sentiment arc, also around chosen characters, and emotion arcs from a word–emotion lexicon you load (such as the NRC Emotion Lexicon, which is free for research but can't be included).
- **Speech** (on an entity's page): their quotes, words, share of dialogue, where they speak, speech verbs and adverbs, per book, and who they talk to and are spoken to by; a small Sentence type select (with its own "Weigh the speech verb" checkbox) scopes this to just questions, exclamations or statements, independently of every Dialogue tab's filter.
- **Topics.** Topic models over the selected books (only those, so the selection decides what is modelled). Each model is saved with its settings, so it doesn't change under you.
  - **Documents:** chunks of about N words (ending at a sentence), groups of paragraphs, chapters or slices (from the Arcs and style setting), or whole books; narration and dialogue, or either alone.
  - **Words:** nouns, verbs, adjectives, adverbs and proper nouns, as lemmas or word forms. Names can be removed using BookNLP's mentions (proper names, all people, or all entities), which is more precise than a name list. General words (thing, way, say, go…) can be removed, plus any of your own.
  - **Methods:** NMF (the default, usually crisper on small collections) or LDA, with a fixed seed so results repeat.
  - **Number of topics:** "Compare" fits a model for a range of numbers and shows coherence, diversity and stability for each. Click a row to use it.
  - **Overview:** each topic with its most probable and most distinctive words, share of the text, share in each book, its strongest passages, coherence and stability (in how many re-runs with other seeds a similar topic came back). Name a topic by typing in its title; the words it rests on always stay visible.
  - **Topic page** (click a topic). Name it at the top, and move between topics. The list at the left jumps between its sections and follows you as you scroll.
    - **Words:** a slider trades frequent words against exclusive ones (relevance, as in LDAvis), with each word's probability, uses and how much of it belongs to this topic. Click a word to search for it in the concordance.
    - **Where it occurs:** a strip per book shaded by the topic's share of each document (click to open the text), a table of which books use it more or less than the others (Mann–Whitney U on documents), and an arc across chapters or slices, following the Arcs and style setting.
    - **Passages:** the documents where the topic is strongest, with its 30 most probable words highlighted. Filter by book.
    - **Entities:** characters, places and other entities mentioned more (or less) in text where the topic is strong, by type. The score ranks them; it isn't a significance test.
    - **Speech:** how much of the topic's text is dialogue, where its top words fall, and which speakers and narrators carry it.
    - **Book details:** the topic's share by series, author, year or tag.
  - **Compare topics** (from the overview or the left of a topic page).
    - **Map of topics:** topics are similar when they share words (cosine of their word weights) or appear in the same chunks (correlation of their shares). You get a similarity network (circles sized by share, lines above a similarity you set; click a circle for the topic or a line for the pair), a cluster tree, a similarity matrix in tree order, and a table of pairs.
    - **Side by side:** two topics with words only in the first, in both, and only in the second; their arcs overlaid; their share in each book; and the entities and speakers that lean towards one rather than the other.
    - **Grids:** topic × book (or series, author, year, tag), topic × character (choose entity types) and topic × speaker. Cells show each item's share of mentions or words in each topic's text, or that against the topic's average. Every grid downloads as CSV.
  - **In the text view.** Switch on **Topics** under Show and choose a model that includes the book. A band above each passage names its leading topics (click it to see every topic and its share), a bar marks the passage's main topic, and each topic's most probable words are underlined in that topic's colour. Or choose one topic to shade passages by how much of it they hold.
  - **On an entity's page.** A Topics section shows which topics the entity's mentions, or its speech, fall in: the share of them in each topic's text, that against the topic's average, and a ranking score.
  - **Small collections give unstable topics.** Check the stability figures before reading much into a topic.
- **Read.** The text of any selected book as one scroll: chapters (or slices, following the Arcs and style setting) load as you scroll, each with a heading, and every paragraph has its number in the margin. The menus at the top (book, what to show, the type legend) stay frozen above a position bar that shows where you are (chapter, paragraph) and jumps between chapters, so they never slide under the text. It can show entities (underlined in their type's colour; click a type in the legend to hide or show it), quotes with speaker → addressees, each paragraph's narrator, events, supersenses, sentence numbers and topics. "Open in the text" links from sentences, quotes, concordance lines and conversations jump to the spot. Click a name for its profile, a quote to correct it, or a narrator label to change a paragraph's narrator. Clicking a pronoun or description ("he", "the detective") shows what it's **attributed to** ("Attributed to Holmes"), with a link to that entity's own profile — not just the word itself.
- **Your corrections.** In the text view, and under "Correct" on any quote in the Dialogue lists, you can:
  - set a quote's addressees (one or several, or "everyone present");
  - add listeners to a conversation, or remove participants;
  - start a new conversation at a quote, or join a conversation to the previous one.
  
  Corrections replace the estimates everywhere (tables, network, profiles) and are marked as yours. Speakers and mentions are still corrected in the companion editor.
- **Narrators.** Choose each book's narrator (a character, or an unnamed narrator) under Library or in the text view, and assign paragraphs told by someone else — one at a time, several in a row, or "Apply to this whole chapter" to give a whole chapter to someone else at once. Narration (text outside quotes) is that narrator's voice. A character who narrates appears twice, "narrating" and in dialogue, so you can compare their narration with their direct speech (Dialogue → Who speaks → Narrators, and How they speak).
- **Linking narrators.** On a narrator's own page, link it with another narrator role to treat them as one voice — Watson narrating one book and Watson narrating another, or two unnamed narrators, or a mix. This only pools their narration; everything else about them (mentions, relations, dialogue) stays separate. Unlink one at a time or all at once.
- **Narrators** (its own page, next to Entity Links). Suggestions from the "I" in each book's narration (outside quotes):
  - **The book's narrator:** the character behind most first-person narration, with each candidate's share.
  - **"Who is this?":** when BookNLP left the narrator's "I" as a group without a name, link it to a character here. This uses the same links as everywhere else.
  - **Paragraphs told by someone else:** runs of paragraphs whose "I" belongs to another character, shown with sample sentences (the "I"s marked), how much evidence there is, and Accept, Not right, or Open in the text. Accepted runs become paragraph exceptions, which you can undo. Rejections are remembered.
  - **Third-person books** have no "I" in the narration, so they get no suggestions; choose a narrator by hand if you want one.
  - Suggestions are only as good as BookNLP's grouping of "I" and its quote boundaries, so merge a split narrator and fix missing quote marks in the companion editor first.
- **Compare.** Two entities, groups, tag groups, books or genders side by side, with differences in both directions. For a **Group**, search and click to add entities (they appear as tags under the search box; the × removes one), or start from a saved group or from the entities ticked on the Entities page. Either side can be limited to some books, for example Holmes in the first book against Holmes in the last, or all suspects in early books against late ones. Comparing two **books** adds a **Split into characters** table: every character in either, with their mentions in each, so comparing the books as a whole doesn't lose who's in them.
- **Network.** Links by shared sentence, shared paragraph, a speaker mentioning someone in a quote, or a speaker talking to someone (estimated addressee). You choose which types to include and how many entities to show at most (the most strongly linked, 300 to begin with; the page says how many there were), and see the usual measures, and communities. Hover over a circle to highlight it and its neighbours; **click a circle to keep that focus** (its measures and links show at the side), and click empty space to release it. A circle without a label shows its name while it is hovered or in focus.
- **Entity Links.** Treat the same person or place in different books as one entity. **Auto-link exact matches** links outright, across your whole library, any entities that agree exactly on name, type and (for people) BookNLP's pronouns — that agreement is the safeguard, so places and things (with no pronouns to check) are left for you; undo any of it like any other link. Beyond that, the app suggests likely matches from names for you to confirm or reject; suggestions are only made between books of the same series (set the series under Library), because names recur between unrelated books. You can still link anything by hand: click either search box to list the entities of every book (most mentioned first) and type to narrow the list; the entity already chosen in the other box is left out. You can also rename, unlink and tag. Each linked character is its own card, with its book appearances listed inside; tick several cards' own checkboxes (not an appearance) and **Unlink selected**, at the top of the list, dissolves all of them at once. Below the people, **Linked narrators** lists any narrator roles you've linked (see Linking narrators, under Narrators) the same way — one card per link, its member roles listed inside, each with its own Unlink, and **Unlink all** to dissolve the whole link.

## Exports

- Every table: **Download CSV**, opens in Data Wrangler.
- Every chart: **SVG** or **PNG**.
- Networks: **GEXF** or **GraphML** for Gephi, with type, tags, mentions, measures and community as node attributes.

## How the numbers are made

Each table has a "How…" note underneath explaining it. In brief:

- **Relations** use BookNLP's rules on the dependency parse, with three additions:
  - conjoined mentions share a role ("Holmes and Watson went");
  - a subject counts for coordinated verbs ("rose and lit his pipe");
  - prepositional attachments are recorded for every type.
  Counts can therefore be slightly higher than in `.book`.
- **Plural groups** (e.g. "Holmes and Watson" and the *they* BookNLP linked to it) are entities of their own. Declare one on its page (in
  its framed "Plural group" box: search for a member and click it; × removes one), from the entity list (tick the entities, then "Make plural group of the others…"), or
  accept a suggestion on the Entities page (entities named after two or more others). On a linked entity it applies in every book (one
  made before you linked the entity carries over). A page only shows the members counted in the selected books (and says how many are below the
  minimum); adding or removing one there keeps the others.
  Whether their mentions, what they do, who they appear with, their quotes and the quotes addressed to them also count for each member
  is up to you: the default is under **Library** (own mentions only, to begin with), and every page that depends on it has its own checkbox
  *Include plural-group mentions* (above the page, or in the "Plural group" box on an entity's page) to switch on impulse. A page keeps
  its choice until you set it back ("reset") or choose other books. A member named inside a plural mention ("Holmes and Watson walked")
  counts once, through its own mention, and a plural group is never counted as appearing with its own members.
- **Change between books** uses Pearson's χ² for each word against all other words, by book, with adjusted standardised residuals to show which books differ.
- **Addressees** aren't in BookNLP's output, so they're estimated, and each estimate records how:
  1. a person named in the quote as a form of address ("Come here, Watson.");
  2. the previous speaker in the same conversation;
  3. the same person as the speaker's previous quote;
  4. the next speaker, for an opening line.
  A conversation ends after 100 narration words without a quote; change this on the Dialogue page.
- **Speech verbs** are the verb whose subject is the mention BookNLP used to attribute the quote. Otherwise it's the nearest speech verb within 8 tokens.
- **Distinctiveness** compares an item's frequency in the target and the reference with a 2×2 table. It is ranked by your choice of log-likelihood, chi-squared, log ratio, %DIFF or odds ratio. p-values come from G² or χ², with an optional Bonferroni correction.
- **Network measures** come from networkx: betweenness and closeness use 1 ÷ weight as distance, and communities use Louvain with a fixed seed.

## Files

- `alex/`: the program
  - `app.py`: starts the server and turns errors into messages
  - `api/`: the web API, one file per area (library, entities, dialogue, corpus, narrative and text view, topics, links, workspaces)
  - `core/`: the analysis
    - `bookdata.py` reads one book and extracts relations; `library.py` holds settings, links, tags and your corrections; `bookcollections.py` collections of books; `entitygroups.py` saved groups of entities; `plurals.py` plural groups; `view.py` combines books, thresholds and links and builds profiles
    - `stats.py` comparison statistics; `corpus.py` concordance, word lists, n-grams, collocates, keywords and reference files; `dialogue.py` quotes, speech verbs, addressees and conversations; `narrative.py` chapters and slices, arcs, style, stylometry, sentiment and emotion; `narrators.py` narrator suggestions; `network.py` networks; `links.py` link suggestions; `reader.py` the text view
    - `topics/` topic modelling
  - `static/`: the browser side (`index.html`, `app.css`, and the scripts in `js/`)
- `tests/`: the tests, the generated corpus they use, and `benchmark.py`, which times every analysis over a whole library
- `alex-data/`: aLex's own files, made in the folder you start it from; it is the Default workspace, and holds `workspaces.json` and `workspaces/` for the others

The details are in [DOCUMENTATION.md](DOCUMENTATION.md); what every figure means and how it is calculated is in [MEASURES.md](MEASURES.md).

## How corrections are kept

Corrections (addressees, conversations, narrators, chapter starts and titles) are attached to quotes and paragraphs by their opening words, not by token numbers. They survive re-exports from the companion editor as long as the quote or paragraph still begins the same way. If you change a quote's opening words in the editor, correct its addressees again; a chapter start whose paragraph changed is quietly ignored.
