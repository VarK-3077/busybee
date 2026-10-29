"""The reduce-or-decline headline is rebuilt from the failed minimums on the v7 rules."""

from decimal import Decimal
from pathlib import Path

from busybee.compose.policy_floor import rebuild_headline
from busybee.schema.io import read_model
from busybee.schema.policy import PolicyEvaluation
from busybee.schema.report import Decision

FIXTURE = Path(__file__).parent / "fixtures" / "indoco_v7_rules.json"
MODEL = "Reduce the credit limit to INR 100 crore"
CAUTION = " (computed without lease liabilities, cash and bank balances and liquid investments)"


def rules():
    return read_model(FIXTURE, PolicyEvaluation).rules


def test_v7_headline_names_failed_criteria_and_drops_unchecked_limit() -> None:
    headline = rebuild_headline(Decision.reduce_or_decline, rules(), MODEL, None, None)
    assert headline == (
        "Reduce the credit line or decline: Net debt / EBITDA 7.30x is above the 4.5x maximum"
        f"{CAUTION}; Interest coverage (EBITDA / interest) 1.16x is below the 2.5x minimum"
    )


def test_limit_follows_only_within_the_maximum_exposure() -> None:
    within = rebuild_headline(Decision.reduce_or_decline, rules(), MODEL, None, Decimal(120))
    above = rebuild_headline(Decision.reduce_or_decline, rules(), MODEL, None, Decimal(80))
    assert within.endswith(" Proposed limit: INR 100 crore.")
    assert "Proposed limit" not in above
