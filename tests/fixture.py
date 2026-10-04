"""A small, deterministic BookNLP-style corpus for the tests.

`build(folder)` writes three tiny "books" (alpha, beta, gamma) in the file layout the
editor exports (`<id>.tokens`, `.entities`, `.quotes`, `.supersense`, `.book`), one dated
folder per book, and returns a `Truth` with the numbers the analyser should find.

The sentences come from a handful of templates whose dependency parses are written by hand,
so what the generator counts (mentions, quotes per speaker, verbs a character does or
suffers, …) is the answer key for the analyser. Paragraphs are drawn from four vocabulary
"themes" (moor, goose, room, case), so a topic model has something real to find.

Nothing here needs BookNLP or spaCy; the corpus is generated from a seeded random generator.
"""
from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from pathlib import Path

LOCAL = "http://127.0.0.1"       # the address test clients use: the analyser only answers requests for this computer (alex/localonly.py)

# ---------- vocabulary ----------
THEMES = {
    "moor": {"nouns": ["moor", "hound", "fog", "hill", "mire", "rock", "track"], "adj": ["dark", "wild", "lonely", "grey"]},
    "goose": {"nouns": ["goose", "bird", "crop", "market", "jewel", "stone", "hat"], "adj": ["fat", "white", "bright"]},
    "room": {"nouns": ["candle", "corridor", "window", "door", "lamp", "chair", "carpet"], "adj": ["dim", "narrow", "quiet"]},
    "case": {"nouns": ["letter", "evidence", "clue", "inspector", "wife", "death", "secret"], "adj": ["strange", "grave"]},
}
# past form, lemma, supersense
VERBS = [("looked", "look", "verb.perception"), ("walked", "walk", "verb.motion"), ("watched", "watch", "verb.perception"),
         ("waited", "wait", "verb.stative")]
SPEECH = ("said", "say", "verb.communication")
QUOTE_OPEN, QUOTE_CLOSE = '"', '"'
PUNCT_NO_SPACE = {".", ",", ";", ":", "!", "?"}

# per book: coref ids of the recurring characters and places, themes with their weights, size in paragraphs, narrator
BOOKS = {
    "alpha": {"holmes": 1, "watson": 2, "street": 10, "place": 11, "themes": {"moor": 5, "room": 2, "case": 2}, "paras": 60, "first_person": True, "chapters": 4},
    "beta": {"holmes": 5, "watson": 6, "ryder": 7, "street": 20, "place": 21, "themes": {"goose": 6, "case": 2, "room": 2}, "paras": 45, "first_person": False, "chapters": 3},
    "gamma": {"holmes": 3, "watson": 4, "lestrade": 8, "street": 9, "place": 12, "themes": {"room": 4, "case": 6}, "paras": 24, "first_person": False, "chapters": 2},
}
STAMPS = {"alpha": "20260101-000000", "beta": "20260102-000000", "gamma": "20260103-000000"}


class Truth:
    """What a book really contains, counted while it was generated."""

    def __init__(self):
        self.mentions = Counter()            # (coref, prop) -> n
        self.quotes = Counter()              # speaker coref -> n quotes
        self.quote_words = Counter()         # speaker coref -> words inside quotes
        self.agent = defaultdict(Counter)    # coref -> lemma -> n   (subject of a verb)
        self.poss = defaultdict(Counter)     # coref -> lemma -> n   (possessor of a noun)
        self.prep = defaultdict(Counter)     # coref -> "verb prep" -> n   (object of a preposition)
        self.vocatives = Counter()           # (speaker, addressed coref) -> n
        self.words = 0                       # tokens that are words (not punctuation / quote marks)
        self.tokens = 0
        self.sentences = 0
        self.paragraphs = 0
        self.headings = 0
        self.theme_paras = Counter()         # theme -> paragraphs
        self.nouns = Counter()               # theme noun lemmas -> n
        self.dialogue_words = 0


