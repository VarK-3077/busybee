"""Render the complete static HTML bundle atomically from a workspace report."""

from __future__ import annotations

import os
import shutil
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import yaml
from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from busybee.policy.policy_sections import PolicySection, split_policy_sections
from busybee.render import (
    assets,
    chunk_blob,
    lean_pages,
    policy_page,
    sections,
    source_pages,
    statements,
)
from busybee.render.links import artifact_slug, original_filename
from busybee.schema.documents import Chunk, Document, Page
from busybee.schema.io import (
    read_json,
    read_jsonl,
    read_model,
    read_models,
    write_json_atomic,
    write_model_atomic,
)
from busybee.schema.lean import LeanArtifact, LeanExplanation
from busybee.schema.policy import Approval, ScoreSpec
from busybee.schema.report import Report


@dataclass(frozen=True)
class BankData:
    """The bank files that the policy page needs, with graceful fallbacks."""

    approval: Approval
    policy_source: str | None
    explanation: LeanExplanation | None
    sections: list[PolicySection]
    score_specs: dict[str, ScoreSpec]


def render_bundle(
    workspace_dir: str | Path,
    out_dir: str | Path,
    banks_dir: str | Path = "banks",
    min_importance: int = sections.DEFAULT_MIN_IMPORTANCE,
    max_per_category: int = sections.DEFAULT_MAX_PER_CATEGORY,
) -> Path:
    """Render report, sources, Lean pages, policy page, assets and data atomically."""
    workspace = Path(workspace_dir)
    out = Path(out_dir)
    report = read_model(workspace / "report.json", Report)
    documents = _load_documents(workspace, report)
    pages_by_doc = _load_pages(workspace)
    chunks = read_jsonl(workspace / "corpus" / "chunks.jsonl", Chunk)
    bank = _load_bank(Path(banks_dir), report)
    environment = _environment()

    out.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(mkdtemp(prefix=f".{out.name}.tmp-", dir=out.parent))
    try:
        _write_bundle(
            temporary,
            workspace,
            report,
            documents,
            pages_by_doc,
            chunks,
            bank,
            environment,
            min_importance,
            max_per_category,
        )
        _replace_directory(temporary, out)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return out


