"""The Lean-evaluated policy rules set a decision floor that code enforces on the model."""

import json
from decimal import Decimal
from pathlib import Path

from busybee.compose.check_ids import scrub_reasons
from busybee.compose.policy_floor import (
    enforce_policy_floor,
    headline_matches_decision,
    headline_rule,
    missing_rule_reasons,
    policy_floor,
    rebuild_headline,
    unevaluated_note,
)
from busybee.compose.run_compose import run_compose
from busybee.llm.mock import MockProvider
from busybee.schema.io import read_json, read_model, write_model_atomic
from busybee.schema.policy import (
    BoundInput,
    PolicyEvaluation,
    RuleOutcome,
    RuleResult,
    RuleStatus,
)
from busybee.schema.report import Decision, KeyReason, Recommendation, Report
from busybee.schema.run import RunConfig


def result(
    rule_id: str, status: RuleStatus, outcome: RuleOutcome = RuleOutcome.refer
) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        name=f"Rule {rule_id}",
        status=status,
        outcome=outcome,
        message=f"{rule_id} message.",
        inputs=[
            BoundInput(slot="cfads", fact_id="F001", value=Decimal("118.5"), unit="INR crore"),
            BoundInput(slot="debt_service", fact_id="F002", value=Decimal("141.2")),
        ],
        policy_section_id="P1",
    )


def test_floor_is_the_strictest_implied_decision() -> None:
    passed = result("a", RuleStatus.passed)
    assert policy_floor([passed])[0] is Decision.approve
    assert policy_floor([passed, result("n", RuleStatus.not_evaluable)])[0] is Decision.approve
    caution = result("c", RuleStatus.caution)
    assert policy_floor([passed, caution])[0] is Decision.refer
    exposure = result("e", RuleStatus.fail, RuleOutcome.pass_required)
    assert policy_floor([exposure])[0] is Decision.approve_with_conditions
    refer = result("r", RuleStatus.fail, RuleOutcome.refer)
    floor, binding = policy_floor([caution, refer, exposure])
    assert floor is Decision.refer and [item.rule_id for item in binding] == ["c", "r"]
    decline = result("d", RuleStatus.fail, RuleOutcome.decline)
    assert policy_floor([refer, decline])[0] is Decision.decline
    assert policy_floor([result("x", RuleStatus.caution, RuleOutcome.caution)])[0] is (
        Decision.approve_with_conditions
    )


def test_lenient_decision_is_overridden_with_template_headline() -> None:
    model = Recommendation(
        decision=Decision.approve_with_conditions,
        headline="Approve INR 60 crore",
        proposed_limit="INR 60 crore",
        conditions=["Monitor covenants."],
        confidence_note="Reasonable.",
    )
    changed, record = enforce_policy_floor(model, [result("dscr_min", RuleStatus.fail)])
    assert changed.decision is Decision.refer
    assert changed.headline == "Refer: dscr_min message."
    assert changed.proposed_limit is None and changed.conditions == []
    assert "overrode the model's decision 'approve_with_conditions' to 'refer'" in (
        changed.confidence_note or ""
    )
    assert "dscr_min" in (changed.confidence_note or "")
    assert record.overridden and record.model_decision is Decision.approve_with_conditions
    assert record.final_decision is Decision.refer and record.rule_ids == ["dscr_min"]
    assert record.model_headline == "Approve INR 60 crore" and record.headline == changed.headline


def test_stricter_or_equal_decisions_are_kept() -> None:
    declined = Recommendation(decision=Decision.decline, headline="Decline the facility")
    kept, record = enforce_policy_floor(declined, [result("dscr_min", RuleStatus.fail)])
    assert kept == declined and not record.overridden and record.floor is Decision.refer
    approve = Recommendation(decision=Decision.approve, headline="Approve")
    kept, record = enforce_policy_floor(approve, [result("ok", RuleStatus.passed)])
    assert kept == approve and not record.overridden


def test_conditions_are_added_for_a_caution_floor() -> None:
    model = Recommendation(decision=Decision.approve, headline="Approve", conditions=["Keep X."])
    changed, _ = enforce_policy_floor(model, [result("c", RuleStatus.caution, RuleOutcome.caution)])
    assert changed.decision is Decision.approve_with_conditions
    assert changed.conditions == ["Keep X.", "c message."]
    assert changed.headline == "Approve with conditions: c message."


def test_ratio_caution_zone_refers() -> None:
    model = Recommendation(decision=Decision.approve_with_conditions, headline="Approve")
    changed, record = enforce_policy_floor(model, [result("icr", RuleStatus.caution)])
    assert changed.decision is Decision.refer and record.overridden


