"""The reduce headline never states a limit the maximum exposure could not compute (Indoco v9a).

With the maximum exposure not evaluable, the model's "INR 0.0 crore" is dropped and the headline
says the limit could not be computed and why; the failed criteria end with a full stop before
the second sentence. A maximum exposure of zero (internal risk grade 7 permits 0%) states the
grade and the proposed amount instead of "Proposed limit: INR 0.0 crore.".
"""

from decimal import Decimal
from pathlib import Path

from busybee.compose.policy_floor import (
    exposure_limit_note,
    exposure_not_evaluable,
    max_exposure_crore,
    rebuild_headline,
)
from busybee.schema.io import read_model
from busybee.schema.policy import BoundInput, PolicyEvaluation, ScoreResult
from busybee.schema.report import Decision

FIXTURE = Path(__file__).parent / "fixtures" / "indoco_v7_rules.json"
MODEL = "Reduce the credit limit to INR 0.0 crore"
REASON = "maximum_exposure not evaluable: input tangible_net_worth is a proxy or misses components"


def _rules():
    return read_model(FIXTURE, PolicyEvaluation).rules


def test_a_not_evaluable_exposure_gives_no_amount_and_says_why() -> None:
    scores = [ScoreResult(score_id="maximum_exposure", grade="Not evaluable", caution=REASON)]
    assert max_exposure_crore(scores) is None
    headline = rebuild_headline(
        Decision.reduce_or_decline,
        _rules(),
        MODEL,
        "INR 0.0 crore",
        max_exposure_crore(scores),
        exposure_limit_note(scores),
    )
    assert "INR 0.0 crore" not in headline
    assert headline.endswith(f"minimum. The proposed limit could not be computed: {REASON}.")


def test_the_criteria_end_with_a_full_stop_before_the_proposed_limit() -> None:
    within = rebuild_headline(
        Decision.reduce_or_decline, _rules(), "Reduce to INR 100 crore", None, Decimal(120)
    )
    assert within.endswith("minimum. Proposed limit: INR 100 crore.")
    computed = [ScoreResult(score_id="maximum_exposure", value_display="120 crore")]
    assert exposure_not_evaluable(computed) == ""


def test_a_zero_exposure_names_the_grade_and_the_proposed_amount() -> None:
    proposed = BoundInput(
        slot="proposed_exposure",
        fact_id="F266",
        value=Decimal("150"),
        unit="INR crore",
        value_scaled=15000,
    )
    scores = [
        ScoreResult(score_id="internal_risk_grade", value_display="7", grade="High risk"),
        ScoreResult(
            score_id="maximum_exposure",
            value_display="0 crore",
            grade="Exceeds limit",
            inputs=[proposed],
        ),
    ]
    headline = rebuild_headline(
        Decision.reduce_or_decline,
        _rules(),
        MODEL,
        "INR 0.0 crore",
        max_exposure_crore(scores),
        exposure_limit_note(scores),
    )
    assert "INR 0.0 crore" not in headline and "Proposed limit" not in headline
    assert headline.endswith(
        "minimum. The policy permits no exposure at internal risk grade 7, so the proposed "
        "INR 150 crore cannot be sanctioned."
    )
    no_limit = rebuild_headline(
        Decision.reduce_or_decline, _rules(), MODEL, None, max_exposure_crore(scores)
    )
    assert "Proposed limit" not in no_limit
