"""One structured LLM call (task "ask") that answers from the retrieved chunks only.

The model writes short sentences, each with the chunk ids it relies on. Ids outside the
retrieved set are removed by `keep_retrieved_citations`; a sentence left without any retrieved
citation stays in the answer but cannot be supported.
"""

from pydantic import BaseModel, Field

from busybee.llm import Message, Role, complete_as
from busybee.llm.provider import Provider
from busybee.schema.documents import ScoredChunk

ASK_TASK = "ask"

_SYSTEM = (
    "You answer questions about a company's documents using ONLY the passages given. "
    "Answer in short factual sentences. Each sentence must state one claim that a passage "
    "states literally, keep numbers, periods and units exactly as written, and list in "
    '"chunk_ids" the ids of the passages it relies on. Cite only ids shown in brackets. '
    "Never add facts from outside the passages. If the passages do not answer the question, "
    'return an empty "sentences" list. Reply with minified JSON: '
    '{"sentences":[{"text":"<sentence>","chunk_ids":["<id>"]}]}'
)


class AskSentence(BaseModel):
    """One answer sentence and the chunk ids the model says it relies on."""

    text: str
    chunk_ids: list[str] = Field(default_factory=list)


class AskReply(BaseModel):
    """The model's whole answer: an ordered list of cited sentences."""

    sentences: list[AskSentence] = Field(default_factory=list)


def passages_block(hits: list[ScoredChunk]) -> str:
    """Render the retrieved chunks as `[chunk_id]` headed passages."""
    return "\n\n".join(f"[{hit.chunk.chunk_id}]\n{hit.chunk.text}" for hit in hits)


def keep_retrieved_citations(reply: AskReply, hits: list[ScoredChunk]) -> AskReply:
    """Drop every cited id that was not retrieved; the sentence text is kept."""
    allowed = {hit.chunk.chunk_id for hit in hits}
    return AskReply(
        sentences=[
            AskSentence(
                text=sentence.text,
                chunk_ids=[cid for cid in dict.fromkeys(sentence.chunk_ids) if cid in allowed],
            )
            for sentence in reply.sentences
            if sentence.text.strip()
        ]
    )


async def compose_answer(provider: Provider, question: str, hits: list[ScoredChunk]) -> AskReply:
    """Ask the model for a cited answer and return it with out-of-set citations removed."""
    messages = [
        Message(role=Role.system, content=_SYSTEM),
        Message(
            role=Role.user,
            content=f"Question:\n{question}\n\nPassages:\n{passages_block(hits)}",
        ),
    ]
    reply = await complete_as(provider, messages, AskReply, task=ASK_TASK)
    return keep_retrieved_citations(reply, hits)
