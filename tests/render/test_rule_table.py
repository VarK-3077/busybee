"""The policy rule results table, its Lean chips and popover records, and reason links."""

import json
import re
from decimal import Decimal
from pathlib import Path

from test_bundle import _build_run

from busybee.render.bundle import render_bundle
from busybee.render.sections import scores_section
from busybee.render.statements import key_reason_html, rule_lean_record
from busybee.schema.io import read_model, write_model_atomic
from busybee.schema.lean import CompileResult, LeanArtifact, LeanArtifactKind
from busybee.schema.policy import BoundInput, RuleOutcome, RuleResult, RuleStatus
from busybee.schema.report import KeyReason, Report

ARTIFACT = LeanArtifact(
    artifact_id="scores_run-1",
    kind=LeanArtifactKind.scores,
    file_path="lean/Runs/run-1/Scores.lean",
    source="theorem rule_dscr_min_violated : True := by decide\n",
    sha256="d" * 64,
    theorems=["rule_dscr_min_violated"],
    compile=CompileResult(ok=True, stdout="rule_dscr_min=fail\n", stderr="", duration_s=0.3),
)


def rule(rule_id: str, status: RuleStatus, **extra: object) -> RuleResult:
    return RuleResult(
        rule_id=rule_id,
        name=f"Rule {rule_id}",
        status=status,
        outcome=RuleOutcome.refer,
        message=f"{rule_id} message.",
        expression="100 * cfads >= 125 * debt_service",
        inputs=[
            BoundInput(slot="cfads", fact_id="F003", value=Decimal("118.5"), unit="INR crore"),
        ],
        policy_section="4",
        policy_section_id="P2",
        lean=ARTIFACT,
        **extra,
    )


def test_table_has_a_row_per_rule_with_badge_and_lean_chip() -> None:
    html = str(
        scores_section(
            [],
            {},
            [
                rule("dscr_min", RuleStatus.fail),
                rule("cr", RuleStatus.caution),
                rule("ok", RuleStatus.passed),
                rule(
                    "late",
                    RuleStatus.not_evaluable,
                    unbound={"default_flag": "not bound"},
                ).model_copy(update={"lean": None, "inputs": []}),
            ],
        )
    )
    assert "<caption>Policy rule results</caption>" in html
    assert html.count('class="bb-rule bb-stmt"') == 4
    for label, tone in (("Fail", "poor"), ("Caution", "weak"), ("Pass", "good")):
        assert f'data-tone="{tone}">{label}</span>' in html
    assert 'data-tone="none">Not evaluable</span>' in html
    assert 'data-lean="rule:dscr_min" data-status="proved"' in html
    assert 'data-lean="rule:late" data-status="unchecked"' in html
    assert "Missing default_flag: not bound" in html
    assert 'href="#fact-F003"' in html and 'href="policy.html#P2"' in html
    assert "CFADS 118.5 INR crore" in html


def test_no_rules_means_no_table() -> None:
    assert "Policy rule results" not in str(scores_section([], {}, []))


def test_rule_record_for_the_popover() -> None:
    record = rule_lean_record(rule("dscr_min", RuleStatus.fail), {})
    assert record["kind"] == "rule" and record["status"] == "proved"
    assert record["grade"] == "Fail" and record["grade_tone"] == "poor"
    assert record["claim"] == "100 * cfads >= 125 * debt_service"
    assert record["theorems"] == ["rule_dscr_min_violated"]
    assert record["bindings"][0]["fact_id"] == "F003"
    assert record["compile"]["ok"] is True and str(record["href"]).startswith("lean/")


def test_reason_links_its_rules() -> None:
    html = str(
        key_reason_html(KeyReason(text="DSCR fails.", kind="policy_rule", rule_ids=["dscr_min"]), 1)
    )
    assert 'href="#rule-dscr_min"' in html


def test_bundle_embeds_the_table_and_rule_popover_records(tmp_path: Path) -> None:
    out = _build_run(tmp_path)
    workspace = tmp_path / "workspace"
    report = read_model(workspace / "report.json", Report)
    report.rule_results = [rule("dscr_min", RuleStatus.fail)]
    write_model_atomic(workspace / "report.json", report)
    out = render_bundle(workspace, tmp_path / "out", banks_dir=tmp_path / "banks")
    index = (out / "index.html").read_text(encoding="utf-8")
    assert 'id="rule-dscr_min"' in index and "Policy rule results" in index
    blob = re.search(r'<script type="application/json" id="bb-lean">(.*?)</script>', index, re.S)
    assert blob is not None
    records = json.loads(blob.group(1))
    assert records["rule:dscr_min"]["kind"] == "rule"
    assert (out / "lean" / "scores_run-1.html").is_file()
