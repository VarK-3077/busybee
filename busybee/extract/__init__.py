"""Read documents with a rolling notebook and extract candidate facts."""

from .condense import (
    MergeOutput,
    condense_entries,
    condense_if_needed,
    merge_groups,
    should_condense,
)
from .condensed import condense_entry, condense_notebook
from .global_mode import extract_corpus_global, extract_global
from .notebook import add_entries, apply_supersedes, merge_notebooks, renumber
from .ordering import document_order_key, order_documents
from .per_document import (
    extract_corpus_per_document,
    extract_document,
    extract_per_document,
    extract_window_list,
    extract_windows,
)
from .prompts import (
    SYSTEM_PROMPT,
    NewEntry,
    RecordDraft,
    WindowOutput,
    build_user_prompt,
    build_window_prompt,
    system_prompt,
)
from .run_extract import run_extract
from .segmented import (
    extract_document_segmented,
    extract_segmented,
    segment_count,
    split_segments,
)
from .windows import chunk_window_text, make_windows, window_text

__all__ = [
    "MergeOutput",
    "NewEntry",
    "RecordDraft",
    "SYSTEM_PROMPT",
    "WindowOutput",
    "add_entries",
    "apply_supersedes",
    "build_user_prompt",
    "build_window_prompt",
    "chunk_window_text",
    "condense_entries",
    "condense_entry",
    "condense_if_needed",
    "condense_notebook",
    "document_order_key",
    "extract_corpus_global",
    "extract_corpus_per_document",
    "extract_document",
    "extract_global",
    "extract_document_segmented",
    "extract_per_document",
    "extract_segmented",
    "extract_window_list",
    "extract_windows",
    "make_windows",
    "merge_groups",
    "merge_notebooks",
    "order_documents",
    "renumber",
    "run_extract",
    "segment_count",
    "should_condense",
    "split_segments",
    "system_prompt",
    "window_text",
]
