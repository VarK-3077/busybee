"""Judge a slot no single fact states: a red-flag count, a default flag, or a missed rating.

One LLM call per slot (task `policy.judge_slot`). The prompt carries the policy rubric (the
sections named in the slot's `judge.rubric_headings`), the slot definition and the candidate
facts: those whose statements contain one of the slot's keywords (default, NPA, SMA, overdue,
qualification, fraud, wilful, Form 483, OAI, warning letter, litigation, pledge, ...), ranked by
how many keywords they hit and capped at `_MAX_FACTS`. The model returns the value, the ids of
the facts that justify it and a one-line justification. Code accepts the answer only when the
value fits the slot (0 or 1 for a flag, a non-negative whole number for a count, a grade of the
slot's `mapping` for a rating that appears in a cited fact), every cited id was shown, and at
least one fact is cited, because a value nobody can trace is not bound. A slot with no
candidate fact is not asked at all: absence of evidence in the pack is not evidence of absence,
so it stays unbound with that reason. The result is a `BoundInput` citing the facts, with the
justification in `note`.

A count slot (major red flags) is different: when candidates exist but the model returns no
value, a value outside the allowed range or an unparsable reply, the slot is bound to 0 with the
justification "no qualifying red flag found among N candidate facts", citing the candidates
examined, and the note starts with `judged_default: true` so the report shows a defaulted
judgement. A flag slot (default flag) never defaults: it stays unbound unless the model gives a
valid answer, because silence is not evidence that no default occurred.
"""

import re
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from busybee.llm import Message, Provider, Role, StructuredOutputError, complete_as
from busybee.policy.bind_rating import grades_in
from busybee.policy.policy_sections import PolicySection
from busybee.schema.facts import VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot, ScoreSpec

JUDGE_TASK = "policy.judge_slot"
_MAX_FACTS = 40
_MAX_COUNT = 20
_NOTE_CHARS = 400
_SHORT_KEYWORD = 4
DEFAULT_MARK = "judged_default: true"
_RATING_WORDS = (
    "rating",
    "rated",
    "ICRA",
    "CRISIL",
    "CARE",
    "Acuite",
    "Brickwork",
    "India Ratings",
)

_SYSTEM = (
    "You are a credit analyst applying a bank's written policy to facts verified from a "
    "borrower's documents. Decide the value of one policy input using ONLY the listed facts "
    "and the policy rubric. Cite the ids of the facts that justify the value: for a zero, the "
    "facts that state the absence (for example no wilful default declared); for a positive "
    "value, the facts that evidence each item. Never cite an id that is not listed. Do not "
    "count something the facts do not evidence, and do not count one issue twice. In the "
    "justification (one line) name any candidate fact that looks adverse but that you did not "
    "count, with the reason (for example not quantified against net worth). Reply with "
    'JSON: {"value": <number or string>, "fact_ids": [...], "justification": "<one line>"}.'
)


class Judgement(BaseModel):
    """The model's value for a judged slot, the facts behind it and a one-line reason."""

    value: str | int | float | None = None
    fact_ids: list[str] = Field(default_factory=list)
    justification: str = ""

    @field_validator("value", mode="before")
    @classmethod
    def _plain(cls, raw: object) -> object:
        return None if isinstance(raw, bool) else raw


def _keyword_patterns(keywords: list[str]) -> list[re.Pattern[str]]:
    return [
        re.compile(
            rf"(?<!\w){re.escape(word)}{r'\w*' if len(word) > _SHORT_KEYWORD else r'(?!\w)'}",
            re.IGNORECASE,
        )
        for word in keywords
    ]


def judge_candidates(
    keywords: list[str], facts: list[VerifiedFact], limit: int = _MAX_FACTS
) -> list[VerifiedFact]:
    """Facts mentioning at least one keyword, most distinct keywords first, at most limit."""
    patterns = _keyword_patterns(keywords)
    scored = []
    for fact in facts:
        hits = sum(1 for pattern in patterns if pattern.search(fact.statement))
        if hits:
            scored.append((hits, fact))
    scored.sort(key=lambda item: -item[0])
    return [fact for _, fact in scored[:limit]]


def rubric_text(headings: list[str], sections: list[PolicySection]) -> str:
    """The text of every policy section whose heading contains one of the headings."""
    wanted = [heading.lower() for heading in headings]
    chosen = [s for s in sections if any(w in s.heading.lower() for w in wanted)]
    return "\n\n".join(f"{section.heading}\n{section.text}" for section in chosen)


def _answer_rule(slot: InputSlot) -> str:
    if slot.mapping:
        table = ", ".join(f"{grade}={index}" for grade, index in slot.mapping.items())
        return (
            "Answer with the latest long-term external rating grade named in the facts, copied "
            f"exactly as one of: {', '.join(slot.mapping)} (bank index table: {table}). "
            "Ignore short-term ratings. value is the grade string."
        )
    if slot.judge and slot.judge.answer == "count":
        return "value is a whole number, the count of distinct major red flags the facts evidence."
    return "value is 1 if the flag is raised on the facts, else 0."