def test_failing_and_caution_rules_get_reasons_unless_cited() -> None:
    results = [
        result("dscr_min", RuleStatus.fail),
        result("cr", RuleStatus.caution),
        result("ok", RuleStatus.passed),
        result("n", RuleStatus.not_evaluable),
    ]
    model = Recommendation(
        decision=Decision.refer,
        key_reasons=[KeyReason(text="Cited by the model.", kind="policy_rule", rule_ids=["cr"])],
    )
    added = missing_rule_reasons(model, results)
    assert [reason.rule_ids for reason in added] == [["dscr_min"]]
    reason = added[0]
    assert reason.kind == "policy_rule"
    assert reason.fact_ids == ["F001", "F002"]
    assert reason.policy_citations[0].section_id == "P1"
    assert "dscr_min message." in reason.text and "cfads 118.5 INR crore" in reason.text
    assert "n" in unevaluated_note(results) and unevaluated_note(results[:3]) == ""


def test_scrub_keeps_known_rule_ids_and_drops_others() -> None:
    reasons = [
        KeyReason(text="a", kind="hard_fact", rule_ids=["dscr_min", "made_up"]),
        KeyReason(text="b", kind="policy_rule", rule_ids=["made_up"], fact_ids=["F001"]),
    ]
    kept = scrub_reasons(
        reasons,
        fact_ids={"F001"},
        score_ids=set(),
        inference_ids=set(),
        rule_ids={"dscr_min"},
    )
    assert kept[0].rule_ids == ["dscr_min"] and kept[0].kind == "policy_rule"
    assert kept[1].rule_ids == [] and kept[1].kind == "hard_fact"


async def test_run_compose_enforces_the_floor_and_records_the_override(
    populated_workspace: Path, cfg: RunConfig, banks_dir: Path
) -> None:
    write_model_atomic(
        populated_workspace / "policy_eval.json",
        PolicyEvaluation(
            rules=[
                result("dscr_min", RuleStatus.fail),
                result("irg_low_risk", RuleStatus.caution, RuleOutcome.caution),
                result("not_ready", RuleStatus.not_evaluable),
            ]
        ),
    )
    lenient = {
        "decision": "approve",
        "headline": "Approve a limit of INR 12 crore",
        "proposed_limit": "INR 12 crore",
        "key_reasons": [
            {"text": "Revenue grew.", "fact_ids": ["F001"]},
            {"text": "Leverage is manageable.", "score_ids": ["financial_strength_score"]},
            {"text": "Cites an invented rule.", "rule_ids": ["invented"], "fact_ids": ["F002"]},
        ],
        "confidence_note": "Fine.",
    }
    provider = MockProvider(
        {"compose": [json.dumps(lenient)], "compose_verdict_check": ['{"checks": []}']}
    )
    report = await run_compose(populated_workspace, cfg, provider, banks_dir)

    prompt = provider.calls[0].messages[-1].content
    assert "Policy rule results" in prompt and "dscr_min | Rule dscr_min | fail" in prompt
    assert "Policy-implied minimum decision: refer (from dscr_min)" in prompt
    recommendation = report.recommendation
    assert recommendation is not None and recommendation.decision is Decision.refer
    assert recommendation.headline == "Refer: dscr_min message."
    assert "overrode the model's decision 'approve' to 'refer'" in (
        recommendation.confidence_note or ""
    )
    assert "not_ready" in (recommendation.confidence_note or "")
    cited = [rule_id for reason in recommendation.key_reasons for rule_id in reason.rule_ids]
    assert sorted(cited) == ["dscr_min", "irg_low_risk"]
    assert all("invented" not in reason.rule_ids for reason in recommendation.key_reasons)
    assert report.audit.decision_override is not None and report.audit.decision_override.overridden
    assert [item.rule_id for item in report.rule_results][:1] == ["dscr_min"]
    saved = read_json(populated_workspace / "decision_override.json")
    assert saved["overridden"] is True and saved["final_decision"] == "refer"
    assert read_model(populated_workspace / "report.json", Report) == report


async def test_run_compose_without_rules_changes_nothing(
    populated_workspace: Path, cfg: RunConfig, banks_dir: Path
) -> None:
    response = {
        "decision": "approve",
        "headline": "Approve.",
        "key_reasons": [
            {"text": "Revenue grew.", "fact_ids": ["F001"]},
            {"text": "Leverage is manageable.", "fact_ids": ["F002"]},
        ],
    }
    provider = MockProvider(
        {"compose": [json.dumps(response)], "compose_verdict_check": ['{"checks": []}']}
    )
    report = await run_compose(populated_workspace, cfg, provider, banks_dir)
    assert report.recommendation is not None
    assert report.recommendation.decision is Decision.approve
    assert report.audit.decision_override is None
    assert read_json(populated_workspace / "decision_override.json")["overridden"] is False


