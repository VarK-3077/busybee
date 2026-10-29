"""Statement templating and category guessing for structured fact records."""

from decimal import Decimal

import pytest

from busybee.extract.record_category import category_from_metric
from busybee.extract.templates import indian_number, record_numbers, statement_from_record
from busybee.schema.facts import FactCategory, FactRecord, FactScope


def test_the_documented_example_sentence() -> None:
    record = FactRecord(
        metric="Revenue from operations",
        value=Decimal("1845.32"),
        unit="crore",
        period="FY2025-26",
        scope=FactScope.consolidated,
        previous_value=Decimal("1664.92"),
        previous_period="FY2024-25",
    )
    assert statement_from_record(record) == (
        "Consolidated revenue from operations was INR 1,845.32 crore in FY2025-26 "
        "(FY2024-25: INR 1,664.92 crore)."
    )
    assert statement_from_record(record) == statement_from_record(record.model_copy())


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("5", "5"),
        ("999.5", "999.5"),
        ("1234", "1,234"),
        ("168607.08", "1,68,607.08"),
        ("12345678", "1,23,45,678"),
        ("-1234567.5", "-12,34,567.5"),
    ],
)
def test_indian_grouping(value: str, text: str) -> None:
    assert indian_number(Decimal(value)) == text


def test_units_scope_qualifier_and_date_periods() -> None:
    percent = FactRecord(metric="EBITDA margin", value=Decimal("14.2"), unit="%", period="FY25")
    assert statement_from_record(percent) == "EBITDA margin was 14.2% in FY25."
    times = FactRecord(
        metric="Interest coverage",
        value=Decimal("2.4"),
        unit="x",
        period="31 March 2025",
        scope=FactScope.standalone,
        qualifier="as restated",
    )
    assert statement_from_record(times) == (
        "Standalone interest coverage was 2.4x as at 31 March 2025, as restated."
    )
    lakh = FactRecord(metric="Total borrowings", value=Decimal("-250"), unit="Rs lakh")
    assert statement_from_record(lakh) == "Total borrowings was -INR 250 lakh."


def test_record_numbers_carry_current_then_previous_value() -> None:
    record = FactRecord(
        metric="Net worth",
        value=Decimal("10"),
        unit="Rs crore",
        period="FY25",
        previous_value=Decimal("9"),
        previous_period="FY24",
    )
    numbers = record_numbers(record)
    assert [(n.value, n.unit, n.period) for n in numbers] == [
        (Decimal("10"), "INR crore", "FY25"),
        (Decimal("9"), "INR crore", "FY24"),
    ]


@pytest.mark.parametrize(
    ("metric", "category"),
    [
        ("Revenue from operations", FactCategory.revenue),
        ("EBITDA (excluding other income)", FactCategory.profitability),
        ("Profit after tax", FactCategory.profitability),
        ("PAT margin", FactCategory.profitability),
        ("Total borrowings", FactCategory.debt_leverage),
        ("Current assets", FactCategory.liquidity),
        ("Net cash flow from operating activities", FactCategory.cash_flow),
        ("Number of employees", FactCategory.other),
    ],
)
def test_category_from_metric(metric: str, category: FactCategory) -> None:
    assert category_from_metric(metric) is category
