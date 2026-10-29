"""Ask pipeline on a tiny saved index with the mock provider: four answer outcomes."""

import asyncio
import json
from pathlib import Path

import numpy as np
import pytest

from busybee.ask import Answer, answer_question
from busybee.ask.render_answer import render_answer
from busybee.index import HashingEmbedder, VectorStore
from busybee.llm import Message, MockProvider
from busybee.schema.documents import Chunk, Document
from busybee.schema.io import write_json_atomic

CHUNKS = [
    Chunk(
        chunk_id="D1:p157:c0",
        doc_id="D1",
        page_no=157,
        index_in_page=0,
        text="Total borrowings stood at 450 crore as at March 31, 2025.",
    ),
    Chunk(
        chunk_id="D1:p3:c0",
        doc_id="D1",
        page_no=3,
        index_in_page=0,
        text="The company manufactures steel pipes at its Pune plant.",
    ),
]


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    embedder = HashingEmbedder()
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))

    vectors = asyncio.run(embedder.embed([chunk.text for chunk in CHUNKS]))
    store.add(CHUNKS, vectors)
    store.save(tmp_path / "index")
    write_json_atomic(
        tmp_path / "corpus" / "documents.json",
        [Document(doc_id="D1", title="Annual report", source_path="docs/ar.pdf").model_dump()],
    )
    return tmp_path


def provider_answering(sentences: list[dict[str, object]], supports: bool = True) -> MockProvider:
    def respond(messages: list[Message], task: str) -> str:
        if task == "ask":
            return json.dumps({"sentences": sentences})
        verdict = "supported" if supports else "unsupported"
        return json.dumps({"v": verdict, "q": ""})

    return MockProvider(respond)


async def ask(workspace: Path, provider: MockProvider, question: str) -> Answer:
    return await answer_question(workspace, question, provider, HashingEmbedder())


async def test_supported_sentence_has_citation_and_pdf_link(workspace: Path) -> None:
    provider = provider_answering(
        [{"text": "Total borrowings were 450 crore.", "chunk_ids": ["D1:p157:c0"]}]
    )
    answer = await ask(workspace, provider, "What were total borrowings?")
    assert answer.answered
    [sentence] = answer.sentences
    assert sentence.supported
    assert sentence.citations[0].pdf_href == "originals/ar.pdf#page=157"
    text = render_answer(answer)
    assert "[supported]" in text and "D1 p.157" in text and "originals/ar.pdf#page=157" in text


async def test_unsupported_sentence_is_flagged(workspace: Path) -> None:
    provider = provider_answering(
        [{"text": "Total borrowings were 450 crore.", "chunk_ids": ["D1:p157:c0"]}],
        supports=False,
    )
    answer = await ask(workspace, provider, "What were total borrowings?")
    assert not answer.sentences[0].supported
    assert "[not supported]" in render_answer(answer)


async def test_wrong_number_is_flagged_without_judge(workspace: Path) -> None:
    provider = provider_answering(
        [{"text": "Total borrowings were 999 crore.", "chunk_ids": ["D1:p157:c0"]}]
    )
    answer = await ask(workspace, provider, "What were total borrowings?")
    assert not answer.sentences[0].supported
    assert "999" in answer.sentences[0].note
    assert all(call["task"] == "ask" for call in provider.calls)


async def test_citation_outside_retrieved_set_is_rejected(workspace: Path) -> None:
    provider = provider_answering(
        [{"text": "Total borrowings were 450 crore.", "chunk_ids": ["D9:p1:c0"]}]
    )
    answer = await ask(workspace, provider, "What were total borrowings?")
    [sentence] = answer.sentences
    assert not sentence.supported
    assert sentence.citations == []
    assert sentence.note == "cites no retrieved chunk"


async def test_question_with_no_hits_says_documents_do_not_answer(workspace: Path) -> None:
    provider = provider_answering([])
    answer = await ask(workspace, provider, "zzqx vvkj")
    assert not answer.answered
    assert "do not answer" in render_answer(answer)
