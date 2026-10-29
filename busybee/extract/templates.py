"""Deterministic sentences for structured fact records.

`statement_from_record(record)` writes the fact sentence from a `FactRecord`, so the model only
supplies fields: "Consolidated revenue from operations was INR 1,845.32 crore in FY2025-26
(FY2024-25: INR 1,664.92 crore)." Numbers use Indian digit grouping (12,34,567.80) with the
decimals exactly as the record holds them; a money unit (crore, lakh, million, billion, or a bare
Rs/INR/USD) is written "INR <value> <magnitude>", a percentage "<value>%", a multiple
"<value>x", any other unit after the number. A record under Non Current/Current Assets or
Liabilities (`record.section`) carries that in the metric: "Standalone non-current
investments". A scope is written before the metric
("Consolidated ..."), a qualifier after the figures (", as restated"), and a date period is
introduced with "as at" instead of "in". `unit_label` gives the canonical unit text used in
`NumericValue.unit` ("INR crore", "%", "x"), and `record_numbers` the labelled numbers of a
record (current value first, then the previous one) so code never re-parses its own sentence.
"""

import re
from decimal import Decimal

from busybee.schema.facts import FactRecord, NumericValue

from .sections import section_phrase

_MAGNITUDES = {
    "crore": "crore",
    "crores": "crore",
    "cr": "crore",
    "lakh": "lakh",
    "lakhs": "lakh",
    "lac": "lakh",
    "lacs": "lakh",
    "million": "million",
    "millions": "million",
    "mn": "million",
    "billion": "billion",
    "billions": "billion",
    "bn": "billion",
}
_CURRENCIES = {"rs": "INR", "rs.": "INR", "inr": "INR", "₹": "INR", "usd": "USD", "$": "USD"}
_PERCENT_WORDS = frozenset({"%", "percent", "per cent", "pct"})
_TIMES_WORDS = frozenset({"x", "times", "×"})
_DATE_PERIOD = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b|\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
    re.IGNORECASE,
)


def _unit_parts(unit: str) -> tuple[str, str]:
    """Split a printed unit into (currency, magnitude); both empty for non-money units."""
    currency, magnitude = "", ""
    for word in re.findall(r"[^\s,()]+", unit.lower()):
        currency = _CURRENCIES.get(word, currency)
        magnitude = _MAGNITUDES.get(word, magnitude)
    return currency, magnitude


def _kind(unit: str) -> str:
    lowered = unit.strip().lower()
    if lowered in _PERCENT_WORDS:
        return "percent"
    if lowered in _TIMES_WORDS:
        return "times"
    currency, magnitude = _unit_parts(unit)
    return "money" if currency or magnitude else "other"


def unit_label(unit: str) -> str:
    """Canonical unit text: "INR crore", "%", "x", or the printed unit when it is neither."""
    kind = _kind(unit)
    if kind == "percent":
        return "%"
    if kind == "times":
        return "x"
    if kind == "money":
        currency, magnitude = _unit_parts(unit)
        return " ".join(part for part in (currency or "INR", magnitude) if part)
    return unit.strip()


def indian_number(value: Decimal) -> str:
    """Format with Indian grouping (last three digits, then pairs), keeping the decimals."""
    text = format(value, "f")
    sign = "-" if text.startswith("-") else ""
    whole, _, fraction = text.lstrip("-").partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        pairs = [head[max(0, i - 2) : i] for i in range(len(head), 0, -2)][::-1]
        whole = ",".join([*pairs, tail])
    return f"{sign}{whole}.{fraction}" if fraction else f"{sign}{whole}"


def _figure(value: Decimal, unit: str) -> str:
    number = indian_number(abs(value))
    sign = "-" if value < 0 else ""
    kind = _kind(unit)
    if kind == "percent":
        return f"{sign}{number}%"
    if kind == "times":
        return f"{sign}{number}x"
    if kind == "money":
        return f"{sign}{_money_prefix(unit)} {number}{_magnitude(unit)}"
    return f"{sign}{number} {unit.strip()}".strip()


def _money_prefix(unit: str) -> str:
    return _unit_parts(unit)[0] or "INR"


def _magnitude(unit: str) -> str:
    magnitude = _unit_parts(unit)[1]
    return f" {magnitude}" if magnitude else ""


def _metric_phrase(record: FactRecord) -> str:
    metric = record.metric.strip()
    side = section_phrase(record.section)
    if side and not re.search(r"\bcurrent\b", metric, re.IGNORECASE):
        head = metric[:1].lower() if metric[1:2].islower() else metric[:1]
        metric = f"{side} {head}{metric[1:]}"
    if record.scope is None:
        return metric[:1].upper() + metric[1:]
    first = metric.split(" ", 1)[0]
    lowered = metric if first[1:].lower() != first[1:] else metric[:1].lower() + metric[1:]
    return f"{record.scope.value.capitalize()} {lowered}"


def _lead(period: str) -> str:
    return "as at" if _DATE_PERIOD.search(period) else "in"


def statement_from_record(record: FactRecord) -> str:
    """The one-sentence statement for a record, identical for identical records."""
    sentence = f"{_metric_phrase(record)} was {_figure(record.value, record.unit)}"
    if record.period.strip():
        sentence += f" {_lead(record.period)} {record.period.strip()}"
    if record.previous_value is not None:
        previous = _figure(record.previous_value, record.unit)
        label = (record.previous_period or "").strip() or "previous period"
        sentence += f" ({label}: {previous})"
    if record.qualifier and record.qualifier.strip():
        sentence += f", {record.qualifier.strip()}"
    return sentence + "."


def record_numbers(record: FactRecord) -> list[NumericValue]:
    """Labelled numbers of a record: the current value, then the previous value if present."""
    unit = unit_label(record.unit)
    numbers = [
        NumericValue(label=record.metric, value=record.value, unit=unit, period=record.period)
    ]
    if record.previous_value is not None:
        numbers.append(
            NumericValue(
                label=record.metric,
                value=record.previous_value,
                unit=unit,
                period=record.previous_period or "",
            )
        )
    return numbers
