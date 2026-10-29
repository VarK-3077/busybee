"""End-to-end compose tests with the mock provider and a workspace on disk."""

import json
from pathlib import Path

from busybee.compose.inputs import load_compose_inputs
from busybee.compose.run_compose import run_compose
from busybee.llm.mock import MockProvider
from busybee.schema.io import read_model
from busybee.schema.report import Decision, Report
from busybee.schema.run import RunConfig


def valid_response() -> str:
    """Return a recommendation that passes id checking."""
    return json.dumps(
        {
            "decision": "approve_with_conditions",
            "headline": "Approve with a lower limit.",
            "proposed_limit": "INR 12 crore",
            "conditions": ["Keep net debt / EBITDA below 3.5 times."],
            "key_reasons": [
                {"text": "Revenue grew.", "fact_ids": ["F001"]},
                {
                    "text": "The financial strength score is adequate.",
                    "score_ids": ["financial_strength_score"],
                },
                {"text": "Leverage is manageable.", "inference_ids": ["I001"]},
            ],
            "confidence_note": "Customer concentration remains an open concern.",
        }
    )


async def test_run_compose_writes_a_valid_report(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    provider = MockProvider(
        {"compose": [valid_response()], "compose_verdict_check": ['{"checks": []}']}
    )

    report = await run_compose(populated_workspace, cfg, provider, banks_dir)

    assert report.recommendation is not None
    assert report.recommendation.decision == Decision.approve_with_conditions
    assert report.recommendation.proposed_limit == "INR 12 crore"
    assert len(report.recommendation.key_reasons) == 3
    assert report.company.startswith("Acme Textiles")
    assert set(report.facts) == {"F001", "F002"}
    assert report.audit.models["compose"] == "mock-model"
    stored = read_model(populated_workspace / "report.json", Report)
    assert stored == report
    assert provider.calls[0].task == "compose"


async def test_run_compose_drops_unknown_ids_from_the_final_report(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    response = json.loads(valid_response())
    response["key_reasons"][0]["fact_ids"].append("F999")
    provider = MockProvider(
        {"compose": [json.dumps(response)], "compose_verdict_check": ['{"checks": []}']}
    )

    report = await run_compose(populated_workspace, cfg, provider, banks_dir)

    assert report.recommendation is not None
    assert report.recommendation.key_reasons[0].fact_ids == ["F001"]
    assert "F999" not in report.recommendation.key_reasons[0].fact_ids


async def test_run_compose_with_empty_workspace_still_writes_report(
    workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    response = {
        "decision": "refer",
        "headline": "Refer because no evidence was supplied.",
        "key_reasons": [
            {"text": "There are no supported facts.", "fact_ids": ["F999"]},
            {"text": "There are no available scores.", "score_ids": ["missing"]},
        ],
        "confidence_note": "The file is incomplete.",
    }
    provider = MockProvider(
        {
            "compose": [json.dumps(response), json.dumps(response)],
            "compose_verdict_check": ['{"checks": []}'],
        }
    )

    report = await run_compose(workspace, cfg, provider, banks_dir)

    assert report.recommendation is not None
    assert report.recommendation.decision == Decision.refer
    assert report.recommendation.key_reasons == []
    assert (workspace / "report.json").exists()
    assert len(provider.calls) == 2


def test_inputs_are_also_loadable_without_a_workspace(
    workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    inputs = load_compose_inputs(workspace, cfg, banks_dir)

    assert inputs.policy_summary
