"""NumericValue extraction from statements and F001-style id assignment."""

from decimal import Decimal

from busybee.schema.facts import VerifiedFact
from busybee.verify.assign_ids import assign_fact_ids
from busybee.verify.numbers import numeric_values_from


def test_numeric_values_label_unit_period() -> None:
    values = numeric_values_from("Net debt stood at Rs 40 crore in FY24, with margin of 12%.")
    assert [(v.label, v.value, v.unit, v.period) for v in values] == [
        ("net debt", Decimal("40"), "INR crore", "FY24"),
        ("margin", Decimal("12"), "%", "FY24"),
    ]


def test_bare_year_is_a_period_not_a_value() -> None:
    values = numeric_values_from("Revenue was 500 million in 2023")
    assert len(values) == 1
    assert values[0].unit == "million"
    assert values[0].period == "2023"


def test_quarter_prefix_is_kept() -> None:
    values = numeric_values_from("Q3 FY24 profit was 8.5 crore")
    assert values[0].period == "Q3 FY24"


def test_statement_without_numbers() -> None:
    assert numeric_values_from("The company is well run") == []


def test_assign_ids_in_order_and_carries_added_by() -> None:
    facts = [
        VerifiedFact(fact_id="", statement=s, added_by=a)
        for s, a in [("a", None), ("b", "adversary")]
    ]
    out = assign_fact_ids(facts)
    assert [f.fact_id for f in out] == ["F001", "F002"]
    assert out[1].added_by == "adversary"
    assert assign_fact_ids(facts, start=10)[0].fact_id == "F010"


def _pairs(statement: str) -> list[tuple[str, str]]:
    return [(v.label, str(v.value)) for v in numeric_values_from(statement)]


def test_day_of_month_is_a_period_never_a_value() -> None:
    statement = (
        "Total borrowings stood at INR 382.0 crore as of 31 March 2025, "
        "up from INR 351.0 crore as of 31 March 2024."
    )
    assert _pairs(statement) == [("borrowings", "382.0"), ("value", "351.0")]
    assert _pairs("Net worth was Rs 100 crore on March 31, 2025.") == [("net worth", "100")]


def test_label_excludes_the_unit_word_of_the_previous_number() -> None:
    statement = (
        "Contingent liabilities not provided for totaled INR 21.6 crore at 31 March 2025, "
        "comprising the INR 14.2 crore GST demand and INR 7.4 crore of bank guarantees."
    )
    labels = [label for label, _ in _pairs(statement)]
    assert [value for _, value in _pairs(statement)] == ["21.6", "14.2", "7.4"]
    assert all("crore" not in label.split() for label in labels)
    assert labels[2] == "gst demand"


def test_fiscal_and_quarter_tokens_and_years_are_periods() -> None:
    statement = "As of 31 March 2025, the Rs 7.4 crore duty in FY25 and Q1 FY26 was 21.6 crore."
    values = numeric_values_from(statement)
    assert [str(v.value) for v in values] == ["7.4", "21.6"]
    assert values[0].period in {"FY25", "2025"}
