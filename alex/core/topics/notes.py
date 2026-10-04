"""The explanatory texts shown under "How this is calculated" on the topic pages.

NOTES        fitting a model and choosing its settings
PAGE_NOTES   the parts of a topic's page (words, where, entities, speech, groups)
COMPARE_NOTES  comparing topics (map, side by side, grids)

They are sent to the browser with the library (see api/library.py), prefixed "page_" / "cmp_".
"""

NOTES = {
    "model": ("A topic model finds groups of words that tend to occur together and says how much of each document belongs to each group. "
              "The books are cut into documents, the words you choose are counted in each, and the model is fitted with a fixed seed so results repeat. "
              "Topics on fiction are usually settings, activities, subject matter and registers rather than themes; treat them as a map to explore and "
              "question, not as findings. What comes out depends on the document size, the words kept and the number of topics you choose."),
    "documents": ("Chunks of about N words end at a sentence boundary. Paragraph groups take a fixed number of paragraphs. Chapters or slices use the "
                  "setting under Arcs and style. Whole books give one document per book, which is only useful with many books."),
    "words": ("Only words of the chosen parts of speech are kept. Names can be removed using BookNLP's mentions, which is more precise than a name list: "
              "every token inside a proper-name mention (or in any person mention, or any entity mention) is dropped. Words are lowercased; "
              "lemmas merge forms such as “looked” and “looking”. Words in fewer documents than the minimum, or in more than the maximum share of "
              "documents, are removed, and so are the built-in general words (thing, way, say, go…) unless you switch them off."),
    "methods": ("LDA (latent Dirichlet allocation, run in batch mode with scikit-learn) is the standard probabilistic model. NMF (non-negative matrix "
                "factorisation of tf–idf weights) is usually crisper on small collections, so it's the default. Both give each document a share of each topic."),
    "metrics": ("Coherence is the mean normalised PMI of the ten top words' co-occurrence in documents (from −1 to 1; higher is better). Diversity is the "
                "share of distinct words among all topics' top ten. Stability re-runs the model with other seeds and counts how often a similar topic "
                "(matched one to one, sharing at least 8 of its top 20 words) comes back. With few documents expect low stability: a topic "
                "that recurs in only some runs may not be a robust pattern."),
    "prevalence": "A topic's share is its average weight across documents, weighted by the number of words kept in each.",
}

PAGE_NOTES = {
    "words": ("Words are ranked by relevance (Sievert & Shirley 2014): λ × log p(word | topic) + (1 − λ) × log of how much more probable the word is in the topic "
              "than in the model overall. At λ = 1 the most frequent words come first; lower values favour words that are exclusive to the topic. Only the "
              "300 most probable words are ranked. Exclusive share is the part of the word's weight in the model that belongs to this topic."),
    "where": ("Each document has a share of this topic. The strip shades every document by its share, darker meaning more, on a scale that runs from 0 to the "
              "topic's highest share anywhere. The arc puts each document in the chapter or slice that holds its middle and shows the topic's share of the words there. "
              "In the table, a book's share is the topic's average share over its documents, weighted by the words kept. The test compares the topic's share "
              "in the book's documents with that in the other books' (Mann–Whitney U on documents). Neighbouring documents are not independent, so treat p as a guide."),
    "entities": ("Each document counts as “topic text” to the extent of its share of the topic. For each entity the analyser compares mentions per 1,000 words in "
                 "topic text with mentions per 1,000 words in the rest (a document with a 30% share counts 30% towards topic text and 70% towards the rest), "
                 "and scores the difference with a log-likelihood. The score ranks entities; it is not a significance test, because the weights are not independent "
                 "observations. Only entities with enough mentions in the model's documents are listed."),
    "speech": ("The share of dialogue is taken over each document's words inside quotes. For speakers, the same comparison as for entities is made with words spoken "
               "per 1,000 words of dialogue, and for narrators with narration words per 1,000 words of narration, using the narrators set in the analyser. "
               "The topic's own vocabulary is its 30 most probable words wherever they appear in the model's documents, in dialogue or in narration."),
    "groups": ("The share is the topic's average over the documents in each group, weighted by the words kept, against its share in the whole model. A book with several "
               "tags counts in each of them. A group's p compares its documents' shares with the other groups' (Mann–Whitney U)."),
}

COMPARE_NOTES = {
    "map": ("Two topics are similar in one of two ways. By shared words: the cosine similarity of their word weights (0 to 1), which is high when they "
            "give weight to the same words. By appearing together: the correlation, over documents, of their shares (−1 to 1), which is high when they rise "
            "and fall in the same stretches of text, even if their words differ. The map places topics by classical multidimensional scaling of 1 − similarity, "
            "so nearer means more similar; the two axes keep only part of the picture, as the percentages show. The lines join topics whose similarity is at "
            "least the value you set. The tree joins the most similar topics first (average linkage)."),
    "pair": ("Shared words are those with weight in both topics, ranked by the smaller of the two. A word is exclusive to a topic when it has more weight there, "
             "ranked by weight × log(ratio) so that both frequent and lopsided words count. Entities and speakers are compared by their rate per 1,000 words "
             "(entities) or per 1,000 dialogue words (speakers) in text weighted by one topic against text weighted by the other, scored with a log-likelihood. "
             "Positive means more in the first topic. The score ranks; it is not a significance test, because a document counts towards both topics."),
    "grid_groups": ("Each cell is the topic's average share over the documents of the book (or group), weighted by the words kept. “Against all” divides that "
                    "by the topic's share in the whole model, so × 2 means twice as much as usual."),
    "grid_items": ("Each document's topic shares add up to 100%, so every entity's mentions (or speaker's words) divide among the topics: the cell is the share of "
                   "the item's mentions that fall in text weighted by that topic. “Against topic average” divides by the topic's share of the whole model, so "
                   "× 2 means the item is found in that topic's text twice as often as chance."),
}
