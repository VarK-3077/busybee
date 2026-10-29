"""Repair loop for quantitative inferences whose unit check or Lean compile failed.

For a failed inference the model gets one follow-up message (task `infer_repair`) holding its
own claim, the exact error and the facts involved, and answers with a corrected lean_claim,
or with quantitative=false when the judgement cannot be expressed as arithmetic. The corrected
claim is quantified again; this repeats up to MAX_REPAIRS times. An inference that still
fails is settled by `settle_failure`: a claim that Lean proved false is dropped from the report
(the note says so, and run_infer keeps it in inferences_dropped.json); any other failure
(unit mismatch, unknown fact, timeout, Lean syntax error) keeps the inference with its Lean
badge "unchecked" and the error recorded in its reasoning.
"""

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

from pydantic import BaseModel

from busybee.infer.compact_facts import compact_fact
from busybee.infer.make_inferences import facts_index
from busybee.infer.prompts import SYSTEM_PROMPT, LeanClaim
from busybee.infer.quantify import lean_failure_message, quantify_inference
from busybee.llm import Message, Provider, Role, complete_as
from busybee.schema.facts import VerifiedFact
from busybee.schema.report import Inference

logger = logging.getLogger(__name__)

TASK = "infer_repair"
MAX_REPAIRS = 2

REPAIR_INSTRUCTIONS = """Your lean_claim for the inference below failed its check.

Correct the claim so that it is true of the listed facts and satisfies every rule in the
system prompt, or, if the judgement cannot be expressed as arithmetic over those facts, return
quantitative=false. If the numbers show the opinion itself is wrong, restate the opinion in
"opinion" so that it matches the facts. Return JSON with: quantitative (bool), lean_claim
(facts and claim, as before) and opinion (only when it must change, else empty)."""


class RepairOutput(BaseModel):
    """The model's corrected claim, or quantitative=false when it cannot be expressed."""

    quantitative: bool = True
    lean_claim: LeanClaim | None = None
    opinion: str = ""


def failure_text(inference: Inference) -> str:
    """The exact error stored on the inference's Lean artifact, or empty when it passed."""
    if inference.lean is None or inference.lean.compile is None or inference.lean.compile.ok:
        return ""
    return lean_failure_message(inference.lean.compile)


def proved_false(inference: Inference) -> bool:
    """True when Lean itself evaluated the claim to false (not a unit or syntax failure)."""
    if inference.lean is None or inference.lean.compile is None:
        return False
    return any("is false" in error.message for error in inference.lean.compile.errors)


def _facts_used(
    inference: Inference, claim: LeanClaim, index: Mapping[str, VerifiedFact]
) -> list[VerifiedFact]:
    """The inference's facts plus every fact the claim maps a variable to, in order."""
    ids = list(inference.fact_ids)
    ids += [reference.partition("#")[0].strip() for reference in claim.facts.values()]
    return [index[fact_id] for fact_id in dict.fromkeys(ids) if fact_id in index]


def repair_messages(
    inference: Inference, claim: LeanClaim, error: str, facts: Sequence[VerifiedFact]
) -> list[Message]:
    """The follow-up message: the failed claim, the exact error, and the facts it used."""
    lines = [
        REPAIR_INSTRUCTIONS,
        f"Opinion: {inference.opinion}",
        f"Reasoning: {inference.reasoning}",
        f"Your lean_claim: facts={claim.facts} claim={claim.claim!r}",
        f"Error: {error}",
        "Facts used (id | category | statement | numbers):",
        *(compact_fact(fact) for fact in facts),
    ]
    return [
        Message(role=Role.system, content=SYSTEM_PROMPT),
        Message(role=Role.user, content="\n".join(lines)),
    ]


async def repair_inference(
    inference: Inference,
    claim: LeanClaim,
    facts: Sequence[VerifiedFact] | Mapping[str, VerifiedFact],
    provider: Provider,
    *,
    output_dir: str | Path,
    run_id: str,
    max_repairs: int = MAX_REPAIRS,
) -> Inference:
    """Re-ask the model about a failed claim until it passes, is withdrawn, or retries run out."""
    index = facts_index(facts)
    current = inference
    for attempt in range(1, max_repairs + 1):
        error = failure_text(current)
        if not error:
            return current
        try:
            reply = await complete_as(
                provider,
                repair_messages(current, claim, error, _facts_used(current, claim, index)),
                RepairOutput,
                task=TASK,
            )
        except Exception as failure:
            logger.warning("repair call failed for %s: %s", inference.inference_id, failure)
            return current
        opinion = reply.opinion.strip() or current.opinion
        if not reply.quantitative or reply.lean_claim is None or not reply.lean_claim.claim.strip():
            return current.model_copy(
                update={
                    "opinion": opinion,
                    "quantitative": False,
                    "lean": None,
                    "reasoning": f"{current.reasoning} [Lean claim withdrawn after check failed: "
                    f"{error}]".strip(),
                }
            )
        claim = LeanClaim(facts=reply.lean_claim.facts, claim=reply.lean_claim.claim.strip())
        fact_ids = list(
            dict.fromkeys(
                [*current.fact_ids]
                + [
                    r.partition("#")[0].strip()
                    for r in claim.facts.values()
                    if r.partition("#")[0].strip() in index
                ]
            )
        )
        retry_input = current.model_copy(update={"opinion": opinion, "fact_ids": fact_ids})
        current = await quantify_inference(
            retry_input, claim, index, output_dir=output_dir, run_id=run_id
        )
        logger.info("repair %d/%d for %s", attempt, max_repairs, inference.inference_id)
    return current


def settle_failure(inference: Inference) -> Inference | None:
    """Return the inference to keep after repairs (None to drop it) for a still-failing claim."""
    error = failure_text(inference)
    if not error:
        return inference
    if proved_false(inference):
        return None
    note = f"[Lean check could not be completed and is shown unchecked: {error}]"
    return inference.model_copy(
        update={"lean": None, "reasoning": f"{inference.reasoning} {note}".strip()}
    )


def drop_note(inference: Inference) -> Inference:
    """Copy of a dropped inference whose reasoning says why it was removed from the report."""
    reason = failure_text(inference)
    note = f"[Dropped from the report: Lean showed the quantitative claim false: {reason}]"
    return inference.model_copy(update={"reasoning": f"{inference.reasoning} {note}".strip()})
