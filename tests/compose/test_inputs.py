"""Tests for loading compose evidence and the policy summary from the workspace."""

from pathlib import Path

from busybee.compose.inputs import load_compose_inputs
from busybee.schema.documents import Document
from busybee.schema.facts import VerifiedFact
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Concern, Inference
from busybee.schema.run import RunConfig


def test_load_compose_inputs_reads_workspace_files(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
    facts: list[VerifiedFact],
    scores: list[ScoreResult],
    inferences: list[Inference],
    concerns: list[Concern],
    documents: list[Document],
) -> None:
    inputs = load_compose_inputs(populated_workspace, cfg, banks_dir)

    assert inputs.facts == facts
    assert inputs.scores == scores
    assert inputs.inferences == inferences
    assert inputs.concerns == concerns
    assert inputs.documents == documents
    assert inputs.policy.bank_id == "demo_bank"
    assert inputs.policy.name == "Test Bank"
    assert inputs.policy.version == "2.3"
    assert inputs.policy.approval.approved is False
    assert len(inputs.policy_summary.splitlines()) == 60
    assert "Policy line 56." in inputs.policy_summary
    assert "Policy line 57." not in inputs.policy_summary


def test_load_compose_inputs_tolerates_missing_files(
    workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    inputs = load_compose_inputs(workspace, cfg, banks_dir)

    assert inputs.facts == []
    assert inputs.scores == []
    assert inputs.inferences == []
    assert inputs.concerns == []
    assert inputs.documents == []
    assert inputs.policy_summary.startswith("# Test Bank")
    assert inputs.fact_ids == set()
    assert inputs.score_ids == set()
    assert inputs.inference_ids == set()


def test_load_compose_inputs_tolerates_missing_bank(tmp_path: Path, cfg: RunConfig) -> None:
    inputs = load_compose_inputs(tmp_path / "missing", cfg, tmp_path / "no-banks")

    assert inputs.policy.policy_md == ""
    assert inputs.policy.version == ""
    assert inputs.policy.approval.approved is False
    assert inputs.policy_summary == ""
