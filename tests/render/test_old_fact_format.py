"""Facts from older runs lack record, scope, conflicts and importance; rendering must not fail."""

from types import SimpleNamespace

from busybee.render.fact_fields import fact_field
from busybee.render.sections import facts_section, split_facts_by_importance
from busybee.render.statements import _binding_record
from busybee.schema.facts import VerifiedFact
from busybee.schema.policy import BoundInput
from busybee.schema.report import Report

OLD_FACT = {
    "fact_id": "F001",
    "statement": "Revenue from operations was INR 5000.00 crore in FY2025",
    "category": "revenue",
    "citations": [{"chunk_id": "D1:p9:c0", "doc_id": "D1", "page_no": 9, "quote": "Revenue"}],
    "numbers": [],
}


def test_old_format_fact_renders_in_sections() -> None:
    fact = VerifiedFact.model_validate(OLD_FACT)
    report = Report(run_id="r", facts={"F001": fact})
    assert "F001" in str(facts_section(report, 1))
    main, rest = split_facts_by_importance(report, 3)
    assert list(main) == ["F001"] and not rest


def test_objects_without_the_optional_fields_get_defaults() -> None:
    bare = SimpleNamespace(
        fact_id="F002", statement="x", citations=[], category="revenue", verification=None
    )
    assert fact_field(bare, "record") is None and fact_field(bare, "scope") is None
    assert fact_field(bare, "conflicts") == () and fact_field(bare, "importance") == 3
    bound = BoundInput(slot="revenue", fact_id="F002", value=1, unit="x", value_scaled=1)
    assert "metric" not in _binding_record(bound, {"F002": bare})  # type: ignore[dict-item]
