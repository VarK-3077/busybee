"""Check the compact fact and score rendering used in inference prompts."""

from decimal import Decimal

from busybee.infer.compact_facts import compact_fact, compact_facts, compact_score
from busybee.schema.facts import (
    Citation,
    FactCategory,
    NumericValue,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.schema.policy import BoundInput, ScoreResult, ScoreStatus


def _fact() -> VerifiedFact:
    return VerifiedFact(
        fact_id="F012",
        statement="Revenue from operations grew 12% to INR 1,234.50 crore in FY26.",
        category=FactCategory.revenue,
        citations=[Citation(chunk_id="D1:p8:c2", doc_id="D1", page_no=8)],
        numbers=[
            NumericValue(label="Revenue", value=Decimal("1234.50"), unit="crore", period="FY26"),
            NumericValue(label="Growth", value=Decimal("12"), unit="%", period="FY26"),
        ],
        verification=Verification(status=VerificationStatus.supported),
    )


def test_compact_fact_has_id_category_statement_and_numbers() -> None:
    rendered = compact_fact(_fact())
    assert rendered.startswith("F012 | revenue | Revenue from operations grew 12%")
    assert "Revenue 1234.50 crore FY26" in rendered
    assert "Growth 12 % FY26" in rendered
    assert "\n" not in rendered


def test_compact_score_includes_status_value_grade_and_facts() -> None:
    score = ScoreResult(
        score_id="S001",
        status=ScoreStatus.computed,
        value_display="72",
        grade="Adequate",
        inputs=[
            BoundInput(slot="net_debt", fact_id="F012", value=Decimal("10")),
            BoundInput(slot="ebitda", fact_id="F013", value=Decimal("20")),
        ],
    )
    rendered = compact_score(score)
    assert rendered == "S001 | score | computed | 72 | Adequate | F012,F013"


def test_compact_facts_appends_scores_after_facts() -> None:
    score = ScoreResult(score_id="S001", status=ScoreStatus.not_computable)
    lines = compact_facts([_fact()], [score]).splitlines()
    assert lines[0].startswith("F012 | revenue |")
    assert lines[1] == "S001 | score | not_computable"
