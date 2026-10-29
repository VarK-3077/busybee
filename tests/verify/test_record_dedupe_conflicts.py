"""Record facts are deduped and conflicted on fields, never on wording similarity."""

from decimal import Decimal

from busybee.extract.templates import record_numbers, statement_from_record
from busybee.schema.facts import (
    Citation,
    FactCategory,
    FactRecord,
    FactScope,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.verify.conflicts import find_conflict_candidates
from busybee.verify.dedupe import dedupe_facts


def record_fact(fact_id: str, doc: str = "D1", **changes: object) -> VerifiedFact:
    base = {
        "metric": "Revenue from operations",
        "value": Decimal("1845.32"),
        "unit": "crore",
        "period": "FY2025-26",
        "scope": FactScope.consolidated,
    }
    record = FactRecord.model_validate(base | changes)
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement_from_record(record),
        category=FactCategory.revenue,
        citations=[Citation(chunk_id=f"{doc}:p1:c0", doc_id=doc, page_no=1)],
        numbers=record_numbers(record),
        verification=Verification(status=VerificationStatus.supported),
        record=record,
    )


def test_same_record_in_different_units_and_period_forms_is_a_duplicate() -> None:
    first = record_fact("")
    second = record_fact("", unit="lakh", value=Decimal("184532"), period="FY26")
    assert len(dedupe_facts([first, second])) == 1


def test_scope_period_value_and_metric_keep_records_apart() -> None:
    base = record_fact("")
    for other in (
        record_fact("", scope=FactScope.standalone),
        record_fact("", period="FY2024-25"),
        record_fact("", value=Decimal("1900")),
        record_fact("", metric="Other income"),
        record_fact("", qualifier="restated"),
    ):
        assert len(dedupe_facts([base, other])) == 2


def test_conflict_candidate_needs_same_metric_period_and_scope_with_different_values() -> None:
    first = record_fact("F001", "D1")
    clash = record_fact("F002", "D2", value=Decimal("1900"))
    candidates = find_conflict_candidates([first, clash])
    assert len(candidates) == 1
    assert (candidates[0].period, candidates[0].unit) == ("FY26", "INR crore")
    assert candidates[0].values == (Decimal("1845.32"), Decimal("1900"))
    same_in_lakh = record_fact("F003", "D2", unit="lakh", value=Decimal("184532"))
    assert find_conflict_candidates([first, same_in_lakh]) == []
    assert (
        find_conflict_candidates([first, record_fact("F004", scope=None, value=Decimal("1"))]) == []
    )
    assert (
        find_conflict_candidates(
            [first, record_fact("F005", period="FY2024-25", value=Decimal("1"))]
        )
        == []
    )
