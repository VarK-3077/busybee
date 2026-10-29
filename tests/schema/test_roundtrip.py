"""Round-trip tests covering every schema model group."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel

from busybee.schema.documents import Chunk, Document, DocumentKind, Page, ScoredChunk
from busybee.schema.facts import (
    Citation,
    DroppedEntry,
    EntryKind,
    FactCategory,
    NotebookEntry,
    NumericValue,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.schema.io import read_model, write_model_atomic
from busybee.schema.lean import (
    CompileResult,
    ExplainItem,
    ExplainSection,
    LeanArtifact,
    LeanArtifactKind,
    LeanError,
    LeanExplanation,
)
from busybee.schema.policy import (
    Approval,
    BankPolicy,
    BoundInput,
    GradeRule,
    InputSlot,
    ScoreResult,
    ScoreSpec,
    ScoreStatus,
)
from busybee.schema.report import (
    AuditBlock,
    Concern,
    Decision,
    FactGroup,
    Inference,
    KeyReason,
    Recommendation,
    Report,
)
from busybee.schema.run import ExtractMode, RunConfig, StageState, StageStatus


def roundtrip(model: BaseModel, model_type: type[BaseModel], tmp_path: Path) -> Path:
    path = tmp_path / f"{model_type.__name__}.json"
    write_model_atomic(path, model)
    loaded = read_model(path, model_type)
    assert loaded == model
    return path


def sample_chunk() -> Chunk:
    return Chunk(
        chunk_id="D1:p2:c1",
        doc_id="D1",
        page_no=2,
        index_in_page=1,
        text="Revenue grew to INR 1,234.50 crore.",
        char_start=14,
        char_end=48,
    )


def sample_citation() -> Citation:
    return Citation(chunk_id="D1:p2:c1", doc_id="D1", page_no=2, quote="Revenue grew")


def sample_number() -> NumericValue:
    return NumericValue(
        label="Revenue",
        value=Decimal("1234.50"),
        unit="INR crore",
        period="FY25",
    )


def sample_verified_fact() -> VerifiedFact:
    return VerifiedFact(
        fact_id="F001",
        statement="Revenue grew to INR 1,234.50 crore in FY25.",
        category=FactCategory.revenue,
        citations=[sample_citation()],
        numbers=[sample_number()],
        verification=Verification(
            status=VerificationStatus.supported,
            method="exact_match",
            notes="all numbers found",
        ),
        source_entry_id="D1:E001",
        added_by="extract",
    )


def sample_compile_result() -> CompileResult:
    return CompileResult(
        ok=False,
        stdout="checking",
        stderr="error",
        duration_s=1.25,
        toolchain="leanprover/lean4:v4.13.0",
        errors=[LeanError(line=7, col=3, message="unknown identifier")],
    )


def sample_lean_artifact() -> LeanArtifact:
    return LeanArtifact(
        artifact_id="run-1:leverage",
        kind=LeanArtifactKind.scores,
        file_path="lean/Runs/run-1/Scores.lean",
        source="def net_debt : Int := 100",
        sha256="abc123",
        theorems=["leverage_grade_a"],
        compile=sample_compile_result(),
    )


def test_document_models_round_trip(tmp_path: Path) -> None:
    document = Document(
        doc_id="D1",
        title="Annual Report FY25",
        kind=DocumentKind.annual_report,
        source_path="annual_report.pdf",
        sha256="deadbeef",
        num_pages=120,
        metadata={"fiscal_year": 2025, "language": "en"},
    )
    roundtrip(document, Document, tmp_path)
    roundtrip(Page(doc_id="D1", page_no=2, text="page text"), Page, tmp_path)
    roundtrip(sample_chunk(), Chunk, tmp_path)
    roundtrip(ScoredChunk(chunk=sample_chunk(), score=0.87), ScoredChunk, tmp_path)


def test_fact_models_round_trip(tmp_path: Path) -> None:
    roundtrip(sample_citation(), Citation, tmp_path)
    roundtrip(sample_number(), NumericValue, tmp_path)
    entry = NotebookEntry(
        entry_id="D1:E001",
        statement="Revenue grew 12% year on year.",
        citations=[sample_citation()],
        category=FactCategory.revenue,
        kind=EntryKind.number,
        importance=5,
        window_no=3,
        doc_id="D1",
        supersedes="D1:E000",
        added_by="extract",
    )
    roundtrip(entry, NotebookEntry, tmp_path)
    roundtrip(
        Verification(
            status=VerificationStatus.resupported,
            method="llm_entailment",
            notes="re-cited from D1:p3:c0",
        ),
        Verification,
        tmp_path,
    )
    roundtrip(sample_verified_fact(), VerifiedFact, tmp_path)
    roundtrip(
        DroppedEntry(entry=entry, reason="not relevant to a credit line", stage="verify"),
        DroppedEntry,
        tmp_path,
    )


def test_decimal_fields_serialise_as_strings(tmp_path: Path) -> None:
    number_path = roundtrip(sample_number(), NumericValue, tmp_path)
    number_raw = json.loads(number_path.read_text(encoding="utf-8"))
    assert number_raw["value"] == "1234.50"

    bound = BoundInput(
        slot="net_debt",
        fact_id="F002",
        value=Decimal("100.25"),
        unit="INR crore",
        value_scaled=10025,
    )
    bound_path = roundtrip(bound, BoundInput, tmp_path)
    bound_raw = json.loads(bound_path.read_text(encoding="utf-8"))
    assert bound_raw["value"] == "100.25"


def test_policy_models_round_trip(tmp_path: Path) -> None:
    slot = InputSlot(
        slot="net_debt",
        description="Net debt in INR crore",
        unit="INR crore",
        scale=100,
    )
    grade = GradeRule(label="A", condition_text="leverage at most 2.5x")
    spec = ScoreSpec(
        score_id="leverage",
        name="Net leverage",
        description="Net debt over EBITDA",
        inputs=[slot],
        lean_function="leverage_grade",
        grades=[grade],
    )
    approval = Approval(
        approved=True,
        by="credit-committee",
        date="2026-10-01",
        notes="approved for pilot",
        generated_by="gpt-test",
    )
    policy = BankPolicy(
        bank_id="demo_bank",
        name="Demo Bank",
        version="1.2",
        policy_md="# Policy",
        scores=[spec],
        lean_path="banks/demo_bank/policy.lean",
        approval=approval,
    )
    result = ScoreResult(
        score_id="leverage",
        status=ScoreStatus.computed,
        inputs=[
            BoundInput(
                slot="net_debt",
                fact_id="F002",
                value=Decimal("100.25"),
                unit="INR crore",
                value_scaled=10025,
            )
        ],
        value_display="2.4x",
        grade="A",
        lean=sample_lean_artifact(),
    )
    for model, model_type in [
        (slot, InputSlot),
        (grade, GradeRule),
        (spec, ScoreSpec),
        (approval, Approval),
        (policy, BankPolicy),
        (result, ScoreResult),
    ]:
        roundtrip(model, model_type, tmp_path)


def test_lean_models_round_trip(tmp_path: Path) -> None:
    error = LeanError(line=7, col=3, message="unknown identifier")
    compile_result = sample_compile_result()
    artifact = sample_lean_artifact()
    item = ExplainItem(
        name="leverage_grade",
        kind="theorem",
        lean="theorem leverage_grade : ...",
        english="Net leverage is at most 2.5 times.",
        doc="A bank-approved threshold.",
    )
    section = ExplainSection(title="Leverage", items=[item])
    explanation = LeanExplanation(sections=[section])
    for model, model_type in [
        (error, LeanError),
        (compile_result, CompileResult),
        (artifact, LeanArtifact),
        (item, ExplainItem),
        (section, ExplainSection),
        (explanation, LeanExplanation),
    ]:
        roundtrip(model, model_type, tmp_path)


def test_report_models_round_trip(tmp_path: Path) -> None:
    fact = sample_verified_fact()
    reason = KeyReason(
        text="Leverage is inside the approved limit.",
        fact_ids=["F001"],
        score_ids=["leverage"],
        inference_ids=["I001"],
    )
    recommendation = Recommendation(
        decision=Decision.approve_with_conditions,
        headline="Approve a small working-capital line.",
        proposed_limit="INR 10 crore",
        conditions=["Monthly stock statements"],
        key_reasons=[reason],
        confidence_note="One rating action is still pending.",
    )
    group = FactGroup(category=FactCategory.revenue, fact_ids=["F001"])
    inference = Inference(
        inference_id="I001",
        opinion="Revenue is growing steadily.",
        fact_ids=["F001"],
        reasoning="Revenue increased in the latest year.",
        confidence=0.8,
        quantitative=False,
        lean=sample_lean_artifact(),
    )
    concern = Concern(
        concern_id="C001",
        opinion="Customer concentration is unclear.",
        fact_ids=["F001"],
        reasoning="No customer-level breakdown was found.",
        query_used="top customer share of revenue",
        found=False,
    )
    audit = AuditBlock(
        models={"extract": "mock-large", "verify": "mock-small"},
        stage_timings={"ingest": 1.2, "verify": 3.4},
        llm_calls=17,
        policy_version="1.2",
        lean_toolchain="leanprover/lean4:v4.13.0",
        generated_at=datetime(2026, 10, 26, 9, 30, tzinfo=UTC),
    )
    report = Report(
        run_id="run-1",
        company="Acme Textiles",
        bank_id="demo_bank",
        policy_approved=True,
        recommendation=recommendation,
        facts={fact.fact_id: fact},
        fact_groups=[group],
        scores=[ScoreResult(score_id="leverage", value_display="2.4x", grade="A")],
        inferences=[inference],
        concerns=[concern],
        documents=[Document(doc_id="D1", title="Annual Report", kind=DocumentKind.annual_report)],
        audit=audit,
    )
    for model, model_type in [
        (reason, KeyReason),
        (recommendation, Recommendation),
        (group, FactGroup),
        (inference, Inference),
        (concern, Concern),
        (audit, AuditBlock),
        (report, Report),
    ]:
        roundtrip(model, model_type, tmp_path)


def test_run_models_round_trip(tmp_path: Path) -> None:
    config = RunConfig(
        run_id="run-1",
        docs_dir=tmp_path / "docs",
        bank_id="demo_bank",
        out_dir=tmp_path / "out",
        workspace_dir=tmp_path / "workspace",
        window_tokens=6000,
        notebook_budget_tokens=24000,
        concurrency=8,
        extract_mode=ExtractMode.global_,
        models={"extract": "mock-large", "verify": "mock-small"},
    )
    status = StageStatus(
        name="verify",
        state=StageState.done,
        started_at=datetime(2026, 10, 26, 9, 0, tzinfo=UTC),
        finished_at=datetime(2026, 10, 26, 9, 5, tzinfo=UTC),
        error=None,
    )
    roundtrip(config, RunConfig, tmp_path)
    roundtrip(status, StageStatus, tmp_path)
