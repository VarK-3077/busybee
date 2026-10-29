"""Exhaustive deterministic number extraction and statement-versus-citation matching."""

from decimal import Decimal

import pytest

from busybee.verify.number_match import extract_numbers, statement_numbers_supported


def D(*values: str) -> list[Decimal]:
    return [Decimal(value) for value in values]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("revenue 1,23,456.78", D("123456.78")),
        ("revenue 1,234,567", D("1234567")),
        ("revenue 123456", D("123456")),
        ("grew 12%", D("12")),
        ("grew 12.5 %", D("12.5")),
        ("loss of (123.4)", D("-123.4")),
        ("loss of -45", D("-45")),
        ("₹5,000", D("5000")),
        ("Rs. 5,000", D("5000")),
        ("5 crore", D("5", "50000000")),
        ("5 cr", D("5", "50000000")),
        ("2.5 lakhs", D("2.5", "250000")),
        ("40 million", D("40", "40000000")),
        ("40 mn", D("40", "40000000")),
        ("1.5 billion", D("1.5", "1500000000")),
        ("1.5bn", D("1.5", "1500000000")),
        ("in 2024", D("2024")),
        ("FY24", D("24", "2024")),
        ("FY2024-25", D("2024", "25", "2025")),
        ("chunk D1:p214:c2", []),
        ("Q3 results", []),
        ("range 10-12", D("10", "12")),
        ("ends here 7.", D("7")),
    ],
)
def test_extract_numbers(text: str, expected: list[Decimal]) -> None:
    assert extract_numbers(text) == expected


def test_grouping_styles_match_each_other() -> None:
    assert statement_numbers_supported("Revenue was 1,23,456.78", "revenue: 123,456.78")[0]
    assert statement_numbers_supported("Revenue was 123456.78", "revenue: 1,23,456.78")[0]


def test_decimal_formatting_is_tolerant() -> None:
    assert statement_numbers_supported("margin 12%", "margin was 12.0 %")[0]


def test_units_are_normalised() -> None:
    assert statement_numbers_supported("Debt of Rs 5 crore", "Debt 50,00,000 ... 5,00,00,000")[0]
    assert statement_numbers_supported("Debt of 50 million", "Debt of 5 crore")[0]
    assert statement_numbers_supported("Debt of 5 crore", "Debt of 50 million")[0]


def test_negative_parentheses_match_negative_sign() -> None:
    assert statement_numbers_supported("loss of (123.4)", "net loss -123.4")[0]
    assert statement_numbers_supported("loss of 123.4", "net loss (123.4)")[0]


def test_years_matched_as_plain_tokens() -> None:
    assert statement_numbers_supported("In 2024 revenue rose", "Year ended 2024")[0]
    ok, missing = statement_numbers_supported("In 2023 revenue rose", "Year ended 2024")
    assert not ok
    assert missing == ["2023"]


def test_fiscal_year_two_digit_matches_four_digit() -> None:
    assert statement_numbers_supported("FY24 revenue", "FY2024 revenue")[0]


def test_missing_number_is_detected_and_reported() -> None:
    ok, missing = statement_numbers_supported("Debt is 500 and revenue is 900", "Debt is 500")
    assert not ok
    assert missing == ["900"]


def test_statement_without_numbers_passes() -> None:
    assert statement_numbers_supported("The company is profitable", "anything") == (True, [])


def test_period_adjacency_rejects_number_far_from_any_period() -> None:
    from busybee.verify.number_match import statement_numbers_supported

    statement = "Revenue was Rs 931.2 crore in FY25"
    far = "Revenue (Rs 931.2 crore)" + " " * 200 + "FY25 column"
    near = "FY25 revenue Rs 931.2 crore"
    assert statement_numbers_supported(statement, far)[0]
    assert not statement_numbers_supported(statement, far, require_period_adjacency=True)[0]
    assert statement_numbers_supported(statement, near, require_period_adjacency=True)[0]


def test_period_adjacency_is_ignored_when_statement_names_no_period() -> None:
    from busybee.verify.number_match import statement_numbers_supported

    assert statement_numbers_supported(
        "Debt is Rs 40 crore", "Debt Rs 40 crore", require_period_adjacency=True
    )[0]


def test_statement_date_matches_another_rendering_of_the_same_date() -> None:
    ok, missing = statement_numbers_supported(
        "Net worth was Rs 10 crore as at March 31, 2026",
        "Net worth Rs 10 crore on 31st March, 2026",
    )
    assert ok, missing
    assert statement_numbers_supported("as at 31.03.2026", "March 31, 2026")[0]
    assert statement_numbers_supported("as at 31 March 2026", "dated 31/03/2026")[0]


def test_statement_date_with_a_different_day_is_not_supported() -> None:
    ok, missing = statement_numbers_supported("as at March 31, 2026", "30th March, 2026")
    assert not ok and missing == ["March 31, 2026"]


def test_date_parts_are_not_required_as_standalone_numbers() -> None:
    assert statement_numbers_supported("Debt 5 crore on 31 March 2026", "31 March 2026: 5 crore")[0]
    assert not statement_numbers_supported("Debt 5 crore on 31 March 2026", "5 crore")[0]


def test_fiscal_range_is_met_by_any_of_its_years() -> None:
    assert statement_numbers_supported("Revenue 5 in FY2025-26", "FY26 revenue 5")[0]
