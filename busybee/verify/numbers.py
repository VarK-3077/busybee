"""Fill VerifiedFact.numbers: turn the numbers in a statement into labelled NumericValues.

Label is guessed from the few content words just before the number, unit comes from a
following % or magnitude word and the currency mark, and the period is the nearest fiscal
token (FY24, optionally with a leading quarter) within a short distance. Bare calendar
years, fiscal tokens and the day of a date ("31" in "31 March 2025" or "March 31, 2025") are
periods, never values. The label is taken only from the words between the previous number
(including its unit word) and this one, so "crore" of an earlier figure never becomes a label.

`canonical_amount` gives every money value a canonical size in crore (1 crore = 100 lakh =
10 million, 1 billion = 100 crore) tagged with its currency, so "INR 1,68,607.08 lakhs" and
"INR 1,686.07 crore" can be compared; `amounts_match` compares two such values with a relative
tolerance of `AMOUNT_TOLERANCE` (0.05%) to absorb rounding between units.
"""

import re
from decimal import Decimal

from busybee.schema.facts import NumericValue

from .number_match import UNIT_ALIASES, NumberMention, find_numbers

_WORD = re.compile(r"[A-Za-z][A-Za-z&/'-]*")
_QUARTER = re.compile(r"(Q[1-4]|H[12])\s?$", re.IGNORECASE)
_STOPWORDS = frozenset(
    "a an and as at by for from in into is of on or the to was were with its our their "
    "stood rose fell grew reached reported total about around approximately over under "
    "than that this which has have had be been are rs inr usd up down".split()
)
_MONTHS = (
    "jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|"
    "sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
_DAY_BEFORE_MONTH = re.compile(rf"^(?:st|nd|rd|th)?\s+(?:{_MONTHS})\b", re.IGNORECASE)
_DAY_AFTER_MONTH = re.compile(rf"\b(?:{_MONTHS})\.?\s+$", re.IGNORECASE)
_PERIOD_DISTANCE = 60
_YEAR_RANGE = range(1900, 2101)
AMOUNT_TOLERANCE = Decimal("0.0005")
_CRORE_PER_UNIT = {
    "crore": Decimal(1),
    "lakh": Decimal("0.01"),
    "million": Decimal("0.1"),
    "billion": Decimal(100),
    "thousand": Decimal("0.0001"),
}
_CURRENCY_NAMES = {"₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR"}


def _is_bare_year(mention: NumberMention) -> bool:
    return (
        not mention.unit
        and not mention.percent
        and not mention.currency
        and mention.value == mention.value.to_integral_value()
        and int(mention.value) in _YEAR_RANGE
        and len(mention.text) == 4
    )


def _period_label(statement: str, mention: NumberMention) -> str:
    label = re.sub(r"\s+", "", mention.text).upper()
    quarter = _QUARTER.search(statement[: mention.start])
    return f"{quarter.group(1).upper()} {label}" if quarter else label


def _nearest_period(statement: str, periods: list[NumberMention], mention: NumberMention) -> str:
    def gap(period: NumberMention) -> int:
        return max(period.start - mention.end, mention.start - period.end, 0)

    close = [period for period in periods if gap(period) <= _PERIOD_DISTANCE]
    if not close:
        return ""
    return _period_label(statement, min(close, key=gap))


def _is_day_of_month(statement: str, mention: NumberMention) -> bool:
    return (
        not (mention.unit or mention.percent or mention.currency)
        and mention.value == mention.value.to_integral_value()
        and 1 <= int(mention.value) <= 31
        and bool(
            _DAY_BEFORE_MONTH.match(statement[mention.end :])
            or _DAY_AFTER_MONTH.search(statement[: mention.start])
        )
    )


def _label_before(statement: str, mention: NumberMention, floor: int = 0) -> str:
    clause = re.split(r"[.,;:()]", statement[floor : mention.start])[-1]
    words = [word for word in _WORD.findall(clause) if word.lower() not in _STOPWORDS]
    return " ".join(words[-4:]).lower() or "value"


def _unit_of(mention: NumberMention) -> str:
    if mention.percent:
        return "%"
    currency = _CURRENCY_NAMES.get(mention.currency.lower(), "")
    return " ".join(part for part in (currency, mention.unit) if part)


def numeric_values_from(statement: str) -> list[NumericValue]:
    """Return the labelled numbers found in statement, in reading order."""
    mentions = find_numbers(statement)
    periods = [mention for mention in mentions if mention.fiscal]
    years = [mention for mention in mentions if not mention.fiscal and _is_bare_year(mention)]
    values: list[NumericValue] = []
    previous_end = 0
    for mention in mentions:
        floor, previous_end = previous_end, mention.end
        if mention.fiscal or mention in years or _is_day_of_month(statement, mention):
            continue
        values.append(
            NumericValue(
                label=_label_before(statement, mention, floor),
                value=Decimal(mention.value),
                unit=_unit_of(mention),
                period=_nearest_period(statement, [*periods, *years], mention),
            )
        )
    return values


def canonical_amount(value: Decimal, unit: str) -> tuple[str, Decimal] | None:
    """Return (currency, size in crore) for a money value with a magnitude word, else None."""
    words = unit.lower().split()
    for word in words:
        canonical = UNIT_ALIASES.get(word)
        if canonical in _CRORE_PER_UNIT:
            currency = next((w.upper() for w in words if w != word), "")
            return currency, value * _CRORE_PER_UNIT[canonical]
    return None


def amounts_match(first: Decimal, second: Decimal) -> bool:
    """True when two crore amounts differ by at most AMOUNT_TOLERANCE of the larger one."""
    return abs(first - second) <= AMOUNT_TOLERANCE * max(abs(first), abs(second))