def _environment() -> Environment:
    """Return the Jinja environment with HTML autoescaping enabled."""
    return Environment(
        loader=PackageLoader("busybee.render", "templates"),
        autoescape=select_autoescape(["html", "xml"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _load_documents(workspace: Path, report: Report) -> list[Document]:
    """Read corpus documents, falling back to the documents carried by the report."""
    path = workspace / "corpus" / "documents.json"
    if path.exists():
        return read_models(path, Document)
    return list(report.documents)


def _load_pages(workspace: Path) -> dict[str, list[Page]]:
    """Read every corpus/pages/<doc_id>.jsonl file."""
    pages_by_doc: dict[str, list[Page]] = {}
    pages_dir = workspace / "corpus" / "pages"
    if pages_dir.exists():
        for path in sorted(pages_dir.glob("*.jsonl")):
            pages_by_doc[path.stem] = read_jsonl(path, Page)
    return pages_by_doc


def _load_bank(banks_dir: Path, report: Report) -> BankData:
    """Load approval, policy Lean source, its explanation, and score specs if present."""
    bank_dir = banks_dir / report.bank_id
    approval = Approval(approved=report.policy_approved)
    approval_path = bank_dir / "approval.json"
    if approval_path.exists():
        try:
            approval = Approval.model_validate(read_json(approval_path))
        except (OSError, ValueError):
            pass
    policy_source = None
    lean_path = bank_dir / "policy.lean"
    if lean_path.exists():
        try:
            policy_source = lean_path.read_text(encoding="utf-8")
        except OSError:
            policy_source = None
    policy_path = bank_dir / "policy.md"
    sections: list[PolicySection] = []
    if policy_path.exists():
        try:
            sections = split_policy_sections(policy_path.read_text(encoding="utf-8"))
        except OSError:
            sections = []
    return BankData(
        approval=approval,
        sections=sections,
        policy_source=policy_source,
        explanation=_explain(policy_source),
        score_specs=_load_score_specs(bank_dir),
    )


def _load_score_specs(bank_dir: Path) -> dict[str, ScoreSpec]:
    """Read the bank's scores.yaml into ScoreSpec models, tolerating absence or damage."""
    path = bank_dir / "scores.yaml"
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            return {}
        specs = [ScoreSpec.model_validate(item) for item in data.get("scores", [])]
    except Exception:
        return {}
    return {spec.score_id: spec for spec in specs}


def _explain(source: str | None) -> LeanExplanation | None:
    """Build the manual Lean explanation when the in-progress module imports."""
    if not source:
        return None
    try:
        from busybee.lean.explain.build import explain_source
    except Exception:
        return None
    try:
        return explain_source(source)
    except Exception:
        return None


def _format_generated(value: datetime | str | None) -> str:
    """Format the audit timestamp for the report header."""
    if value is None:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y %H:%M")
    return str(value)


def _bank_label(report: Report) -> str:
    """Return the kicker's bank and policy label."""
    bank = statements.humanise(report.bank_id) if report.bank_id else "Bank"
    version = report.audit.policy_version
    return f"{bank} · policy {version}" if version else bank


def _policy_label(report: Report) -> str:
    """Return the policy name used by the notice and the policy page title."""
    label = (
        f"{statements.humanise(report.bank_id)} credit policy"
        if report.bank_id
        else "Credit policy"
    )
    if report.audit.policy_version:
        label += f" {report.audit.policy_version}"
    return label


def _lean_records(report: Report, score_specs: dict[str, ScoreSpec]) -> dict[str, dict[str, Any]]:
    """Build the #bb-lean payload for every score and quantitative inference."""
    records: dict[str, dict[str, Any]] = {}
    for score in report.scores:
        spec = score_specs.get(score.score_id)
        records[score.score_id] = statements.score_lean_record(
            score,
            report.facts,
            name=spec.name if spec else None,
            grades=spec.grades if spec else None,
            slots=statements.slot_index(score_specs),
        )
    for rule in report.rule_results:
        records[statements.rule_lean_key(rule)] = statements.rule_lean_record(
            rule, report.facts, statements.slot_index(score_specs)
        )
    for inference in report.inferences:
        if inference.quantitative:
            records[inference.inference_id] = statements.inference_lean_record(
                inference, report.facts
            )
    return records


def _artifact_pages(
    report: Report, score_specs: dict[str, ScoreSpec]
) -> dict[str, tuple[LeanArtifact, str]]:
    """Return artifact_id -> (artifact, human title) for every Lean artifact."""
    pages: dict[str, tuple[LeanArtifact, str]] = {}
    for score in report.scores:
        if score.lean is None:
            continue
        spec = score_specs.get(score.score_id)
        title = spec.name if spec and spec.name else statements.humanise(score.score_id)
        pages.setdefault(score.lean.artifact_id, (score.lean, title))
    for rule in report.rule_results:
        if rule.lean is not None:
            pages.setdefault(rule.lean.artifact_id, (rule.lean, "Policy scores and rules"))
    for inference in report.inferences:
        if inference.lean is None or inference.lean.artifact_id in pages:
            continue
        pages[inference.lean.artifact_id] = (
            inference.lean,
            f"Inference {inference.inference_id}",
        )
    return pages


def _write_bundle(
    root: Path,
    workspace: Path,
    report: Report,
    documents: Sequence[Document],
    pages_by_doc: dict[str, list[Page]],
    chunks: Sequence[Chunk],
    bank: BankData,
    environment: Environment,
    min_importance: int = sections.DEFAULT_MIN_IMPORTANCE,
    max_per_category: int = sections.DEFAULT_MAX_PER_CATEGORY,
) -> None:
    """Write every file into the temporary bundle directory."""
    assets.copy_assets(root / "assets")
    _copy_originals(root, workspace, documents)
    write_model_atomic(root / "data" / "report.json", report)
    write_json_atomic(
        root / "data" / "shown_facts.json",
        sections.shown_fact_ids(report, min_importance, max_per_category),
    )

    policy_label = _policy_label(report)
    approval = bank.approval.model_copy(update={"approved": report.policy_approved})
    policy_notice = (
        sections.approval_line_html(approval)
        if report.policy_approved
        else sections.approval_notice_html(
            approved=False,
            policy_label=policy_label,
            generated_by=bank.approval.generated_by,
            date=bank.approval.date,
        )
    )
    report_notice = (
        Markup("")
        if report.policy_approved
        else sections.approval_notice_html(
            approved=False,
            policy_label=policy_label,
            generated_by=bank.approval.generated_by,
            date=bank.approval.date,
        )
    )
    page_count = sum(len(pages_by_doc.get(document.doc_id, [])) for document in documents)
    index_html = environment.get_template("report.html").render(
        root="",
        title=f"Credit review · {report.company or report.run_id}",
        bank_label=_bank_label(report),
        company=report.company or report.run_id,
        subtitle="Credit review",
        policy_version=report.audit.policy_version,
        bank_id=report.bank_id,
        document_count=len(documents),
        page_count=page_count,
        generated_at=_format_generated(report.audit.generated_at),
        notice=report_notice,
        recommendation=sections.recommendation_section(report.recommendation),
        scores=sections.scores_section(report.scores, bank.score_specs, report.rule_results),
        facts=sections.facts_section(report, min_importance, max_per_category),
        inferences=sections.inferences_section(report.inferences),
        concerns=sections.concerns_section(report.concerns),
        appendix=sections.appendix_section(report, min_importance, max_per_category),
        footer=sections.audit_footer_html(report),
        chunks=chunk_blob.build_chunk_blob(report, documents, bank.sections, policy_label),
        lean_records=_lean_records(report, bank.score_specs),
    )
    _write_text(root / "index.html", index_html)

    for document in documents:
        source_html = source_pages.render_source_page(
            environment,
            document,
            pages_by_doc.get(document.doc_id, []),
            [chunk for chunk in chunks if chunk.doc_id == document.doc_id],
        )
        _write_text(root / "sources" / f"{document.doc_id}.html", source_html)

    for artifact_id, (artifact, title) in _artifact_pages(report, bank.score_specs).items():
        lean_html = lean_pages.render_lean_page(
            environment,
            artifact,
            title=title,
            explanation=_explain(artifact.source),
        )
        _write_text(root / "lean" / f"{artifact_slug(artifact_id)}.html", lean_html)
        _write_text(root / "lean" / f"{artifact_slug(artifact_id)}.lean", artifact.source)

    policy_html = policy_page.render_policy_page(
        environment,
        bank_id=report.bank_id,
        policy_label=policy_label,
        approval=approval,
        notice=policy_notice,
        explanation=bank.explanation,
        policy_source=bank.policy_source,
        sections=bank.sections,
    )
    _write_text(root / "policy.html", policy_html)


def _copy_originals(root: Path, workspace: Path, documents: Sequence[Document]) -> None:
    """Copy each document's original file into originals/ for the PDF links."""
    destination = root / "originals"
    for document in documents:
        if not document.source_path:
            continue
        source = _resolve_source_path(document.source_path, workspace)
        if source is None:
            continue
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / original_filename(document))


def _resolve_source_path(source_path: str, workspace: Path) -> Path | None:
    """Find an original document path from absolute, cwd-relative, or workspace-relative input."""
    source = Path(source_path)
    candidates = (
        [source]
        if source.is_absolute()
        else [
            Path.cwd() / source,
            workspace / source,
            source,
        ]
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _write_text(path: Path, text: str) -> None:
    """Write a UTF-8 file atomically inside the temporary bundle."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def _replace_directory(temporary: Path, out: Path) -> None:
    """Replace out/ with the fully rendered temporary directory."""
    if not out.exists():
        os.replace(temporary, out)
        return
    stale = out.with_name(f".{out.name}.stale-{os.getpid()}")
    if stale.exists():
        shutil.rmtree(stale)
    os.replace(out, stale)
    try:
        os.replace(temporary, out)
    except BaseException:
        os.replace(stale, out)
        raise
    shutil.rmtree(stale, ignore_errors=True)
