"""Answer questions about a finished run: retrieve, compose with citations, verify, print.

`answer_question` is the single-question pipeline; `chat_loop` repeats it over lines read from
an input function until a blank line, "exit" or end of input.
"""

from collections.abc import Callable
from pathlib import Path

from busybee.ask.check_sentences import check_sentences
from busybee.ask.compose_answer import compose_answer
from busybee.ask.model import Answer
from busybee.ask.render_answer import render_answer
from busybee.ask.retrieve import load_run_documents, load_run_store, retrieve
from busybee.index.embedder.protocol import Embedder
from busybee.index.embedder.registry import embedder_from_env
from busybee.llm.provider import Provider
from busybee.schema.documents import Document, ScoredChunk

NOT_ANSWERED = "The documents do not answer this question."


def _not_answered(question: str) -> Answer:
    return Answer(question=question, answered=False, message=NOT_ANSWERED)


async def answer_from_hits(
    question: str,
    hits: list[ScoredChunk],
    documents: dict[str, Document],
    provider: Provider,
) -> Answer:
    """Compose and verify an answer from already retrieved chunks."""
    if not hits:
        return _not_answered(question)
    reply = await compose_answer(provider, question, hits)
    if not reply.sentences:
        return _not_answered(question)
    chunks = {hit.chunk.chunk_id: hit.chunk for hit in hits}
    sentences = await check_sentences(reply.sentences, chunks, documents, provider)
    return Answer(question=question, answered=True, sentences=sentences)


async def answer_question(
    workspace: Path,
    question: str,
    provider: Provider,
    embedder: Embedder | None = None,
) -> Answer:
    """Answer one question from the run in workspace."""
    store = load_run_store(workspace)
    hits = await retrieve(store, embedder or embedder_from_env(), question)
    return await answer_from_hits(question, hits, load_run_documents(workspace), provider)


async def chat_loop(
    workspace: Path,
    provider: Provider,
    read_line: Callable[[], str],
    write: Callable[[str], None],
    embedder: Embedder | None = None,
) -> None:
    """Answer questions until read_line returns a blank line, "exit" or raises EOFError."""
    while True:
        try:
            question = read_line().strip()
        except EOFError:
            return
        if not question or question.lower() in {"exit", "quit"}:
            return
        write(render_answer(await answer_question(workspace, question, provider, embedder)))
