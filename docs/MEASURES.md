# Measures: what the analyser shows, and how it is made

Every figure, table column and chart in the analyser is defined here: what it says, how to read it, what it assumes, where the data
comes from, how it is calculated and where in the code. The user guide (guide.md) explains *using* the analyser and DOCUMENTATION.md explains *how it
is built*; this file explains *what the numbers mean*. The same explanations appear, shorter, under the "How this is calculated"
notes in the interface.

**How each entry is written.** *Says*: what the figure tells you. *Read it as*: how to interpret it, and how not to. *Assumes*: what has to
be true for it to be meaningful. *Data*: which BookNLP file or which of your settings it comes from. *Calculation*: the recipe.
*Code*: the file and function (`core/view.py: profile` means the function `profile` in `core/view.py`; look there for the exact recipe).

Contents: 0 Ground rules · 1 Entities and their profiles · 2 Groups of entities · 3 Comparing two sets of words (keyness) ·
4 The same entity in several books · 5 Dialogue · 6 Narrators · 7 The corpus tools · 8 Chapters, arcs and style ·
9 Stylometry · 10 Sentiment and emotion · 11 Topics · 12 Networks · 13 Suggestions (links and narrators)

---

## 0. Ground rules

These apply everywhere, so they are stated once.

**Token, word, sentence, paragraph.** BookNLP's `.tokens` file has one row per token (a word, a punctuation mark, a piece such as *n't*).
Everything is addressed by the token's position (0, 1, 2 …). Sentences and paragraphs are BookNLP's own (`sentence_ID`, `paragraph_ID`).
*Words* means tokens that are not punctuation:

* in the **entity pages** ("per 1,000 words") a word is a token whose part of speech is not PUNCT, SPACE, SYM or X
  (`core/bookdata.py: BookData.n_words`);
* in the **corpus tools, dialogue, style and narration** a word is a token that is not PUNCT, SPACE or SYM and not a quotation mark
  (`core/corpus.py: cindex`, key `isword`, which dialogue and the other tools share).

The two counts differ only by tokens tagged X (foreign words, stray symbols), which are few. Where a figure divides by "words", it says
which of the two it uses.

**Per 1,000 words.** A rate: `1000 × count ÷ words`. It lets you compare texts of different lengths. It is a rate of *tokens*, not of
distinct things.

**In scope.** Corpus tools can be restricted to narration, dialogue, or one speaker's or group's quotes. A word is *in scope* when it lies
inside that part of the text (`core/corpus.py: Scope`). "Words in scope" is the denominator of every rate on those pages.

**The selection.** The books chosen at the top right. A `View` (`core/view.py`) is built for exactly those books; every number on a page is
for them, together, unless the page says "per book".

**The minimum.** Entities with fewer mentions than your minimum (Library → Minimum mentions) are left out of lists, profiles, comparisons,
networks and groups. It is set per type and can be applied per book or across the selected books combined (`count_mode`).
*Code*: `core/view.py: View._make_unit`.

**Entity, unit, member.** BookNLP groups the mentions of one character or place in one book into a *coreference group*. A *unit* is one such
group, or several you have linked across books (`p:<n>`). A *member* is one book's group inside a unit. *Code*: `core/view.py`, module
docstring.

**Significance and effect size.** Several tables give a p-value and an effect size. A p-value says how surprising a difference would be if
only chance were at work; an effect size says how big it is. With small counts effect sizes can be huge and unreliable, and with large
counts tiny differences can be significant. Read both, and prefer the effect size for "how much" and the p-value for "how sure".
Neighbouring passages of a book are not independent observations, so p-values are guides, not proofs.

**What is BookNLP's and what is added.** Mentions, coreference groups, quotes and their speakers, POS tags, the dependency parse,
supersenses and events are BookNLP's output, used as given. Everything derived from them (relations, addressees, conversations, narrators,
chapters, similarities) is computed here, and mistakes in BookNLP's layers carry through. Speakers and mentions are corrected in the editor
(and the books re-exported), not here.

---

## 1. Entities and their profiles

### 1.1 Mentions
* **Says**: how often the entity is referred to.
* **Read it as**: a count of references, not of pages or scenes: "Holmes" and "he" both count when BookNLP grouped them with him.
* **Assumes**: BookNLP's coreference is right. A character split into two groups is counted as two entities (fix it in the editor, or link
  them on the Links page); a merged pair is counted as one.
* **Data**: `.entities`, one row per mention (`COREF`, `start_token`, `end_token`, `prop`, `cat`, `text`).
* **Calculation**: the number of mentions in the unit's groups. A group's *type* is the most common `cat` among its mentions. A unit's
  type is the type with most mentions over its members.
* **Code**: `core/bookdata.py: BookData._entities`; `core/view.py: View._make_unit`.

