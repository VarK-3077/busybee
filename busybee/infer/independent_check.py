"""Fresh-context check that an inference's reasoning uses only its listed facts."""

import asyncio
import logging
from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from busybee.infer.compact_facts import compact_facts
from busybee.infer.make_inferences import facts_index
from busybee.infer.prompts import LOW_CONFIDENCE
from busybee.llm import Message, Provider, Role, complete_as
from busybee.schema.facts import VerifiedFact
from busybee.schema.report import Inference

logger = logging.getLogger(__name__)

TASK = "infer_check"

SYSTEM_PROMPT = """You are an independent credit reviewer checking another analyst's work.

You will be given a list of verified facts and one inference's reasoning paragraph. Decide
whether the reasoning relies only on those listed facts. A problem is anything the reasoning
adds that the facts do not support: an unlisted number, a fact from outside the list, an
assumption about management or the market, or a causal claim the facts cannot establish.

Return JSON with:
- ok: true only when every step of the reasoning is supported by the listed facts.
- problems: a list of short, specific problems. Use an empty list when ok is true."""


class CheckOutput(BaseModel):
    """The fresh-context reviewer's verdict on one inference."""

    ok: bool = True
    problems: list[str] = Field(default_factory=list)


def build_messages(inference: Inference, facts: Sequence[VerifiedFact]) -> list[Message]:
    """Build the facts-plus-reasoning prompt without showing the inference opinion."""
    supplied = compact_facts(facts)
    user = f"Listed facts:\n{supplied}\n\nReasoning to check:\n{inference.reasoning}"
    return [
        Message(role=Role.system, content=SYSTEM_PROMPT),
        Message(role=Role.user, content=user),
    ]


def check_messages(inference: Inference, facts: Sequence[VerifiedFact]) -> list[Message]:
    """Alias for build_messages."""
    return build_messages(inference, facts)


def _append_problem(reasoning: str, problem: str) -> str:
    """Append the independent-check finding to the reasoning in brackets."""
    base = reasoning.rstrip()
    suffix = f"[Independent check: {problem}]"
    return f"{base} {suffix}" if base else suffix


async def check_inference(
    inference: Inference,
    facts: Sequence[VerifiedFact] | Mapping[str, VerifiedFact],
    provider: Provider,
) -> Inference:
    """Downgrade one inference when the fresh-context check finds a problem."""
    index = facts_index(facts)
    listed = [index[fact_id] for fact_id in inference.fact_ids if fact_id in index]
    try:
        output = await complete_as(
            provider,
            build_messages(inference, listed),
            CheckOutput,
            task=TASK,
        )
    except Exception as error:
        logger.warning("independent check failed for %s: %s", inference.inference_id, error)
        return inference.model_copy(
            update={
                "confidence": LOW_CONFIDENCE,
                "reasoning": _append_problem(inference.reasoning, f"check unavailable ({error})"),
            }
        )
    problems = [problem.strip() for problem in output.problems if problem.strip()]
    if output.ok and not problems:
        return inference
    problem = "; ".join(problems) or "the reasoning relies on facts outside the listed set"
    return inference.model_copy(
        update={
            "confidence": LOW_CONFIDENCE,
            "reasoning": _append_problem(inference.reasoning, problem),
        }
    )


async def independent_check(
    inferences: Sequence[Inference],
    facts: Sequence[VerifiedFact] | Mapping[str, VerifiedFact],
    provider: Provider,
) -> list[Inference]:
    """Check independent inferences concurrently, preserving their order."""
    return list(
        await asyncio.gather(
            *(check_inference(inference, facts, provider) for inference in inferences)
        )
    )
