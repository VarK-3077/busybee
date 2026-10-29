"""Render facts (grouped by category), scores and inferences as a compact markdown draft.

This is the only input the adversary's fresh-context critic sees: section 2 lists every
verified fact under its category heading as `- F001: statement`, followed by the score lines
(value and grade, with the bound fact ids), and section 3 lists each inference with its
supporting fact ids, confidence and reasoning. It is deliberately terse so the critic reads
the whole thing in one prompt.
"""

from collections.abc import Sequence

from busybee.schema.facts import FactCategory, VerifiedFact
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Inference


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _facts_section(facts: Sequence[VerifiedFact]) -> list[str]:
    lines = ["## Facts"]
    if not facts:
        return [*lines, "(none)"]
    for category in FactCategory:
        members = [fact for fact in facts if fact.category == category]
        if not members:
            continue
        lines.append(f"### {category.value}")
        lines.extend(f"- {fact.fact_id}: {_one_line(fact.statement)}" for fact in members)
    return lines


def _score_line(score: ScoreResult) -> str:
    fact_ids = ", ".join(bound.fact_id for bound in score.inputs) or "none"
    value = score.value_display or score.status.value
    grade = score.grade or "n/a"
    return f"- {score.score_id}: {value} (grade {grade}; facts {fact_ids})"


def _scores_section(scores: Sequence[ScoreResult]) -> list[str]:
    lines = ["## Scores"]
    return [*lines, *(_score_line(score) for score in scores)] if scores else [*lines, "(none)"]


def _inference_line(inference: Inference) -> str:
    fact_ids = ", ".join(inference.fact_ids) or "none"
    return (
        f"- {inference.inference_id}: {_one_line(inference.opinion)} "
        f"(facts {fact_ids}; confidence {inference.confidence:.2f}) "
        f"- {_one_line(inference.reasoning)}"
    )


def _inferences_section(inferences: Sequence[Inference]) -> list[str]:
    lines = ["## Inferences"]
    if not inferences:
        return [*lines, "(none)"]
    return [*lines, *(_inference_line(inference) for inference in inferences)]


def draft_markdown(
    facts: Sequence[VerifiedFact],
    scores: Sequence[ScoreResult],
    inferences: Sequence[Inference],
) -> str:
    """Return the markdown draft with Facts, Scores and Inferences sections."""
    lines = [
        "# Credit review draft",
        *_facts_section(facts),
        *_scores_section(scores),
        *_inferences_section(inferences),
    ]
    return "\n".join(lines) + "\n"
