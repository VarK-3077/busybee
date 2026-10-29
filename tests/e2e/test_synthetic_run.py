"""End-to-end: the whole pipeline on the synthetic Acme corpus with the fake LLM."""

import asyncio
import json
from pathlib import Path

import pytest

from busybee.orchestrate.config import build_run_config
from busybee.orchestrate.run import run_pipeline
from busybee.orchestrate.stages import stage_names
from busybee.schema.documents import Chunk
from busybee.schema.facts import VerifiedFact
from busybee.schema.io import read_jsonl, read_model, read_models
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Report
from busybee.schema.run import RunConfig, StageState, StageStatus

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "data" / "synthetic" / "acme_textiles"


@pytest.fixture(autouse=True)
def fake_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUSYBEE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("BUSYBEE_LLM_MOCK_CALLABLE", "fake_llm:fake_llm")
    monkeypatch.setenv("BUSYBEE_EMBED_PROVIDER", "hashing")


@pytest.fixture(scope="module")
def run_dirs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    base = tmp_path_factory.mktemp("synthetic")
    cfg = build_run_config(
        DOCS,
        "demo_bank",
        base / "out",
        run_id="e2e",
        workspace_root=base,
        proposed_exposure="432",
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("BUSYBEE_LLM_PROVIDER", "mock")
        patch.setenv("BUSYBEE_LLM_MOCK_CALLABLE", "fake_llm:fake_llm")
        patch.setenv("BUSYBEE_EMBED_PROVIDER", "hashing")
        run_synthetic(cfg)
    return cfg.workspace_dir, cfg.out_dir


def run_synthetic(cfg: RunConfig) -> None:
    asyncio.run(run_pipeline(cfg, banks_dir=ROOT / "banks"))


def _log_tasks(workspace: Path) -> list[str]:
    lines = (workspace / "llm_log.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line)["task"] for line in lines if line.strip()]


def test_report_has_facts_and_resolving_citations(run_dirs: tuple[Path, Path]) -> None:
    workspace, _ = run_dirs
    report = read_model(workspace / "report.json", Report)
    chunk_ids = {c.chunk_id for c in read_jsonl(workspace / "corpus" / "chunks.jsonl", Chunk)}
    assert len(report.facts) >= 10
    assert report.recommendation is not None
    for fact in report.facts.values():
        assert fact.citations
        if fact.added_by == "bank_input":
            continue
        assert all(citation.chunk_id in chunk_ids for citation in fact.citations)


def test_bundle_contains_every_fact_id(run_dirs: tuple[Path, Path]) -> None:
    workspace, out = run_dirs
    html = (out / "index.html").read_text(encoding="utf-8")
    report = read_model(workspace / "report.json", Report)
    assert all(fact_id in html for fact_id in report.facts)


def test_lean_scores_are_computed_with_compiling_artifacts(
    run_dirs: tuple[Path, Path],
) -> None:
    workspace, out = run_dirs
    scores = {s.score_id: s for s in read_models(workspace / "scores.json", ScoreResult)}
    assert set(scores) == {"financial_strength_score", "internal_risk_grade", "maximum_exposure"}
    for score in scores.values():
        assert score.status == "computed"
        assert score.lean is not None and score.lean.compile.ok is True
    assert scores["financial_strength_score"].value_display == "67"
    assert scores["financial_strength_score"].grade == "Adequate"
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "Adequate" in html and "Low risk" in html


def test_all_stages_done(run_dirs: tuple[Path, Path]) -> None:
    workspace, _ = run_dirs
    statuses = read_models(workspace / "stages.json", StageStatus)
    assert {s.name for s in statuses} == set(stage_names())
    assert all(s.state is StageState.done for s in statuses)


def test_resume_reruns_only_compose_and_render(tmp_path: Path) -> None:
    cfg = build_run_config(
        DOCS, "demo_bank", tmp_path / "out", run_id="resume", workspace_root=tmp_path
    )
    asyncio.run(run_pipeline(cfg, banks_dir=ROOT / "banks"))
    workspace = cfg.workspace_dir
    calls_before = len(_log_tasks(workspace))
    (workspace / "report.json").unlink()
    (cfg.out_dir / "index.html").unlink()

    asyncio.run(run_pipeline(cfg, resume=True, banks_dir=ROOT / "banks"))

    new_tasks = _log_tasks(workspace)[calls_before:]
    assert new_tasks and set(new_tasks) == {"compose", "compose_verdict_check"}
    assert (workspace / "report.json").exists()
    assert (cfg.out_dir / "index.html").exists()


def test_recommendation_has_all_three_kinds_and_company_name(
    run_dirs: tuple[Path, Path],
) -> None:
    workspace, out = run_dirs
    report = read_model(workspace / "report.json", Report)
    assert report.company == "Acme Textiles Limited"
    assert report.recommendation is not None
    reasons = report.recommendation.key_reasons
    assert {reason.kind for reason in reasons} == {"policy_rule", "hard_fact", "inference"}
    rule = next(reason for reason in reasons if reason.kind == "policy_rule")
    assert rule.policy_citations and rule.policy_citations[0].quote
    html = (out / "index.html").read_text(encoding="utf-8")
    policy_html = (out / "policy.html").read_text(encoding="utf-8")
    section_id = rule.policy_citations[0].section_id
    assert f'data-cites="{section_id}"' in html
    assert f'id="{section_id}"' in policy_html


def test_report_sections_put_scores_right_after_recommendation(
    run_dirs: tuple[Path, Path],
) -> None:
    _, out = run_dirs
    html = (out / "index.html").read_text(encoding="utf-8")
    names = ("recommendation", "scores", "facts", "inferences")
    ids = [html.index(f'id="{name}"') for name in names]
    assert ids == sorted(ids)
    assert "<dt>Run</dt>" not in html


def test_bank_input_flows_through_scores_and_renders_as_a_bank_input_chip(
    run_dirs: tuple[Path, Path],
) -> None:
    workspace, out = run_dirs
    report = read_model(workspace / "report.json", Report)
    bank_facts = [f for f in report.facts.values() if f.added_by == "bank_input"]
    assert [f.statement for f in bank_facts] == [
        "Bank input: proposed exposure INR 432 crore (from the credit request)"
    ]
    scores = {s.score_id: s for s in read_models(workspace / "scores.json", ScoreResult)}
    exposure_inputs = {i.slot: i for i in scores["maximum_exposure"].inputs}
    assert exposure_inputs["proposed_exposure"].fact_id == bank_facts[0].fact_id
    flags = {i.slot: i for i in scores["internal_risk_grade"].inputs}
    assert flags["external_rating_index"].value_scaled == 5
    assert flags["default_flag"].note and flags["major_red_flag_count"].note
    assert "judge_slot" in "".join(_log_tasks(workspace))
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "bank input" in html and "bb-cite--bank" in html


def test_policy_rules_are_proved_in_lean_and_shown_in_the_report(
    run_dirs: tuple[Path, Path],
) -> None:
    workspace, out = run_dirs
    report = read_model(workspace / "report.json", Report)
    status = {rule.rule_id: rule.status.value for rule in report.rule_results}
    assert status["dscr_min"] == "pass"
    assert status["exposure_within_cap"] == "fail"
    assert "not_evaluable" not in status.values()
    exposure = next(rule for rule in report.rule_results if rule.rule_id == "exposure_within_cap")
    assert exposure.lean is not None and exposure.lean.compile is not None
    assert exposure.lean.compile.ok
    assert "rule_exposure_within_cap_violated" in exposure.lean.theorems
    assert (workspace / "policy_eval.json").is_file()
    assert (workspace / "decision_override.json").is_file()
    recommendation = report.recommendation
    assert recommendation is not None
    cited = {rule_id for reason in recommendation.key_reasons for rule_id in reason.rule_ids}
    assert {"exposure_within_cap", "interest_coverage_min"} <= cited
    html = (out / "index.html").read_text(encoding="utf-8")
    assert "Policy rule results" in html and 'id="rule-dscr_min"' in html


def test_table_rows_become_record_facts_verified_by_record_match(
    run_dirs: tuple[Path, Path],
) -> None:
    workspace, _ = run_dirs
    facts = read_models(workspace / "verified_facts.json", VerifiedFact)
    matched = [
        fact
        for fact in facts
        if fact.record is not None
        and fact.verification is not None
        and fact.verification.method == "record_match"
    ]
    assert matched
    income = next(f for f in matched if f.record and f.record.metric == "Total income")
    assert income.statement.startswith("Total income was INR 936.8 crore in FY2024-25")
