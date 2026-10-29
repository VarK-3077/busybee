"""Unit normalisation in quantified claims: money units, inherited units, cross-multiplication."""

from decimal import Decimal

import pytest

from busybee.infer.prompts import LeanClaim
from busybee.infer.quantify import QuantifyError, build_lean_source, unit_class_and_factor
from busybee.schema.facts import Citation, FactCategory, FactRecord, NumericValue, VerifiedFact
from busybee.schema.report import Inference


def _fact(fact_id: str, statement: str, numbers: list[tuple[str, str]], **extra) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        category=FactCategory.other,
        citations=[Citation(chunk_id="D1:p2:c1", doc_id="D1", page_no=2)],
        numbers=[NumericValue(label="n", value=Decimal(v), unit=u) for v, u in numbers],
        **extra,
    )


def _inference() -> Inference:
    return Inference(
        inference_id="I001",
        opinion="o",
        fact_ids=[],
        reasoning="r",
        confidence=0.8,
        quantitative=True,
    )


def _build(facts: dict[str, str], claim: str, fact_list: list[VerifiedFact]) -> str:
    return build_lean_source(_inference(), LeanClaim(facts=facts, claim=claim), fact_list)


@pytest.mark.parametrize(
    ("unit", "factor"),
    [
        ("INR crore", "1"),
        ("INR lakh", "0.01"),
        ("Rs lakhs", "0.01"),
        ("₹ million", "0.1"),
        ("INR billion", "100"),
        ("INR thousand", "0.0001"),
        ("INR", "0.0000001"),
        ("₹", "0.0000001"),
    ],
)
def test_all_money_units_are_one_class_in_crore(unit: str, factor: str) -> None:
    assert unit_class_and_factor(unit) == ("money", Decimal(factor))


def test_lakh_and_crore_are_converted_before_scaling() -> None:
    facts = [
        _fact("F001", "Loss INR 500 lakh.", [("500", "INR lakh")]),
        _fact("F002", "Cost INR 6 crore.", [("6", "INR crore")]),
    ]
    source = _build({"loss": "F001", "cost": "F002"}, "loss < cost", facts)
    assert "def loss : Int := 5" in source
    assert "def cost : Int := 6" in source


def test_logged_net_loss_with_plain_numbers_inherits_lakh() -> None:
    facts = [
        _fact("F001", "Net loss INR 5,547.27 lakh.", [("5547.27", "INR lakh")]),
        _fact("F002", "Finance cost INR 71.5 crore.", [("71.5", "INR crore")]),
        _fact(
            "F003",
            "Warren loss of 5,547.27 in the lakh table.",
            [("5547.27", "")],
            record=FactRecord(metric="Warren loss", value=Decimal("5547.27"), unit="INR lakh"),
        ),
        _fact(
            "F004",
            "FPP loss of 1,200.00; total INR 9,000 lakh.",
            [("1200", ""), ("9000", "INR lakh")],
        ),
    ]
    source = _build(
        {"net_loss": "F001", "finance_cost": "F002", "warren_loss": "F003", "fpp_loss": "F004"},
        "net_loss < finance_cost + warren_loss + fpp_loss",
        facts,
    )
    assert "def warren_loss : Int := 5547" in source
    assert "def fpp_loss : Int := 12" in source


def test_logged_interest_coverage_cross_multiplication_is_allowed() -> None:
    facts = [
        _fact("F001", "Interest coverage was 2.5 times.", [("2.5", "x")]),
        _fact("F002", "Finance cost INR 40 crore.", [("40", "INR crore")]),
        _fact("F003", "EBITDA INR 100 crore.", [("100", "INR crore")]),
    ]
    source = _build(
        {"interest_coverage": "F001", "finance_cost": "F002", "ebitda": "F003"},
        "ebitda * 100 >= 250 * finance_cost",
        facts,
    )
    assert "def ebitda" in source


def test_logged_receivable_days_with_aged_receivables() -> None:
    facts = [
        _fact("F001", "Trade receivables INR 900 lakh.", [("900", "INR lakh")]),
        _fact(
            "F002",
            "Aged receivables of 300.",
            [("300", "")],
            record=FactRecord(metric="Aged receivables", value=Decimal(300), unit="INR lakh"),
        ),
        _fact("F003", "Receivable days were 120 days.", [("120", "days")]),
        _fact("F004", "Revenue INR 3,650 lakh.", [("3650", "INR lakh")]),
    ]
    source = _build(
        {
            "trade_receivables": "F001",
            "aged_receivables": "F002",
            "receivable_days": "F003",
            "revenue": "F004",
        },
        "trade_receivables * 365 >= receivable_days * revenue + aged_receivables",
        facts,
    )
    assert "def aged_receivables : Int := 3" in source


