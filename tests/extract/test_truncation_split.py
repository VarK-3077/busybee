"""Truncated extract replies are split in halves, recursively, and every half is kept."""

import json
import re
from pathlib import Path

from busybee.extract.per_document import extract_document
from busybee.llm import Message, MockProvider
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.facts import DroppedEntry
from busybee.schema.run import RunConfig

CUT = '{"entries": [{"statement": "Cut off mid reply", "chunk_ids": ["D1:p1:c0"], "kind":'


def config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        run_id="r",
        docs_dir=tmp_path / "docs",
        bank_id="bank",
        out_dir=tmp_path / "out",
        workspace_dir=tmp_path / "workspace",
        window_tokens=10_000,
        notebook_budget_tokens=10_000,
    )


def chunks(count: int) -> list[Chunk]:
    return [
        Chunk(
            chunk_id=f"D1:p1:c{i}",
            doc_id="D1",
            page_no=1,
            index_in_page=i,
            text=f"Fact number {i} is {i}00.",
        )
        for i in range(count)
    ]


def reply(chunk_id: str) -> str:
    number = chunk_id.rsplit("c", 1)[1]
    entry = {
        "statement": f"Fact number {number} is {number}00.",
        "chunk_ids": [chunk_id],
        "category": "revenue",
        "kind": "number",
        "importance": 4,
    }
    return json.dumps({"entries": [entry]})


def shown_ids(messages: list[Message]) -> list[str]:
    return re.findall(r"^\[(D1:p1:c\d+)\]$", messages[-1].content, flags=re.MULTILINE)


async def read(count: int, tmp_path: Path, responder, dropped=None):
    provider = MockProvider(responder)
    entries = await extract_document(
        Document(doc_id="D1", title="T", kind=DocumentKind.other),
        chunks(count),
        config(tmp_path),
        provider,
        dropped=dropped,
    )
    return entries, [c for c in provider.calls if c["task"] == "extract"]


async def test_truncated_first_reply_splits_and_keeps_both_halves(tmp_path: Path) -> None:
    def responder(messages: list[Message], task: str) -> str:
        ids = shown_ids(messages)
        if task != "extract":
            return "{}"
        return CUT if len(ids) > 1 else reply(ids[0])

    entries, calls = await read(2, tmp_path, responder)

    assert sorted(e.statement for e in entries) == [
        "Fact number 0 is 000.",
        "Fact number 1 is 100.",
    ]
    assert len(calls) == 3


async def test_splitting_recurses_down_to_single_chunks(tmp_path: Path) -> None:
    def responder(messages: list[Message], task: str) -> str:
        ids = shown_ids(messages)
        if task != "extract":
            return "{}"
        return CUT if len(ids) > 1 else reply(ids[0])

    entries, calls = await read(4, tmp_path, responder)

    assert len(entries) == 4
    assert len(calls) == 1 + 2 + 4


async def test_single_chunk_that_truncates_is_reread_limited_and_logged(tmp_path: Path) -> None:
    def responder(messages: list[Message], task: str) -> str:
        if task != "extract":
            return "{}"
        return reply("D1:p1:c0") if "at most 25 entries" in messages[-1].content else CUT

    dropped: list[DroppedEntry] = []
    entries, calls = await read(1, tmp_path, responder, dropped)

    assert [e.statement for e in entries] == ["Fact number 0 is 000."]
    assert len(calls) == 2
    assert [d.stage for d in dropped] == ["extract.truncated"]


async def test_limited_reread_that_still_truncates_is_logged_not_silent(tmp_path: Path) -> None:
    def responder(messages: list[Message], task: str) -> str:
        return CUT if task == "extract" else "{}"

    dropped: list[DroppedEntry] = []
    entries, _ = await read(1, tmp_path, responder, dropped)

    assert entries == []
    assert [d.stage for d in dropped] == ["extract.truncated"]
