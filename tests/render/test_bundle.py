"""End-to-end tests for the static HTML bundle renderer."""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

from busybee.ingest.corpus_store import write_corpus
from busybee.render.bundle import render_bundle
from busybee.schema.documents import Chunk, Document, DocumentKind, Page
from busybee.schema.facts import (
    Citation,
    FactCategory,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.schema.io import write_json_atomic, write_model_atomic
from busybee.schema.lean import CompileResult, LeanArtifact, LeanArtifactKind
from busybee.schema.policy import BoundInput, ScoreResult, ScoreStatus
from busybee.schema.report import (
    AuditBlock,
    Concern,
    Decision,
    FactGroup,
    Inference,
    KeyReason,
    PolicyCitation,
    Recommendation,
    Report,
)

PAGE_ONE = (
    "Alpha start. Revenue from operations rose to 1284.6 crore in FY2025 "
    "from 1102.3 crore in FY2024, an increase of 16.5 per cent. "
    "Filler material appears between the two chunks. "
    "EBITDA was 171.2 crore and finance costs were 38.9 crore. "
    "The final sentence closes the page."
)
FIRST_SENTENCE = (
    "Alpha start. Revenue from operations rose to 1284.6 crore in FY2025 "
    "from 1102.3 crore in FY2024, an increase of 16.5 per cent."
)
PAGE_TWO = (
    "Beta start. Total borrowings were 462.0 crore as at 31 March 2025. "
    "A customs demand of 27.3 crore is under appeal and unprovided."
)
PAGE_THREE = (
    "Gamma start. CARE Ratings reaffirmed the long-term facilities at CARE A-; "
    "Stable in September 2024."
)


class PageCollector(HTMLParser):
    """Collect ids, citation ids, Lean ids, and per-chunk text from one page."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.cites: list[str] = []
        self.lean: list[str] = []
        self.text: list[str] = []
        self.chunk_text: dict[str, str] = {}
        self._current_chunk: str | None = None
        self._in_chunk_id = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        element_id = attributes.get("id")
        if element_id:
            self.ids.add(element_id)
        if attributes.get("data-cites"):
            self.cites.extend(
                part.strip() for part in str(attributes["data-cites"]).split(",") if part.strip()
            )
        if attributes.get("data-lean"):
            self.lean.append(str(attributes["data-lean"]))
        classes = str(attributes.get("class", "")).split()
        if "bb-chunk-id" in classes:
            self._in_chunk_id = True
        if tag == "section" and "bb-chunk" in classes and element_id:
            self._current_chunk = element_id

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._in_chunk_id = False
        if tag == "section":
            self._current_chunk = None

    def handle_data(self, data: str) -> None:
        self.text.append(data)
        if self._current_chunk and not self._in_chunk_id:
            self.chunk_text[self._current_chunk] = (
                self.chunk_text.get(self._current_chunk, "") + data
            )


def _squash(text: str) -> str:
    """Collapse template whitespace so text comparisons ignore layout."""
    return " ".join(text.split())


def _collect(html: str) -> PageCollector:
    """Parse an HTML file and return the collected attributes and text."""
    parser = PageCollector()
    parser.feed(html)
    parser.close()
    return parser


def _blob(html: str, blob_id: str) -> dict[str, object]:
    """Extract one application/json blob from a rendered page."""
    match = re.search(
        rf'<script type="application/json" id="{blob_id}">(.*?)</script>',
        html,
        re.DOTALL,
    )
    assert match is not None
    return json.loads(match.group(1))


def _citation(chunk_id: str, doc_id: str, page_no: int, quote: str) -> Citation:
    """Build a citation for the fake corpus."""
    return Citation(chunk_id=chunk_id, doc_id=doc_id, page_no=page_no, quote=quote)


def _fact(
    fact_id: str,
    statement: str,
    category: FactCategory,
    citation: Citation,
    status: VerificationStatus = VerificationStatus.supported,
) -> VerifiedFact:
    """Build a verified fact with one citation."""
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        category=category,
        citations=[citation],
        verification=Verification(status=status, method="exact_match"),
    )


def _build_run(base: Path, *, policy_approved: bool = False) -> Path:
    """Write a small workspace, fake bank and corpus, then render the bundle."""
    docs_dir = base / "docs"
    workspace = base / "workspace"
    banks_dir = base / "banks"
    docs_dir.mkdir(parents=True)
    (docs_dir / "annual.pdf").write_bytes(b"%PDF-1.4 fake annual report")
    (docs_dir / "rating.pdf").write_bytes(b"%PDF-1.4 fake rating rationale")

    documents = [
        Document(
            doc_id="D1",
            title="Acme Textiles Ltd — Annual Report FY2025",
            kind=DocumentKind.annual_report,
            source_path=str(docs_dir / "annual.pdf"),
            sha256="a" * 64,
            num_pages=2,
        ),
        Document(
            doc_id="D2",
            title="Acme Textiles Ltd — Rating Rationale",
            kind=DocumentKind.rating_rationale,
            source_path=str(docs_dir / "rating.pdf"),
            sha256="b" * 64,
            num_pages=1,
        ),
    ]

    first_end = len(FIRST_SENTENCE)
    second_start = PAGE_ONE.index("Revenue from operations")
    second_end = PAGE_ONE.index("The final sentence")
    chunks = [
        Chunk(
            chunk_id="D1:p1:c1",
            doc_id="D1",
            page_no=1,
            index_in_page=1,
            text=PAGE_ONE[:first_end],
            char_start=0,
            char_end=first_end,
        ),
        Chunk(
            chunk_id="D1:p1:c2",
            doc_id="D1",
            page_no=1,
            index_in_page=2,
            text=PAGE_ONE[second_start:second_end],
            char_start=second_start,
            char_end=second_end,
        ),
        Chunk(
            chunk_id="D1:p2:c1",
            doc_id="D1",
            page_no=2,
            index_in_page=1,
            text=PAGE_TWO,
            char_start=0,
            char_end=len(PAGE_TWO),
        ),
        Chunk(
            chunk_id="D2:p1:c1",
            doc_id="D2",
            page_no=1,
            index_in_page=1,
            text=PAGE_THREE,
            char_start=0,
            char_end=len(PAGE_THREE),
        ),
    ]
    pages_by_doc = {
        "D1": [
            Page(doc_id="D1", page_no=1, text=PAGE_ONE),
            Page(doc_id="D1", page_no=2, text=PAGE_TWO),
        ],
        "D2": [Page(doc_id="D2", page_no=1, text=PAGE_THREE)],
    }
    write_corpus(workspace, documents, pages_by_doc, chunks)

    c1 = _citation(
        "D1:p1:c1",
        "D1",
        1,
        "Revenue from operations rose to 1284.6 crore in FY2025 from 1102.3 crore "
        "in FY2024, an increase of 16.5 per cent.",
    )
    c2 = _citation(
        "D1:p1:c2",
        "D1",
        1,
        "EBITDA was 171.2 crore and finance costs were 38.9 crore.",
    )
    c3 = _citation(
        "D1:p2:c1",
        "D1",
        2,
        "Total borrowings were 462.0 crore as at 31 March 2025.",
    )
    c4 = _citation(
        "D2:p1:c1",
        "D2",
        1,
        "CARE Ratings reaffirmed the long-term facilities at CARE A-; Stable in September 2024.",
    )
    c5 = _citation(
        "D1:p2:c1",
        "D1",
        2,
        "A customs demand of 27.3 crore is under appeal and unprovided.",
    )
    facts = {
        "F001": _fact(
            "F001",
            "Revenue rose 16.5 per cent to 1284.6 crore.",
            FactCategory.revenue,
            c1,
        ),
        "F002": _fact(
            "F002",
            "Exports were 58 per cent of revenue.",
            FactCategory.revenue,
            c2,
        ),
        "F003": _fact(
            "F003",
            "Net debt was 412.6 crore.",
            FactCategory.debt_leverage,
            c3,
        ),
        "F004": _fact(
            "F004",
            "EBITDA was 171.2 crore and finance costs 38.9 crore.",
            FactCategory.profitability,
            c2,
        ),
        "F005": _fact(
            "F005",
            "CARE Ratings reaffirmed CARE A-; Stable.",
            FactCategory.ratings,
            c4,
            VerificationStatus.resupported,
        ),
        "F006": _fact(
            "F006",
            "A 27.3 crore customs demand is under appeal.",
            FactCategory.litigation_regulatory,
            c5,
        ),
    }

    score_artifact = LeanArtifact(
        artifact_id="S1",
        kind=LeanArtifactKind.scores,
        file_path="lean/Runs/run-1/Scores.lean",
        source=(
            "-- SECTION: Leverage\n"
            "def net_debt : Int := 41260 -- F003 D1:p2:c1\n"
            "def ebitda : Int := 17120 -- F004 D1:p1:c2\n\n"
            "/-- Net debt stays under three times EBITDA. -/\n"
            "theorem s1 : 10 * net_debt ≤ 30 * ebitda := by decide\n"
        ),
        sha256="c" * 64,
        theorems=["10 * net_debt ≤ 30 * ebitda"],
        compile=CompileResult(
            ok=True,
            stdout="",
            stderr="",
            duration_s=0.42,
            toolchain="leanprover/lean4:v4.12.0",
        ),
    )
    score = ScoreResult(
        score_id="S1",
        status=ScoreStatus.computed,
        inputs=[
            BoundInput(
                slot="net_debt",
                fact_id="F003",
                value=Decimal("412.6"),
                unit="₹ crore",
                value_scaled=41260,
            ),
            BoundInput(
                slot="ebitda",
                fact_id="F004",
                value=Decimal("171.2"),
                unit="₹ crore",
                value_scaled=17120,
            ),
        ],
        value_display="2.41×",
        grade="Comfortable",
        lean=score_artifact,
    )

    inference_artifact = LeanArtifact(
        artifact_id="I1",
        kind=LeanArtifactKind.inference,
        file_path="lean/Runs/run-1/Inference_I1.lean",
        source="theorem i1 : 10 * (41260 + 6000) < 300 * 17120 := by decide\n",
        sha256="d" * 64,
        theorems=["10 * (41260 + 6000) < 300 * 17120"],
        compile=CompileResult(
            ok=True,
            duration_s=0.31,
            toolchain="leanprover/lean4:v4.12.0",
        ),
    )
    inferences = [
        Inference(
            inference_id="I1",
            opinion="Leverage leaves headroom for the proposed limit.",
            fact_ids=["F003", "F004"],
            reasoning="Net debt plus the limit stays under three times EBITDA.",
            confidence=0.8,
            quantitative=True,
            lean=inference_artifact,
        ),
        Inference(
            inference_id="I2",
            opinion="Growth is increasingly export-led.",
            fact_ids=["F001", "F002"],
            reasoning="Export share rose while revenue grew.",
            confidence=0.5,
            quantitative=False,
        ),
    ]
    concerns = [
        Concern(
            concern_id="C1",
            opinion="The customs appeal outcome is unknown.",
            fact_ids=["F006", "F003"],
            reasoning="An adverse ruling would absorb much of year-end cash.",
            query_used="CESTAT customs duty drawback appeal hearing outcome",
            found=False,
        )
    ]
    recommendation = Recommendation(
        decision=Decision.approve_with_conditions,
        headline="Approve the working-capital limit with conditions.",
        proposed_limit="₹60.0 crore",
        conditions=["Quarterly stock and receivables statements."],
        key_reasons=[
            KeyReason(
                text="Net debt/EBITDA of 2.7x is within the 3.5x policy cap.",
                kind="policy_rule",
                policy_citations=[
                    PolicyCitation(section_id="P2", heading="Leverage", quote="at most 3.5 times")
                ],
                fact_ids=["F003"],
                score_ids=["S1"],
            ),
            KeyReason(text="Cash is ample at year end.", kind="hard_fact", fact_ids=["F003"]),
            KeyReason(text="Demand should stay firm.", kind="inference", inference_ids=["I1"]),
        ],
        confidence_note="Moderate confidence: one annual report only.",
    )
    report = Report(
        run_id="run-1",
        company="Acme Textiles Ltd",
        bank_id="demo_bank",
        policy_approved=policy_approved,
        recommendation=recommendation,
        facts=facts,
        fact_groups=[
            FactGroup(category=FactCategory.revenue, fact_ids=["F001", "F002"]),
            FactGroup(category=FactCategory.profitability, fact_ids=["F004"]),
            FactGroup(category=FactCategory.debt_leverage, fact_ids=["F003"]),
            FactGroup(category=FactCategory.ratings, fact_ids=["F005"]),
            FactGroup(category=FactCategory.litigation_regulatory, fact_ids=["F006"]),
            FactGroup(category=FactCategory.liquidity, fact_ids=[]),
        ],
        scores=[score],
        inferences=inferences,
        concerns=concerns,
        documents=documents,
        audit=AuditBlock(
            models={"extract": "mock-model"},
            stage_timings={"render": 0.1},
            llm_calls=12,
            policy_version="1.0",
            lean_toolchain="leanprover/lean4:v4.12.0",
            generated_at=datetime(2026, 10, 26, 12, 0),
        ),
    )
    write_model_atomic(workspace / "report.json", report)

    bank_dir = banks_dir / "demo_bank"
    bank_dir.mkdir(parents=True)
    write_json_atomic(
        bank_dir / "approval.json",
        {
            "approved": policy_approved,
            "by": "A. Reviewer" if policy_approved else None,
            "date": "21 Oct 2026",
            "notes": "Reviewed.",
            "generated_by": "model-x-large",
        },
    )
    (bank_dir / "policy.md").write_text(
        "# Demo Bank — Credit Policy\n\nVersion 1.0.\n\n## Leverage\n\n"
        "Net debt / EBITDA must be at most 3.5 times.\n\n| Ratio | Limit |\n|---|---|\n"
        "| Net debt / EBITDA | at most 3.5 times |\n",
        encoding="utf-8",
    )
    (bank_dir / "scores.yaml").write_text(
        "scores:\n"
        "  - score_id: S1\n"
        "    name: Net debt to EBITDA\n"
        "    description: Leverage.\n"
        "    lean_function: s1\n"
        "    grades:\n"
        "      - label: Comfortable\n"
        "      - label: Watch\n"
        "      - label: Breach\n",
        encoding="utf-8",
    )
    (bank_dir / "policy.lean").write_text(
        "-- SECTION: Leverage\n"
        "/-- Net debt is at most three times EBITDA. -/\n"
        "def leverage_comfortable (net_debt ebitda : Int) : Prop :=\n"
        "  0 < ebitda ∧ net_debt ≤ 3 * ebitda\n",
        encoding="utf-8",
    )

    return render_bundle(workspace, base / "out", banks_dir=banks_dir)


def test_bundle_writes_files_and_every_citation_resolves(tmp_path: Path) -> None:
    out = _build_run(tmp_path)
    expected = [
        "index.html",
        "policy.html",
        "sources/D1.html",
        "sources/D2.html",
        "lean/S1.html",
        "lean/I1.html",
        "lean/S1.lean",
        "lean/I1.lean",
        "assets/tokens.css",
        "assets/document.css",
        "assets/components.css",
        "assets/components.js",
        "data/report.json",
        "originals/annual.pdf",
        "originals/rating.pdf",
    ]
    for relative in expected:
        assert (out / relative).is_file(), relative

    for html_path in out.rglob("*.html"):
        _collect(html_path.read_text(encoding="utf-8"))

    index_html = (out / "index.html").read_text(encoding="utf-8")
    index = _collect(index_html)
    chunk_blob = _blob(index_html, "bb-chunks")
    lean_blob = _blob(index_html, "bb-lean")

    source_pages = {
        doc_id: _collect((out / "sources" / f"{doc_id}.html").read_text(encoding="utf-8"))
        for doc_id in ("D1", "D2")
    }
    assert index.cites
    policy_page = _collect((out / "policy.html").read_text(encoding="utf-8"))
    for chunk_id in index.cites:
        assert chunk_id in chunk_blob
        if chunk_id.startswith("P"):
            assert chunk_id in policy_page.ids
            assert chunk_blob[chunk_id]["href"] == f"policy.html#{chunk_id}"
            assert chunk_blob[chunk_id]["quote"] == "at most 3.5 times"
            continue
        doc_id = chunk_id.split(":", 1)[0]
        assert chunk_id in source_pages[doc_id].ids
        record = chunk_blob[chunk_id]
        assert record["href"] == f"sources/{doc_id}.html#{chunk_id}"
        assert str(record["pdf_href"]).startswith("originals/")
        assert str(record["pdf_href"]).endswith(f"#page={record['page_no']}")
        assert "new_tab" not in record

    assert index.lean
    for lean_id in index.lean:
        assert lean_id in lean_blob
        href = lean_blob[lean_id]["href"]
        if href is not None:
            assert str(href).startswith("lean/")

    assert "bb-notice" in index_html
    assert "policy.html" in index_html


def test_notice_bar_only_appears_for_unapproved_policy(tmp_path: Path) -> None:
    approved_out = _build_run(tmp_path / "approved", policy_approved=True)
    approved_index = (approved_out / "index.html").read_text(encoding="utf-8")
    approved_policy = (approved_out / "policy.html").read_text(encoding="utf-8")
    assert "bb-notice" not in approved_index
    assert "Policy approved" in approved_policy

    unapproved_out = _build_run(tmp_path / "unapproved", policy_approved=False)
    unapproved_index = (unapproved_out / "index.html").read_text(encoding="utf-8")
    assert "bb-notice" in unapproved_index


def test_source_page_renders_overlap_only_once(tmp_path: Path) -> None:
    out = _build_run(tmp_path)
    html = (out / "sources" / "D1.html").read_text(encoding="utf-8")
    page = _collect(html)

    first = _squash(page.chunk_text["D1:p1:c1"])
    second = _squash(page.chunk_text["D1:p1:c2"])
    first_end = len(FIRST_SENTENCE)
    second_end = PAGE_ONE.index("The final sentence")
    assert first == _squash(PAGE_ONE[:first_end])
    assert second == _squash(PAGE_ONE[first_end:second_end])
    assert "Filler material appears between the two chunks." in second
    assert html.count(FIRST_SENTENCE) == 1


def test_policy_page_shows_source_when_explainer_is_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    import busybee.lean.explain.build as explain_build

    def unavailable(source: str):
        raise RuntimeError("explainer still in progress")

    monkeypatch.setattr(explain_build, "explain_source", unavailable)
    out = _build_run(tmp_path)
    policy_html = (out / "policy.html").read_text(encoding="utf-8")
    assert "def leverage_comfortable" in policy_html
    assert "bb-explain" not in policy_html


def test_recommendation_groups_reasons_by_kind_in_sketch_order(tmp_path: Path) -> None:
    index_html = (_build_run(tmp_path) / "index.html").read_text(encoding="utf-8")

    rules = index_html.index("Hard rules from bank policies")
    facts = index_html.index("Hard facts")
    inferences = index_html.index("Inferences &amp; guess of future")
    assert rules < facts < inferences
    assert index_html.index("bb-headline") < rules
    assert 'data-cites="P2"' in index_html
    assert "Net debt/EBITDA of 2.7x is within the 3.5x policy cap." in index_html


def test_policy_page_anchors_every_section(tmp_path: Path) -> None:
    policy_html = (_build_run(tmp_path) / "policy.html").read_text(encoding="utf-8")

    assert 'id="P1"' in policy_html and 'id="P2"' in policy_html
    assert "<table" in policy_html


def test_header_links_policy_and_has_no_run_field(tmp_path: Path) -> None:
    for approved in (False, True):
        html = _build_run(tmp_path / str(approved), policy_approved=approved) / "index.html"
        text = html.read_text(encoding="utf-8")
        assert '<dt>Bank policy</dt><dd><a href="policy.html">' in text
        assert "<dt>Run</dt>" not in text


def test_sections_run_recommendation_scores_facts_inferences_concerns(tmp_path: Path) -> None:
    text = (_build_run(tmp_path) / "index.html").read_text(encoding="utf-8")
    order = [
        text.index(f'id="{section}"')
        for section in ("recommendation", "scores", "facts", "inferences", "concerns")
    ]
    assert order == sorted(order)
    assert "Policy scores" in text
    assert 'id="group-scores"' not in text


def test_statement_ids_trail_the_sentence_and_scores_have_no_margin_id(tmp_path: Path) -> None:
    text = (_build_run(tmp_path) / "index.html").read_text(encoding="utf-8")
    assert "bb-fact-id" not in text and "bb-block-id" not in text
    assert '<a class="bb-sid" href="#fact-F001">F001</a><button class="bb-cite"' in text
    assert 'class="bb-sid" href="#inf-I1"' in text
    score = text[text.index('id="score-S1"') :].split("</li>", 1)[0]
    assert "bb-sid" not in score and "bb-score-leader" in score
    assert "data-paginate" in text


def test_lean_page_links_its_bundled_source_not_the_local_path(tmp_path: Path) -> None:
    out = _build_run(tmp_path)
    page = (out / "lean" / "S1.html").read_text(encoding="utf-8")
    assert 'href="S1.lean"' in page and "lean/S1.lean" in page
    assert "lean/Runs/run-1" not in page


def test_notice_names_a_generator_only_when_there_is_one() -> None:
    from busybee.render.sections import approval_notice_html

    hand = str(approval_notice_html(approved=False, policy_label="Demo policy"))
    assert "formalisation of Demo policy has not yet been reviewed and approved" in hand
    assert "generated by" not in hand
    made = str(approval_notice_html(approved=False, policy_label="P", generated_by="model-x"))
    assert "generated by" in made and "model-x" in made


def test_bundle_writes_shown_fact_ids(tmp_path: Path) -> None:
    out = _build_run(tmp_path)
    shown = json.loads((out / "data" / "shown_facts.json").read_text())
    report = json.loads((out / "data" / "report.json").read_text())
    assert set(shown) == {"main", "appendix"}
    assert set(shown["main"]) | set(shown["appendix"]) == set(report["facts"])
    assert not set(shown["main"]) & set(shown["appendix"])
