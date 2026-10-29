"""The implausible-figure guard compares only INR amounts of the same line item (Indoco v9a).

F270 is consolidated total equity of INR 91,365.11 lakh; F044 states an 85% equity stake bought
for USD 4 million. F044 mentions "equity" but its figures are a percentage and a foreign-currency
consideration, so it must never be the comparator. A share count is never one either. A genuine
lakh-versus-crore mismatch on the same line item is still flagged.
"""

from decimal import Decimal

from busybee.policy.components import outlier_reason
from busybee.schema.facts import FactScope, NumericValue, VerifiedFact
from busybee.verify.numbers import numeric_values_from

EQUITY = "Consolidated total equity (net worth) as at March 31, 2026 was INR 91,365.11 lakh."
STAKE = (
    "The company acquired an 85% equity stake in a US subsidiary on June 05, 2023, for an "
    "aggregate consideration of USD 4 Million."
)


def _fact(fact_id: str, statement: str, scope: FactScope | None) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id, statement=statement, scope=scope, numbers=numeric_values_from(statement)
    )


def _stake() -> VerifiedFact:
    numbers = [
        NumericValue(label="acquired", value=Decimal(85), unit="%", period="2023"),
        NumericValue(
            label="aggregate consideration", value=Decimal(4), unit="million", period="2023"
        ),
    ]
    return VerifiedFact(fact_id="F044", statement=STAKE, numbers=numbers)


def test_a_stake_percentage_or_foreign_consideration_is_never_a_comparator() -> None:
    equity = _fact("F270", EQUITY, FactScope.consolidated)
    assert outlier_reason("total_equity", equity, equity.numbers[0], [equity, _stake()]) is None


def test_a_share_count_is_never_a_comparator() -> None:
    equity = _fact("F270", EQUITY, FactScope.consolidated)
    numbers = [NumericValue(label="value", value=Decimal(4), unit="million shares", period="2023")]
    shares = VerifiedFact(
        fact_id="F045", statement="Total equity shares outstanding were 4 million.", numbers=numbers
    )
    assert outlier_reason("total_equity", equity, equity.numbers[0], [equity, shares]) is None


def test_the_same_line_item_in_crore_on_the_other_basis_is_still_flagged() -> None:
    equity = _fact("F270", EQUITY, FactScope.consolidated)
    other = _fact(
        "F301",
        "Standalone total equity as at March 31, 2026 was INR 91,365.11 crore.",
        FactScope.standalone,
    )
    reason = outlier_reason("total_equity", equity, equity.numbers[0], [equity, _stake(), other])
    assert reason is not None and "F301" in reason and "F044" not in reason
