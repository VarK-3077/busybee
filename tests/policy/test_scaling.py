"""Unit conversions into scaled integers and the explicit errors for bad input."""

from decimal import Decimal

import pytest

from busybee.policy.scaling import ScalingError, to_scaled_int
from busybee.schema.policy import InputSlot

MONEY = InputSlot(slot="ebitda", unit="INR crore x 100", scale=100)
BPS = InputSlot(slot="growth", unit="basis points", scale=1)
COUNT = InputSlot(slot="flags", unit="count", scale=1)


@pytest.mark.parametrize(
    ("value", "unit", "expected"),
    [
        ("12.34", "INR crore", 1234),
        ("1234", "lakh", 1234),
        ("500", "INR million", 5000),
        ("2.5", "billion", 25000),
        ("1250000000", "INR", 12500),
        ("12", "crore", 1200),
    ],
)
def test_money_units_convert_to_crore_times_scale(value: str, unit: str, expected: int) -> None:
    assert to_scaled_int(Decimal(value), unit, MONEY) == expected


def test_percent_becomes_basis_points() -> None:
    assert to_scaled_int(Decimal("8.7"), "%", BPS) == 870
    assert to_scaled_int(Decimal("-10"), "percent", BPS) == -1000
    assert to_scaled_int(Decimal("870"), "bps", BPS) == 870


def test_dimensionless_slot_accepts_plain_numbers() -> None:
    assert to_scaled_int(Decimal("2"), "count", COUNT) == 2
    assert to_scaled_int(Decimal("9"), "", COUNT) == 9


@pytest.mark.parametrize(
    ("value", "unit", "slot"),
    [
        ("1", "percent", MONEY),
        ("1", "furlongs", MONEY),
        ("1", "INR crore", COUNT),
        ("1", "crore", BPS),
        ("1.2345", "INR crore", MONEY),
    ],
)
def test_bad_conversions_raise_scaling_error(value: str, unit: str, slot: InputSlot) -> None:
    with pytest.raises(ScalingError):
        to_scaled_int(Decimal(value), unit, slot)


def test_score_value_display_divides_by_scale_and_appends_unit() -> None:
    from busybee.policy.scaling import format_score_value
    from busybee.schema.policy import ScoreSpec

    cap = ScoreSpec(score_id="cap", name="Cap", unit="crore", value_scale=100)
    plain = ScoreSpec(score_id="fss", name="FSS", unit="points")
    assert format_score_value(cap, "15364") == "153.64 crore"
    assert format_score_value(cap, "15360") == "153.6 crore"
    assert format_score_value(cap, "50000") == "500 crore"
    assert format_score_value(cap, "0") == "0 crore"
    assert format_score_value(plain, "63") == "63"


def test_converted_lakh_money_rounds_half_up_to_the_slot_scale() -> None:
    assert to_scaled_int(Decimal("73950.40"), "INR lakh", MONEY) == 73950
    assert to_scaled_int(Decimal("6032.58"), "INR lakh", MONEY) == 6033
