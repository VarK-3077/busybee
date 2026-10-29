"""Check the arithmetic and direction of every recommendation reason, and drop the false ones.

Reasons are LLM prose such as "Net debt/EBITDA of 2.7x is within the 4.5x cap", and nothing
else verifies the comparison. Two independent checks run on each `policy_rule` and `hard_fact`
reason. (a) `deterministic_findings` parses "<number><unit> <verb> ... <number><unit>" with the
verbs exceeds / is above / is below / falls below / is within / meets / fails, converts % and
x/times to one ratio scale (113.4% = 1.134x) and money to crore, and tests the stated
direction in code. (b) `llm_findings` sends one batched fresh-context call (task
`compose_verdict_check`) with each reason, its cited facts, scores and policy sections, and
gets `correct | incorrect | unverifiable` back. A reason either check calls wrong is removed
and recorded as a `RejectedReason`. `check_verdicts` returns the cleaned recommendation and the
rejections; `needs_reask` says whether the decision leaned on a removed reason (fewer than two
reasons left, or the headline names the removed reason's metric) so compose should ask again.
"""

import re
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, Field

from busybee.llm import Provider, complete_as
from busybee.llm.messages import Message, Role
from busybee.llm.structured import StructuredOutputError
from busybee.schema.facts import VerifiedFact
from busybee.schema.policy import ScoreResult, ScoreSpec
from busybee.schema.report import KeyReason, Recommendation

from .check_ids import MIN_KEY_REASONS
from .inputs import ComposeInputs

VERDICT_TASK = "compose_verdict_check"
CHECKED_KINDS = ("policy_rule", "hard_fact")
SECTION_CHARS = 1200
_NUMBER = r"-?\d[\d,]*(?:\.\d+)?"
_UNIT = r"%|×|x\b|times\b|crores?\b|cr\b|lakhs?\b|bps\b"
_QUANTITY = re.compile(rf"(?P<n>{_NUMBER})\s*(?P<u>{_UNIT})", re.IGNORECASE)
_VERBS = re.compile(
    r"(?P<neg>(?:does not|doesn't|did not|do not)\s+)?"
    r"(?P<v>exceeds?|is above|are above|is below|are below|falls? below|is within|are within"
    r"|meets?|fails? to meet|fails?)\b",
    re.IGNORECASE,
)
_CAP_WORDS = ("cap", "maximum", "max ", "limit", "ceiling", "upper", "not exceed")
_FLOOR_WORDS = ("minimum", "min ", "floor", "at least", "requirement", "threshold")
_NEAR = 70
_STOP = frozenset(
    "the company companys consolidated with that this from have been which their policy "
    "ratio score level".split()
)


class RejectedReason(BaseModel):
    """A reason removed by a verdict check, with who rejected it and why."""

    text: str
    kind: str
    source: Literal["deterministic", "llm"]
    note: str
    fact_ids: list[str] = Field(default_factory=list)
    score_ids: list[str] = Field(default_factory=list)
    round: int = 1


class ReasonVerdict(BaseModel):
    """The independent checker's judgement of one reason."""

    index: int
    verdict: Literal["correct", "incorrect", "unverifiable"] = "unverifiable"
    note: str = ""


class VerdictOutput(BaseModel):
    """The checker's structured reply: one verdict per reason index."""

    checks: list[ReasonVerdict] = Field(default_factory=list)


def _to_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", ""))
    except InvalidOperation:
        return None


def _kind_of(unit: str) -> str:
    lowered = unit.lower()
    if lowered in {"%"}:
        return "percent"
    if lowered in {"x", "×", "times"}:
        return "times"
    if lowered in {"crore", "crores", "cr", "lakh", "lakhs"}:
        return "money"
    return lowered


def _normalised(value: Decimal, unit: str, as_ratio: bool) -> Decimal:
    lowered = unit.lower()
    if lowered == "%" and as_ratio:
        return value / 100
    if lowered.startswith("lakh"):
        return value / 100
    return value


def _comparable(left: str, right: str) -> tuple[bool, bool]:
    """Return (comparable, convert_percent_to_ratio) for two unit kinds."""
    if left == right:
        return True, False
    if {left, right} == {"percent", "times"}:
        return True, True
    return False, False