### 1.2 Share of type (%)
* **Says**: the entity's part of all mentions of its type in the selection ("12% of all mentions of people").
* **Read it as**: a measure of prominence among its own kind. It depends on which entities pass the minimum.
* **Calculation**: `100 × mentions ÷ all mentions of counted units of that type`. Empty for a group of several types.
* **Code**: `core/view.py: Unit.as_row`.

### 1.3 Mentions per 1,000 words
* **Says**: how densely the entity is mentioned.
* **Assumes**: comparable between books of different length; less so between a book and one chapter.
* **Calculation**: `1000 × mentions ÷ words`, where words are those of the books the entity is counted in (each book once).
* **Code**: `core/view.py: View._profile` (`per1k`), `words_in`.

### 1.4 Where it falls (the strip)
* **Says**: where in each book the mentions are.
* **Read it as**: a heat strip from start (left) to end (right); darker means more mentions in that slice.
* **Calculation**: each book's tokens are cut into 100 equal slices; a mention counts in the slice holding its first token. The shade is the
  slice's count relative to the largest slice of that book's strip.
* **Code**: `core/view.py: View._presence`; `static/js/core.js: presenceChart`.

### 1.5 How it is referred to
* **Says**: the mix of names (PROP), descriptions (NOM: "the detective") and pronouns (PRON).
* **Read it as**: a character mostly pronoun-referenced is narrated closely; one mostly named appears in dialogue or lists.
* **Data**: the `prop` column of `.entities`.
* **Calculation**: mentions of each kind, with the most frequent forms of each (pronouns lowercased).
* **Code**: `core/view.py: View._profile` (`by_prop`, `forms`).
* **Pronouns**: the pronoun set BookNLP inferred for the character (`g.argmax` in `.book`), e.g. *he/him/his*. It is BookNLP's
  guess, shown as given, and also used as evidence in link suggestions.

### 1.5a Named or described in dialogue by
* **Says**: which speakers name or describe the entity inside their quotes.
* **Read it as**: who talks *about* it. Pronouns are left out, because inside a quote they mostly mean the speaker or the listener.
* **Calculation**: mentions of kind PROP or NOM lying inside a quote, grouped by the quote's speaker; the entity's own mentions of itself,
  and (for a group) mentions by its members, are not counted.
* **Code**: `core/view.py: View._named_by`.

### 1.6 What they do and what is done to them (relations)
Five lists, each a count of words attached to the entity's mentions by the dependency parse (`.tokens`: `dependency_relation`,
`syntactic_head_ID`):

| List | Says | Rule |
|---|---|---|
| Actions (agent) | verbs the entity does | mention is the subject (nsubj) of a verb, or the "by" agent of a passive |
| Done to them (patient) | verbs done to it | mention is object, indirect object or passive subject |
| Possessions (poss) | things it owns | mention is the possessor of a noun ("his pipe") |
| Modifiers (mod) | how it is described | adjectives attached to it, nouns in apposition, complements of "to be" |
| Prepositions and settings (prep) | "went to London" | mention is the object of a preposition attached to a verb, noun or adjective |

* **Read it as**: a portrait of the character in verbs and nouns, from the text's grammar only. It cannot see what the grammar hides
  (a pronoun BookNLP mislinked, a sentence the parser got wrong).
* **Assumes**: the parse is right. Extensions to BookNLP's rules, all documented in the code: a conjoined mention takes the role of the
  first conjunct ("Holmes and Watson went"); a subject also counts for verbs joined to its verb ("rose and lit" gives *rise* and *light*);
  prepositions are recorded for every type. Counts can therefore exceed those in BookNLP's `.book`.
* **Columns**: *Count* (occurrences), *Per 1,000 words* (rate, see 1.3), *%* (share of the list's total), *Events* (how many of these
  verbs BookNLP marks as EVENT, `event` column), *Supersense* (the most common WordNet supersense BookNLP gave the verb, `.supersense`).
  Clicking a row shows the sentences, so any count can be checked.
* **Code**: `core/bookdata.py: BookData._relations`, `_add`; `core/view.py: View._relation_tables`.

### 1.7 Kinds of action (supersenses)
* **Says**: which kinds of verb the entity does or suffers: communication, cognition, perception, motion…
* **Data**: `.supersense` (WordNet lexical categories per token), attached to the verbs of the agent and patient lists.
* **Calculation**: counts of the supersense of each verb found in 1.6; verbs without one are counted apart and not shown.
* **Code**: `core/view.py: View._supersense_tables`.

### 1.8 Appears with (co-occurrence)
* **Says**: which other entities are mentioned in the same sentence.
* **Read it as**: proximity in the text, not interaction: two people can share a sentence without meeting.
* **Calculation**: the number of sentences that mention both; a sentence counts once per other entity.
* **Code**: `core/view.py: View.cooccurring` (uses `BookData.sent_members`, `group_sents`).
* **The small network** beside it draws the entity with its 15 strongest companions and the links among them (see 12).

