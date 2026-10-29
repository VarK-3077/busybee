"""Verdict checks: false comparisons are removed and logged; a dependent decision is re-asked."""

import json
from pathlib import Path

import pytest

from busybee.compose.run_compose import run_compose
from busybee.compose.verdict_check import deterministic_findings
from busybee.llm.mock import MockProvider
from busybee.schema.run import RunConfig

FALSE_REASON = (
    "The company's consolidated net debt to equity ratio of 113.4% exceeds the policy "
    "maximum of 3.0 times (300%)."
)


def test_113_percent_against_3_times_is_caught_deterministically() -> None:
    notes = deterministic_findings(FALSE_REASON)
    assert len(notes) == 1
    assert "1.134" in notes[0] and "false" in notes[0]


@pytest.mark.parametrize(
    "text",
    [
        "Net debt/EBITDA of 2.7x is within the 4.5x cap.",
        "Interest coverage 3.4x exceeds the 2.5x minimum.",
        "Net debt to equity of 113.4% is within the policy maximum of 3.0 times.",
        "Current ratio of 1.2x falls below the 1.5x minimum.",
        "Debt service cover of 1.1x fails the 1.25x minimum.",
    ],
)
def test_correct_comparisons_pass(text: str) -> None:
    assert deterministic_findings(text) == []


@pytest.mark.parametrize(
    "text",
    [
        "Net debt/EBITDA of 5.2x is within the 4.5x cap.",
        "Interest coverage of 2.0x exceeds the 2.5x minimum.",
        "Leverage of 4.1x does not exceed the 3.0x cap.",
        "Revenue growth of 3% meets the 5% minimum.",
    ],
)
def test_false_comparisons_are_caught(text: str) -> None:
    assert len(deterministic_findings(text)) == 1


def _response(headline: str, reasons: list[dict]) -> str:
    return json.dumps(
        {
            "decision": "approve_with_conditions",
            "headline": headline,
            "key_reasons": reasons,
            "confidence_note": "ok",
        }
    )


GOOD = [
    {"text": "Net debt/EBITDA of 2.7x is within the 4.5x cap.", "fact_ids": ["F002"]},
    {"text": "Revenue was INR 1,234.50 crore.", "fact_ids": ["F001"]},
]
BAD = {"text": FALSE_REASON, "fact_ids": ["F002"]}


async def test_deterministic_rejection_is_removed_and_logged(
    populated_workspace: Path, cfg: RunConfig, banks_dir: Path
) -> None:
    provider = MockProvider(
        {
            "compose": [_response("Approve a limit.", [*GOOD, BAD])],
            "compose_verdict_check": ['{"checks": []}'],
        }
    )
    report = await run_compose(populated_workspace, cfg, provider, banks_dir)
    assert report.recommendation is not None
    assert [r.text for r in report.recommendation.key_reasons] == [r["text"] for r in GOOD]
    logged = json.loads((populated_workspace / "compose_rejected.json").read_text())
    assert [item["source"] for item in logged] == ["deterministic"]
    assert "1.134" in logged[0]["note"]
    assert [call.task for call in provider.calls] == ["compose", "compose_verdict_check"]
    checked = provider.calls[1].messages[-1].content
    assert "Reason 0" in checked and "Reason 2" not in checked


async def test_llm_incorrect_reason_is_removed_and_logged(
    populated_workspace: Path, cfg: RunConfig, banks_dir: Path
) -> None:
    verdict = {
        "checks": [
            {"index": 0, "verdict": "correct", "note": ""},
            {"index": 1, "verdict": "incorrect", "note": "F001 says 1,234.50 not 9."},
            {"index": 2, "verdict": "unverifiable", "note": "no evidence"},
        ]
    }
    reasons = [GOOD[0], {"text": "Revenue was INR 9 crore.", "fact_ids": ["F001"]}, GOOD[1]]
    provider = MockProvider(
        {
            "compose": [_response("Approve a limit.", reasons)],
            "compose_verdict_check": [json.dumps(verdict)],
        }
    )
    report = await run_compose(populated_workspace, cfg, provider, banks_dir)
    assert report.recommendation is not None
    assert [r.text for r in report.recommendation.key_reasons] == [GOOD[0]["text"], GOOD[1]["text"]]
    logged = json.loads((populated_workspace / "compose_rejected.json").read_text())
    assert [(i["source"], i["note"]) for i in logged] == [("llm", "F001 says 1,234.50 not 9.")]


async def test_decision_that_leaned_on_a_removed_reason_is_asked_again(
    populated_workspace: Path, cfg: RunConfig, banks_dir: Path
) -> None:
    first = _response(
        "Decline: net debt to equity ratio is above the policy maximum.",
        [BAD, GOOD[1], {"text": "Leverage looks manageable.", "inference_ids": ["I001"]}],
    )
    second = _response(
        "Approve a limit; the net debt to equity ratio is within policy.",
        [
            {
                "text": "Net debt to equity of 113.4% is within the 3.0 times cap.",
                "fact_ids": ["F002"],
            },
            *GOOD,
        ],
    )
    provider = MockProvider(
        {
            "compose": [first, second],
            "compose_verdict_check": ['{"checks": []}'],
        }
    )
    report = await run_compose(populated_workspace, cfg, provider, banks_dir)
    assert report.recommendation is not None
    assert report.recommendation.headline.startswith("Approve")
    assert len(report.recommendation.key_reasons) == 3
    retry_note = provider.calls[2].messages[-1].content
    assert "113.4%" in retry_note and "rejected" in retry_note
    assert [call.task for call in provider.calls] == [
        "compose",
        "compose_verdict_check",
        "compose",
        "compose_verdict_check",
    ]
    logged = json.loads((populated_workspace / "compose_rejected.json").read_text())
    assert [(item["source"], item["round"]) for item in logged] == [("deterministic", 1)]


async def test_removing_a_reason_without_touching_the_decision_does_not_reask(
    populated_workspace: Path, cfg: RunConfig, banks_dir: Path
) -> None:
    provider = MockProvider(
        {
            "compose": [_response("Approve a limit.", [*GOOD, BAD, GOOD[1]])],
            "compose_verdict_check": ['{"checks": []}'],
        }
    )
    await run_compose(populated_workspace, cfg, provider, banks_dir)
    assert [call.task for call in provider.calls].count("compose") == 1
