"""Citation precision: does each fact's cited quote and chunk really support its statement?

Every fact with at least one citation is shown to the model with its statement and each cited
quote beside the cited chunk text; the judge answers supported or not per fact. Facts without
citations or whose chunks are missing count as unsupported. Citation precision is supported
facts over all report facts, a sample of the verdicts being suitable for human spot checks.
Task tag: `eval_citation`; response model: `CitationOutput`.
"""

import asyncio
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from busybee.llm import Message, Role, complete_as
from busybee.llm.provider import Provider
from busybee.schema.documents import Chunk
from busybee.schema.facts import VerifiedFact

from .common import (
    JUDGE_TEMPERATURE,
    batches_of,
    cited_passages,
    cited_quotes,
    judge_halving,
    ratio,
)

CITATION_TASK = "eval_citation"
BATCH_SIZE = 10

_SYSTEM = (
    "You check citations in a credit-review report. For each fact id say whether the quoted "
    "text and the cited source text together support the statement, including its numbers. "
    "Answer supported=false if the source is missing, unrelated, or contradicts the statement."
)


class CitationVerdict(BaseModel):
    """Whether one fact's citation supports its statement."""

    fact_id: str
    supported: bool


class CitationOutput(BaseModel):
    """The model reply for one batch of facts."""

    verdicts: list[CitationVerdict] = Field(default_factory=list)


class CitationPrecisionResult(BaseModel):
    """Citation precision plus the ids of facts whose citation was not supported."""

    citation_precision: float | None = None
    supported: int = 0
    total: int = 0
    unsupported: list[str] = Field(default_factory=list)


def _block(fact: VerifiedFact, chunks_by_id: Mapping[str, Chunk]) -> str:
    statement = " ".join(fact.statement.split())
    return (
        f"FACT {fact.fact_id}: {statement}\nQUOTE: {cited_quotes(fact)}\n"
        f"SOURCE:\n{cited_passages(fact, chunks_by_id)}"
    )


async def _judge_once(
    batch: Sequence[VerifiedFact], chunks_by_id: Mapping[str, Chunk], provider: Provider
) -> dict[str, bool]:
    content = "\n\n".join(_block(fact, chunks_by_id) for fact in batch)
    messages = [
        Message(role=Role.system, content=_SYSTEM),
        Message(role=Role.user, content=content),
    ]
    output = await complete_as(
        provider, messages, CitationOutput, task=CITATION_TASK, temperature=JUDGE_TEMPERATURE
    )
    return {v.fact_id: v.supported for v in output.verdicts}


def _failed(fact: VerifiedFact) -> dict[str, bool]:
    return {fact.fact_id: False}


async def _judge_batch(
    batch: Sequence[VerifiedFact], chunks_by_id: Mapping[str, Chunk], provider: Provider
) -> dict[str, bool]:
    return await judge_halving(
        batch, lambda part: _judge_once(part, chunks_by_id, provider), _failed
    )


async def compute_citation_precision(
    facts: Sequence[VerifiedFact],
    chunks_by_id: Mapping[str, Chunk],
    provider: Provider,
    *,
    batch_size: int = BATCH_SIZE,
) -> CitationPrecisionResult:
    """Return the share of report facts whose citation the judge accepts."""
    cited = [f for f in facts if any(c.chunk_id in chunks_by_id for c in f.citations)]
    results = await asyncio.gather(
        *(_judge_batch(b, chunks_by_id, provider) for b in batches_of(cited, batch_size))
    )
    verdicts: dict[str, bool] = {}
    for result in results:
        verdicts.update(result)
    unsupported = [f.fact_id for f in facts if not verdicts.get(f.fact_id, False)]
    return CitationPrecisionResult(
        citation_precision=ratio(len(facts) - len(unsupported), len(facts)),
        supported=len(facts) - len(unsupported),
        total=len(facts),
        unsupported=unsupported,
    )