### 1.9 What's distinctive
* **Says**: words (from one of the five lists) markedly more typical of this entity than of a comparison group.
* **Calculation**: keyness (section 3) of the entity's list against the same list of everyone else of the same type (or the group you choose),
  with the entity's own mentions excluded from the reference.
* **Code**: `core/view.py: View.distinctive`.

---

## 2. Groups of entities

You can tick several entities on the Entities page and analyse them together, and use such groups on the Compare page.

* **Says**: the pooled portrait of several entities counted as one.
* **Read it as**: figures for "these entities, together". A group of a hero and a sidekick is not their average: it is their sum.
* **Assumes**: it makes sense to add them. A group of different types has no share of type.
* **Calculation**: the group's members are those of all its entities, so mentions, forms, relations, supersenses, presence and quotes are
  summed. A sentence or quote counts once however many of the group's entities it holds. Entities of the group are never counted as
  outsiders: "named in dialogue by", "talks to", "spoken to by" and "appears with" leave out the group's own members; the Speech section
  adds **Quotes between members** (quotes spoken by one member and addressed to another).
* **The members table**: each entity's *mentions*, *% of the group* (its mentions ÷ the group's) and *per 1,000 words* (its own mentions
  over the words of the books it appears in).
* **Saved groups** store only entity ids and follow the minimum, the selected books and your links (an entity you linked afterwards is
  followed to its person).
* **Code**: `core/view.py: View.group_of`, `group_unit`, `group_profile`, `_profile`; `core/entitygroups.py`;
  `core/dialogue.py: entity`.

---

## 3. Comparing two sets of words (keyness)

Used for: distinctive words of an entity or group, the Compare page, keywords, distinctive speech verbs, a speaker's or narrator's
distinctive vocabulary.

**Setup.** For one item (a word) you have a *target* text and a *reference* text. `a` and `b` are the item's counts in target and
reference; `c` and `d` are the total counts of all items in each (the two text sizes). `Code: core/stats.py: compare, keyness`.

| Measure | Says | Calculation |
|---|---|---|
| **Log-likelihood G²** | how surprising the difference is | `2 Σ O ln(O/E)` over the four cells, with expected counts from the pooled rate (Rayson & Garside 2000). Signed + when the item is relatively more frequent in the target |
| **χ²** | the same, by Pearson's test | for the 2×2 table (item vs other items, target vs reference), without Yates' correction; signed like G² |
| **p** | chance that a difference this large arises by chance | from χ² with 1 degree of freedom (`p_chi1`); for G² and χ² alike |
| **Log ratio** | how many times more frequent, on a log₂ scale | `log₂((a÷c) ÷ (b÷d))` (Hardie 2014): 1 means twice as frequent, −1 half as frequent. Zero counts are replaced by 0.5 |
| **%DIFF** | relative difference in percent | `((a÷c) − (b÷d)) ÷ (b÷d) × 100` (Gabrielatos & Marchi 2012). Zero counts replaced by 0.5 |
| **Odds ratio** | the same as odds | `(a ÷ (c−a)) ÷ (b ÷ (d−b))` with a 95% interval from the log odds ratio's standard error; 0.5 is added to every cell when one is zero (Haldane–Anscombe) |

* **Read it as**: G² or χ² rank by *evidence* (large samples give large values even for small differences); log ratio, %DIFF and the odds
  ratio rank by *size of effect* (rare items give large values on little evidence). Use them together, and check with the
  sentences (every row opens its evidence).
* **Options**: *Minimum frequency* (an item must occur at least this often in the target, or on either side for two-way comparisons);
  *Significance level*; *Bonferroni correction* divides the level by the number of items tested, because testing many items produces
  false alarms; *Show non-significant* lists the rest, dimmed. Tested items are those with at least the minimum frequency.
* **Assumes**: words are independent draws, which they are not (a repeated phrase counts every time). Treat p as a ranking aid.
* **Code**: `core/stats.py: keyness`; used by `View.distinctive`, `corpus.keywords`, `dialogue.voice`, `dialogue.verbs`.

---

## 4. The same entity in several books

Shown on an entity's page when it is counted in two or more of the selected books (a linked entity, or a group).

* **Overview table**: per book, *mentions*, *per 1,000 words of that book*, *% of the type's mentions in that book*, the *names /
  descriptions / pronouns %* of its mentions, each list *per 100 mentions*, and the *most used names*.
