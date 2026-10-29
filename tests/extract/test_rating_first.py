"""Rating rationales are read first and their key points reach the other documents' prompts."""

import json
import re
from pathlib import Path

from busybee.extract.per_document import extract_per_document
from busybee.extract.rating_first import DIGEST_TOKENS, rating_digest
from busybee.extract.segmented import extract_segmented
from busybee.llm import MockProvider, count_tokens
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.facts import NotebookEntry
from busybee.schema.run import RunConfig

FLAG = "ICRA flagged a negative outlook on the rating."


def entry(statement: str, importance: int = 3) -> NotebookEntry:
    return NotebookEntry(entry_id="D2:E001", statement=statement, importance=importance)


def test_digest_prefers_important_entries_dedupes_and_keeps_reading_order() -> None:
    entries = [entry("Minor point.", 2), entry("Key point.", 5), entry("key point.", 5)]
    assert rating_digest(entries) == "- Minor point.\n- Key point."
    assert rating_digest(entries, max_tokens=count_tokens("- Key point.\n")) == "- Key point."


def test_digest_stays_within_the_token_cap() -> None:
    entries = [entry(f"Rating point number {n} with some words attached.", 3) for n in range(400)]
    assert count_tokens(rating_digest(entries)) <= DIGEST_TOKENS


def config(tmp_path: Path) -> RunConfig:
    return RunConfig(
        run_id="t",
        docs_dir=tmp_path,
        bank_id="b",
        out_dir=tmp_path,
        workspace_dir=tmp_path,
        window_tokens=10_000,
    )


def documents() -> list[Document]:
    return [
        Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report),
        Document(doc_id="D2", title="ICRA rationale", kind=DocumentKind.rating_rationale),
    ]


def chunks_by_doc() -> dict[str, list[Chunk]]:
    return {
        doc_id: [
            Chunk(
                chunk_id=f"{doc_id}:p1:c0", doc_id=doc_id, page_no=1, index_in_page=0, text="Text."
            )
        ]
        for doc_id in ("D1", "D2")
    }


def echo_provider() -> MockProvider:
    def reply(messages, task: str) -> str:
        prompt = messages[-1].content
        chunk_id = re.search(r"New chunks for window \d+:\n\[([^\]]+)\]", prompt)[1]
        statement = FLAG if chunk_id.startswith("D2") else f"Fact from {chunk_id}."
        entry_ = {"statement": statement, "chunk_ids": [chunk_id], "importance": 4}
        return json.dumps({"entries": [entry_]})

    return MockProvider(reply)


def user_prompts(provider: MockProvider) -> dict[str, str]:
    return {
        re.search(r"\[(D\d)", call.messages[-1].content)[1]: call.messages[-1].content
        for call in provider.calls
        if call.task == "extract"
    }


async def test_segmented_reads_rating_rationales_first_and_shares_their_digest(
    tmp_path: Path,
) -> None:
    provider = echo_provider()
    entries = await extract_segmented(documents(), chunks_by_doc(), config(tmp_path), provider)
    extract_calls = [call for call in provider.calls if call.task == "extract"]
    assert "[D2:p1:c0]" in extract_calls[0].messages[-1].content
    prompts = user_prompts(provider)
    assert "What the rating agency flagged" not in prompts["D2"]
    assert "What the rating agency flagged" in prompts["D1"] and f"- {FLAG}" in prompts["D1"]
    assert [e.doc_id for e in entries] == ["D1", "D2"]


async def test_per_document_mode_does_the_same(tmp_path: Path) -> None:
    provider = echo_provider()
    entries = await extract_per_document(documents(), chunks_by_doc(), config(tmp_path), provider)
    prompts = user_prompts(provider)
    assert f"- {FLAG}" in prompts["D1"] and "flagged" not in prompts["D2"]
    assert [e.doc_id for e in entries] == ["D1", "D2"]


async def test_without_rating_rationales_nothing_is_added(tmp_path: Path) -> None:
    provider = echo_provider()
    only = [documents()[0]]
    await extract_segmented(only, chunks_by_doc(), config(tmp_path), provider)
    assert "flagged" not in user_prompts(provider)["D1"]