def _direction(verb: str, negated: bool, right_context: str) -> str | None:
    """Map a verb to the relation a must have to b: gt, lt, le, ge, or None if unclear."""
    word = verb.lower()
    context = right_context.lower()
    capped = any(w in context for w in _CAP_WORDS)
    floored = any(w in context for w in _FLOOR_WORDS)
    if word.startswith("exceed") or word.endswith("above"):
        relation = "gt"
    elif word.endswith("below"):
        relation = "lt"
    elif word.endswith("within"):
        relation = "ge" if floored and not capped else "le"
    elif word.startswith("meet") or word.startswith("fail"):
        if capped == floored:
            return None
        relation = "le" if capped else "ge"
        if word.startswith("fail"):
            relation = {"le": "gt", "ge": "lt"}[relation]
    else:
        return None
    if negated:
        relation = {"gt": "le", "lt": "ge", "le": "gt", "ge": "lt"}[relation]
    return relation


_HOLDS = {
    "gt": lambda a, b: a > b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "ge": lambda a, b: a >= b,
}
_WORDS = {"gt": "exceed", "lt": "be below", "le": "be at or below", "ge": "be at or above"}


def deterministic_findings(text: str) -> list[str]:
    """Return a note for each stated comparison in text whose direction is arithmetically false."""
    notes = []
    for verb in _VERBS.finditer(text):
        left = [m for m in _QUANTITY.finditer(text, max(0, verb.start() - _NEAR), verb.start())]
        right = _QUANTITY.search(text, verb.end(), verb.end() + _NEAR)
        if not left or right is None:
            continue
        a_match = left[-1]
        a, b = _to_decimal(a_match.group("n")), _to_decimal(right.group("n"))
        ok, as_ratio = _comparable(_kind_of(a_match.group("u")), _kind_of(right.group("u")))
        if a is None or b is None or not ok:
            continue
        relation = _direction(
            verb.group("v"), bool(verb.group("neg")), text[verb.end() : right.end() + 40]
        )
        if relation is None:
            continue
        a_norm = _normalised(a, a_match.group("u"), as_ratio)
        b_norm = _normalised(b, right.group("u"), as_ratio)
        if not _HOLDS[relation](a_norm, b_norm):
            notes.append(
                f"{a_match.group(0)} (= {a_norm.normalize():f}) does not {_WORDS[relation]} "
                f"{right.group(0)} (= {b_norm.normalize():f}), so the stated verdict is false"
            )
    return notes


def _checker_system() -> str:
    return (
        "You audit the verdict sentences of a credit recommendation. For each numbered reason, "
        "decide from the cited evidence alone whether the sentence is correct: the numbers it "
        "quotes appear in (or follow from) the cited facts and scores, and every comparison it "
        "states is true. Normalise units before comparing (113.4% is 1.134x; 3.0 times is "
        "300%; lakh to crore divides by 100). Answer correct, incorrect (a number is wrong or "
        "a comparison is false), or unverifiable (the evidence is not enough to tell). Give a "
        "one-sentence note for anything not correct. The recommendation may be reduce_or_decline "
        "(reduce the credit line or decline), a valid decision when a minimum standard fails; "
        "a reason saying a ratio is below or above its minimum is judged only on its numbers. "
        "Return JSON "
        '{"checks": [{"index": 0, "verdict": "correct", "note": ""}]} with one entry per reason.'
    )


def _score_line(score: ScoreResult, specs: Mapping[str, ScoreSpec]) -> str:
    spec = specs.get(score.score_id)
    meaning = f" ({spec.value_meaning})" if spec and spec.value_meaning else ""
    value = score.value_display or score.status.value
    return f"{score.score_id}: {value}, grade {score.grade or 'none'}{meaning}"


def _evidence_block(
    index: int,
    reason: KeyReason,
    facts: Mapping[str, VerifiedFact],
    scores: Mapping[str, ScoreResult],
    specs: Mapping[str, ScoreSpec],
) -> str:
    lines = [f"Reason {index} [{reason.kind}]: {reason.text}"]
    lines += [f"  fact {fid}: {facts[fid].statement}" for fid in reason.fact_ids if fid in facts]
    lines += [
        f"  score {_score_line(scores[sid], specs)}" for sid in reason.score_ids if sid in scores
    ]
    for citation in reason.policy_citations:
        text = " ".join(citation.quote.split())[:SECTION_CHARS]
        lines.append(f"  policy {citation.section_id} ({citation.heading}): {text}")
    return "\n".join(lines)


