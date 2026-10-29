"""Deterministic verification of a structured fact record against its cited chunk.

`record_match_quote(record, chunk_text)` returns the verbatim line that proves the record, or
None. The record passes when, in the chunk text (table header prefix included): (1) the current
value, and the previous value when the record has one, occurs as a number on a line whose words
cover at least `MIN_LABEL_COVERAGE` (60%) of the metric label's content tokens; (2) the record's
unit word (crore, lakh, million, billion, %, x) occurs within `UNIT_WINDOW` characters of that
value or, when the unit is stated only once for the whole table, is the only such unit word in
the chunk (a bare currency such as Rs needs no unit word); (3) the record's period, and the
previous period if given, is a fiscal token of the chunk (FY2024-25 and FY25 agree) or, for any
other period, appears in it verbatim. A failure here only means the entry goes to the LLM
entailment path with its templated statement; it is never a rejection by itself.
"""

import re
from decimal import Decimal

from busybee.extract.templates import unit_label
from busybee.schema.facts import FactRecord

from .number_match import UNIT_ALIASES, NumberMention, find_numbers
from .record_compare import metric_tokens, periods_in

MIN_LABEL_COVERAGE = 0.6
UNIT_WINDOW = 120
METHOD_RECORD_MATCH = "record_match"
_UNIT_WORD = re.compile(r"\b(crores?|crs?|lakhs?|lacs?|millions?|mn|billions?|bn)\b|%|(?<=\d)x\b")


def _unit_words(text: str) -> set[str]:
    return {
        "%"
        if match.group(0) == "%"
        else "x"
        if match.group(0) == "x"
        else UNIT_ALIASES[match.group(0).lower()]
        for match in _UNIT_WORD.finditer(text)
    }


def _wanted_unit(unit: str) -> str:
    last = unit_label(unit).split()[-1] if unit_label(unit) else ""
    return last if last in {"%", "x", "crore", "lakh", "million", "billion"} else ""


def _line_bounds(text: str, mention: NumberMention) -> tuple[int, int]:
    start = text.rfind("\n", 0, mention.start) + 1
    end = text.find("\n", mention.end)
    return start, len(text) if end < 0 else end


def _covers_label(line: str, tokens: frozenset[str]) -> bool:
    if not tokens:
        return False
    found = metric_tokens(line)
    return len(tokens & found) >= MIN_LABEL_COVERAGE * len(tokens)


def _unit_ok(text: str, mention: NumberMention, wanted: str) -> bool:
    if not wanted:
        return True
    around = text[max(0, mention.start - UNIT_WINDOW) : mention.end + UNIT_WINDOW]
    near = _unit_words(around)
    if near:
        return wanted in near
    return _unit_words(text) == {wanted}


def _value_line(record_value: Decimal, record: FactRecord, text: str) -> str | None:
    tokens = metric_tokens(record.metric)
    wanted = _wanted_unit(record.unit)
    for mention in find_numbers(text):
        if mention.fiscal or abs(mention.value) != abs(record_value):
            continue
        start, end = _line_bounds(text, mention)
        line = text[start:end]
        if _covers_label(line, tokens) and _unit_ok(text, mention, wanted):
            return line.strip()
    return None


def _period_ok(period: str, text: str) -> bool:
    if not period.strip():
        return True
    fiscal = periods_in(period)
    if fiscal:
        return bool(fiscal & periods_in(text))
    return " ".join(period.lower().split()) in " ".join(text.lower().split())


def record_match_quote(record: FactRecord, chunk_text: str) -> str | None:
    """The verbatim chunk line holding the record's value, or None when any check fails."""
    if not _period_ok(record.period, chunk_text):
        return None
    quote = _value_line(record.value, record, chunk_text)
    if quote is None:
        return None
    if record.previous_value is not None:
        if not _period_ok(record.previous_period or "", chunk_text):
            return None
        if _value_line(record.previous_value, record, chunk_text) is None:
            return None
    return quote
