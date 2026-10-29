"""Tests for segmented extraction: segment arithmetic, ordering, ids, supersedes, prompts."""

import asyncio
import json
import re
from pathlib import Path

import pytest

from busybee.extract.per_document import extract_per_document
from busybee.extract.run_extract import run_extract
from busybee.extract.segmented import extract_segmented, segment_count, split_segments
from busybee.llm import MockProvider, count_tokens, limiter
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.io import append_jsonl, write_models_atomic
from busybee.schema.run import ExtractMode, RunConfig

TEXT = "Revenue was INR 931.2 crore in FY25."


def config(tmp_path: Path, **overrides) -> RunConfig:
    values = {
        "run_id": "test-run",
        "docs_dir": tmp_path / "docs",
        "bank_id": "bank",
        "out_dir": tmp_path / "out",
        "workspace_dir": tmp_path / "workspace",
        "window_tokens": count_tokens(TEXT),
        "notebook_budget_tokens": 10_000,
        "concurrency": 4,
        "segment_min_windows": 6,
    }
    values.update(overrides)
    return RunConfig(**values)


def chunks_for(doc_id: str, pages: int) -> list[Chunk]:
    return [
        Chunk(chunk_id=f"{doc_id}:p{p}:c0", doc_id=doc_id, page_no=p, index_in_page=0, text=TEXT)
        for p in range(1, pages + 1)
    ]


def echo_provider(supersede: dict[str, str] | None = None) -> MockProvider:
    """Answer each extract call with one entry citing the single chunk shown in the prompt."""
    supersede = supersede or {}

    def reply(messages, task: str) -> str:
        prompt = messages[-1].content
        chunk_id = re.search(r"New chunks for window \d+:\n\[([^\]]+)\]", prompt).group(1)
        return json.dumps(
            {
                "entries": [
                    {
                        "statement": f"Fact from {chunk_id}.",
                        "chunk_ids": [chunk_id],
                        "supersedes": supersede.get(chunk_id),
                    }
                ]
            }
        )

    return MockProvider(reply)


def test_segment_arithmetic() -> None:
    assert segment_count(0, 4, 6) == 0
    assert segment_count(1, 4, 6) == 1
    assert segment_count(7, 4, 6) == 1
    assert segment_count(12, 4, 6) == 2
    assert segment_count(40, 4, 6) == 4
    assert segment_count(80, 4, 6) == 4
    assert [len(part) for part in split_segments(list(range(40)), 4)] == [10, 10, 10, 10]
    assert [len(part) for part in split_segments(list(range(42)), 4)] == [11, 11, 10, 10]
    assert split_segments(list(range(5)), 1) == [[0, 1, 2, 3, 4]]


async def test_concurrent_segments_merge_in_document_order(tmp_path: Path) -> None:
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    chunks = chunks_for("D1", 24)
    provider = echo_provider()

    entries = await extract_segmented(
        [doc], {"D1": chunks}, config(tmp_path, segment_min_windows=3), provider
    )

    assert [e.entry_id for e in entries] == [f"D1:E{n:03d}" for n in range(1, 25)]
    assert [e.window_no for e in entries] == list(range(1, 25))
    assert [e.citations[0].chunk_id for e in entries] == [c.chunk_id for c in chunks]
    prompts = [call.messages[-1].content for call in provider.calls]
    assert any("Reading position: pages 1–6 of 24" in p for p in prompts)
    assert any("pages 19–24 of 24" in p for p in prompts)


async def test_supersede_inside_a_segment_still_works(tmp_path: Path) -> None:
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    chunks = chunks_for("D1", 6)
    provider = echo_provider({"D1:p3:c0": "D1:E001", "D1:p5:c0": "E001"})

    entries = await extract_segmented(
        [doc],
        {"D1": chunks},
        config(tmp_path, concurrency=2, segment_min_windows=3),
        provider,
    )

    assert [e.citations[0].chunk_id for e in entries] == [
        "D1:p2:c0",
        "D1:p3:c0",
        "D1:p5:c0",
        "D1:p6:c0",
    ]
    assert [e.entry_id for e in entries] == [f"D1:E{n:03d}" for n in range(1, 5)]
    assert [e.window_no for e in entries] == [2, 3, 5, 6]


async def test_supersede_link_to_a_removed_entry_is_dropped_after_renumber(tmp_path: Path) -> None:
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    chunks = chunks_for("D1", 6)
    provider = echo_provider({"D1:p6:c0": "D1:E001"})
    cfg = config(tmp_path, concurrency=2, segment_min_windows=3)

    entries = await extract_segmented([doc], {"D1": chunks}, cfg, provider)

    assert entries[-1].supersedes is None
    assert len(entries) == 5


