"""Merge duplicate verified facts deterministically, before fact ids are assigned.

Two facts are duplicates when they have the same category, one fact's set of numeric values
is a subset of the other's, their fiscal-year mentions do not conflict (when both name years,
one set of years contains the other, so FY24 and FY25 statements never merge), they are not one
consolidated and one standalone (`VerifiedFact.scope`), and at least one wording test
passes: (a) token Jaccard similarity of the lowercase word sets (punctuation, stopwords, fiscal
years, bare numbers and unit words removed) is at least `JACCARD_THRESHOLD`; (b) the two share at
least `MIN_SHARED_VALUES` numeric values and their subject-word overlap (shared words over the
shorter statement's words; a plain Jaccard would reject a short restatement of a long
sentence) is at least `MIN_SHARED_VALUES_OVERLAP`; (c) the single shared value carries a unit
(a percent
or money unit) and the statements share at least `MIN_SHARED_SUBJECT_TOKENS` such words that
make up at least `MIN_SUBJECT_OVERLAP` of the shorter statement's words, i.e. the same subject
phrase. Money values are compared by their canonical size in crore (`canonical_amount`: lakh,
million and billion are converted) within a 0.05% tolerance, so "INR 1,68,607.08 lakhs" and
"INR 1,686.07 crore" are the same value; other numbers must be equal. Fiscal years are read from
FY tokens ("FY25", "FY 2024-25") and from "year ended <month> <day>, <year>" phrases. A merge
is refused whenever the two statements name different facility or instrument nouns
(term loan, cash credit, GST, contingent, ...) unless both name exactly the same ones. The
later fact folds into the first one that matches. The merged fact keeps the
statement, numbers and category of the richer fact (the one with more values; the earlier one
on a tie), the earlier fact's `source_entry_id` and the higher importance; citations are
unioned by distinct chunk id and the merged entry ids are recorded in `verification.notes`.
Facts without any number are never merged, since matching words alone is too weak a signal.
When both facts carry a structured `record`, none of the above applies: they are duplicates
exactly when metric tokens, period, scope, qualifier and the canonical value agree
(`record_compare`), so no Jaccard similarity is involved.
"""

import re
from collections.abc import Sequence
from decimal import Decimal
from typing import NamedTuple

from busybee.schema.facts import Verification, VerificationStatus, VerifiedFact

from .numbers import amounts_match, canonical_amount
from .record_compare import same_measurement, same_record_value

JACCARD_THRESHOLD = 0.3
MIN_SHARED_VALUES = 2
MIN_SHARED_VALUES_OVERLAP = 0.2
MIN_SHARED_SUBJECT_TOKENS = 2
MIN_SUBJECT_OVERLAP = 0.3
_WORD = re.compile(r"[a-z0-9]+")
_FISCAL_TOKEN = re.compile(r"\b(?:fy|cy)\s?'?(\d{2,4})(?:\s?[-/]\s?(\d{2,4}))?\b")
_YEAR_ENDED = re.compile(
    r"\b(?:year|period|quarter)s?\s+ended\s+(?:\d{1,2}(?:st|nd|rd|th)?\s+)?[a-z]+\.?\s*"
    r"(?:\d{1,2}(?:st|nd|rd|th)?,?\s+)?(\d{4})\b"
)
_INSTRUMENTS = (
    ("term loan", re.compile(r"\bterm loans?\b")),
    ("cash credit", re.compile(r"\bcash credits?\b")),
    ("working capital", re.compile(r"\bworking capital\b")),
    ("non-fund", re.compile(r"\bnon[- ]fund\b")),
    ("bank guarantee", re.compile(r"\bbank guarantees?\b")),
    ("letter of credit", re.compile(r"\bletters? of credit\b")),
    ("contingent", re.compile(r"\bcontingent\b")),
    ("gst", re.compile(r"\bgst\b")),
    ("bond", re.compile(r"\bbonds?\b")),
    ("debenture", re.compile(r"\bdebentures?\b")),
    ("ncd", re.compile(r"\bncds?\b")),
    ("ecb", re.compile(r"\becbs?\b")),
)
_UNIT_WORDS = frozenset(
    "inr rs rupees crore crores lakh lakhs million billion percent times x".split()
)
_STOPWORDS = frozenset(
    "a an and as at by for from in into is it its of on or than that the to was were with "
    "which has have had be been are this their".split()
)


def statement_tokens(statement: str) -> frozenset[str]:
    """Lowercase word set of a statement without punctuation, stopwords and fiscal-year tokens."""
    return frozenset(
        word
        for word in _WORD.findall(_FISCAL_TOKEN.sub(" ", statement.lower()).replace(",", ""))
        if word not in _STOPWORDS
    )


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    """Jaccard similarity of two token sets (0 when both are empty)."""
    union = left | right
    return len(left & right) / len(union) if union else 0.0


class _Amount(NamedTuple):
    kind: str
    value: Decimal


def _amount(value: Decimal, unit: str) -> _Amount:
    money = canonical_amount(value, unit)
    if money is None:
        return _Amount("", value.normalize())
    return _Amount(money[0], money[1].normalize())


