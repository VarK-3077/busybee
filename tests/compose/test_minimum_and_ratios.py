"""Failed minimums give reduce_or_decline; ratios with different definitions get a note."""

import json
from dataclasses import replace
from pathlib import Path

from busybee.compose.minimum_standards import criterion_text, minimum_headline
from busybee.compose.policy_floor import (
    DECISION_RANK,
    enforce_policy_floor,
    headline_matches_decision,
    policy_floor,
    rebuild_headline,
)
from busybee.compose.ratio_definitions import (
    annotate_ratio_definitions,
    conflicting_ratios,
    ratio_values,
)
from busybee.schema.documents import Document
from busybee.schema.policy import BankPolicy, RuleResult, RuleStatus
from busybee.schema.report import Decision, Inference, KeyReason, Recommendation

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "indoco_ratios.json").read_text())
EXPECTED = (
    "Reduce the credit line or decline: Interest coverage 1.78x is below the 2.5x minimum; "
    "DSCR 1.00x is below the 1.25x minimum"
)


def rules() -> list[RuleResult]:
    return [RuleResult.model_validate(raw) for raw in FIXTURE["rule_results"]]


def test_failed_minimums_floor_names_each_criterion_with_value_and_minimum() -> None:
    floor, binding = policy_floor(rules())
    assert floor is Decision.reduce_or_decline
    assert [r.rule_id for r in binding] == ["interest_coverage_min", "dscr_min"]
    assert minimum_headline(rules()) == EXPECTED
    assert rebuild_headline(floor, rules(), "Refer the facility") == EXPECTED
    assert headline_matches_decision(EXPECTED, Decision.reduce_or_decline)


def test_enforce_overrides_refer_and_keeps_decline() -> None:
    refer = Recommendation(
        decision=Decision.refer, headline="Refer it", proposed_limit="INR 50 crore"
    )
    changed, record = enforce_policy_floor(refer, rules())
    assert changed.decision is Decision.reduce_or_decline and changed.headline == EXPECTED
    assert changed.proposed_limit is None and record.overridden
    decline = Recommendation(decision=Decision.decline, headline="Decline it")
    kept, record = enforce_policy_floor(decline, rules())
    assert kept.decision is Decision.decline and not record.overridden


def test_decline_trigger_beats_failed_minimum_and_minimum_beats_refer() -> None:
    results = rules()
    flagged = next(r for r in results if r.rule_id == "irg_not_decline")
    results = [
        r if r is not flagged else flagged.model_copy(update={"status": RuleStatus.fail})
        for r in results
    ]
    assert policy_floor(results)[0] is Decision.decline
    only_refer = [r for r in rules() if r.rule_id not in ("interest_coverage_min", "dscr_min")]
    only_refer[0] = only_refer[0].model_copy(update={"status": RuleStatus.fail})
    assert policy_floor([only_refer[-4]])[0] is not Decision.reduce_or_decline
    assert DECISION_RANK[Decision.refer] < DECISION_RANK[Decision.reduce_or_decline]
    assert DECISION_RANK[Decision.reduce_or_decline] < DECISION_RANK[Decision.decline]


def test_explicit_result_fields_win_and_missing_value_names_criterion() -> None:
    interest = next(r for r in rules() if r.rule_id == "interest_coverage_min")
    assert criterion_text(interest) == "Interest coverage 1.78x is below the 2.5x minimum"
    explicit = interest.model_copy(
        update={
            "measure": "Net debt / EBITDA",
            "computed_value": "4.71x",
            "threshold": "at most 4.5x",
        }
    )
    assert criterion_text(explicit) == "Net debt / EBITDA 4.71x is above the 4.5x maximum"
    bare = interest.model_copy(update={"inputs": []})
    assert criterion_text(bare) == "Interest coverage at least 2.5x fails its minimum standard"


def test_ratio_note_for_indoco_company_reported_vs_policy() -> None:
    inferences = [Inference.model_validate(raw) for raw in FIXTURE["inferences"]]
    grouped = ratio_values(rules(), inferences, [])
    values = {round(m.value, 1) for m in grouped["interest coverage"]}
    assert values == {1.8, 0.1, 0.9}
    notes = conflicting_ratios(grouped)
    assert "interest coverage" in notes and "DSCR" not in notes["interest coverage"]
    assert "shown with different definitions" in notes["interest coverage"]
    assert "1.78x (policy rule)" in notes["interest coverage"]
    assert "0.1x (I001, consolidated)" in notes["interest coverage"]
    assert "0.9x (I004, standalone)" in notes["interest coverage"]


def test_annotate_adds_the_note_next_to_every_mention_once() -> None:
    from busybee.compose.inputs import ComposeInputs

    inferences = [Inference.model_validate(raw) for raw in FIXTURE["inferences"]]
    inputs = ComposeInputs(
        facts=[],
        scores=[],
        inferences=inferences,
        concerns=[],
        documents=[Document(doc_id="D1", title="AR")],
        policy=BankPolicy(bank_id="b"),
        policy_summary="",
        rule_results=rules(),
    )
    reason = KeyReason(
        text="Interest coverage 1.78x is below the 2.5x minimum.", kind="policy_rule"
    )
    rec = Recommendation(decision=Decision.reduce_or_decline, key_reasons=[reason])
    new_inputs, new_rec = annotate_ratio_definitions(inputs, rec)
    assert "shown with different definitions" in new_inputs.inferences[0].reasoning
    assert "shown with different definitions" in new_rec.key_reasons[0].text
    interest = next(r for r in new_inputs.rule_results if r.rule_id == "interest_coverage_min")
    dscr = next(r for r in new_inputs.rule_results if r.rule_id == "dscr_min")
    assert (
        "different definitions" in interest.message and "different definitions" not in dscr.message
    )
    again_inputs, again_rec = annotate_ratio_definitions(new_inputs, new_rec)
    assert again_rec.key_reasons[0].text == new_rec.key_reasons[0].text
    assert replace(again_inputs).inferences[0].reasoning == new_inputs.inferences[0].reasoning
