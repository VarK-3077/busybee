"""Render verified facts and score results as compact one-line prompts entries."""

from collections.abc import Iterable

from busybee.schema.facts import NumericValue, VerifiedFact
from busybee.schema.policy import ScoreResult


def _one_line(text: str) -> str:
    """Collapse whitespace so one fact or number stays on one prompt line."""
    return " ".join(str(text).split())


def compact_number(number: NumericValue) -> str:
    """Render one numeric value as `label: value unit period`."""
    pieces = [number.label, str(number.value), number.unit, number.period]
    return _one_line(" ".join(piece for piece in pieces if piece))


def compact_fact(fact: VerifiedFact) -> str:
    """Render one fact as `F012 | category | statement | numbers`."""
    numbers = "; ".join(compact_number(number) for number in fact.numbers)
    fields = [fact.fact_id, fact.category.value, _one_line(fact.statement), numbers]
    return " | ".join(field for field in fields if field)


def compact_score(score: ScoreResult) -> str:
    """Render one score result with its status, value, grade, and bound facts."""
    facts = ",".join(dict.fromkeys(bound.fact_id for bound in score.inputs))
    fields = [
        score.score_id,
        "score",
        score.status.value,
        score.value_display or "",
        score.grade or "",
        facts,
    ]
    return " | ".join(field for field in fields if field)


def compact_facts(
    facts: Iterable[VerifiedFact],
    scores: Iterable[ScoreResult] = (),
) -> str:
    """Render facts and scores as the compact text block supplied to LLM prompts."""
    lines = [compact_fact(fact) for fact in facts]
    lines.extend(compact_score(score) for score in scores)
    return "\n".join(line for line in lines if line)