class Sentence:
    """Tokens of one sentence, added one by one; heads are given as labels and resolved at the end."""

    def __init__(self):
        self.tok = []      # dicts: word, lemma, pos, tag, dep, head (label or index), label, ss
        self.mentions = []  # (start, end, coref, prop, cat) as token indexes in the sentence
        self.quote = None   # (start, end, speaker coref, mention (start, end) or None)

    def add(self, word, lemma=None, pos="X", tag="X", dep="dep", head="root", label=None, ss=None):
        self.tok.append({"word": word, "lemma": lemma or word.lower(), "pos": pos, "tag": tag, "dep": dep, "head": head, "label": label, "ss": ss})
        return len(self.tok) - 1

    def index(self, label):
        return next(i for i, t in enumerate(self.tok) if t["label"] == label)

    def resolve(self):
        heads = []
        for i, t in enumerate(self.tok):
            h = t["head"]
            heads.append(i if h == "self" else self.index(h) if isinstance(h, str) else h)
        return heads


class Builder:
    """Writes one book: turns sentences into the five export files and fills in the truth."""

    def __init__(self, bid, spec, seed):
        self.bid, self.spec, self.rng = bid, spec, random.Random(seed)
        self.truth = Truth()
        self.paragraphs: list[list[Sentence]] = []
        h, w, st, pl = spec["holmes"], spec["watson"], spec["street"], spec["place"]
        self.holmes, self.watson, self.street, self.place = h, w, st, pl
        self.first_person = spec["first_person"]

    # ---------- sentence templates ----------
    def _subject(self, s, who):
        """Add a subject to sentence s: returns (token index, coref). who: 'holmes', 'watson' or 'pron'."""
        if who == "pron":
            i = s.add("He", "he", "PRON", "PRP", "nsubj", "root", label="subj")
            s.mentions.append((i, i, self.holmes, "PRON", "PER"))
            return i, self.holmes
        if who == "narrator":
            i = s.add("I", "I", "PRON", "PRP", "nsubj", "root", label="subj")
            s.mentions.append((i, i, self.watson, "PRON", "PER"))
            return i, self.watson
        name = "Holmes" if who == "holmes" else "Watson"
        c = self.holmes if who == "holmes" else self.watson
        i = s.add(name, name, "PROPN", "NNP", "nsubj", "root", label="subj")
        s.mentions.append((i, i, c, "PROP", "PER"))
        return i, c

    def action(self, theme):
        """'Holmes looked at the stone .'"""
        s = Sentence()
        who = self.rng.choice(["narrator", "holmes", "pron"] if self.first_person else ["holmes", "watson", "pron"])
        _, coref = self._subject(s, who)
        past, lemma, ss = self.rng.choice(VERBS)
        s.add(past, lemma, "VERB", "VBD", "ROOT", "self", label="root", ss=ss)
        s.add("at", "at", "ADP", "IN", "prep", "root", label="prep")
        s.add("the", "the", "DET", "DT", "det", "noun")
        noun = self.rng.choice(THEMES[theme]["nouns"])
        s.add(noun, noun, "NOUN", "NN", "pobj", "prep", label="noun", ss="noun.artifact")
        s.add(".", ".", "PUNCT", ".", "punct", "root")
        self.truth.agent[coref][lemma] += 1
        self.truth.nouns[noun] += 1
        return s

    def possession(self, theme):
        """'Holmes took his pipe .' (a subject, a patient verb and a possessed noun)"""
        s = Sentence()
        _, coref = self._subject(s, "holmes")
        s.add("took", "take", "VERB", "VBD", "ROOT", "self", label="root", ss="verb.possession")
        i = s.add("his", "his", "PRON", "PRP$", "poss", "noun", label="his")
        s.mentions.append((i, i, self.holmes, "PRON", "PER"))
        noun = self.rng.choice(THEMES[theme]["nouns"])
        s.add(noun, noun, "NOUN", "NN", "dobj", "root", label="noun", ss="noun.artifact")
        s.add(".", ".", "PUNCT", ".", "punct", "root")
        self.truth.agent[self.holmes]["take"] += 1
        self.truth.poss[self.holmes][noun] += 1
        self.truth.nouns[noun] += 1
        return s

    def travel(self):
        """'Holmes and Watson walked to Baker Street .' (conjoined subjects and a place)"""
        s = Sentence()
        a = s.add("Holmes", "Holmes", "PROPN", "NNP", "nsubj", "root", label="subj")
        s.add("and", "and", "CCONJ", "CC", "cc", "subj")
        b = s.add("Watson", "Watson", "PROPN", "NNP", "conj", "subj")
        s.mentions += [(a, a, self.holmes, "PROP", "PER"), (b, b, self.watson, "PROP", "PER")]
        s.add("walked", "walk", "VERB", "VBD", "ROOT", "self", label="root", ss="verb.motion")
        s.add("to", "to", "ADP", "IN", "prep", "root", label="prep")
        p = s.add("Baker", "Baker", "PROPN", "NNP", "compound", "street")
        q = s.add("Street", "Street", "PROPN", "NNP", "pobj", "prep", label="street", ss="noun.location")
        s.mentions.append((p, q, self.street, "PROP", "LOC"))
        s.add(".", ".", "PUNCT", ".", "punct", "root")
        self.truth.agent[self.holmes]["walk"] += 1
        self.truth.agent[self.watson]["walk"] += 1   # the analyser lets a conjunct share the role of the first
        self.truth.prep[self.street]["walk to"] += 1
        return s

    def description(self, theme):
        """'The dark hill was lonely .' (no entities; modifiers)"""
        s = Sentence()
        s.add("The", "the", "DET", "DT", "det", "noun")
        adj = self.rng.choice(THEMES[theme]["adj"])
        s.add(adj, adj, "ADJ", "JJ", "amod", "noun")
        noun = self.rng.choice(THEMES[theme]["nouns"])
        s.add(noun, noun, "NOUN", "NN", "nsubj", "root", label="noun", ss="noun.object")
        s.add("was", "be", "AUX", "VBD", "ROOT", "self", label="root")
        adj2 = self.rng.choice(THEMES[theme]["adj"])
        s.add(adj2, adj2, "ADJ", "JJ", "acomp", "root")
        s.add(".", ".", "PUNCT", ".", "punct", "root")
        self.truth.nouns[noun] += 1
        return s

    def quote(self, theme, speaker="holmes"):
        """'" I see the stone , " said Holmes .' or with a vocative: '" Watson , look at the stone , " said Holmes .'"""
        s = Sentence()
        sp = self.holmes if speaker == "holmes" else self.watson
        other = self.watson if speaker == "holmes" else self.holmes
        other_name = "Watson" if speaker == "holmes" else "Holmes"
        noun = self.rng.choice(THEMES[theme]["nouns"])
        q0 = s.add(QUOTE_OPEN, QUOTE_OPEN, "PUNCT", "``", "punct", "said")
        voc = self.rng.random() < 0.4
        if voc:
            v = s.add(other_name, other_name, "PROPN", "NNP", "npadvmod", "look")
            s.mentions.append((v, v, other, "PROP", "PER"))
            s.add(",", ",", "PUNCT", ",", "punct", "look")
            s.add("look", "look", "VERB", "VB", "ccomp", "said", label="look", ss="verb.perception")
            s.add("at", "at", "ADP", "IN", "prep", "look", label="at")
            s.add("the", "the", "DET", "DT", "det", "noun")
            s.add(noun, noun, "NOUN", "NN", "pobj", "at", label="noun", ss="noun.artifact")
            words_in = 5
            self.truth.vocatives[(sp, other)] += 1
        else:
            i = s.add("I", "I", "PRON", "PRP", "nsubj", "see")
            s.mentions.append((i, i, sp, "PRON", "PER"))
            s.add("see", "see", "VERB", "VBP", "ccomp", "said", label="see", ss="verb.perception")
            s.add("the", "the", "DET", "DT", "det", "noun")
            s.add(noun, noun, "NOUN", "NN", "dobj", "see", label="noun", ss="noun.artifact")
            words_in = 4
            self.truth.agent[sp]["see"] += 1     # "I" is a mention and the subject of "see"
        s.add(",", ",", "PUNCT", ",", "punct", "said")
        q1 = s.add(QUOTE_CLOSE, QUOTE_CLOSE, "PUNCT", "''", "punct", "said")
        s.add("said", "say", "VERB", "VBD", "ROOT", "self", label="said", ss=SPEECH[2])
        name = "Holmes" if speaker == "holmes" else "Watson"
        m = s.add(name, name, "PROPN", "NNP", "nsubj", "said", label="who")
        s.mentions.append((m, m, sp, "PROP", "PER"))
        s.add(".", ".", "PUNCT", ".", "punct", "said")
        s.quote = (q0, q1, sp, (m, m))
        self.truth.quotes[sp] += 1
        self.truth.quote_words[sp] += words_in
        self.truth.dialogue_words += words_in
        self.truth.agent[sp]["say"] += 1
        self.truth.nouns[noun] += 1
        return s

    def heading(self, n):
        s = Sentence()
        s.add("CHAPTER", "chapter", "NOUN", "NN", "ROOT", "self", label="root")
        s.add(["I", "II", "III", "IV", "V"][n], "i", "NUM", "CD", "nummod", "root")
        s.add(".", ".", "PUNCT", ".", "punct", "root")
        return s

    # ---------- a whole book ----------
    def make(self):
        spec, rng = self.spec, self.rng
        themes = [t for t, w in spec["themes"].items() for _ in range(w)]
        per_chapter = max(1, spec["paras"] // spec["chapters"])
        n = 0
        for ch in range(spec["chapters"]):
            self.paragraphs.append([self.heading(ch)])
            self.truth.headings += 1
            for _ in range(per_chapter):
                theme = rng.choice(themes)
                self.truth.theme_paras[theme] += 1
                kinds = [lambda: self.action(theme), lambda: self.description(theme), lambda: self.quote(theme, "holmes"),
                         lambda: self.quote(theme, "watson"), lambda: self.possession(theme), lambda: self.travel()]
                weights = [3, 2, 3, 1, 1, 1]
                para = [rng.choices(kinds, weights)[0]() for _ in range(rng.randint(3, 5))]
                self.paragraphs.append(para)
                n += 1
        return self

    # ---------- files ----------
    def write(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        tokens, ents, quotes, sup, raw = [], [], [], [], []
        pos, doc = 0, 0                      # byte position and document token index
        sid = 0
        for pid, para in enumerate(self.paragraphs):
            self.truth.paragraphs += 1
            for s in para:
                heads = s.resolve()
                base = doc
                opening = False       # the previous token was an opening quote mark: no space after it
                for i, t in enumerate(s.tok):
                    w = t["word"]
                    closing = w == '"' and s.quote is not None and i == s.quote[1]
                    gap = 0 if pos == 0 else 1
                    if i and (w in PUNCT_NO_SPACE or closing or opening):
                        gap = 0
                    opening = w == '"' and s.quote is not None and i == s.quote[0]
                    onset = pos + gap
                    offset = onset + len(w)
                    pos = offset
                    raw.append(" " * gap + w)          # the "original text" .txt mirrors the byte offsets exactly
                    tokens.append("\t".join(str(x) for x in (pid, sid, i, doc, w, t["lemma"], onset, offset, t["pos"], t["tag"], t["dep"], base + heads[i],
                                                             "EVENT" if t["pos"] == "VERB" else "O")))
                    if t["pos"] not in ("PUNCT", "SPACE", "SYM") and w != '"':
                        self.truth.words += 1
                    self.truth.tokens += 1
                    if t["ss"]:
                        sup.append("\t".join(str(x) for x in (doc, doc, t["ss"], w)))
                    doc += 1
                for a, b, c, prop, cat in s.mentions:
                    text = " ".join(x["word"] for x in s.tok[a:b + 1])
                    ents.append("\t".join(str(x) for x in (c, base + a, base + b, prop, cat, text)))
                    self.truth.mentions[(c, prop)] += 1
                if s.quote:
                    q0, q1, spk, (ma, mb) = s.quote
                    quotes.append("\t".join(str(x) for x in (base + q0, base + q1, base + ma, base + mb, s.tok[ma]["word"], spk,
                                                             " ".join(x["word"] for x in s.tok[q0:q1 + 1]))))
                sid += 1
                self.truth.sentences += 1
        bid = self.bid
        head = "paragraph_ID\tsentence_ID\ttoken_ID_within_sentence\ttoken_ID_within_document\tword\tlemma\tbyte_onset\tbyte_offset\tPOS_tag\tfine_POS_tag\tdependency_relation\tsyntactic_head_ID\tevent"
        (folder / f"{bid}.tokens").write_text(head + "\n" + "\n".join(tokens) + "\n", encoding="utf-8")
        (folder / f"{bid}.entities").write_text("COREF\tstart_token\tend_token\tprop\tcat\ttext\n" + "\n".join(ents) + "\n", encoding="utf-8")
        (folder / f"{bid}.quotes").write_text("quote_start\tquote_end\tmention_start\tmention_end\tmention_phrase\tchar_id\tquote\n" + "\n".join(quotes) + "\n", encoding="utf-8")
        (folder / f"{bid}.supersense").write_text("start_token\tend_token\tsupersense_category\ttext\n" + "\n".join(sup) + "\n", encoding="utf-8")
        (folder / f"{bid}.txt").write_text("".join(raw), encoding="utf-8")   # the editor now copies this alongside the other files
        chars = [{"id": self.holmes, "name": "Holmes", "g": {"argmax": "he/him/his"}}, {"id": self.watson, "name": "Watson", "g": {"argmax": "he/him/his"}}]
        if "ryder" in self.spec:
            chars.append({"id": self.spec["ryder"], "g": {"argmax": "he/him/his"}})
        (folder / f"{bid}.book").write_text(json.dumps({"characters": chars}), encoding="utf-8")


def build(root: Path, seed: int = 7):
    """Write the corpus under root (one dated folder per book, like the editor's exports). -> {book id: Truth}"""
    truth = {}
    for k, (bid, spec) in enumerate(BOOKS.items()):
        b = Builder(bid, spec, seed + k).make()
        b.write(Path(root) / f"{bid}-{STAMPS[bid]}")
        truth[bid] = b.truth
    return truth


def many_specs(count, seed=11, paras=16):
    """`count` small book specs (b00, b01, …), each with its own coreference numbers, themes and size, so a library of them is not one book
    repeated: every fifth is told in the first person, and the characters' numbers differ from book to book."""
    rng = random.Random(seed)
    names = list(THEMES)
    specs = {}
    for k in range(count):
        base = 100 * (k % 7)
        specs[f"b{k:02d}"] = {
            "holmes": base + 1, "watson": base + 2, "street": base + 10, "place": base + 11,
            "themes": {t: rng.randint(1, 6) for t in rng.sample(names, 3)},
            "paras": paras + rng.randint(0, 8), "first_person": k % 5 == 0, "chapters": 2 + k % 3}
    return specs


def build_many(root: Path, count: int = 60, seed: int = 11):
    """Write `count` small books under root, one dated folder each, as `build` does, for tests of a large library
    -> {book id: Truth}. The books are generated, not copied, so none is the same as another."""
    truth = {}
    for k, (bid, spec) in enumerate(many_specs(count, seed).items()):
        b = Builder(bid, spec, seed * 1000 + k).make()
        b.write(Path(root) / f"{bid}-20260201-{k:06d}")
        truth[bid] = b.truth
    return truth
