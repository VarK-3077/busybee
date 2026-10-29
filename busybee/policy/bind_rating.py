"""Bind a categorical slot (an external rating grade) to its bank index without the model.

The policy's table (`InputSlot.mapping`, e.g. AAA = 1 ... A = 6 ... D = 22) is the only
authority on the index. `rating_binding` scans fact statements that talk about a rating for a
long-term grade from that table, written as `[ICRA]A (Negative)`, `'A+'`, `AA-/Stable` and so
on. A bare single letter (A, B, C, D) counts only when it is bracketed, quoted or followed by
an outlook in parentheses or a slash, so ordinary prose ("A downgrade", "Plant C") never
matches, and short-term grades such as A1+ or A2 never match because digits cannot follow a
grade. Inside one statement the grade after the last "to"/"at"/"of" wins (the end of a
downgrade chain), and text after a short-term mention is ignored. Across statements the one
with the latest month-year or year wins, ties going to the worse (higher) index; the other
grades seen are named in the binding note. The result is a `BoundInput` citing that fact, or
None when no fact states a grade, in which case the caller may ask the model.
"""

import re
from decimal import Decimal

from busybee.schema.facts import VerifiedFact
from busybee.schema.policy import BoundInput, InputSlot

_RATING_CONTEXT = re.compile(
    r"\brat(?:ing|ed|ings)\b|\bICRA\b|\bCRISIL\b|\bCARE\b|\bAcuit[eé]\b|\bBrickwork\b|\bIND-?Ra\b",
    re.IGNORECASE,
)
_SHORT_TERM = re.compile(r"short[- ]term", re.IGNORECASE)
_LONG_TERM = re.compile(r"long[- ]term", re.IGNORECASE)
_INTRODUCER = re.compile(r"(?:\bto|\bat|\bof|\bas|→)\s*\W{0,3}\w*\W{0,3}$", re.IGNORECASE)
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()
_DATE = re.compile(
    r"(?:(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2},?\s+)?)?"
    r"\b(20\d{2})\b",
    re.IGNORECASE,
)


def _grade_pattern(grades: list[str]) -> re.Pattern[str]:
    ordered = sorted(grades, key=len, reverse=True)
    alternatives = "|".join(re.escape(grade) for grade in ordered)
    return re.compile(rf"(?<![A-Za-z0-9+\-])({alternatives})(?![A-Za-z0-9+\-])")


def _long_term_text(statement: str) -> str:
    """The part of a statement about the long-term rating, or '' for a short-term-only one."""
    long_term = _LONG_TERM.search(statement)
    short_term = _SHORT_TERM.search(statement)
    if short_term is None:
        return statement
    if long_term is None or short_term.start() < long_term.start():
        return ""
    return statement[: short_term.start()]


def _accepted(match: re.Match[str], text: str) -> bool:
    grade = match.group(1)
    if len(grade) > 1:
        return True
    before, after = text[: match.start()], text[match.end() :]
    return bool(
        before.endswith(("]", "'", '"', "‘", "“"))
        or after.startswith(("'", '"', "’", "”"))
        or re.match(r"\s*[(/\[]", after)
    )


def grades_in(statement: str, grades: list[str]) -> list[str]:
    """Long-term rating grades named in a statement, in reading order (empty if none)."""
    if not _RATING_CONTEXT.search(statement):
        return []
    text = _long_term_text(statement)
    pattern = _grade_pattern(grades)
    return [m.group(1) for m in pattern.finditer(text) if _accepted(m, text)]


def _final_grade(statement: str, grades: list[str]) -> str | None:
    """The grade a statement ends on: the last one introduced by to/at/of, else the last."""
    text = _long_term_text(statement)
    pattern = _grade_pattern(grades)
    found = [m for m in pattern.finditer(text) if _accepted(m, text)]
    if not found:
        return None
    introduced = [m for m in found if _INTRODUCER.search(text[max(0, m.start() - 16) : m.start()])]
    return (introduced or found)[-1].group(1)


def _date_key(statement: str) -> tuple[int, int]:
    best = (0, 0)
    for month, year in _DATE.findall(statement):
        key = (int(year), _MONTHS.index(month.lower()[:3]) + 1 if month else 0)
        best = max(best, key)
    return best


def rating_binding(slot: InputSlot, facts: list[VerifiedFact]) -> BoundInput | None:
    """Bind the slot to the index of the latest long-term grade facts state, or None."""
    grades = list(slot.mapping)
    candidates = []
    for fact in facts:
        grade = _final_grade(fact.statement, grades) if grades_in(fact.statement, grades) else None
        if grade is not None:
            candidates.append((fact, grade))
    if not candidates:
        return None
    fact, grade = max(
        candidates, key=lambda item: (_date_key(item[0].statement), slot.mapping[item[1]])
    )
    index = slot.mapping[grade]
    others = sorted({g for _, g in candidates if g != grade}, key=lambda g: slot.mapping[g])
    note = f"rating {grade} maps to index {index} in the policy table"
    if others:
        note += f"; other grades named in the facts: {', '.join(others)}"
    return BoundInput(
        slot=slot.slot,
        fact_id=fact.fact_id,
        value=Decimal(index),
        unit=slot.unit,
        value_scaled=index * slot.scale,
        note=note,
    )