async def test_per_document_mode_is_unchanged(tmp_path: Path) -> None:
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    chunks = chunks_for("D1", 4)
    provider = echo_provider({"D1:p3:c0": "D1:E001"})

    entries = await extract_per_document(
        [doc], {"D1": chunks}, config(tmp_path, extract_mode=ExtractMode.per_document), provider
    )

    assert [e.entry_id for e in entries] == ["D1:E002", "D1:E003", "D1:E004"]
    assert [e.window_no for e in entries] == [2, 3, 4]
    assert all("Reading position" not in c.messages[-1].content for c in provider.calls)


async def test_run_extract_segmented_writes_notebook_in_merged_order(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    docs = [
        Document(doc_id="D1", title="A", kind=DocumentKind.annual_report, source_path="a.md"),
        Document(doc_id="D2", title="B", kind=DocumentKind.covenant, source_path="b.md"),
    ]
    chunks = chunks_for("D1", 8) + chunks_for("D2", 2)
    write_models_atomic(workspace / "corpus" / "documents.json", docs)
    for item in chunks:
        append_jsonl(workspace / "corpus" / "chunks.jsonl", item)

    entries = await run_extract(workspace, config(tmp_path, segment_min_windows=2), echo_provider())

    lines = (workspace / "notebook.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["entry_id"] for line in lines] == [e.entry_id for e in entries]
    assert len({e.entry_id for e in entries}) == 10
    assert [e.doc_id for e in entries] == ["D1"] * 8 + ["D2"] * 2


class FlakyExtractProvider:
    """Echoes entries like echo_provider but raises for chunks on pages in `fail_pages`."""

    name = "flaky"
    model = "flaky"

    def __init__(self, fail_pages: set[int]) -> None:
        self.inner = echo_provider()
        self.fail_pages = fail_pages
        self.seen_chunks: list[str] = []

    async def complete(self, messages, **kwargs):
        match = re.search(r"New chunks for window \d+:\n\[([^\]]+)\]", messages[-1].content)
        if match is not None:
            chunk_id = match.group(1)
            if int(chunk_id.split(":")[1][1:]) in self.fail_pages:
                raise ConnectionError("server down")
            self.seen_chunks.append(chunk_id)
        return await self.inner.complete(messages, **kwargs)


async def test_extract_resumes_finished_segments_from_the_progress_file(tmp_path: Path) -> None:
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    chunks = chunks_for("D1", 24)
    cfg = config(tmp_path, segment_min_windows=3)
    progress = tmp_path / "extract_progress.jsonl"
    first = FlakyExtractProvider(set(range(13, 19)))

    with pytest.raises(ConnectionError):
        await extract_segmented([doc], {"D1": chunks}, cfg, first, progress_path=progress)

    assert len(progress.read_text().splitlines()) == 3

    second = FlakyExtractProvider(set())
    entries = await extract_segmented([doc], {"D1": chunks}, cfg, second, progress_path=progress)

    assert sorted(second.seen_chunks) == sorted(f"D1:p{p}:c0" for p in range(13, 19))
    expected = await extract_segmented([doc], {"D1": chunks}, cfg, echo_provider())
    assert [e.model_dump() for e in entries] == [e.model_dump() for e in expected]


async def test_run_extract_removes_the_progress_file_when_done(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    doc = Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)
    write_models_atomic(workspace / "corpus" / "documents.json", [doc])
    for chunk in chunks_for("D1", 3):
        append_jsonl(workspace / "corpus" / "chunks.jsonl", chunk)
    workspace.mkdir(exist_ok=True)
    (workspace / "extract_progress.jsonl").write_text("", encoding="utf-8")

    await run_extract(workspace, config(tmp_path), echo_provider())

    assert not (workspace / "extract_progress.jsonl").exists()
    assert (workspace / "notebook.json").exists()


def test_segment_count_with_larger_windows_and_default_min_windows() -> None:
    assert segment_count(2, 12, 3) == 1
    assert segment_count(3, 12, 3) == 1
    assert segment_count(9, 12, 3) == 3
    assert segment_count(60, 12, 3) == 12
    assert all(len(part) >= 3 for part in split_segments(list(range(10)), segment_count(10, 12, 3)))


async def test_extract_windows_in_flight_never_exceed_extract_concurrency(tmp_path: Path) -> None:
    limiter.configure(12)
    active = 0
    peak = 0
    chunk_re = re.compile(r"New chunks for window \d+:\n\[([^\]]+)\]")

    async def slow(messages, task: str) -> str:
        nonlocal active, peak
        if task != "extract":
            return json.dumps({"entries": []})
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        chunk_id = chunk_re.search(messages[-1].content).group(1)
        return json.dumps({"entries": [{"statement": "F.", "chunk_ids": [chunk_id]}]})

    docs = [Document(doc_id=f"D{n}", title="R", kind=DocumentKind.annual_report) for n in (1, 2)]
    by_doc = {d.doc_id: chunks_for(d.doc_id, 12) for d in docs}
    cfg = config(tmp_path, concurrency=12, extract_concurrency=2, segment_min_windows=2)

    entries = await extract_segmented(docs, by_doc, cfg, MockProvider(slow))

    assert len(entries) == 24
    assert peak == 2
