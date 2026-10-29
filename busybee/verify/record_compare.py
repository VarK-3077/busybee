"""Field-wise comparison of structured fact records, shared by dedupe, conflicts and record_match.

Two records describe the same measurement when their metric tokens (lowercase content words with
a trailing plural s removed, stopwords and unit words dropped) are equal, their canonical
periods are equal (FY2024-25, FY25 and FY2025 all give FY25; a quarter prefix is kept; any other
period is compared as lowercase words) and their scopes and qualifiers are equal. Values are
compared in canonical form: money converts to crore (lakh, million, billion) with the 0.05%
tolerance of `amounts_match`, every other unit compares as written within the same unit label.
There is no fuzzy wording step: a record fact is never merged on Jaccard similarity.
"""

import re
from decimal import Decimal

from busybee.extract.templates import unit_label
from busybee.schema.facts import FactRecord

from .numbers import amounts_match, canonical_amount

_WORD = re.compile(r"[a-z0-9]+")
_FISCAL = re.compile(
    r"\b(?:(q[1-4]|h[12])\s?)?(?:fy|cy)\s?'?(\d{2,4})(?:\s?[-/–]\s?(\d{2,4}))?\b", re.IGNORECASE
)
_STOPWORDS = frozenset("a an and as at by for from in of on or the to with total".split())
_UNIT_WORDS = frozenset("inr rs rupees crore crores lakh lakhs million billion".split())


def metric_tokens(metric: str) -> frozenset[str]:
    """Content words of a metric label, plural s removed ("borrowings" and "borrowing" agree)."""
    words = (word for word in _WORD.findall(metric.lower()) if word not in _UNIT_WORDS)
    return frozenset(
        word.removesuffix("s") if len(word) > 3 else word
        for word in words
        if word not in _STOPWORDS
    )


def canonical_period(period: str) -> str:
    """FY25 / Q1 FY25 for fiscal tokens, else the lowercase words of the period."""
    match = _FISCAL.search(period)
    if match is None:
        return " ".join(_WORD.findall(period.lower()))
    quarter, first, second = match.groups()
    year = (second or first)[-2:]
    return f"{quarter.upper()} FY{year}" if quarter else f"FY{year}"


def periods_in(text: str) -> frozenset[str]:
    """Canonical fiscal periods named anywhere in text."""
    return frozenset(canonical_period(match.group(0)) for match in _FISCAL.finditer(text))


def canonical_value(value: Decimal, unit: str) -> tuple[str, Decimal]:
    """(kind, size): money in crore tagged with the currency, other units tagged by label."""
    money = canonical_amount(value, unit_label(unit))
    if money is None:
        return unit_label(unit), value
    return money[0] or "INR", money[1]


def same_value(first: tuple[str, Decimal], second: tuple[str, Decimal]) -> bool:
    """True when two canonical values have the same kind and equal size (money with tolerance)."""
    if first[0] != second[0]:
        return False
    if first[1] == second[1]:
        return True
    return first[0] in {"INR", "USD"} and amounts_match(first[1], second[1])


def same_measurement(first: FactRecord, second: FactRecord) -> bool:
    """True when metric, period, scope and qualifier agree (the values may still differ)."""
    return (
        bool(metric_tokens(first.metric))
        and metric_tokens(first.metric) == metric_tokens(second.metric)
        and canonical_period(first.period) == canonical_period(second.period)
        and first.scope == second.scope
        and (first.qualifier or "").casefold() == (second.qualifier or "").casefold()
    )


def same_record_value(first: FactRecord, second: FactRecord) -> bool:
    """True when the two current values are equal in canonical form."""
    return same_value(
        canonical_value(first.value, first.unit), canonical_value(second.value, second.unit)
    )