def verdict_messages(reasons: Sequence[tuple[int, KeyReason]], inputs: ComposeInputs) -> list:
    """Build the fresh-context prompt: every checked reason with only its own evidence."""
    facts = {fact.fact_id: fact for fact in inputs.facts}
    scores = {score.score_id: score for score in inputs.scores}
    specs = {spec.score_id: spec for spec in inputs.score_specs}
    sections = {section.section_id: section for section in inputs.policy_sections}
    blocks = []
    for index, reason in reasons:
        cited = [
            c.model_copy(update={"quote": sections[c.section_id].text})
            if c.section_id in sections
            else c
            for c in reason.policy_citations
        ]
        blocks.append(
            _evidence_block(
                index, reason.model_copy(update={"policy_citations": cited}), facts, scores, specs
            )
        )
    body = "\n\n".join(blocks)
    return [
        Message(role=Role.system, content=_checker_system()),
        Message(role=Role.user, content=f"Reasons to audit:\n\n{body}\n\nReturn the JSON."),
    ]


async def llm_findings(
    provider: Provider, reasons: Sequence[tuple[int, KeyReason]], inputs: ComposeInputs
) -> dict[int, str]:
    """One batched call; return index -> note for every reason judged incorrect."""
    if not reasons:
        return {}
    try:
        output = await complete_as(
            provider, verdict_messages(reasons, inputs), VerdictOutput, task=VERDICT_TASK
        )
    except StructuredOutputError:
        return {}
    known = {index for index, _ in reasons}
    return {
        check.index: check.note or "judged incorrect by the independent check"
        for check in output.checks
        if check.verdict == "incorrect" and check.index in known
    }


def _reject(reason: KeyReason, source: str, note: str, round_no: int) -> RejectedReason:
    return RejectedReason(
        text=reason.text,
        kind=reason.kind,
        source=source,  # type: ignore[arg-type]
        note=note,
        fact_ids=reason.fact_ids,
        score_ids=reason.score_ids,
        round=round_no,
    )


async def check_verdicts(
    provider: Provider, recommendation: Recommendation, inputs: ComposeInputs, round_no: int = 1
) -> tuple[Recommendation, list[RejectedReason]]:
    """Remove reasons whose stated verdict is false by either check; return what was removed."""
    checked = [
        (index, reason)
        for index, reason in enumerate(recommendation.key_reasons)
        if reason.kind in CHECKED_KINDS
    ]
    rejected: dict[int, RejectedReason] = {}
    for index, reason in checked:
        notes = deterministic_findings(reason.text)
        if notes:
            rejected[index] = _reject(reason, "deterministic", "; ".join(notes), round_no)
    remaining = [(index, reason) for index, reason in checked if index not in rejected]
    for index, note in (await llm_findings(provider, remaining, inputs)).items():
        rejected[index] = _reject(recommendation.key_reasons[index], "llm", note, round_no)
    if not rejected:
        return recommendation, []
    kept = [r for i, r in enumerate(recommendation.key_reasons) if i not in rejected]
    cleaned = recommendation.model_copy(update={"key_reasons": kept})
    return cleaned, [rejected[i] for i in sorted(rejected)]


def _content_words(text: str) -> set[str]:
    words = re.findall(r"[a-z]{4,}", text.lower())
    return {word for word in words if word not in _STOP}


def _metric_words(reason_text: str) -> set[str]:
    return _content_words(re.split(r"\d", reason_text, maxsplit=1)[0])


def needs_reask(recommendation: Recommendation, rejected: Sequence[RejectedReason]) -> bool:
    """True when a removed reason left fewer than two reasons or its metric is in the headline."""
    if not rejected:
        return False
    if len(recommendation.key_reasons) < MIN_KEY_REASONS:
        return True
    headline = _content_words(recommendation.headline)
    for item in rejected:
        metric = _metric_words(item.text)
        if metric and len(metric & headline) >= min(2, len(metric)):
            return True
    return False


def reask_note(rejected: Sequence[RejectedReason]) -> str:
    """Follow-up message that lists the removed reasons and why."""
    lines = "\n".join(f"- {item.text} (rejected: {item.note})" for item in rejected)
    return (
        "Code and an independent checker found these reasons of your recommendation false and "
        f"removed them:\n{lines}\nReturn the whole recommendation again as JSON. Recompute every "
        "comparison with units normalised (113.4% is 1.134x, not above 3.0x), correct the "
        "decision and headline if they relied on a false verdict, and give only reasons whose "
        "numbers and comparisons are right."
    )