* **Words, book by book**: for each word of the chosen list, its count in each book with its share of that book's list. **χ²**, **p** and
  **Cramér's V** test whether the word's share changes across books.
  * **Calculation**: the 2×k table (word vs all other words, by book), Pearson's χ² with k−1 degrees of freedom, p from that, and
    `V = √(χ² ÷ N)` (0 = the share is the same in every book, larger = it changes more). Words below the minimum frequency are listed without a test.
  * **Adjusted standardised residuals**: each book's cell is shaded when its residual is beyond ±1.96 (blue: more than expected from the
    other books, red: less). `(observed − expected) ÷ √(expected × (1 − book share) × (1 − word share))`.
  * **Code**: `core/stats.py: across`; `core/view.py: View.by_book`.
* **Assumes**: books are comparable in kind. Different-length lists per book are handled by working with shares.

---

## 5. Dialogue

BookNLP's `.quotes` gives each quote's start and end, the mention used to attribute it (`mention_start/end`) and the speaker (`char_id`).
Quotes with no speaker are counted but not attributed.

### 5.1 Words spoken, share of dialogue, quotes
* **Says**: how much a speaker says.
* **Calculation**: *quotes* = the speaker's quotes; *words spoken* = words inside them (not punctuation or quotation marks);
  *share of dialogue* = words spoken ÷ all words inside quotes in the selected books (including unattributed quotes).
* **Assumes**: BookNLP's quote boundaries and attributions are right; a missing quotation mark or a wrongly attributed speaker changes these
  counts (fix in the editor).
* **Code**: `core/dialogue.py: book_dialogue`, `overview`, `entity`.

### 5.2 Dialogue share along a book
* **Calculation**: the share of words inside quotes in each fiftieth of a book, lightly smoothed with its neighbours in the chart.
* **Code**: `core/dialogue.py: book_dialogue` (`time`).

### 5.3 Speech verbs and adverbs
* **Says**: how quotes are introduced ("said quietly").
* **Calculation**: the verb of the quote is the verb the attributing mention is the subject of ("said Holmes", "he cried", method
  *subject*), else the nearest speech verb (a built-in list of 77, or any verb BookNLP gives the communication supersense) within 8 tokens
  after the quote or before it, in the same paragraph (method *near*). Adverbs are the manner adverbs attached to that verb (not *then, again, now*).
  *% "said"* is the share of a speaker's quotes introduced by *say*.
* **Distinctive verbs** use keyness (section 3) of the speaker's verbs against all other speakers'.
* **Code**: `core/dialogue.py: _speech_verb`, `verbs`.

### 5.4 Conversations
* **Says**: runs of quotes that belong together.
* **Calculation**: a new conversation starts when more than `conv_gap` narration words (default 100, Dialogue page) lie between one quote and
  the next, unless you split or joined there. Participants are the speakers plus listeners you add minus those you remove.
* **Code**: `core/dialogue.py: book_dialogue`, `participants`.

### 5.5 Addressees (estimated)
* **Says**: whom a quote is spoken to. BookNLP does not record this, so it is *estimated*, and every estimate keeps its method.
* **Calculation**, in this order: (1) *named*: a person named inside the quote as a form of address, a name at the start, after a comma, or
  after *my / dear / O* ("Watson, come here"), or a description after *my / dear / O* or closing the quote after a comma ("My dear
  fellow, …"); (2) *reply*: the previous speaker in the same conversation, if someone else; (3) *continues*: the same person as the
  speaker's previous quote; (4) *next*: for an opening line, the next speaker. Otherwise none. Your corrections replace the estimate
  (*set by you*, or *everyone present*).
* **Read it as**: a good guess in two-person exchanges, weaker in crowds. Networks and "talks to" tables inherit its errors.
* **Code**: `core/dialogue.py: _vocative`, `book_dialogue`, `addressees`.
* **Addressed** (in the speaker table): quotes estimated to be addressed to the person.

### 5.6 Speaking style
| Column | Calculation |
|---|---|
| Words per quote | mean words per quote (also the median in the data) |
| Questions, Exclamations | quotes containing `?` (or `!`), per 100 quotes |
| I / You / We | words from the sets *I, me, my, mine, myself* / *you, your…, thee, thou…* / *we, us, our…*, per 1,000 words spoken |
| Word length | mean letters per word |
| MATTR | moving-average type–token ratio over windows of 100 words (Covington & McFall 2010): the mean over every window of (different words ÷ 100). Unlike the plain ratio it does not fall as more is said. Under 100 words the plain type–token ratio is shown in brackets |

* **Code**: `core/dialogue.py: style`, `mattr`, `style_table`.

---

## 6. Narrators

Narration is every word outside quotes, paragraph by paragraph. Each paragraph belongs to a *narrator role*: the book's narrator (chosen
under Library or in the text view, else an "unnamed narrator" of that book) unless you gave that paragraph to someone else.
*Code*: `core/dialogue.py: narrator_of`, `narration_recs`.

