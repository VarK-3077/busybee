"""Minimum-standard rules (the policy's ratio-threshold section) and their headline wording.

A rule belongs to the minimum standards when its message says "minimum standard". When such a
rule fails, compose recommends "Reduce the credit line or decline". `criterion_text` states one
failed criterion as "<ratio> <value> is below|above the <threshold> minimum", reading the
measure, `computed_value` and `threshold` ("at least 2.5x") from the rule result when it carries
them (`getattr` defaults) and otherwise computing the ratio from the inputs' `value_scaled`
(all slots of one rule share a scale) and the threshold from the rule message; without a value
the criterion is named alone. A rule carrying a `caution_reason` ("missing component(s): a, b; ...")
gets the qualifier "(computed without a and b)". `minimum_headline` joins the failed criteria after
the decision label and may add the model's proposed limit as a second sentence, only when a maximum
exposure is known, above zero, and the amount does not exceed it. When the maximum exposure could
not be computed or is zero, `limit_note` is the sentence that says so and no amount is stated.
"""

import re
from decimal import Decimal

from busybee.schema.policy import RuleResult, RuleStatus

REDUCE_LABEL = "Reduce the credit line or decline"
_RATIOS = (
    ({"ebitda", "interest_expense"}, "ebitda", "interest_expense", "Interest coverage"),
    ({"cfads", "debt_service"}, "cfads", "debt_service", "DSCR"),
    (
        {"current_assets", "current_liabilities"},
        "current_assets",
        "current_liabilities",
        "Current ratio",
    ),
    ({"net_debt", "ebitda"}, "net_debt", "ebitda", "Net debt / EBITDA"),
    ({"total_debt", "total_equity"}, "total_debt", "total_equity", "Debt / equity"),
)
_THRESHOLD = re.compile(r"(\d+(?:\.\d+)?)\s*(x|%)\s*minimum standard", re.IGNORECASE)
_LIMIT_WORDS = re.compile(r"(at least|at most)\s+(\S+)", re.IGNORECASE)
_MISSING = re.compile(r"missing component\(s\):\s*([^;]+)", re.IGNORECASE)
_AMOUNT = re.compile(r"INR\s*(\d+(?:\.\d+)?)\s*crore", re.IGNORECASE)
_PERCENT = re.compile(r"more than (\d+(?:\.\d+)?)\s*%", re.IGNORECASE)


def is_minimum_standard(result: RuleResult) -> bool:
    """Whether the rule is a minimum-standard (ratio threshold) rule."""
    return "minimum standard" in result.message.lower()


def failed_minimums(results: list[RuleResult]) -> list[RuleResult]:
    """The minimum-standard rules whose status is fail."""
    return [r for r in results if r.status is RuleStatus.fail and is_minimum_standard(r)]


def _scaled(result: RuleResult) -> dict[str, int]:
    return {item.slot: item.value_scaled for item in result.inputs}


def _ratio(result: RuleResult) -> tuple[str, str | None, bool]:
    """(criterion name, formatted value or None, is_percent) from the inputs' scaled values."""
    slots = _scaled(result)
    for needed, top, bottom, name in _RATIOS:
        if needed <= set(slots):
            if slots[bottom] > 0:
                return name, f"{Decimal(slots[top]) / Decimal(slots[bottom]):.2f}x", False
            return name, None, False
    if {"revenue_current", "revenue_previous"} <= set(slots):
        previous = slots["revenue_previous"]
        if previous > 0:
            change = (Decimal(slots["revenue_current"]) / Decimal(previous) - 1) * 100
            return "Revenue growth", f"{change:.1f}%", True
        return "Revenue growth", None, True
    return result.name, None, False


def ratio_value_of(result: RuleResult) -> tuple[str, float] | None:
    """(ratio name, computed value) of a ratio rule in x terms, else None."""
    name, value, percent = _ratio(result)
    if value is None or percent or name == result.name:
        return None
    return name.lower(), float(value.rstrip("x"))


def _limit(result: RuleResult, percent: bool) -> str | None:
    """The limit as "below the 2.5x minimum" / "above the 4.5x maximum", else None."""
    explicit = getattr(result, "threshold", "")
    if explicit:
        match = _LIMIT_WORDS.search(explicit)
        if match:
            least = match.group(1).lower() == "at least"
            side, kind = ("below", "minimum") if least else ("above", "maximum")
            return f"{side} the {match.group(2)} {kind}"
        return f"outside the {explicit} standard"
    if percent:
        found = _PERCENT.search(result.message)
        return f"below the -{found.group(1)}% minimum" if found else None
    found = _THRESHOLD.search(result.message)
    if not found:
        return None
    above = result.rule_id.endswith("_max")
    return f"{'above' if above else 'below'} the {found.group(1)}{found.group(2).lower()} " + (
        "maximum" if above else "minimum"
    )


def _qualifier(result: RuleResult) -> str:
    """The "(computed without a, b and c)" note from the caution reason's components, else empty."""
    found = _MISSING.search(getattr(result, "caution_reason", ""))
    if not found:
        return ""
    parts = [part.strip() for part in found.group(1).split(",") if part.strip()]
    joined = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    return f" (computed without {joined})" if parts else ""


def criterion_text(result: RuleResult) -> str:
    """One failed criterion with its computed value, the minimum and any missing-component note."""
    return _criterion(result) + _qualifier(result)


def _criterion(result: RuleResult) -> str:
    name, value, percent = _ratio(result)
    name = getattr(result, "measure", "") or name
    value = getattr(result, "computed_value", "") or value
    limit = _limit(result, percent)
    if not value:
        return f"{name} fails its minimum standard"
    if limit is None:
        return f"{name} {value} fails its minimum standard"
    return f"{name} {value} is {limit}"


def limit_sentence(texts: list[str], max_exposure: Decimal | None, limit_note: str = "") -> str:
    """The " Proposed limit: INR X crore." sentence for an amount within the maximum exposure."""
    if limit_note:
        return f" {limit_note}"
    if max_exposure is None or max_exposure <= 0:
        return ""
    for text in texts:
        found = _AMOUNT.search(text or "")
        if found:
            amount = Decimal(found.group(1))
            return f" Proposed limit: INR {found.group(1)} crore." if amount <= max_exposure else ""
    return ""


def minimum_headline(
    results: list[RuleResult],
    model_texts: list[str] | None = None,
    max_exposure: Decimal | None = None,
    limit_note: str = "",
) -> str:
    """ "Reduce the credit line or decline: <criterion>; <criterion>." plus an allowed limit."""
    criteria = [criterion_text(r) for r in failed_minimums(results)]
    head = f"{REDUCE_LABEL}: {'; '.join(criteria)}" if criteria else REDUCE_LABEL
    limit = limit_sentence(model_texts or [], max_exposure, limit_note)
    return f"{head.rstrip('.')}.{limit}" if limit else head
