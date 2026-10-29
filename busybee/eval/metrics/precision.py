"""Important-statement precision: the share of report facts that are important and correct.

Report facts go to the model in batches together with the text of the chunks they cite; for
each fact the judge says whether it matters for a credit-line decision and whether the cited
text shows it to be correct. A fact the model forgets to judge counts as not good. Precision is
good facts over all report facts.
Task tag: `eval_precision`; response model: `PrecisionOutput`.
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

PRECISION_TASK = "eval_precision"
BATCH_SIZE = 10

_SYSTEM = (
    "You audit facts from a credit-review report. For each fact id decide (1) important: would "
    "a credit officer sizing a credit line care about it, and (2) correct: does the cited "
    "source text show the statement is accurate, numbers included. Judge only from the text."
)


class FactVerdict(BaseModel):
    """Importance and correctness verdict for one fact."""

    fact_id: str
    important: bool
    correct: bool


class PrecisionOutput(BaseModel):
    """The model reply for one batch of facts."""

    verdicts: list[FactVerdict] = Field(default_factory=list)


class PrecisionResult(BaseModel):
    """Precision plus the ids of facts judged unimportant or incorrect."""

    precision: float | None = None
    good: int = 0
    total: int = 0
    unimportant: list[str] = Field(default_factory=list)
    incorrect: list[str] = Field(default_factory=list)


def _block(fact: VerifiedFact, chunks_by_id: Mapping[str, Chunk]) -> str:
    statement = " ".join(fact.statement.split())
    return (
        f"FACT {fact.fact_id}: {statement}\nQUOTE: {cited_quotes(fact)}\n"
        f"SOURCE:\n{cited_passages(fact, chunks_by_id)}"
    )


async def _judge_once(
    batch: Sequence[VerifiedFact], chunks_by_id: Mapping[str, Chunk], provider: Provider
) -> dict[str, FactVerdict]:
    content = "\n\n".join(_block(fact, chunks_by_id) for fact in batch)
    messages = [
        Message(role=Role.system, content=_SYSTEM),
        Message(role=Role.user, content=content),
    ]
    output = await complete_as(
        provider, messages, PrecisionOutput, task=PRECISION_TASK, temperature=JUDGE_TEMPERATURE
    )
    return {v.fact_id: v for v in output.verdicts}


def _failed(fact: VerifiedFact) -> dict[str, FactVerdict]:
    return {fact.fact_id: FactVerdict(fact_id=fact.fact_id, important=False, correct=False)}


async def _judge_batch(
    batch: Sequence[VerifiedFact], chunks_by_id: Mapping[str, Chunk], provider: Provider
) -> dict[str, FactVerdict]:
    return await judge_halving(
        batch, lambda part: _judge_once(part, chunks_by_id, provider), _failed
    )


async def compute_precision(
    facts: Sequence[VerifiedFact],
    chunks_by_id: Mapping[str, Chunk],
    provider: Provider,
    *,
    batch_size: int = BATCH_SIZE,
) -> PrecisionResult:
    """Return precision of the report facts under the LLM judge."""
    results = await asyncio.gather(
        *(_judge_batch(b, chunks_by_id, provider) for b in batches_of(facts, batch_size))
    )
    verdicts: dict[str, FactVerdict] = {}
    for result in results:
        verdicts.update(result)
    good = 0
    unimportant: list[str] = []
    incorrect: list[str] = []
    for fact in facts:
        verdict = verdicts.get(fact.fact_id)
        if verdict is None:
            incorrect.append(fact.fact_id)
            continue
        if not verdict.important:
            unimportant.append(fact.fact_id)
        if not verdict.correct:
            incorrect.append(fact.fact_id)
        good += int(verdict.important and verdict.correct)
    return PrecisionResult(
        precision=ratio(good, len(facts)),
        good=good,
        total=len(facts),
        unimportant=unimportant,
        incorrect=incorrect,
    )
