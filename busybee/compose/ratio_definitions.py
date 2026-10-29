"""Flag a ratio that the report shows with different values, and say so next to each mention.

The same ratio name (interest coverage, DSCR, net debt / EBITDA, current ratio, debt / equity)
can carry the policy value (computed by a rule from its inputs) and a company-reported value
quoted in an inference or a reason, on another basis (consolidated, standalone) or with another
definition. `ratio_values` collects every "<name> ... <number>x" mention in rule results,
inferences and key reasons, and `annotate_ratio_definitions` (plain code, no LLM call) appends
"Note: <ratio> shown with different definitions: 1.78x (policy rule), 0.1x (I001, consolidated),
..." to every text that mentions a ratio whose values differ at one decimal. The note is added
once; texts that already carry it are left alone.
"""

import re
from dataclasses import dataclass, replace

from busybee.schema.policy import RuleResult
from busybee.schema.report import Inference, KeyReason, Recommendation

from .inputs import ComposeInputs
from .minimum_standards import ratio_value_of

NOTE_MARK = "shown with different definitions"
_NAMES = {
    "interest coverage": r"interest\s+(?:service\s+)?coverage",
    "dscr": r"dscr|debt\s+service\s+coverage",
    "net debt / ebitda": r"net\s+debt\s*(?:/|to|-to-)\s*ebitda",
    "current ratio": r"current\s+ratio",
    "debt / equity": r"(?:total\s+)?debt\s*(?:/|to|-to-)\s*equity",
}
_DISPLAY = {"dscr": "DSCR", "net debt / ebitda": "Net debt / EBITDA"}
_QUANTITY = r"(?P<n>\d+(?:\.\d+)?)\s*(?:x\b|×|times\b)"
_WINDOW = 90
_BASIS = ("consolidated", "standalone")


@dataclass(frozen=True)
class Mention:
    """One value of a ratio and where it was read."""

    ratio: str
    value: float
    source: str


def _basis(text: str, start: int, end: int) -> str:
    near = text[max(0, start - 40) : end].lower()
    return next((word for word in _BASIS if word in near), "")


def mentions_in(text: str, source: str) -> list[Mention]:
    """Every "<ratio name> ... <number>x" mention in the text."""
    found: list[Mention] = []
    for ratio, pattern in _NAMES.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            tail = text[match.end() : match.end() + _WINDOW]
            quantity = re.search(_QUANTITY, tail, re.IGNORECASE)
            if quantity is None:
                continue
            basis = _basis(text, match.start(), match.end() + quantity.end())
            label = f"{source}, {basis}" if basis else source
            found.append(Mention(ratio, float(quantity.group("n")), label))
    return found


def _rule_mention(rule: RuleResult) -> Mention | None:
    found = ratio_value_of(rule)
    return Mention(found[0], found[1], "policy rule") if found else None


def ratio_values(
    rules: list[RuleResult], inferences: list[Inference], reasons: list[KeyReason]
) -> dict[str, list[Mention]]:
    """Mentions grouped by ratio; rule results give the policy value."""
    grouped: dict[str, list[Mention]] = {}
    items = [_rule_mention(rule) for rule in rules]
    for inference in inferences:
        items += mentions_in(f"{inference.opinion} {inference.reasoning}", inference.inference_id)
    for reason in reasons:
        items += mentions_in(reason.text, "reason")
    for item in items:
        if item is not None:
            grouped.setdefault(item.ratio, []).append(item)
    return grouped


def conflicting_ratios(grouped: dict[str, list[Mention]]) -> dict[str, str]:
    """Ratio name -> note text for each ratio shown with more than one value at one decimal."""
    notes: dict[str, str] = {}
    for ratio, items in grouped.items():
        if len({round(item.value, 1) for item in items}) < 2:
            continue
        seen: dict[tuple[float, str], Mention] = {}
        for item in items:
            seen.setdefault((round(item.value, 1), item.source), item)
        shown = ", ".join(f"{m.value:g}x ({m.source})" for m in seen.values())
        notes[ratio] = f"Note: {_DISPLAY.get(ratio, ratio)} {NOTE_MARK}: {shown}."
    return notes


def _annotated(text: str, notes: dict[str, str]) -> str:
    if NOTE_MARK in text:
        return text
    names = {m.ratio for m in mentions_in(text, "")}
    extra = [note for ratio, note in notes.items() if ratio in names]
    return " ".join([text, *extra]) if extra else text


def _rule_ratio(rule: RuleResult) -> str | None:
    found = ratio_value_of(rule)
    return found[0] if found else None


def annotate_ratio_definitions(
    inputs: ComposeInputs, recommendation: Recommendation
) -> tuple[ComposeInputs, Recommendation]:
    """Append the different-definitions note to every text that mentions a conflicting ratio."""
    notes = conflicting_ratios(
        ratio_values(inputs.rule_results, inputs.inferences, recommendation.key_reasons)
    )
    if not notes:
        return inputs, recommendation
    rules = [
        rule.model_copy(update={"message": " ".join([rule.message, notes[ratio]])})
        if (ratio := _rule_ratio(rule)) in notes and NOTE_MARK not in rule.message
        else rule
        for rule in inputs.rule_results
    ]
    inferences = [
        inference.model_copy(update={"reasoning": _annotated(inference.reasoning, notes)})
        if inference.reasoning
        else inference.model_copy(update={"opinion": _annotated(inference.opinion, notes)})
        for inference in inputs.inferences
    ]
    reasons = [
        reason.model_copy(update={"text": _annotated(reason.text, notes)})
        for reason in recommendation.key_reasons
    ]
    return (
        replace(inputs, rule_results=rules, inferences=inferences),
        recommendation.model_copy(update={"key_reasons": reasons}),
    )
