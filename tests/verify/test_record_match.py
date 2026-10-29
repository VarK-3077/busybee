"""Deterministic record verification: pass, unit, period and label mismatches, and the flow."""

from decimal import Decimal

import pytest

from busybee.extract.templates import statement_from_record
from busybee.schema.facts import FactRecord, NotebookEntry
from busybee.verify.record_match import record_match_quote
from busybee.verify.verify_entries import VerifyContext, verify_entries

from .helpers import judge_provider, make_chunk, make_entry

TABLE_TEXT = (
    "Balance sheet as at 31 March 2025\nParticulars (Rs crore)\n"
    "[TABLE: FY2024-25 | FY2023-24]\n"
    "Total borrowings | FY2024-25: 412.6 | FY2023-24: 380.1\n"
    "Current assets | FY2024-25: 640.0 | FY2023-24: 590.4\n[/TABLE]"
)


def _record(**changes: object) -> FactRecord:
    base = {
        "metric": "Total borrowings",
        "value": Decimal("412.6"),
        "unit": "crore",
        "period": "FY2024-25",
        "previous_value": Decimal("380.1"),
        "previous_period": "FY2023-24",
    }
    return FactRecord.model_validate(base | changes)


def test_record_passes_and_quotes_the_row() -> None:
    quote = record_match_quote(_record(), TABLE_TEXT)
    assert quote == "Total borrowings | FY2024-25: 412.6 | FY2023-24: 380.1"
    assert quote in TABLE_TEXT


def test_period_may_be_written_in_another_form() -> None:
    assert record_match_quote(_record(period="FY25", previous_period="FY24"), TABLE_TEXT)


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "lakh"},
        {"period": "FY2022-23"},
        {"metric": "Total reserves and surplus"},
        {"value": Decimal("412.7")},
        {"previous_value": Decimal("1.0")},
        {"metric": "Current assets"},
    ],
)
def test_mismatches_fail(changes: dict[str, object]) -> None:
    assert record_match_quote(_record(**changes), TABLE_TEXT) is None


def test_value_on_another_rows_line_fails_the_label_check() -> None:
    assert record_match_quote(_record(value=Decimal("640.0")), TABLE_TEXT) is None


def test_label_needs_sixty_percent_of_content_tokens() -> None:
    assert record_match_quote(_record(metric="Total borrowings (net of cash)"), TABLE_TEXT) is None
    assert record_match_quote(_record(metric="Borrowings"), TABLE_TEXT)


def test_percent_and_multiple_units() -> None:
    text = (
        "Ratios\n[TABLE: FY25]\nEBITDA margin | FY25: 14.2 %\nInterest cover | FY25: 2.4x\n[/TABLE]"
    )
    margin = FactRecord(metric="EBITDA margin", value=Decimal("14.2"), unit="%", period="FY25")
    cover = FactRecord(metric="Interest cover", value=Decimal("2.4"), unit="x", period="FY25")
    assert record_match_quote(margin, text) and record_match_quote(cover, text)
    assert record_match_quote(margin.model_copy(update={"unit": "crore"}), text) is None


def _entry(record: FactRecord) -> NotebookEntry:
    entry = make_entry("D1:E001", statement_from_record(record))
    return entry.model_copy(update={"record": record})


async def test_verify_uses_record_match_without_any_entailment_call() -> None:
    provider = judge_provider(supports=lambda statement, passage: False)
    ctx = VerifyContext(
        provider=provider,
        chunks_by_id={"D1:p1:c0": make_chunk("D1:p1:c0", TABLE_TEXT)},
        store=None,
        embedder=None,
    )
    facts, dropped = await verify_entries([_entry(_record())], ctx, check_relevance=False)
    assert dropped == []
    fact = facts[0]
    assert fact.verification is not None and fact.verification.method == "record_match"
    assert fact.record is not None and fact.numbers[0].label == "Total borrowings"
    assert provider.calls == []


async def test_failed_record_falls_through_to_the_llm_path_with_the_templated_statement() -> None:
    provider = judge_provider(supports=lambda statement, passage: True)
    ctx = VerifyContext(
        provider=provider,
        chunks_by_id={"D1:p1:c0": make_chunk("D1:p1:c0", TABLE_TEXT)},
        store=None,
        embedder=None,
    )
    record = _record(period="FY2024-25", unit="lakh")
    facts, _ = await verify_entries([_entry(record)], ctx, check_relevance=False)
    assert provider.calls
    assert facts[0].verification is not None
    assert facts[0].verification.method != "record_match"
    assert facts[0].statement == statement_from_record(record)
