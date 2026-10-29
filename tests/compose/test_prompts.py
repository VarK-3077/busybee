"""Tests for the recommendation prompt and its structured response model."""

from pathlib import Path

from busybee.compose.inputs import load_compose_inputs
from busybee.compose.prompts import (
    RecommendationOutput,
    build_evidence,
    build_messages,
    build_system_prompt,
)
from busybee.llm.messages import Role
from busybee.schema.report import Decision, KeyReason
from busybee.schema.run import RunConfig


def test_system_prompt_states_decisions_and_reason_rules(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    inputs = load_compose_inputs(populated_workspace, cfg, banks_dir)
    prompt = build_system_prompt(inputs)

    for decision in ("approve", "approve_with_conditions", "decline", "refer"):
        assert decision in prompt
    for kind in ("policy_rule", "hard_fact", "inference"):
        assert kind in prompt
    assert "confidence note" in prompt
    assert "open concerns" in prompt
    assert "names the amount" in prompt


def test_messages_include_every_evidence_id(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    inputs = load_compose_inputs(populated_workspace, cfg, banks_dir)
    messages = build_messages(inputs)

    assert [message.role for message in messages] == [Role.system, Role.user]
    evidence = messages[1].content
    assert "F001" in evidence
    assert "F002" in evidence
    assert "financial_strength_score" in evidence
    assert "I001" in evidence
    assert "C001" in evidence
    assert "Acme Textiles" in evidence
    assert "[P1] Test Bank — Corporate Credit Policy" in evidence
    assert "Policy line 56." in evidence


def test_recommendation_output_round_trips_key_reasons() -> None:
    output = RecommendationOutput(
        decision=Decision.approve_with_conditions,
        headline="Approve with a lower limit.",
        proposed_limit="INR 12 crore",
        conditions=["Keep net debt / EBITDA below 3.5 times."],
        key_reasons=[KeyReason(text="Revenue grew.", fact_ids=["F001"])],
        confidence_note="The open concern on concentration is noted.",
    )

    restored = RecommendationOutput.model_validate_json(output.model_dump_json())

    assert restored == output
    assert restored.key_reasons[0].fact_ids == ["F001"]


def test_scores_carry_value_and_grade_semantics(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    from dataclasses import replace

    from busybee.schema.policy import GradeRule, ScoreResult, ScoreSpec

    spec = ScoreSpec(
        score_id="maximum_exposure",
        name="Maximum Exposure test",
        description="Largest permissible exposure.",
        unit="crore",
        value_scale=100,
        value_meaning="The maximum permissible exposure in INR crore, not a flag.",
        grades=[GradeRule(label="Exceeds limit", condition_text="proposed above the cap")],
    )
    score = ScoreResult(
        score_id="maximum_exposure", value_display="153.64 crore", grade="Exceeds limit"
    )
    inputs = replace(
        load_compose_inputs(populated_workspace, cfg, banks_dir),
        scores=[score],
        score_specs=[spec],
    )
    evidence = build_evidence(inputs)

    assert "- maximum_exposure: 153.64 crore, grade Exceeds limit (computed)" in evidence
    assert "Maximum Exposure test: Largest permissible exposure." in evidence
    assert "value in crore: The maximum permissible exposure in INR crore, not a flag." in evidence
    assert '"Exceeds limit" = proposed above the cap' in evidence
