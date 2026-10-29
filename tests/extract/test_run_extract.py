"""Tests for the run_extract files written to the workspace."""

import json
from pathlib import Path

from busybee.extract.run_extract import run_extract
from busybee.llm import MockProvider
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.facts import DroppedEntry, NotebookEntry
from busybee.schema.io import append_jsonl, read_models, write_models_atomic
from busybee.schema.run import RunConfig


def config(tmp_path: Path, **overrides) -> RunConfig:
    values = {
        "run_id": "test-run",
        "docs_dir": tmp_path / "docs",
        "bank_id": "bank",
        "out_dir": tmp_path / "out",
        "workspace_dir": tmp_path / "workspace",
        "window_tokens": 10_000,
        "notebook_budget_tokens": 10_000,
    }
    values.update(overrides)
    return RunConfig(**values)


def write_corpus(workspace: Path, documents: list[Document], chunks: list[Chunk]) -> None:
    corpus = workspace / "corpus"
    write_models_atomic(corpus / "documents.json", documents)
    for chunk in chunks:
        append_jsonl(corpus / "chunks.jsonl", chunk)


def response(statement: str, chunk_id: str) -> str:
    return json.dumps(
        {
            "entries": [
                {
                    "statement": statement,
                    "chunk_ids": [chunk_id],
                    "category": "revenue",
                    "kind": "number",
                    "importance": 4,
                }
            ]
        }
    )


async def test_run_extract_writes_the_notebook_and_dropped_files(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    doc = Document(
        doc_id="D1",
        title="Annual Report",
        kind=DocumentKind.annual_report,
        source_path="annual.md",
    )
    item = Chunk(
        chunk_id="D1:p1:c0",
        doc_id="D1",
        page_no=1,
        index_in_page=0,
        text="Revenue was INR 931.2 crore in FY25.",
    )
    write_corpus(workspace, [doc], [item])
    provider = MockProvider(
        {"extract": [response("Revenue was INR 931.2 crore in FY25.", item.chunk_id)]}
    )

    entries = await run_extract(workspace, config(tmp_path), provider)

    assert [entry.entry_id for entry in entries] == ["D1:E001"]
    notebook_lines = (workspace / "notebook.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(notebook_lines) == 1
    assert NotebookEntry.model_validate_json(notebook_lines[0]) == entries[0]
    assert read_models(workspace / "notebook.json", NotebookEntry) == entries
    assert read_models(workspace / "dropped.json", DroppedEntry) == []


async def test_run_extract_records_entries_with_no_valid_citation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    doc = Document(
        doc_id="D1",
        title="Annual Report",
        kind=DocumentKind.annual_report,
        source_path="annual.md",
    )
    item = Chunk(
        chunk_id="D1:p1:c0",
        doc_id="D1",
        page_no=1,
        index_in_page=0,
        text="Revenue was INR 931.2 crore in FY25.",
    )
    write_corpus(workspace, [doc], [item])
    provider = MockProvider({"extract": [response("An unsupported statement.", "D9:p9:c9")]})

    entries = await run_extract(workspace, config(tmp_path), provider)

    assert entries == []
    assert (workspace / "notebook.jsonl").read_text(encoding="utf-8") == ""
    assert read_models(workspace / "notebook.json", NotebookEntry) == []
    dropped = read_models(workspace / "dropped.json", DroppedEntry)
    assert len(dropped) == 1
    assert dropped[0].stage == "extract"
    assert "D9:p9:c9" in dropped[0].reason
