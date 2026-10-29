"""Tests for evidence-id scrubbing, reason pruning, and the single re-ask path."""

import json
from pathlib import Path

from busybee.compose.check_ids import (
    reask_instruction,
    recommendation_from_output,
    scrub_reasons,
)
from busybee.compose.prompts import RecommendationOutput
from busybee.compose.run_compose import run_compose
from busybee.llm.mock import MockProvider
from busybee.policy.policy_sections import PolicySection
from busybee.schema.report import Decision, KeyReason, PolicyCitation
from busybee.schema.run import RunConfig


def test_scrub_reasons_removes_unknown_ids_and_uncited_reasons() -> None:
    reasons = [
        KeyReason(
            text="Revenue grew.",
            fact_ids=["F001", "F999", "F001"],
            score_ids=["missing_score"],
            inference_ids=["I001"],
        ),
        KeyReason(text="Unknown only.", fact_ids=["F999"]),
        KeyReason(text="Score supports leverage.", score_ids=["financial_strength_score"]),
    ]

    cleaned = scrub_reasons(
        reasons,
        fact_ids={"F001"},
        score_ids={"financial_strength_score"},
        inference_ids={"I001"},
    )

    assert len(cleaned) == 2
    assert cleaned[0].fact_ids == ["F001"]
    assert cleaned[0].score_ids == []
    assert cleaned[0].inference_ids == ["I001"]
    assert cleaned[1].text == "Score supports leverage."


def test_recommendation_from_output_reports_too_few_reasons() -> None:
    output = RecommendationOutput(
        decision=Decision.approve,
        headline="Approve.",
        key_reasons=[KeyReason(text="Revenue grew.", fact_ids=["F001"])],
    )

    recommendation, problems = recommendation_from_output(
        output,
        fact_ids={"F001"},
        score_ids=set(),
        inference_ids=set(),
    )

    assert recommendation.decision == Decision.approve
    assert len(recommendation.key_reasons) == 1
    assert problems
    assert "at least 2" in problems[0]


def test_reask_instruction_lists_valid_ids() -> None:
    text = reask_instruction(
        ["Only 1 key reason survived."],
        fact_ids={"F002", "F001"},
        score_ids={"financial_strength_score"},
        inference_ids=set(),
    )

    assert "Only 1 key reason survived." in text
    assert "F001" in text
    assert "financial_strength_score" in text


async def test_run_compose_reasks_once_and_keeps_second_recommendation(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    first = {
        "decision": "approve",
        "headline": "First attempt.",
        "key_reasons": [{"text": "Only one usable reason.", "fact_ids": ["F001"]}],
    }
    second = {
        "decision": "approve_with_conditions",
        "headline": "Approve: second attempt.",
        "conditions": ["Reduce the limit."],
        "key_reasons": [
            {"text": "Revenue grew.", "fact_ids": ["F001"]},
            {"text": "Leverage is manageable.", "score_ids": ["financial_strength_score"]},
        ],
        "confidence_note": "The open concern on concentration remains.",
    }
    provider = MockProvider(
        {
            "compose": [json.dumps(first), json.dumps(second)],
            "compose_verdict_check": ['{"checks": []}'],
        }
    )

    report = await run_compose(populated_workspace, cfg, provider, banks_dir)

    assert len(provider.calls) == 3
    assert report.recommendation is not None
    assert report.recommendation.headline == "Approve: second attempt."
    assert len(report.recommendation.key_reasons) == 2


def test_scrub_reasons_checks_policy_citations_and_downgrades_unsupported_rules() -> None:
    section = PolicySection(
        section_id="P2", heading="Leverage", text="Net debt / EBITDA is at most 4.5 times."
    )
    reasons = [
        KeyReason(
            text="Within cap.",
            kind="policy_rule",
            policy_citations=[
                PolicyCitation(section_id="P2", quote="at most 4.5 times"),
                PolicyCitation(section_id="P99", quote="invented"),
            ],
            fact_ids=["F001"],
        ),
        KeyReason(
            text="Bad quote.",
            kind="policy_rule",
            policy_citations=[PolicyCitation(section_id="P2", quote="made up words")],
        ),
        KeyReason(
            text="Unknown section.",
            kind="policy_rule",
            policy_citations=[PolicyCitation(section_id="P99")],
            fact_ids=["F001"],
        ),
    ]

    cleaned = scrub_reasons(
        reasons,
        fact_ids={"F001"},
        score_ids=set(),
        inference_ids=set(),
        policy_sections={"P2": section},
    )

    assert [reason.kind for reason in cleaned] == ["policy_rule", "policy_rule", "hard_fact"]
    assert [c.section_id for c in cleaned[0].policy_citations] == ["P2"]
    assert cleaned[0].policy_citations[0].heading == "Leverage"
    assert cleaned[0].policy_citations[0].quote == "at most 4.5 times"
    assert cleaned[1].policy_citations[0].quote.startswith("Net debt / EBITDA")
    assert cleaned[2].policy_citations == []
