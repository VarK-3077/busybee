"""Tests for Report assembly, company naming, and copied evidence sections."""

from pathlib import Path

from busybee.compose.assemble import build_report, company_name
from busybee.compose.inputs import load_compose_inputs
from busybee.schema.io import write_json_atomic
from busybee.schema.report import Recommendation
from busybee.schema.run import RunConfig


def test_company_falls_back_to_first_document_title(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    inputs = load_compose_inputs(populated_workspace, cfg, banks_dir)

    assert company_name(cfg, inputs.documents) == (
        "Acme Textiles Audited Financial Statements FY2024-25"
    )


def test_manifest_company_wins_over_document_title(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    write_json_atomic(cfg.docs_dir / "manifest.json", {"company": "Acme Textiles Limited"})
    inputs = load_compose_inputs(populated_workspace, cfg, banks_dir)

    assert company_name(cfg, inputs.documents) == "Acme Textiles Limited"


def test_build_report_copies_evidence_and_builds_groups(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    inputs = load_compose_inputs(populated_workspace, cfg, banks_dir)
    recommendation = Recommendation(decision="approve", headline="Approve.")

    report = build_report(cfg, inputs, recommendation)

    assert report.run_id == "run-1"
    assert report.bank_id == "demo_bank"
    assert report.company == "Acme Textiles Audited Financial Statements FY2024-25"
    assert report.policy_approved is False
    assert report.recommendation == recommendation
    assert set(report.facts) == {"F001", "F002"}
    assert report.scores == inputs.scores
    assert report.inferences == inputs.inferences
    assert report.concerns == inputs.concerns
    assert report.documents == inputs.documents
    assert [group.fact_ids for group in report.fact_groups] == [["F001"], ["F002"]]


def test_report_company_comes_from_manifest_beside_per_file_entries(
    populated_workspace: Path,
    cfg: RunConfig,
    banks_dir: Path,
) -> None:
    write_json_atomic(
        cfg.docs_dir / "manifest.json",
        {"company": "Acme Textiles Limited", "a.md": {"title": "Annual report", "kind": "other"}},
    )
    inputs = load_compose_inputs(populated_workspace, cfg, banks_dir)

    report = build_report(cfg, inputs, Recommendation(decision="approve"))

    assert report.company == "Acme Textiles Limited"