A **narrator's profile** (Entities → Narrators) shows:

| Figure | Calculation |
|---|---|
| Words narrated | narration words in the paragraphs of the role |
| Paragraphs | paragraphs of the role that contain narration |
| Share of all narration | words narrated ÷ all narration words in the selection |
| Per 1,000 words | words narrated ÷ all words of the books the role narrates in, × 1,000 |
| Set by paragraph | paragraphs you assigned to this role as exceptions |
| Where they narrate | paragraphs of the role in each 1% of the book (like the strip in 1.4) |
| Voice | the style figures of 5.6 for the role's narration (a "quote" is a paragraph: *questions* is the share of paragraphs with a `?`), next to all narration and next to the same character's dialogue |
| Book by book | paragraphs, words, share of the book's narration, words per paragraph |
| What's distinctive | keyness (section 3) of the role's words against other narration, everyone's dialogue, or the same character's dialogue |

* **Read it as**: "voice" figures compare *how the story is told*; they say nothing about mentions. The character's own profile (mentions,
  relations, dialogue) is separate.
* **Code**: `core/dialogue.py: narrator_rows`, `narrator_profile`, `voice`.

---

## 7. The corpus tools

All tools work on the words of the selected books in scope. Searches are *simple* (words, `*`, `?`, `a|b`, `#` any word) or *pattern*
(`[lemma="say"] [pos="ADV"]` over word, lemma, pos, tag, dep, ent, prop, char, ss, event, quote, speaker). *Code*:
`core/corpus.py` (`parse_simple`, `parse_pattern`, `Matcher`).

### 7.1 Hits, per 1,000 words, per book
* **Calculation**: hits are non-overlapping matches, leftmost first, lying wholly inside the scope. Per 1,000 words = hits ÷ words in scope × 1,000.
  A search stops at 20,000 hits. A candidate that is outside the scope, or lacks the near word or the context you asked for, is not a hit
  and does not count towards that limit (so a common word searched in dialogue only still reaches the later books), and it does not
  block the text it covers from being part of a later hit.
* **The plot**: each book is divided into 200 equal slices; a slice is shaded by its number of hits (the darkest slice of the book is the
  darkest shade). It is drawn from these counts, never from single hits, so a word with tens of thousands of hits draws as quickly as a rare one.
* **Code**: `core/corpus.py: kwic_search` (finds, filters and sorts the hits), `kwic_lines` (the text of the lines shown), `kwic` (both),
  `Matcher.hits`.