def _messages(
    spec: ScoreSpec, slot: InputSlot, rubric: str, facts: list[VerifiedFact]
) -> list[Message]:
    listed = "\n".join(f"{fact.fact_id}: {fact.statement}" for fact in facts)
    content = (
        f"Score: {spec.score_id}. Input: {slot.slot} ({slot.unit}).\n"
        f"Definition: {slot.description}\n{_answer_rule(slot)}\n\n"
        f"Policy rubric:\n{rubric or '(no rubric text; use the definition)'}\n\n"
        f"Candidate facts:\n{listed}\n\nReturn the JSON for input {slot.slot}."
    )
    return [Message(role=Role.system, content=_SYSTEM), Message(role=Role.user, content=content)]


def _numeric(slot: InputSlot, answer: Judgement) -> int | str:
    """The accepted integer value, or the reason the answer is rejected."""
    try:
        number = Decimal(str(answer.value).strip())
    except Exception:
        return f"value {answer.value!r} is not a number"
    if number != number.to_integral_value():
        return f"value {answer.value!r} is not a whole number"
    value = int(number)
    flag = slot.judge is not None and slot.judge.answer == "flag"
    if flag and value not in (0, 1):
        return f"flag value {value} must be 0 or 1"
    if not 0 <= value <= _MAX_COUNT:
        return f"value {value} is out of range"
    return value


def _rating_index(slot: InputSlot, answer: Judgement, shown: dict[str, VerifiedFact]) -> int | str:
    grade = str(answer.value or "")
    grade = (grade.split("]", 1)[1] if "]" in grade else grade).strip().strip("'\" ")
    if grade not in slot.mapping:
        return f"grade {answer.value!r} is not in the policy rating table"
    if not any(grade in grades_in(shown[f].statement, list(slot.mapping)) for f in answer.fact_ids):
        return f"grade {grade} does not appear in the cited facts"
    return slot.mapping[grade]


async def judge_slot(
    provider: Provider,
    spec: ScoreSpec,
    slot: InputSlot,
    facts: list[VerifiedFact],
    sections: list[PolicySection],
) -> BoundInput | str:
    """Ask the model for the slot's value; return the binding or the reason it stays unbound."""
    if slot.mapping:
        keywords = list(_RATING_WORDS)
        headings = slot.judge.rubric_headings if slot.judge else []
    elif slot.judge is not None:
        keywords, headings = slot.judge.keywords, slot.judge.rubric_headings
    else:
        return "slot has no judgement settings"
    candidates = judge_candidates(keywords, facts)
    if not candidates:
        return "no verified fact mentions this topic, so the pack cannot evidence a value"
    shown = {fact.fact_id: fact for fact in candidates}
    is_count = slot.judge is not None and slot.judge.answer == "count" and not slot.mapping
    try:
        answer = await complete_as(
            provider,
            _messages(spec, slot, rubric_text(headings, sections), candidates),
            Judgement,
            task=JUDGE_TASK,
        )
    except StructuredOutputError as error:
        if is_count:
            return _defaulted_count(slot, candidates, f"unparsable reply: {error}")
        raise
    if is_count and answer.value is None:
        return _defaulted_count(slot, candidates, "no value returned")
    cited = list(dict.fromkeys(answer.fact_ids))
    if not cited or any(fact_id not in shown for fact_id in cited):
        return f"the model's answer cited no valid fact ({answer.fact_ids})"
    answer = answer.model_copy(update={"fact_ids": cited})
    if answer.value is None:
        return f"the model found no value in {len(candidates)} candidate facts"
    value = _rating_index(slot, answer, shown) if slot.mapping else _numeric(slot, answer)
    if isinstance(value, str):
        if is_count:
            return _defaulted_count(slot, candidates, value)
        return f"judgement rejected: {value}"
    note = " ".join(answer.justification.split())[:_NOTE_CHARS] or "judged from the cited facts"
    return BoundInput(
        slot=slot.slot,
        fact_id=cited[0],
        value=Decimal(value),
        unit=slot.unit,
        value_scaled=value * slot.scale,
        derived_from=cited if len(cited) > 1 else [],
        note=note,
    )


def _defaulted_count(slot: InputSlot, candidates: list[VerifiedFact], why: str) -> BoundInput:
    """A count slot bound to 0 because the model gave no usable count, citing what was examined."""
    ids = [fact.fact_id for fact in candidates]
    return BoundInput(
        slot=slot.slot,
        fact_id=ids[0],
        value=Decimal(0),
        unit=slot.unit,
        value_scaled=0,
        derived_from=ids if len(ids) > 1 else [],
        note=(
            f"{DEFAULT_MARK}; no qualifying red flag found among {len(ids)} candidate facts "
            f"({why}); examined: {', '.join(ids)}"
        ),
    )
