"""Shared workspace, config, and bank fixtures for the compose tests."""

from pathlib import Path

import pytest

from busybee.schema.documents import Document, DocumentKind
from busybee.schema.facts import Citation, FactCategory, VerifiedFact
from busybee.schema.io import write_models_atomic
from busybee.schema.policy import ScoreResult
from busybee.schema.report import Concern, Inference
from busybee.schema.run import RunConfig

POLICY_TEXT = (
    "# Test Bank — Corporate Credit Policy\n"
    "\n"
    "Version 2.3.\n"
    "\n" + "\n".join(f"Policy line {number}." for number in range(1, 71)) + "\n"
)


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Return an empty workspace directory."""
    path = tmp_path / "workspace"
    path.mkdir()
    return path


@pytest.fixture
def docs_dir(tmp_path: Path) -> Path:
    """Return an empty document-pack directory."""
    path = tmp_path / "docs"
    path.mkdir()
    return path


@pytest.fixture
def banks_dir(tmp_path: Path) -> Path:
    """Return a banks root containing demo_bank with policy and approval."""
    root = tmp_path / "banks"
    bank = root / "demo_bank"
    bank.mkdir(parents=True)
    (bank / "policy.md").write_text(POLICY_TEXT, encoding="utf-8")
    (bank / "approval.json").write_text(
        '{"approved": false, "notes": "awaiting review"}',
        encoding="utf-8",
    )
    return root


@pytest.fixture
def cfg(tmp_path: Path, workspace: Path, docs_dir: Path) -> RunConfig:
    """Return a minimal run configuration pointing at the fixtures."""
    return RunConfig(
        run_id="run-1",
        docs_dir=docs_dir,
        bank_id="demo_bank",
        out_dir=tmp_path / "out",
        workspace_dir=workspace,
        models={"compose": "mock-model"},
    )


@pytest.fixture
def populated_workspace(
    workspace: Path,
    facts: list[VerifiedFact],
    scores: list[ScoreResult],
    inferences: list[Inference],
    concerns: list[Concern],
    documents: list[Document],
) -> Path:
    """Write the five compose input files into the workspace."""
    write_models_atomic(workspace / "verified_facts.json", facts)
    write_models_atomic(workspace / "scores.json", scores)
    write_models_atomic(workspace / "inferences.json", inferences)
    write_models_atomic(workspace / "concerns.json", concerns)
    write_models_atomic(workspace / "corpus" / "documents.json", documents)
    return workspace


@pytest.fixture
def documents() -> list[Document]:
    """Return one source document used as the company-name fallback."""
    return [
        Document(
            doc_id="D1",
            title="Acme Textiles Audited Financial Statements FY2024-25",
            kind=DocumentKind.financial_statements,
        )
    ]


@pytest.fixture
def facts() -> list[VerifiedFact]:
    """Return two verified facts in different categories."""
    return [
        VerifiedFact(
            fact_id="F001",
            statement="Revenue from operations was INR 1,234.50 crore in FY2024-25.",
            category=FactCategory.revenue,
            citations=[Citation(chunk_id="D1:p1:c1", doc_id="D1", page_no=1, quote="Revenue")],
            added_by="extract",
        ),
        VerifiedFact(
            fact_id="F002",
            statement="Net debt was INR 900.00 crore at year end.",
            category=FactCategory.debt_leverage,
            citations=[Citation(chunk_id="D1:p1:c2", doc_id="D1", page_no=1, quote="Net debt")],
            added_by="extract",
        ),
    ]


@pytest.fixture
def scores() -> list[ScoreResult]:
    """Return one computed score."""
    return [
        ScoreResult(
            score_id="financial_strength_score",
            value_display="72",
            grade="Adequate",
        )
    ]


@pytest.fixture
def inferences() -> list[Inference]:
    """Return one inference citing the first fact."""
    return [
        Inference(
            inference_id="I001",
            opinion="Leverage is manageable but revenue concentration is a risk.",
            fact_ids=["F001", "F002"],
            confidence=0.7,
        )
    ]


@pytest.fixture
def concerns() -> list[Concern]:
    """Return one open concern."""
    return [
        Concern(
            concern_id="C001",
            opinion="Customer concentration is not disclosed.",
            fact_ids=["F001"],
            query_used="customer concentration",
            found=False,
        )
    ]
