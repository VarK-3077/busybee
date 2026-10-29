"""Try to answer one critic question from the documents.

Flow: vector search with the question's query (k=6); one LLM call reads the retrieved chunks
and, if they answer the question, writes a single self-contained statement (task
`adversary_answer`, model `AnswerOutput`); then the statement is entailment-checked against
every retrieved chunk. Chunks whose verdict is `supported` become citations (with the verbatim
quote) of a `NotebookEntry(added_by="adversary")`. If nothing is found, or entailment rejects
the statement, the result carries no entry and a reason, which the caller turns into a
`Concern{found=False}`.
"""

import asyncio
from dataclasses import dataclass

from pydantic import BaseModel

from busybee.index import VectorStore, search
from busybee.index.embedder.protocol import Embedder
from busybee.llm import Message, Role, StructuredOutputError, complete_as
from busybee.llm.provider import Provider
from busybee.schema.documents import ScoredChunk
from busybee.schema.facts import Citation, FactCategory, NotebookEntry
from busybee.verify.entailment import Verdict, judge_entailment

from .questions import Question

ANSWER_TASK = "adversary_answer"
SEARCH_K = 6
ADVERSARY = "adversary"

_SYSTEM = (
    "You answer a credit officer's question strictly from the numbered passages. If the "
    "passages answer it, set 'answered' true and write 'statement': one self-contained "
    "factual sentence (include the company, figures, units and period) that the passages "
    "directly support, and choose its 'category'. If they do not answer it, set 'answered' "
    "false and leave 'statement' empty. Never use outside knowledge."
)


class AnswerOutput(BaseModel):
    """Whether the passages answer the question, and the extracted statement."""

    answered: bool = False
    statement: str = ""
    category: FactCategory = FactCategory.other


@dataclass(frozen=True)
class GapResult:
    """The outcome for one question: a notebook entry if answered, else the reason why not."""

    entry: NotebookEntry | None
    reason: str = ""


def _passages(hits: list[ScoredChunk]) -> str:
    return "\n\n".join(f"[{hit.chunk.chunk_id}]\n{hit.chunk.text}" for hit in hits)


async def _extract_answer(
    question: Question, hits: list[ScoredChunk], provider: Provider
) -> AnswerOutput | None:
    messages = [
        Message(role=Role.system, content=_SYSTEM),
        Message(
            role=Role.user,
            content=f"Question: {question.question}\n\nPassages:\n{_passages(hits)}",
        ),
    ]
    try:
        return await complete_as(provider, messages, AnswerOutput, task=ANSWER_TASK)
    except StructuredOutputError:
        return None


async def answer_question(
    question: Question,
    entry_id: str,
    *,
    store: VectorStore,
    embedder: Embedder,
    provider: Provider,
    k: int = SEARCH_K,
) -> GapResult:
    """Search the index for the question and return an adversary entry or the reason not."""
    hits = await search(store, embedder, question.search_query or question.question, k=k)
    if not hits:
        return GapResult(None, "no passages retrieved")
    answer = await _extract_answer(question, hits, provider)
    if answer is None or not answer.answered or not answer.statement.strip():
        return GapResult(None, "retrieved passages do not answer the question")
    verdicts = await asyncio.gather(
        *(judge_entailment(answer.statement, hit.chunk.text, provider) for hit in hits)
    )
    citations = [
        Citation(
            chunk_id=hit.chunk.chunk_id,
            doc_id=hit.chunk.doc_id,
            page_no=hit.chunk.page_no,
            quote=verdict.quote,
        )
        for hit, verdict in zip(hits, verdicts, strict=True)
        if verdict.verdict is Verdict.supported
    ]
    if not citations:
        return GapResult(None, "entailment rejected the extracted statement")
    entry = NotebookEntry(
        entry_id=entry_id,
        statement=answer.statement.strip(),
        citations=citations,
        category=answer.category,
        doc_id=citations[0].doc_id,
        added_by=ADVERSARY,
    )
    return GapResult(entry, "")