def test_headline_matching_rules() -> None:
    approve, conditions = Decision.approve, Decision.approve_with_conditions
    assert headline_matches_decision("Approve a limit.", approve)
    assert headline_matches_decision("Approved: INR 12 crore", conditions)
    assert headline_matches_decision("Sanction the limit", approve)
    assert headline_matches_decision("Refer to committee", Decision.refer)
    assert headline_matches_decision("Committee review needed", Decision.refer)
    assert headline_matches_decision("Decline: default flag", Decision.decline)
    assert headline_matches_decision("Reject the request", Decision.decline)
    assert not headline_matches_decision("Approve a limit.", Decision.refer)
    assert not headline_matches_decision("Refer: dscr", conditions)
    assert not headline_matches_decision("Decline", Decision.refer)
    assert not headline_matches_decision("Strong borrower overall", Decision.approve)
    assert not headline_matches_decision("", Decision.approve)


def test_rebuild_headline_uses_rule_message_and_amount_only_on_approve() -> None:
    rules = [result("ok", RuleStatus.passed), result("c", RuleStatus.caution, RuleOutcome.caution)]
    rules.append(result("f", RuleStatus.fail))
    assert (
        rebuild_headline(Decision.refer, rules, "Approve it", "INR 5 crore") == "Refer: f message."
    )
    mixed = [
        result("soft", RuleStatus.fail, RuleOutcome.caution),
        result("ratio", RuleStatus.caution),
        result("hard", RuleStatus.fail, RuleOutcome.decline),
    ]
    assert rebuild_headline(Decision.decline, mixed, "") == "Decline: hard message."
    assert rebuild_headline(Decision.refer, mixed, "") == "Refer: ratio message."
    chosen = headline_rule(Decision.approve_with_conditions, mixed)
    assert chosen is not None and chosen.rule_id == "soft"
    assert headline_rule(Decision.refer, []) is None
    assert (
        rebuild_headline(Decision.approve_with_conditions, rules[:2], "x", "INR 5 crore")
        == "Approve with conditions (INR 5 crore): c message."
    )
    assert rebuild_headline(Decision.decline, [], "Model reason text", None) == (
        "Decline: Model reason text"
    )


async def test_run_compose_rebuilds_a_headline_that_contradicts_the_decision(
    populated_workspace: Path, cfg: RunConfig, banks_dir: Path
) -> None:
    write_model_atomic(
        populated_workspace / "policy_eval.json",
        PolicyEvaluation(rules=[result("dscr_min", RuleStatus.fail)]),
    )
    inconsistent = {
        "decision": "refer",
        "headline": "Approve a working-capital limit with covenant monitoring.",
        "proposed_limit": "INR 12 crore",
        "key_reasons": [
            {"text": "Revenue grew.", "fact_ids": ["F001"]},
            {"text": "Leverage is manageable.", "fact_ids": ["F002"]},
        ],
    }
    provider = MockProvider(
        {"compose": [json.dumps(inconsistent)], "compose_verdict_check": ['{"checks": []}']}
    )
    report = await run_compose(populated_workspace, cfg, provider, banks_dir)

    recommendation = report.recommendation
    assert recommendation is not None and recommendation.decision is Decision.refer
    assert recommendation.headline == "Refer: dscr_min message."
    assert recommendation.proposed_limit is None
    saved = read_json(populated_workspace / "decision_override.json")
    assert saved["overridden"] is False and saved["headline_rebuilt"] is True
    assert saved["headline_rule_id"] == "dscr_min"
    assert saved["headline"] == "Refer: dscr_min message."


async def test_run_compose_keeps_a_matching_headline(
    populated_workspace: Path, cfg: RunConfig, banks_dir: Path
) -> None:
    response = {
        "decision": "approve",
        "headline": "Approve a limit of INR 12 crore",
        "proposed_limit": "INR 12 crore",
        "key_reasons": [{"text": "Revenue grew.", "fact_ids": ["F001"]}],
    }
    provider = MockProvider(
        {"compose": [json.dumps(response)], "compose_verdict_check": ['{"checks": []}']}
    )
    report = await run_compose(populated_workspace, cfg, provider, banks_dir)
    assert report.recommendation is not None
    assert report.recommendation.headline == "Approve a limit of INR 12 crore"
    assert report.recommendation.proposed_limit == "INR 12 crore"
    assert read_json(populated_workspace / "decision_override.json")["headline_rebuilt"] is False
