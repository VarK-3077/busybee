"""Tests for sequential per-document extraction, supersedes, and global mode."""

import json
from pathlib import Path

from busybee.extract.global_mode import extract_global
from busybee.extract.per_document import extract_document, extract_per_document
from busybee.llm import MockProvider, count_tokens
from busybee.schema.documents import Chunk, Document, DocumentKind
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


def chunk(chunk_id: str, text: str) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id=chunk_id.split(":")[0],
        page_no=1,
        index_in_page=int(chunk_id.rsplit("c", 1)[1]),
        text=text,
    )


def response(statement: str, chunk_id: str, **fields) -> str:
    payload = {
        "entries": [
            {
                "statement": statement,
                "chunk_ids": [chunk_id],
                "category": fields.get("category", "revenue"),
                "kind": fields.get("kind", "number"),
                "importance": fields.get("importance", 4),
                "supersedes": fields.get("supersedes"),
            }
        ]
    }
    return json.dumps(payload)


async def test_windows_produce_correctly_numbered_and_cited_entries(tmp_path: Path) -> None:
    first = chunk("D1:p1:c0", "Revenue was INR 931.2 crore in FY25.")
    second = chunk("D1:p2:c0", "Net debt was INR 352.0 crore in FY25.")
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    provider = MockProvider(
        {
            "extract": [
                response("Revenue was INR 931.2 crore in FY25.", first.chunk_id),
                response(
                    "Net debt was INR 352.0 crore in FY25.",
                    second.chunk_id,
                    category="debt_leverage",
                    importance=5,
                ),
            ]
        }
    )

    entries = await extract_document(
        doc,
        [first, second],
        config(tmp_path, window_tokens=count_tokens(first.text)),
        provider,
    )

    assert [entry.entry_id for entry in entries] == ["D1:E001", "D1:E002"]
    assert [entry.window_no for entry in entries] == [1, 2]
    assert [entry.citations[0].chunk_id for entry in entries] == [
        "D1:p1:c0",
        "D1:p2:c0",
    ]
    assert [entry.citations[0].page_no for entry in entries] == [1, 1]
    assert [call.task for call in provider.calls] == [
        "extract",
        "extract",
    ]


async def test_a_later_window_can_supersede_an_earlier_entry(tmp_path: Path) -> None:
    first = chunk("D1:p1:c0", "Revenue was INR 931.2 crore in FY25.")
    second = chunk("D1:p2:c0", "Revenue was restated to INR 941.0 crore in FY25.")
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    provider = MockProvider(
        {
            "extract": [
                response("Revenue was INR 931.2 crore in FY25.", first.chunk_id),
                response(
                    "Revenue was restated to INR 941.0 crore in FY25.",
                    second.chunk_id,
                    supersedes="D1:E001",
                ),
            ]
        }
    )

    entries = await extract_document(
        doc,
        [first, second],
        config(tmp_path, window_tokens=count_tokens(first.text)),
        provider,
    )

    assert len(entries) == 1
    assert entries[0].entry_id == "D1:E002"
    assert entries[0].supersedes == "D1:E001"
    assert entries[0].citations[0].chunk_id == "D1:p2:c0"


async def test_per_document_merges_in_document_order(tmp_path: Path) -> None:
    first = chunk("D1:p1:c0", "Revenue was INR 931.2 crore in FY25.")
    second = chunk("D2:p1:c0", "Net debt was INR 352.0 crore in FY25.")
    documents = [
        Document(doc_id="D1", title="First", kind=DocumentKind.annual_report),
        Document(doc_id="D2", title="Second", kind=DocumentKind.covenant),
    ]
    provider = MockProvider(
        {
            "extract": [
                response("Revenue was INR 931.2 crore in FY25.", first.chunk_id),
                response(
                    "Net debt was INR 352.0 crore in FY25.",
                    second.chunk_id,
                    category="debt_leverage",
                ),
            ]
        }
    )

    entries = await extract_per_document(
        documents,
        {"D1": [first], "D2": [second]},
        config(tmp_path),
        provider,
    )

    assert [entry.doc_id for entry in entries] == ["D1", "D2"]
    assert [entry.entry_id for entry in entries] == ["D1:E001", "D2:E001"]
    assert [entry.statement for entry in entries] == [
        "Revenue was INR 931.2 crore in FY25.",
        "Net debt was INR 352.0 crore in FY25.",
    ]


