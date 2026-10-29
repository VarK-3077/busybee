"""Shared builders for the verify tests: chunks, entries, a tiny store and a scripted judge."""

import json
import re
from collections.abc import Callable

import numpy as np

from busybee.index import HashingEmbedder, VectorStore
from busybee.llm import Message, MockProvider
from busybee.schema.documents import Chunk
from busybee.schema.facts import Citation, NotebookEntry


def make_chunk(chunk_id: str, text: str) -> Chunk:
    doc, page, _ = chunk_id.split(":")
    return Chunk(
        chunk_id=chunk_id,
        doc_id=doc,
        page_no=int(page[1:]),
        index_in_page=0,
        text=text,
    )


def make_entry(entry_id: str, statement: str, chunk_id: str = "D1:p1:c0") -> NotebookEntry:
    doc = chunk_id.split(":")[0]
    page = int(chunk_id.split(":")[1][1:])
    return NotebookEntry(
        entry_id=entry_id,
        statement=statement,
        citations=[Citation(chunk_id=chunk_id, doc_id=doc, page_no=page)],
    )


async def make_store(chunks: list[Chunk]) -> tuple[VectorStore, HashingEmbedder]:
    embedder = HashingEmbedder()
    store = VectorStore(vectors=np.zeros((0, embedder.dim), dtype=np.float32))
    store.add(chunks, await embedder.embed([chunk.text for chunk in chunks]))
    return store, embedder


def judge_provider(
    is_relevant: Callable[[str], bool] = lambda entry_id: True,
    supports: Callable[[str, str], bool] = lambda statement, passage: statement in passage,
) -> MockProvider:
    """Scripted provider: relevance by entry id, entailment by predicate, quote = passage."""

    def respond(messages: list[Message], task: str) -> str:
        content = messages[-1].content
        if task == "verify_relevance":
            ids = re.findall(r"^- (\S+) \|", content, re.MULTILINE)
            return json.dumps({"drop": [[i, "trivia"] for i in ids if not is_relevant(i)]})
        if task == "verify_entailment_passage":
            passage = content.split("Source passage:\n", 1)[1].split("\n\nStatements:\n")[0]
            passage = re.sub(r"^\[[^\]\n]+\]\n", "", passage)
            lines = content.split("\n\nStatements:\n", 1)[1].splitlines()
            items = [line.split(". ", 1) for line in lines]
            return json.dumps(
                [
                    {
                        "id": n,
                        "v": "supported" if supports(text, passage) else "unsupported",
                        "q": passage.strip()[:40] if supports(text, passage) else "",
                    }
                    for n, text in items
                ]
            )
        if task == "verify_entailment_batch":
            statement = content.split("Statement:\n", 1)[1].split("\n\nSource passages:\n")[0]
            blocks = content.split("Source passages:\n", 1)[1]
            judgements = []
            for block in re.split(r"\n\n(?=\[[^\]\n]+\]\n)", blocks):
                chunk_id, passage = re.fullmatch(r"\[([^\]\n]+)\]\n(.*)", block, re.S).groups()
                ok = supports(statement, passage)
                judgements.append(
                    {
                        "id": chunk_id,
                        "v": "supported" if ok else "unsupported",
                        "q": passage.strip()[:40] if ok else "",
                    }
                )
            return json.dumps({"r": judgements})
        statement = content.split("Statement:\n", 1)[1].split("\n\nSource passage:\n")[0]
        passage = re.sub(r"^\[[^\]\n]+\]\n", "", content.split("Source passage:\n", 1)[1])
        if supports(statement, passage):
            return json.dumps({"v": "supported", "q": passage.strip()[:40]})
        return json.dumps({"v": "unsupported", "q": ""})

    return MockProvider(respond)