### 7.2 Dispersion (Juilland's D)
* **Says**: how evenly something is spread through the text.
* **Read it as**: 1 = perfectly even, 0 = all in one place. A frequent word can be badly dispersed (a character's name in one chapter).
* **Calculation**: `D = 1 − V ÷ √(parts − 1)`, V the coefficient of variation of the counts in ten equal parts (of a book for the
  concordance, of the selected text taken in book order for lists).
* **Code**: `core/corpus.py: juilland`.

### 7.3 Range
* The number of selected books an item occurs in.

### 7.4 Word list
* **Says**: how often each word, lemma, word+POS, word+POS+lemma or POS occurs.
* **Columns**: *Frequency*, *Per 1,000* (÷ words in scope), *Range* (7.3), *Dispersion* (7.2). *Types* are the distinct items; the
  *type/token ratio* is types ÷ tokens counted.
* **Word forms** are lowercased unless *Case sensitive* is on; lemmas are lowercased. A **word+POS+lemma** row is one combination of form,
  word class and lemma, so the same word as noun and as verb, or with two lemmas, is two rows.
* **Word-type filter**: only tokens of the chosen POS, fine tags and entity types are counted (a token is in an entity type when a mention
  of that kind covers it; several values of one kind mean *any*; different kinds must *all* hold). Rates and dispersion still refer to all
  words in scope ("nouns per 1,000 words"); the type/token ratio then compares the counted types with the counted tokens.
* **Code**: `core/corpus.py: counts`, `wordlist`, `token_test`, `filter_options`, `item_of`.

### 7.5 N-grams
* **Says**: recurrent runs of n consecutive words.
* **Calculation**: runs of the chosen lengths, not crossing a sentence end (if chosen) or a gap in the scope; *containing* keeps runs with
  a matching word anywhere, first or last. Frequency, per 1,000, range.
* **Size**: every different n-gram is held while the list is made, so a long range of lengths over many books needs much more memory than a
  short one: 2–5-grams over sixty books (about 700,000 words, a million different n-grams) take about three seconds and 170 MB, 1–8-grams
  about six seconds and 350 MB. At most the 5,000 most frequent are listed (the page says how many qualified).
* **Code**: `core/corpus.py: ngrams`.

### 7.6 Collocates
* **Says**: words that occur near the search term more (or less) often than chance.
* **Definitions**: *O* (Freq) = occurrences of the collocate in the windows (`L`/`R` split by side); *E* = expected count =
  `hits × collocate frequency in the corpus × window size ÷ tokens`; window = the chosen words left and right, stopping at the scope's edge and (if chosen) the sentence's.
* **Measures**: MI = `log₂(O/E)`; T-score = `(O − E) ÷ √O`; MI3 = `log₂(O³/E)`; logDice = `14 + log₂(2O ÷ (hits + collocate frequency))`;
  **log-likelihood** from the 2×2 table (collocate inside vs outside the windows), signed + when more frequent than expected, with p from χ²(1).
* **Read it as**: MI favours rare, exclusive partners; T-score favours frequent ones; logDice sits between and does not depend on corpus size.
  Rank by more than one and look at the concordance.
* **Word-type filter**: only decides which collocates are listed; windows and hit counts are unchanged; a collocate's corpus frequency
  counts only its own tokens of the chosen types, so a word is compared with its uses as that word class.
* **Code**: `core/corpus.py: collocates`, `_window`, `_ll4`.

### 7.7 Keywords
* **Says**: words more (or, optionally, less) frequent in the target than in a reference: other books (with their own scope) or a reference
  file (a word list or text you load; word forms only).
* **Calculation**: keyness (section 3) per word; *Range* = target books it occurs in.
* **Code**: `core/corpus.py: keywords`; reference files: `make_reference`, `parse_wordlist`.

### 7.8 Concordance sorting and the context search
* **Sorting**: up to three levels; each has a position (the hit, the 1st–5th word to its left or right, or the book) and something to
  compare: the word (A–Z), its lemma, its POS, its fine tag, or *frequency* (how often that word occurs at that position among these hits,
  most frequent first). An arrow reverses a level. Hits that tie on every level keep the order of the text.
* **Context search**: a second search (simple or pattern) in the window around each hit (words to the left and right, not counting the hit;
  stopping at the scope's edge and, if chosen, the sentence's); hits are kept when a match lies wholly inside the window, or, inverted,
  when none does. Matches of the second search are found over the whole book first (leftmost, non-overlapping).
* **Code**: `core/corpus.py: _sort_levels`, `_sort_hits`, `_ctx_filter`.

---

## 8. Chapters, arcs and style

### 8.1 Segments: slices and chapters
* **Says**: how books are divided for anything measured "per segment".
* **Slices**: n equal token counts per book. **Chapters**: start at heading paragraphs: 12 words or fewer, not a quote, beginning with
  a heading word (Chapter, Book, Part, Adventure…) or a numeral, or written in capitals (not initials and a name), or (if chosen) short
  lines without closing punctuation. Consecutive heading lines are joined; a heading closer than the *minimum chapter length* (words) to
  the previous one is ignored (tables of contents, signatures); text before the first chapter is an *Opening* if long enough; a book with
  fewer than two headings is cut into slices.
* **Your edits** (Edit chapters): headings you removed are dropped, paragraphs you start chapters at are added (your starts ignore the
  minimum length), titles you give replace the found ones; the text before the first start is an "Opening". Edits name paragraphs by
  their opening words and apply everywhere chapters do.
* **Code**: `core/narrative.py: segments`, `_is_heading`, `_edited_starts`, `book_segments`, `edit_chapters`.

### 8.2 Arcs
* **Says**: how something rises and falls through the books.
* **Calculation**, per segment: *entities*: mentions per 1,000 words; *events*: tokens BookNLP marks as EVENT per 1,000 words;
  *supersenses*: supersense tags starting in the segment per 1,000 words (runs of one supersense count once); *dialogue*: the share (%) of
  the segment's words inside quotes; *topics*: see 11.
* **Code**: `core/narrative.py: arcs`.

### 8.3 Style figures
Per book, chapter or slice. Only sentences that start inside the span count as sentences.

| Figure | Calculation |
|---|---|
| Sentence length | mean words per sentence (and standard deviation, median) |
| Word length | mean letters per word |
| MATTR | as in 5.6 (windows of 100 words) |
| Hapaxes | words occurring once in the text, as a share of its words |
| Lexical density | share of words that are nouns, proper nouns, verbs, adjectives or adverbs |
| Dependency distance | mean number of tokens between a word and its syntactic head |
| Tree depth | mean, over sentences, of the depth of the deepest word in the dependency tree |
| Subordinate clauses | relations advcl, ccomp, xcomp, acl, relcl, csubj per sentence |
| Passives | passive subjects (nsubjpass) per 1,000 words |
| Questions | sentences containing `?`, per 100 sentences |
| Dialogue share | share of words inside quotes |
| Flesch Reading Ease, Flesch–Kincaid grade | `206.835 − 1.015 × sentence length − 84.6 × syllables per word`; `0.39 × sentence length + 11.8 × syllables per word − 15.59`; syllables are estimated from vowel groups, so treat both as approximate |
| POS profile | share of words that are each part of speech |

* **Code**: `core/narrative.py: style_metrics`, `style`.

---

## 9. Stylometry

* **Says**: which texts (books, chapters or slices) are written most alike, judged by how often they use the most frequent words.
* **Calculation**: each text's relative frequency of each of the *n* most frequent words (word forms, lowercased; optionally without pronouns;
  words missing from too many texts are culled), turned into z-scores across the texts. **Classic Delta** (Burrows 2002) is the mean absolute
  difference of two texts' z-scores; **Cosine Delta** (Smith & Aldridge 2011) is 1 − the cosine of their z-score vectors, usually the most
  reliable; **Euclidean** is the straight-line distance. The **cluster tree** joins the closest texts first (average, complete or Ward
  linkage). The **map** is a principal component analysis of the z-scores (two axes, with the share of variance each keeps and the words that
  weigh most). **Nearest texts** lists each text's three closest.