def _same_amount(first: _Amount, second: _Amount) -> bool:
    if first.kind != second.kind:
        return False
    return first.value == second.value or (
        bool(first.kind) and amounts_match(first.value, second.value)
    )


def _value_set(fact: VerifiedFact) -> frozenset[_Amount]:
    return frozenset(_amount(number.value, number.unit) for number in fact.numbers)


def _matched(values: frozenset[_Amount], other: frozenset[_Amount]) -> frozenset[_Amount]:
    return frozenset(
        value for value in values if any(_same_amount(value, candidate) for candidate in other)
    )


def fiscal_years(statement: str) -> frozenset[str]:
    """Two-digit closing years named in a statement.

    FY25, FY2024-25, FY2025 and "year ended March 31, 2025" all give '25'.
    """
    lowered = statement.lower()
    return frozenset(
        [(match.group(2) or match.group(1))[-2:] for match in _FISCAL_TOKEN.finditer(lowered)]
        + [match.group(1)[-2:] for match in _YEAR_ENDED.finditer(lowered)]
    )


def _years_compatible(first: str, second: str) -> bool:
    years, other = fiscal_years(first), fiscal_years(second)
    return not years or not other or years <= other or other <= years


def _has_unit(fact: VerifiedFact, value: _Amount) -> bool:
    return any(
        number.unit.strip() and _same_amount(_amount(number.value, number.unit), value)
        for number in fact.numbers
    )


def _subject_tokens(statement: str) -> frozenset[str]:
    return frozenset(
        word
        for word in statement_tokens(statement)
        if len(word) > 1 and not word.isdigit() and word not in _UNIT_WORDS
    )


def instrument_nouns(statement: str) -> frozenset[str]:
    """Facility and instrument nouns (term loan, GST, ...) named in a statement."""
    lowered = statement.lower()
    return frozenset(name for name, pattern in _INSTRUMENTS if pattern.search(lowered))


def _wording_agrees(first: VerifiedFact, second: VerifiedFact, shared: frozenset[_Amount]) -> bool:
    tokens, other = _subject_tokens(first.statement), _subject_tokens(second.statement)
    similarity = jaccard(tokens, other)
    if similarity >= JACCARD_THRESHOLD:
        return True
    if len(shared) >= MIN_SHARED_VALUES:
        smaller = min(len(tokens), len(other))
        return smaller > 0 and len(tokens & other) >= MIN_SHARED_VALUES_OVERLAP * smaller
    (value,) = shared
    with_unit = _has_unit(first, value) or _has_unit(second, value)
    subject = _subject_tokens(first.statement) & _subject_tokens(second.statement)
    smaller = min(len(_subject_tokens(first.statement)), len(_subject_tokens(second.statement)))
    return (
        with_unit
        and len(subject) >= MIN_SHARED_SUBJECT_TOKENS
        and len(subject) >= MIN_SUBJECT_OVERLAP * smaller
    )


def _scopes_compatible(first: VerifiedFact, second: VerifiedFact) -> bool:
    return first.scope is None or second.scope is None or first.scope == second.scope


def are_duplicates(first: VerifiedFact, second: VerifiedFact) -> bool:
    """True when category, value sets, fiscal years and wording all agree (see module doc)."""
    if first.record is not None and second.record is not None:
        return same_measurement(first.record, second.record) and same_record_value(
            first.record, second.record
        )
    values, other = _value_set(first), _value_set(second)
    small, large = (values, other) if len(values) <= len(other) else (other, values)
    return (
        bool(values)
        and bool(other)
        and first.category == second.category
        and _matched(small, large) == small
        and _scopes_compatible(first, second)
        and _years_compatible(first.statement, second.statement)
        and instrument_nouns(first.statement) == instrument_nouns(second.statement)
        and _wording_agrees(first, second, small)
    )


def _entry_label(fact: VerifiedFact) -> str:
    return fact.source_entry_id or fact.fact_id or "?"


def _merged(keeper: VerifiedFact, duplicate: VerifiedFact) -> VerifiedFact:
    seen = {citation.chunk_id for citation in keeper.citations}
    extra = [citation for citation in duplicate.citations if citation.chunk_id not in seen]
    old = keeper.verification or Verification(status=VerificationStatus.supported)
    note = f"merged duplicate {_entry_label(duplicate)}"
    notes = f"{old.notes}; {note}" if old.notes else note
    richer = duplicate if len(_value_set(duplicate)) > len(_value_set(keeper)) else keeper
    return keeper.model_copy(
        update={
            "statement": richer.statement,
            "numbers": richer.numbers,
            "citations": [*keeper.citations, *extra],
            "importance": max(keeper.importance, duplicate.importance),
            "scope": richer.scope or keeper.scope or duplicate.scope,
            "record": richer.record,
            "verification": old.model_copy(update={"notes": notes}),
        }
    )


def dedupe_facts(facts: Sequence[VerifiedFact]) -> list[VerifiedFact]:
    """Return facts with duplicates folded into their first occurrence, order preserved."""
    kept: list[VerifiedFact] = []
    for fact in facts:
        for index, keeper in enumerate(kept):
            if are_duplicates(keeper, fact):
                kept[index] = _merged(keeper, fact)
                break
        else:
            kept.append(fact)
    return kept