def test_ratio_in_fact_with_money_stays_plain() -> None:
    facts = [
        _fact(
            "F001", "Debt INR 120 crore capped at 3.5 times.", [("120", "INR crore"), ("3.5", "")]
        ),
        _fact("F002", "Net debt to EBITDA was 2.7 times.", [("2.7", "")]),
    ]
    assert "-- scale: x10" in _build({"r": "F002", "limit": "F001#3.5"}, "r < limit", facts)
    with pytest.raises(QuantifyError, match="incompatible units"):
        _build({"r": "F002", "debt": "F001"}, "r < debt", facts)


def test_days_against_money_directly_is_rejected() -> None:
    facts = [
        _fact("F001", "Receivable days were 120 days.", [("120", "days")]),
        _fact("F002", "Revenue INR 3,650 lakh.", [("3650", "INR lakh")]),
    ]
    with pytest.raises(QuantifyError, match="mixes incompatible units"):
        _build({"receivable_days": "F001", "revenue": "F002"}, "receivable_days < revenue", facts)


def test_ratio_claim_ignores_mapped_but_unused_money_variables() -> None:
    facts = [
        _fact("F001", "Interest coverage was 0.1x.", [("0.1", "x")]),
        _fact("F002", "Finance cost INR 122.25 crore.", [("122.25", "INR crore")]),
        _fact("F003", "EBITDA INR 14,516 lakh.", [("14516", "INR lakh")]),
    ]
    source = _build(
        {"interest_coverage": "F001", "finance_cost": "F002", "ebitda": "F003"},
        "interest_coverage < 1",
        facts,
    )
    assert "theorem claim : interest_coverage < 100" in source


def test_ratio_from_two_money_amounts_in_lakh_and_crore() -> None:
    facts = [
        _fact("F001", "EBITDA INR 14,516 lakh.", [("14516", "INR lakh")]),
        _fact("F002", "Finance cost INR 122.25 crore.", [("122.25", "INR crore")]),
    ]
    source = _build(
        {"ebitda": "F001", "finance_cost": "F002"}, "100 * ebitda < 120 * finance_cost", facts
    )
    assert "def ebitda : Int := 14516" in source
    assert "def finance_cost : Int := 12225" in source


def test_used_money_variable_beside_a_ratio_without_cross_multiplication_still_fails() -> None:
    facts = [
        _fact("F001", "Interest coverage was 0.1x.", [("0.1", "x")]),
        _fact("F002", "Finance cost INR 122.25 crore.", [("122.25", "INR crore")]),
    ]
    with pytest.raises(QuantifyError, match="incompatible units"):
        _build({"coverage": "F001", "finance_cost": "F002"}, "coverage < finance_cost", facts)


def test_unit_taken_from_statement_when_fact_has_none() -> None:
    facts = [
        _fact("F001", "Warren reported a loss of (6,216.68) lakhs.", [("-6216.68", "")]),
        _fact("F002", "Net loss INR 98.7 crore.", [("-98.7", "INR crore")]),
    ]
    source = _build({"warren": "F001", "net": "F002"}, "warren > net", facts)
    assert "def warren : Int := -6217" in source or "def warren : Int := -6216" in source


def test_default_number_skips_a_months_count() -> None:
    facts = [
        _fact(
            "F001",
            "Receivables aged 6 months and above were INR 15,887.02 lakhs.",
            [("6", ""), ("15887.02", "INR lakh")],
        ),
        _fact("F002", "Trade receivables INR 54,120.19 lakh.", [("54120.19", "INR lakh")]),
    ]
    source = _build({"aged": "F001", "total": "F002"}, "aged < total", facts)
    assert "def aged : Int := 158" in source


def test_bare_literal_is_scaled_but_multipliers_are_not() -> None:
    facts = [
        _fact("F001", "Coverage 0.9x.", [("0.9", "x")]),
        _fact("F002", "Debt 3x.", [("3", "x")]),
    ]
    source = _build({"a": "F001", "b": "F002"}, "a < 1 && 2 * a <= b", facts)
    assert "a < 10 && 2 * a <= b" in source
