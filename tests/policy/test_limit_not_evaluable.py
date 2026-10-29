"""A non-additive score with a cautioned input is not evaluable, not zero (Indoco v9a).

The maximum exposure is a limit computation, not a sum of bands, so a cautioned tangible net
worth cannot drop a band: the score gets no value, grade "Not evaluable" and the reason as its
caution. The additive Financial Strength Score keeps band zeroing instead.
"""

from decimal import Decimal

from policy_helpers import BANKS_DIR

from busybee.policy.bands import SCORE_NOT_EVALUABLE, not_evaluable_reason
from busybee.policy.bank_fs import load_bank
from busybee.policy.run_scores import _not_evaluable
from busybee.schema.policy import BoundInput, ScoreResult

CAUTION = "implausible figure: F270 total_equity is 2.28e+3x another figure, check the unit"


def _policy() -> str:
    return (BANKS_DIR / "demo_bank" / "policy.lean").read_text()


def _spec(score_id: str):
    return next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == score_id)


def _item(slot: str, caution: str = "") -> BoundInput:
    return BoundInput(
        slot=slot, fact_id="F001", value=Decimal(1), value_scaled=100, caution=caution
    )


def _exposure_inputs() -> list[BoundInput]:
    return [
        _item("proposed_exposure"),
        _item("projected_turnover"),
        _item("tangible_net_worth", CAUTION),
    ]


def test_a_cautioned_limit_input_makes_the_score_not_evaluable() -> None:
    reason = not_evaluable_reason(_spec("maximum_exposure"), _exposure_inputs(), _policy())
    assert reason is not None and "tangible_net_worth" in reason and CAUTION in reason
    result = _not_evaluable(
        ScoreResult(score_id="maximum_exposure", value_display="0 crore", grade="Exceeds limit"),
        reason,
    )
    assert result.value_display is None
    assert result.grade == SCORE_NOT_EVALUABLE
    assert result.caution == reason


def test_clean_limit_inputs_and_additive_scores_are_left_alone() -> None:
    clean = [_item(item.slot) for item in _exposure_inputs()]
    assert not_evaluable_reason(_spec("maximum_exposure"), clean, _policy()) is None
    fss = _spec("financial_strength_score")
    bound = [_item(slot.slot, CAUTION) for slot in fss.inputs]
    assert not_evaluable_reason(fss, bound, _policy()) is None
