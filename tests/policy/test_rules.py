"""Policy rules: parsing, Lean translation, and real Lean evaluation on the demo bank."""

import json
import shutil

import policy_helpers
import pytest
from policy_helpers import BANKS_DIR, binding_json, example_facts, judge_replies, write_facts

from busybee.lean.project import project_dir
from busybee.lean.toolchain import find_lake, find_lean
from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank, load_rules
from busybee.policy.rules import RuleError, lean_condition, parse_condition, validate_rule
from busybee.policy.run_scores import run_scores
from busybee.schema.policy import PolicyEvaluation, PolicyRule, RuleOutcome, RuleStatus

needs_lean = pytest.mark.skipif(
    find_lean() is None or find_lake() is None, reason="Lean toolchain is not installed"
)


def _rule(expression: str, **extra: str) -> PolicyRule:
    return PolicyRule(
        rule_id="r", name="r", expression=expression, outcome=RuleOutcome.refer, **extra
    )


def test_expression_translates_to_division_free_lean() -> None:
    names = {"cfads": "x_cfads", "debt_service": "x_ds"}
    text = lean_condition("debt_service <= 0 or 100 * cfads >= 125 * debt_service", names)
    assert text == "(x_ds ≤ 0) ∨ (100 * x_cfads ≥ 125 * x_ds)"
    assert "/" not in text
    assert lean_condition("2 * (cfads - debt_service) != 0 and cfads > -1", names) == (
        "2 * (x_cfads - x_ds) ≠ 0 ∧ x_cfads > (-1)"
    )
    assert len(parse_condition("a > 1 and b > 2 or c > 3")) == 2


def test_invalid_rules_are_rejected() -> None:
    known = {"cfads", "debt_service"}
    with pytest.raises(RuleError, match="integer literals"):
        validate_rule(_rule("cfads >= 1.25 * debt_service"), known)
    with pytest.raises(RuleError, match="unknown slot"):
        validate_rule(_rule("cfads >= ebitda"), known)
    with pytest.raises(RuleError):
        validate_rule(_rule("cfads"), known)
    caution = PolicyRule(
        rule_id="c",
        name="c",
        expression="cfads > 0",
        outcome=RuleOutcome.caution,
        caution_expression="cfads > 5",
    )
    with pytest.raises(RuleError, match="caution rule"):
        validate_rule(caution, known)


def test_demo_bank_rules_load_and_cover_the_policy() -> None:
    bank = load_bank(BANKS_DIR, "demo_bank")
    ids = {rule.rule_id for rule in bank.rules}
    assert {"dscr_min", "default_flag_clear", "exposure_within_cap", "irg_not_decline"} <= ids
    assert len(ids) == len(bank.rules)
    yaml_text = (BANKS_DIR / "demo_bank" / "scores.yaml").read_text()
    with pytest.raises(RuleError):
        load_rules(
            yaml_text + '  - {rule_id: x, name: x, expression: "nope > 1", outcome: refer}\n',
            bank.scores,
        )


@pytest.fixture(autouse=True)
def clean_run_dir(run_config):
    yield
    shutil.rmtree(project_dir() / "Runs" / run_config.run_id, ignore_errors=True)


def _provider() -> MockProvider:
    facts = example_facts()
    return MockProvider(
        {"policy.bind_inputs": [binding_json(facts)], "policy.judge_slot": judge_replies(facts)}
    )


@needs_lean
async def test_example_borrower_rules_pass_and_caution(tmp_path, run_config) -> None:
    write_facts(tmp_path, example_facts())
    await run_scores(tmp_path, run_config, _provider(), BANKS_DIR)
    evaluation = PolicyEvaluation.model_validate(
        json.loads((tmp_path / "policy_eval.json").read_text())
    )
    status = {rule.rule_id: rule.status for rule in evaluation.rules}
    assert status["dscr_min"] is RuleStatus.passed
    assert status["interest_coverage_min"] is RuleStatus.caution
    assert status["no_major_red_flag"] is RuleStatus.caution
    assert status["irg_low_risk"] is RuleStatus.caution
    assert status["exposure_within_cap"] is RuleStatus.passed
    assert status["irg_not_decline"] is RuleStatus.passed
    assert RuleStatus.fail not in status.values()
    assert RuleStatus.not_evaluable not in status.values()
    rule = next(r for r in evaluation.rules if r.rule_id == "interest_coverage_min")
    assert rule.policy_section_id == "P5" and {i.slot for i in rule.inputs} == {
        "ebitda",
        "interest_expense",
    }
    source = rule.lean.source
    assert 'IO.println s!"rule_interest_coverage_min={rule_interest_coverage_min_status}"' in source
    for theorem in (
        "rule_interest_coverage_min_status_is",
        "rule_interest_coverage_min_met",
        "rule_interest_coverage_min_in_caution_zone",
        "rule_irg_low_risk_violated",
        "rule_dscr_min_met",
    ):
        assert theorem in rule.lean.theorems
    assert rule.lean.compile.ok
    irg = next(r for r in evaluation.rules if r.rule_id == "irg_low_risk")
    assert irg.score_ids == ["internal_risk_grade"] and irg.inputs[0].value_scaled == 5


@needs_lean
async def test_failing_rule_is_proved_violated(tmp_path, run_config, monkeypatch) -> None:
    monkeypatch.setitem(policy_helpers.EXAMPLE, "cfads", ("200.00", "INR crore", "CFADS"))
    write_facts(tmp_path, example_facts())
    await run_scores(tmp_path, run_config, _provider(), BANKS_DIR)
    evaluation = PolicyEvaluation.model_validate(
        json.loads((tmp_path / "policy_eval.json").read_text())
    )
    dscr = next(r for r in evaluation.rules if r.rule_id == "dscr_min")
    assert dscr.status is RuleStatus.fail and dscr.outcome is RuleOutcome.refer
    assert "theorem rule_dscr_min_violated" in dscr.lean.source
    assert 'rule_dscr_min_status = "fail"' in dscr.lean.source
    assert dscr.lean.compile.ok


@needs_lean
async def test_unbound_inputs_make_rules_not_evaluable(tmp_path, run_config) -> None:
    facts = example_facts(omit={"default_flag", "cfads"})
    write_facts(tmp_path, facts)
    provider = MockProvider(
        {"policy.bind_inputs": [binding_json(facts)], "policy.judge_slot": judge_replies(facts)}
    )
    await run_scores(tmp_path, run_config, provider, BANKS_DIR)
    evaluation = PolicyEvaluation.model_validate(
        json.loads((tmp_path / "policy_eval.json").read_text())
    )
    by_id = {rule.rule_id: rule for rule in evaluation.rules}
    assert by_id["default_flag_clear"].status is RuleStatus.not_evaluable
    assert list(by_id["default_flag_clear"].unbound) == ["default_flag"]
    assert "cfads" in by_id["dscr_min"].unbound
    assert by_id["irg_not_decline"].status is RuleStatus.not_evaluable
    assert "internal_risk_grade" in by_id["irg_not_decline"].unbound
    assert by_id["current_ratio_min"].status is RuleStatus.passed
    assert by_id["dscr_min"].lean is None