* **Read it as**: small distance = similar frequent-word habits (author, genre, period). Short texts (under about 2,000 words) give
  unstable results; at most 400 texts are compared.
* **Code**: `core/narrative.py: stylometry`, `_cluster`.

---

## 10. Sentiment and emotion

* **Sentiment**: VADER's *compound* score (−1 most negative to +1 most positive; Hutto & Gilbert 2014) for each BookNLP sentence, averaged
  over the sentences that start in a segment. "Around an entity" averages only sentences that mention it. *Positive* / *negative* sentences
  score at least +0.05 / at most −0.05.
  * **Read it as**: rough tone. VADER was built for social media; literary irony, archaic wording and negation are handled badly.
  * **Code**: `core/narrative.py: sentence_scores`, `sentiment`.
* **Emotion**: with a word–emotion lexicon you load (such as the NRC Emotion Lexicon), words of each category per 1,000 words of a segment;
  a word counts by its form, else by its lemma, and may belong to several categories. **Code**: `core/narrative.py: emotion`.

---

## 11. Topics

A topic model finds groups of words that tend to occur together and says how much of each document belongs to each group. Topics on
fiction are settings, activities and registers rather than themes: a map to explore, not findings. Everything depends on the document
size, the words kept and the number of topics.

* **Documents**: chunks of about N words ending at a sentence, groups of paragraphs, chapters or slices, or whole books; narration and
  dialogue, or either alone. **Words** kept: chosen parts of speech, as lemmas or forms; tokens inside name (or person, or any entity)
  mentions are dropped using BookNLP's mentions; general words and your stop-words removed; words in too few or too many documents removed.
  The one function that decides which words count is `core/topics/model.py: kept_tokens`.
* **Fit**: NMF on tf–idf (default) or batch LDA, with a fixed seed. Each document gets shares of each topic that sum to 1.
* **Share of the text (topic size)**: the topic's average weight over documents, weighted by the words kept in each.
* **Coherence** (−1 to 1, higher is better): the mean normalised PMI of the co-occurrence, in documents, of the ten top words of the topic.
  **Diversity**: the share of distinct words among all topics' top ten. **Stability**: the model is re-fitted with other seeds and a topic
  *recurs* when a re-run has a topic (matched one to one) sharing at least 40% of its top 20 words; shown as "recurs in x of n runs".
  * **Read them as**: with few documents expect low stability; a topic that recurs in few runs may not be a robust pattern.
  * **Code**: `core/topics/model.py: npmi_coherence`, `diversity`, `match`, `stability`.
* **Relevance** (Sievert & Shirley 2014; the slider): `λ × log p(w|topic) + (1 − λ) × log(p(w|topic) ÷ p(w))`. λ = 1 ranks the most
  probable words, lower values favour words exclusive to the topic. **Exclusive share**: the part of a word's weight in the model that
  belongs to this topic. *Code*: `relevance`; `core/topics/page.py: part_words`.
* **Where it occurs**: each document shaded by its share; the **arc** puts each document in the chapter or slice holding its middle and
  shows the topic's share of the words there; the **books table** compares a book's documents' shares with the other books' with a
  **Mann–Whitney U** test (two-sided; needs at least five documents on each side; documents next to each other are not independent, so p is a guide).
  *Code*: `part_where`, `arc_of`, `group_rows`, `mann_whitney`.
