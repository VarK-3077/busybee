"""Unit tests for render link builders, statement fragments, and grade tones."""

from __future__ import annotations

import json
import re
from html import unescape

from busybee.render.lean_pages import explanation_html
from busybee.render.links import (
    artifact_slug,
    lean_href,
    pdf_href,
    report_pdf_href,
    source_href,
)
from busybee.render.statements import (
    citation_chip_html,
    grade_tone,
    lean_status_for_score,
    statement_html,
    tone_for_index,
)
from busybee.schema.documents import Document, DocumentKind
from busybee.schema.facts import Citation, Verification, VerificationStatus
from busybee.schema.lean import (
    CompileResult,
    ExplainItem,
    ExplainSection,
    LeanArtifact,
    LeanArtifactKind,
    LeanExplanation,
)
from busybee.schema.policy import ScoreResult, ScoreStatus


def test_source_and_pdf_links_are_bundle_relative() -> None:
    document = Document(
        doc_id="D2",
        title="Rating rationale",
        kind=DocumentKind.rating_rationale,
        source_path="/tmp/pack/rating rationale.pdf",
    )
    assert source_href("D2:p4:c1") == "sources/D2.html#D2:p4:c1"
    assert pdf_href(document, 4) == "../originals/rating%20rationale.pdf#page=4"
    assert lean_href("run-1:S1") == "lean/run-1-S1.html#lean-run-1-S1"
    assert artifact_slug("run-1:S1") == "run-1-S1"


def test_report_pdf_href_targets_pdf_originals_only() -> None:
    pdf = Document(
        doc_id="D2", title="R", kind=DocumentKind.rating_rationale, source_path="/x/a b.pdf"
    )
    news = Document(
        doc_id="D3", title="N", kind=DocumentKind.rating_rationale, source_path="/x/n.md"
    )
    bare = Document(doc_id="D4", title="B", kind=DocumentKind.rating_rationale)
    assert report_pdf_href(pdf, 4) == "originals/a%20b.pdf#page=4"
    assert report_pdf_href(news, 1) is None
    assert report_pdf_href(bare, 1) is None
    assert report_pdf_href(None, 1) is None
    assert report_pdf_href(pdf, 0) is None


def test_statement_html_escapes_text_and_appends_a_chip() -> None:
    citations = [
        Citation(chunk_id="D1:p1:c1", doc_id="D1", page_no=1, quote="one"),
        Citation(chunk_id="D1:p2:c1", doc_id="D1", page_no=2, quote="two"),
    ]
    verification = Verification(status=VerificationStatus.resupported, method="llm_entailment")
    html = str(statement_html("Revenue < 200 & rising", citations, "fact-F001", verification))
    assert "Revenue &lt; 200 &amp; rising" in html
    assert 'data-cites="D1:p1:c1,D1:p2:c1"' in html
    assert 'data-status="resupported"' in html
    assert 'data-method="llm_entailment"' in html
    assert '<span class="bb-cite-more">+1</span>' in html
    assert 'id="fact-F001-cite"' in html


def test_chip_carries_each_citations_own_quote() -> None:
    citations = [
        Citation(chunk_id="D1:p1:c1", doc_id="D1", page_no=1, quote='finance "cost" 5'),
        Citation(chunk_id="D1:p1:c2", doc_id="D1", page_no=1, quote="debtors 9"),
    ]
    html = str(citation_chip_html(citations))
    match = re.search(r'data-quotes="([^"]*)"', html)
    assert match is not None
    assert json.loads(unescape(match.group(1))) == ['finance "cost" 5', "debtors 9"]


def test_citation_chip_is_empty_without_citations() -> None:
    assert str(citation_chip_html([])) == ""


def test_grade_tones_follow_the_spec_order() -> None:
    assert grade_tone("Comfortable", ["Comfortable", "Watch", "Breach"]) == "good"
    assert grade_tone("Watch", ["Comfortable", "Watch", "Breach"]) == "weak"
    assert grade_tone("Breach", ["Comfortable", "Watch", "Breach"]) == "poor"
    assert grade_tone("Comfortable", ["Comfortable", "Breach"]) == "good"
    assert grade_tone("Breach", ["Comfortable", "Breach"]) == "poor"
    assert grade_tone(None) == "none"
    assert grade_tone("Adequate") == "fair"
    assert tone_for_index(0, 4) == "good"
    assert tone_for_index(3, 4) == "poor"


def test_lean_status_for_score_maps_policy_states() -> None:
    artifact = LeanArtifact(
        artifact_id="S1",
        kind=LeanArtifactKind.scores,
        source="theorem s1 : True := by trivial\n",
        theorems=["True"],
        compile=CompileResult(ok=True),
    )
    computed = ScoreResult(
        score_id="S1",
        status=ScoreStatus.computed,
        value_display="2.41×",
        grade="Comfortable",
        lean=artifact,
    )
    assert lean_status_for_score(computed) == "proved"

    failed_artifact = artifact.model_copy(
        update={"compile": CompileResult(ok=False, stderr="error")}
    )
    failed = computed.model_copy(
        update={"status": ScoreStatus.lean_failed, "lean": failed_artifact}
    )
    assert lean_status_for_score(failed) == "failed"

    unbound = ScoreResult(
        score_id="S2",
        status=ScoreStatus.not_computable,
        inputs=[],
        value_display=None,
        grade=None,
        lean=None,
    )
    assert lean_status_for_score(unbound) == "unchecked"

    no_compile = computed.model_copy(update={"lean": artifact.model_copy(update={"compile": None})})
    assert lean_status_for_score(no_compile) == "unchecked"


def test_explanation_html_renders_lean_beside_english() -> None:
    explanation = LeanExplanation(
        sections=[
            ExplainSection(
                title="Leverage",
                items=[
                    ExplainItem(
                        name="leverage_comfortable",
                        kind="def",
                        lean="def leverage_comfortable : Prop := net_debt ≤ 3 * ebitda",
                        english="Net debt is at most three times EBITDA.",
                        doc="Policy section 4.",
                    )
                ],
            )
        ]
    )
    html = str(explanation_html(explanation))
    assert 'class="bb-explain-section"' in html
    assert 'id="explain-leverage_comfortable"' in html
    assert "Net debt is at most three times EBITDA." in html
    assert "Policy section 4." in html
    assert "net_debt ≤ 3 * ebitda" in html
    assert str(explanation_html(None)) == ""


def test_bank_input_citation_shows_a_bank_input_chip() -> None:
    citation = Citation(
        chunk_id="REQ:p1:c1", doc_id="REQ", page_no=1, quote="q", source="bank_input"
    )
    html = str(citation_chip_html([citation]))
    assert "bank input" in html
    assert "bb-cite--bank" in html
    assert "REQ" not in html.split(">", 1)[1]
