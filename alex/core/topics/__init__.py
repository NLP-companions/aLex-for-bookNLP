"""Topic modelling over the selected books.

    model.py    settings, documents, words, fitting, quality figures, `build`
    store.py    where fitted models are kept (one JSON file each)
    page.py     the model overview and the parts of a topic's page
    compare.py  comparing topics: map, side by side, grids
    uses.py     topics in Arcs, on entity pages and in the text view
    notes.py    the explanatory texts shown in the interface

The names below are the package's public interface; the browser reaches them through api/topics.py.
"""
from .compare import compare_map, compare_pair, grid_groups, grid_items, model_topics
from .errors import TopicError
from .model import DEFAULTS, POS_CHOICES, build, clean_cfg, scan
from .notes import COMPARE_NOTES, NOTES, PAGE_NOTES
from .page import (overview, part_entities, part_groups, part_passages, part_speech, part_where, part_words)
from .store import configure, delete, list_models, load, rename
from .uses import arc_series, entity_topics, reader_layer

__all__ = [
    "COMPARE_NOTES", "DEFAULTS", "NOTES", "PAGE_NOTES", "POS_CHOICES", "TopicError", "arc_series", "build", "clean_cfg", "compare_map",
    "compare_pair", "configure", "delete", "entity_topics", "grid_groups", "grid_items", "list_models", "load", "model_topics",
    "overview", "part_entities", "part_groups", "part_passages", "part_speech", "part_where", "part_words", "reader_layer", "rename", "scan",
]
