"""A winner shows the conflict badge; the loser is appendix-only; the concern is open."""

from busybee.render.sections import appendix_section, concerns_section, facts_section
from busybee.schema.facts import (
    ConflictNote,
    FactCategory,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.schema.report import Concern, Report


def _report() -> Report:
    winner = VerifiedFact(
        fact_id="F001",
        statement="Revenue was INR 931.2 crore in FY25.",
        category=FactCategory.revenue,
        importance=5,
        conflicts=[ConflictNote(fact_id="F087", note="News says Rs 1,018 crore <b>")],
    )
    loser = VerifiedFact(
        fact_id="F087",
        statement="Revenue was Rs 1,018 crore in FY25.",
        category=FactCategory.revenue,
        importance=5,
        verification=Verification(status=VerificationStatus.conflicted),
    )
    concern = Concern(
        concern_id="CF001",
        opinion="Sources disagree on revenue for FY25: F001 versus F087.",
        fact_ids=["F001", "F087"],
        reasoning="F001 is kept.",
    )
    return Report(
        run_id="r",
        facts={"F001": winner, "F087": loser},
        concerns=[concern],
    )


def test_badge_lists_conflicting_fact_and_escapes_note() -> None:
    html = str(facts_section(_report()))
    assert 'class="bb-badge bb-conflict" data-status="conflict"' in html
    assert "F087" in html and "News says Rs 1,018 crore &lt;b&gt;" in html


def test_conflicted_fact_is_not_in_facts() -> None:
    report = _report()
    html = str(facts_section(report))
    assert 'id="fact-F087"' not in html
    assert 'id="fact-F001"' in html


def test_conflict_concern_is_in_open_concerns() -> None:
    html = str(concerns_section(_report().concerns))
    assert 'id="concern-CF001"' in html and "Sources conflict" in html
    assert "F001" in html and "F087" in html


def test_conflicted_fact_renders_in_appendix_only() -> None:
    report = _report()
    appendix = str(appendix_section(report))
    assert 'id="fact-F087"' in appendix and 'data-ref="F087"' in appendix
    assert "Revenue was Rs 1,018 crore in FY25." in appendix
    assert 'data-status="conflicted"' in appendix
    assert "overruled by F001 (source priority)" in appendix
    assert 'id="fact-F087"' not in str(facts_section(report))