async def test_global_mode_reads_the_whole_corpus_as_one_stream(tmp_path: Path) -> None:
    first = chunk("D1:p1:c0", "Revenue was INR 931.2 crore in FY25.")
    second = chunk("D2:p1:c0", "Net debt was INR 352.0 crore in FY25.")
    documents = [
        Document(doc_id="D1", title="First", kind=DocumentKind.annual_report),
        Document(doc_id="D2", title="Second", kind=DocumentKind.covenant),
    ]
    payload = json.dumps(
        {
            "entries": [
                {
                    "statement": "Revenue was INR 931.2 crore in FY25.",
                    "chunk_ids": [first.chunk_id],
                    "category": "revenue",
                    "kind": "number",
                    "importance": 4,
                },
                {
                    "statement": "Net debt was INR 352.0 crore in FY25.",
                    "chunk_ids": [second.chunk_id],
                    "category": "debt_leverage",
                    "kind": "number",
                    "importance": 5,
                },
            ]
        }
    )
    provider = MockProvider({"extract": [payload]})

    entries = await extract_global(
        documents,
        {"D1": [first], "D2": [second]},
        config(tmp_path),
        provider,
    )

    assert [entry.entry_id for entry in entries] == ["D1:E001", "D2:E001"]
    assert [entry.doc_id for entry in entries] == ["D1", "D2"]
    assert len(provider.calls) == 1


async def test_extraction_condenses_when_the_notebook_exceeds_the_budget(
    tmp_path: Path,
) -> None:
    first = chunk("D1:p1:c0", "Revenue was INR 931.2 crore in FY25.")
    second = chunk("D1:p2:c0", "Revenue was INR 931.2 crore in FY25.")
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    provider = MockProvider(
        {
            "extract": [
                response("Revenue was INR 931.2 crore in FY25.", first.chunk_id),
                response("Revenue was INR 931.2 crore in FY25.", second.chunk_id),
            ],
            "condense": [json.dumps({"groups": [["D1:E001", "D1:E002"]]})],
        }
    )

    entries = await extract_document(
        doc,
        [first, second],
        config(
            tmp_path,
            window_tokens=count_tokens(first.text),
            notebook_budget_tokens=0,
        ),
        provider,
    )

    assert [call.task for call in provider.calls] == [
        "extract",
        "condense",
        "extract",
        "condense",
    ]
    assert len(entries) == 1
    assert [citation.chunk_id for citation in entries[0].citations] == [
        "D1:p1:c0",
        "D1:p2:c0",
    ]


async def test_stale_supersedes_link_is_not_reported_in_later_windows(
    tmp_path: Path, caplog
) -> None:
    import logging

    chunks = [
        chunk("D1:p1:c0", "Revenue was INR 931.2 crore in FY25."),
        chunk("D1:p2:c0", "Revenue was restated to INR 941.0 crore in FY25."),
        chunk("D1:p3:c0", "Net debt was INR 352.0 crore in FY25."),
        chunk("D1:p4:c0", "Cash was INR 20.0 crore in FY25."),
    ]
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    provider = MockProvider(
        {
            "extract": [
                response("Revenue was INR 931.2 crore in FY25.", chunks[0].chunk_id),
                response(
                    "Revenue was restated to INR 941.0 crore in FY25.",
                    chunks[1].chunk_id,
                    supersedes="D1:E001",
                ),
                response("Net debt was INR 352.0 crore in FY25.", chunks[2].chunk_id),
                response("Cash was INR 20.0 crore in FY25.", chunks[3].chunk_id),
            ]
        }
    )
    with caplog.at_level(logging.WARNING):
        entries = await extract_document(
            doc, chunks, config(tmp_path, window_tokens=count_tokens(chunks[0].text)), provider
        )

    assert [e.entry_id for e in entries] == ["D1:E002", "D1:E003", "D1:E004"]
    assert not [r for r in caplog.records if "supersedes unknown" in r.getMessage()]


async def test_extract_calls_pass_an_explicit_output_budget(tmp_path: Path) -> None:
    provider = MockProvider({"extract": [response("Revenue was 5.", "D1:p1:c0")]})
    await extract_document(
        Document(doc_id="D1", title="T", kind=DocumentKind.other),
        [chunk("D1:p1:c0", "Revenue was 5.")],
        config(tmp_path, window_tokens=10_000),
        provider,
    )
    extract_calls = [call for call in provider.calls if call["task"] == "extract"]
    assert extract_calls[0]["max_tokens"] == 8000
    from busybee.extract.per_document import extract_max_tokens

    assert extract_max_tokens(100_000) == 16000


async def test_truncated_reply_splits_the_window_and_retries_each_half(tmp_path: Path) -> None:
    chunks = [chunk("D1:p1:c0", "Revenue was 5."), chunk("D1:p1:c1", "Profit was 2.")]
    truncated = '{"entries": [{"statement": "' + "word " * 3000
    replies = [
        truncated,
        response("Revenue was 5.", "D1:p1:c0"),
        response("Profit was 2.", "D1:p1:c1", category="profitability"),
    ]
    provider = MockProvider({"extract": replies})
    entries = await extract_document(
        Document(doc_id="D1", title="T", kind=DocumentKind.other),
        chunks,
        config(tmp_path, window_tokens=10, notebook_budget_tokens=10_000),
        provider,
    )
    # window_tokens=10 gives a 3005-token budget; the long reply exceeds 95% of it.
    assert sorted(entry.statement for entry in entries) == ["Profit was 2.", "Revenue was 5."]
    assert len([c for c in provider.calls if c["task"] == "extract"]) >= 3
