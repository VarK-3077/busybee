"""Meta-commentary entries are dropped with stage extract.filter and written to dropped.json."""

import json
from pathlib import Path

from busybee.extract.filters import drop_meta_commentary, is_meta_commentary
from busybee.extract.prompts import SYSTEM_PROMPT
from busybee.extract.run_extract import run_extract
from busybee.llm import MockProvider
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.facts import NotebookEntry
from busybee.schema.io import append_jsonl, write_models_atomic
from busybee.schema.run import RunConfig


def entry(entry_id: str, statement: str) -> NotebookEntry:
    return NotebookEntry(entry_id=entry_id, statement=statement)


def test_meta_patterns_match() -> None:
    for text in (
        "The provided passages do not mention covenants.",
        "The passage lists no litigation.",
        "The document does not mention any rating.",
        "Promoter holding is not specified in the filing.",
        "No information is available on debt.",
        "No information available on debt.",
    ):
        assert is_meta_commentary(text), text
    assert not is_meta_commentary("Revenue was Rs 931.2 crore in FY25.")


def test_drop_meta_commentary_splits_entries() -> None:
    kept, dropped = drop_meta_commentary(
        [entry("D1:E1", "Revenue was Rs 5 crore."), entry("D1:E2", "No information is available.")]
    )
    assert [e.entry_id for e in kept] == ["D1:E1"]
    assert dropped[0].stage == "extract.filter" and dropped[0].entry.entry_id == "D1:E2"


def test_prompt_forbids_comparisons_substitution_and_meta() -> None:
    text = SYSTEM_PROMPT.casefold()
    assert "comparisons" in text and "causal" in text
    assert "swap" in text and "meta-commentary" in text


async def test_run_extract_logs_filtered_entries(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    doc = Document(doc_id="D1", title="AR", kind=DocumentKind.annual_report, source_path="a.md")
    chunk = Chunk(chunk_id="D1:p1:c0", doc_id="D1", page_no=1, index_in_page=0, text="Revenue 5.")
    write_models_atomic(workspace / "corpus" / "documents.json", [doc])
    append_jsonl(workspace / "corpus" / "chunks.jsonl", chunk)
    reply = json.dumps(
        {
            "entries": [
                {"statement": "Revenue was 5.", "chunk_ids": ["D1:p1:c0"]},
                {
                    "statement": "The provided passages do not mention debt.",
                    "chunk_ids": ["D1:p1:c0"],
                },
            ]
        }
    )
    cfg = RunConfig(
        run_id="r",
        docs_dir=tmp_path / "docs",
        bank_id="b",
        out_dir=tmp_path / "out",
        workspace_dir=workspace,
        window_tokens=10_000,
        notebook_budget_tokens=10_000,
    )
    entries = await run_extract(workspace, cfg, MockProvider(reply))
    assert [e.statement for e in entries] == ["Revenue was 5."]
    dropped = json.loads((workspace / "dropped.json").read_text())
    assert [d["stage"] for d in dropped] == ["extract.filter"]
