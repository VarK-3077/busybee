"""Call the inference writer and scrub fact ids before anything reaches the report."""

import logging
from collections.abc import Iterable, Mapping

from busybee.infer.compact_facts import compact_facts
from busybee.infer.prompts import (
    MAX_INFERENCES,
    TASK,
    InferenceDraft,
    InferenceOutput,
    LeanClaim,
    build_messages,
    normalise_confidence,
)
from busybee.llm import Provider, complete_as
from busybee.schema.facts import VerifiedFact
from busybee.schema.ids import make_inference_id
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Inference

logger = logging.getLogger(__name__)

FactSource = Iterable[VerifiedFact] | Mapping[str, VerifiedFact]


def facts_index(facts: FactSource) -> dict[str, VerifiedFact]:
    """Return a fact-id keyed mapping from either a sequence or a mapping."""
    if isinstance(facts, Mapping):
        return dict(facts)
    return {fact.fact_id: fact for fact in facts}


def _scrub_fact_ids(fact_ids: Iterable[str], known: set[str]) -> list[str]:
    """Keep only known fact ids, preserving order and removing duplicates."""
    cleaned = (str(fact_id).strip() for fact_id in fact_ids)
    return list(dict.fromkeys(fact_id for fact_id in cleaned if fact_id in known))


def _scrub_lean_claim(
    draft: InferenceDraft,
    fact_ids: list[str],
) -> tuple[bool, LeanClaim | None]:
    """Drop mappings to facts that did not survive validation."""
    claim = draft.lean_claim
    if not draft.quantitative or claim is None:
        return False, None
    allowed = set(fact_ids)
    mappings = {
        name.strip(): fact_id.strip()
        for name, fact_id in claim.facts.items()
        if name.strip() and fact_id.partition("#")[0].strip() in allowed
    }
    statement = claim.claim.strip()
    if not mappings or not statement:
        return False, None
    return True, LeanClaim(facts=mappings, claim=statement)


def validate_inference_drafts(
    output: InferenceOutput,
    facts: FactSource,
    *,
    max_inferences: int = MAX_INFERENCES,
) -> list[InferenceDraft]:
    """Drop unknown fact ids, drop facts-free inferences, and cap the list length."""
    index = facts_index(facts)
    known = set(index)
    kept: list[InferenceDraft] = []
    for draft in output.inferences:
        if len(kept) >= max_inferences:
            break
        fact_ids = _scrub_fact_ids(draft.fact_ids, known)
        if not fact_ids:
            logger.warning("dropping inference with no valid fact ids: %s", draft.opinion)
            continue
        quantitative, lean_claim = _scrub_lean_claim(draft, fact_ids)
        if draft.quantitative and lean_claim is None:
            logger.warning("dropping invalid Lean claim for inference: %s", draft.opinion)
        kept.append(
            draft.model_copy(
                update={
                    "opinion": draft.opinion.strip(),
                    "fact_ids": fact_ids,
                    "reasoning": draft.reasoning.strip(),
                    "quantitative": quantitative,
                    "lean_claim": lean_claim,
                }
            )
        )
    return kept


async def make_inference_drafts(
    facts: FactSource,
    scores: Iterable[ScoreResult],
    provider: Provider,
    *,
    max_inferences: int = MAX_INFERENCES,
) -> list[InferenceDraft]:
    """Ask the model for inferences and validate its fact references."""
    if max_inferences <= 0:
        return []
    index = facts_index(facts)
    compact = compact_facts(index.values(), scores)
    output = await complete_as(
        provider,
        build_messages(compact),
        InferenceOutput,
        task=TASK,
    )
    return validate_inference_drafts(output, index, max_inferences=max_inferences)


def to_inference(draft: InferenceDraft, number: int) -> Inference:
    """Convert a validated draft into the report's Inference model."""
    return Inference(
        inference_id=make_inference_id(number),
        opinion=draft.opinion,
        fact_ids=list(draft.fact_ids),
        reasoning=draft.reasoning,
        confidence=normalise_confidence(draft.confidence),
        quantitative=draft.quantitative,
    )


async def make_inferences(
    facts: FactSource,
    scores: Iterable[ScoreResult],
    provider: Provider,
    *,
    max_inferences: int = MAX_INFERENCES,
) -> list[Inference]:
    """Return validated report inferences without Lean quantification."""
    drafts = await make_inference_drafts(
        facts,
        scores,
        provider,
        max_inferences=max_inferences,
    )
    return [to_inference(draft, number) for number, draft in enumerate(drafts, start=1)]