* **Entities and speech** (also the Topics section of an entity's page): each document counts as topic text to the extent of its share
  (30% share = 30% topic text, 70% elsewhere). An entity's rate per 1,000 words in topic text is compared with its rate elsewhere: *share*
  (part of its mentions falling in the topic's text), *lift* (that share ÷ the topic's share of the whole model), *score* (a signed
  log-likelihood). The score ranks; it is not a significance test, because the weights are not independent observations. For speakers the
  rate is per 1,000 dialogue words, for narrators per 1,000 narration words. *Code*: `assoc`; `core/topics/uses.py: entity_topics`.
* **Compare topics**: *similarity by shared words* is the cosine of their word weights (0–1); *by appearing together* is the correlation of
  their document shares (−1 to 1); the map is classical multidimensional scaling of 1 − similarity (nearer = more similar; two axes keep
  only part of the picture), the tree is average linkage. *Code*: `core/topics/compare.py`.
* **Grids**: each cell is the item's (book's, character's, speaker's) share of mentions or words in each topic's text, or that against the
  topic's average ("× 2" = twice as much as usual).

---

## 12. Networks

Nodes are entities of the types you choose; an edge's **weight** is:

| Links by | Says | Weight |
|---|---|---|
| Same sentence / paragraph | mentioned together (undirected) | number of shared sentences / paragraphs |
| Speaker mentions them in a quote | who talks about whom (directed, speaker → mentioned) | quotes; speakers mentioning themselves are not counted |
| Speaker talks to them | who talks to whom (directed, speaker → estimated addressee) | quotes; inherits the addressee estimate (5.5) |

Edges weaker than the *minimum link strength* are dropped, and unlinked entities too unless you show them. A network of a whole library can
have thousands of entities, more than anyone can read and more than the measures and the layout can work out in a useful time, so at most
*Show at most* entities are kept (300 by default, 1,000 at most): those with the greatest strength (the sum of their edge weights), then the
most mentions. The page says how many entities there were. Measures are those of the network that is shown, not of the whole library, so a
shown entity's strength or community can differ from what it would be among all of them; raise the minimum link strength to thin a network
out evenly instead.

| Measure | Says | Calculation |
|---|---|---|
| Degree | number of neighbours | edges at the node (undirected version for directed networks) |
| Strength | how much it is linked | sum of edge weights |
| In-/out-degree, in-/out-strength | (directed only) incoming and outgoing edges | counted separately |
| Betweenness | how often it lies on the shortest paths between others (a broker) | normalised 0–1, with distance = 1 ÷ weight so frequent pairs are close |
| Closeness | how near it is to everyone else | with distance = 1 ÷ weight; can exceed 1; compare within one network only |
| Eigenvector | linked to well-linked entities | weighted, on the undirected graph; meaningful within a connected part, near zero outside the largest |
| Clustering | how much its neighbours are linked to each other | weighted clustering coefficient, undirected |
| Community | a tightly linked group | Louvain method on weights, seed 42 so results repeat |
| Density, components, communities | of the whole network | edges ÷ possible edges; connected parts; number of communities |

* **Read it as**: measures describe the *network you built*; they change with the link kind, types and minimum strength. Circle size is one
  chosen measure; the layout is a spring layout (positions carry no meaning beyond nearness within a connected part).
* **Focus**: hovering or clicking a circle highlights it and its neighbours; this is display only.
* **Code**: `core/network.py: build` (including the limit), `measures`, `layout`, `export`.

---

## 13. Suggestions (links and narrators)

### 13.1 Link suggestions
* **Says**: pairs of entities in different books that may be the same person or place.
* **Data**: names (PROP mentions), BookNLP's pronouns, entity type, and the *series* of each book (Library).
* **Calculation**: only entities with at least one proper name and two mentions, of the same type, in different books **that share a series**
  (compared case-insensitively; books without a series get none). Titles (Mr, Dr, Father…) are set aside. Score, strongest evidence
  first: the same full name 1.0; the same single name 0.85; for people the same last name 0.6; spellings at least 85% alike (`0.7 × similarity`);
  a shared word 0.35. For people, agreeing pronouns add 0.05 and different pronouns subtract 0.4. Scores of 0.2 or less are dropped.
* **Read it as**: an ordering of what to check, not a probability. "Not the same" is remembered.
* **Code**: `core/links.py: suggest`.

### 13.2 Narrator suggestions
* **Says**: who narrates a book, and which stretches are told by someone else.
* **Data**: first-person pronouns (I, me, my, mine, myself) outside quotes, each belonging to the coreference group BookNLP put it in.
* **Calculation**: the suggested narrator is the character behind most of them. A *run* is a stretch of paragraphs whose "I" belongs to
  someone else (paragraphs without an "I" can sit inside it, up to a set number in a row); *evidence* is the number of "I" in the run
  that belong to that character, *strength* their share of all "I" in the run. Runs with too little evidence and runs you rejected are
  left out. "We" is not counted, and third-person books give no suggestions.
* **Code**: `core/narrators.py: book_suggestions`.
