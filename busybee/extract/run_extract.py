"""Run the extract stage over the corpus and write the rolling notebook files.

In the default segmented mode each finished segment notebook is checkpointed in
`extract_progress.jsonl` and reused if the stage is re-run after a crash; the file is deleted
once notebook.json and dropped.json are written. Meta-commentary entries are removed by
`filters.drop_meta_commentary` before notebook.json is written and logged in dropped.json.
Boilerplate pages (AGM notice, CSR, BRSR, governance report, ...) are dropped before windowing
(see boilerplate.py) and listed in `extract_skipped_pages.json`.
Entries whose citations were inferred (`rescue_citations`) are listed in extract_rescued.json.
"""

from pathlib import Path

from busybee.ingest.corpus_store import load_corpus
from busybee.llm.provider import Provider
from busybee.schema.documents import Chunk
from busybee.schema.facts import DroppedEntry, NotebookEntry
from busybee.schema.io import append_jsonl, write_json_atomic, write_models_atomic
from busybee.schema.run import ExtractMode, RunConfig

from .aids import ReadingAids
from .boilerplate import configured_titles, drop_boilerplate, enabled
from .filters import drop_meta_commentary
from .global_mode import extract_global
from .ordering import order_documents
from .per_document import extract_per_document
from .policy_focus import load_policy_focus
from .progress import PROGRESS_FILE
from .rescue_citations import RESCUED_FILE, rescued_records
from .segmented import extract_segmented

SKIPPED_FILE = "extract_skipped_pages.json"


def _chunks_by_doc(chunks: list[Chunk]) -> dict[str, list[Chunk]]:
    """Group corpus chunks per document in page reading order."""
    grouped: dict[str, list[Chunk]] = {}
    for chunk in chunks:
        grouped.setdefault(chunk.doc_id, []).append(chunk)
    for doc_chunks in grouped.values():
        doc_chunks.sort(key=lambda chunk: (chunk.page_no, chunk.index_in_page))
    return grouped


def _is_global(mode: ExtractMode | str) -> bool:
    """Accept either the enum or its string value when choosing the extract mode."""
    return ExtractMode(mode) is ExtractMode.global_


async def run_extract(
    workspace_dir: str | Path,
    cfg: RunConfig,
    provider: Provider,
    banks_dir: str | Path | None = None,
) -> list[NotebookEntry]:
    """Extract notebook entries and write notebook.jsonl, notebook.json, and dropped.json.

    With `banks_dir`, the bank's policy sets the importance of each entry (see policy_focus.py).
    """
    aids = ReadingAids(focus=load_policy_focus(banks_dir, cfg.bank_id))
    workspace = Path(workspace_dir)
    corpus = load_corpus(workspace)
    documents = order_documents(corpus.documents)
    chunks_by_doc = _chunks_by_doc(corpus.chunks)
    skipped: dict[str, list[int]] = {}
    if enabled():
        chunks_by_doc, skipped = drop_boilerplate(documents, chunks_by_doc, configured_titles())
    write_json_atomic(workspace / SKIPPED_FILE, skipped)
    chunks_by_id = {chunk.chunk_id: chunk for chunk in corpus.chunks}

    notebook_path = workspace / "notebook.jsonl"
    notebook_path.parent.mkdir(parents=True, exist_ok=True)
    notebook_path.write_text("", encoding="utf-8")

    def append_window(_window_no: int, entries: list[NotebookEntry]) -> None:
        for entry in entries:
            append_jsonl(notebook_path, entry)

    dropped: list[DroppedEntry] = []
    if _is_global(cfg.extract_mode):
        entries = await extract_global(
            documents,
            chunks_by_doc,
            cfg,
            provider,
            chunks_by_id=chunks_by_id,
            dropped=dropped,
            on_window=append_window,
        )
    elif ExtractMode(cfg.extract_mode) is ExtractMode.segmented:
        entries = await extract_segmented(
            documents,
            chunks_by_doc,
            cfg,
            provider,
            chunks_by_id=chunks_by_id,
            dropped=dropped,
            progress_path=workspace / PROGRESS_FILE,
            aids=aids,
        )
        for entry in entries:
            append_jsonl(notebook_path, entry)
    else:
        entries = await extract_per_document(
            documents,
            chunks_by_doc,
            cfg,
            provider,
            chunks_by_id=chunks_by_id,
            dropped=dropped,
            on_window=append_window,
        )

    entries, filtered = drop_meta_commentary(entries)
    dropped.extend(filtered)
    write_models_atomic(workspace / "notebook.json", entries)
    write_models_atomic(workspace / "dropped.json", dropped)
    write_json_atomic(workspace / RESCUED_FILE, rescued_records(entries))
    (workspace / PROGRESS_FILE).unlink(missing_ok=True)
    return entries
