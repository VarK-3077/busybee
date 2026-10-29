"""Important-statement recall: the share of gold material facts found in the report.

Each gold fact is matched against the report's verified facts by `eval.judge` (deterministic
shared-number prefilter, then a batched LLM judgement). Recall is reported over all gold facts
and over the `must_have` subset, together with the missed statements for inspection.
"""

from collections.abc import Sequence

from pydantic import BaseModel, Field

from busybee.eval.gold import GoldFact
from busybee.eval.judge import match_statements
from busybee.llm.provider import Provider
from busybee.schema.facts import VerifiedFact

from .common import ratio


class RecallResult(BaseModel):
    """Recall numbers plus which gold statements were found or missed."""

    recall: float | None = None
    recall_must_have: float | None = None
    matched: int = 0
    total: int = 0
    matches: dict[str, str] = Field(default_factory=dict)
    matched_fact_ids: dict[str, list[str]] = Field(default_factory=dict)
    missed: list[str] = Field(default_factory=list)


async def compute_recall(
    gold_facts: Sequence[GoldFact], facts: Sequence[VerifiedFact], provider: Provider
) -> RecallResult:
    """Return recall of gold facts among the report facts."""
    found = await match_statements([g.statement for g in gold_facts], facts, provider)
    hits = [bool(found[i]) for i in range(len(gold_facts))]
    must = [hit for hit, gold in zip(hits, gold_facts, strict=True) if gold.must_have]
    return RecallResult(
        recall=ratio(sum(hits), len(hits)),
        recall_must_have=ratio(sum(must), len(must)),
        matched=sum(hits),
        total=len(hits),
        matches={gold_facts[i].statement: ids[0] for i, ids in found.items() if ids},
        matched_fact_ids={gold_facts[i].statement: ids for i, ids in found.items() if ids},
        missed=[g.statement for g, hit in zip(gold_facts, hits, strict=True) if not hit],
    )
