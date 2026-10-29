"""Section 3 keeps important and referenced facts; the appendix holds every other fact."""

from busybee.orchestrate.config import build_run_config
from busybee.render.sections import appendix_section, facts_section, split_facts_by_importance
from busybee.schema.documents import Document, DocumentKind
from busybee.schema.facts import Citation, FactCategory, FactScope, VerifiedFact
from busybee.schema.policy import BoundInput, ScoreResult
from busybee.schema.report import Concern, Inference, KeyReason, Recommendation, Report


def _fact(fact_id: str, importance: int, category: FactCategory = FactCategory.revenue):
    return VerifiedFact(
        fact_id=fact_id, statement=f"Statement {fact_id}.", category=category, importance=importance
    )


def _report(**extra) -> Report:
    facts = {
        f.fact_id: f
        for f in (
            _fact("F001", 5),
            _fact("F002", 3),
            _fact("F003", 2),
            _fact("F004", 1, FactCategory.liquidity),
            _fact("F005", 1),
            _fact("F006", 2),
            _fact("F007", 1),
            _fact("F008", 2),
        )
    }
    return Report(run_id="r", facts=facts, **extra)


def test_low_importance_facts_move_to_the_appendix() -> None:
    report = _report()
    main, rest = split_facts_by_importance(report, 3)
    assert list(main) == ["F001", "F002"]
    assert list(rest) == ["F003", "F004", "F005", "F006", "F007", "F008"]
    html = str(facts_section(report, 3))
    assert "F001" in html and "F002" in html and "F003" not in html
    appendix = str(appendix_section(report, 3))
    assert 'id="appendix"' in appendix and "Appendix: other verified facts" in appendix
    assert 'id="appendix-group-liquidity"' in appendix and "F004" in appendix
    assert "F001" not in appendix


def test_referenced_facts_stay_in_the_main_section() -> None:
    report = _report(
        recommendation=Recommendation(
            decision="approve", key_reasons=[KeyReason(text="x", fact_ids=["F003"])]
        ),
        scores=[
            ScoreResult(
                score_id="s",
                inputs=[BoundInput(slot="a", fact_id="F004", value=1, derived_from=["F005"])],
            )
        ],
        inferences=[Inference(inference_id="I001", opinion="o", fact_ids=["F006"])],
        concerns=[Concern(concern_id="C001", opinion="c", fact_ids=["F007"])],
    )
    main, rest = split_facts_by_importance(report, 3)
    assert list(rest) == ["F008"]
    assert {"F003", "F004", "F005", "F006", "F007"} <= set(main)


def test_threshold_one_leaves_no_appendix_and_default_env_is_four() -> None:
    report = _report()
    assert str(appendix_section(report, 1, 0)) == ""
    cfg = build_run_config(".", "b", "out", env={})
    assert cfg.report_min_importance == 4
    cfg = build_run_config(".", "b", "out", env={"BUSYBEE_REPORT_MIN_IMPORTANCE": "3"})
    assert cfg.report_min_importance == 3


def _capped_report(**extra) -> Report:
    facts = [
        VerifiedFact(fact_id="F001", statement="Standalone revenue was 5.", importance=4),
        VerifiedFact(fact_id="F002", statement="Consolidated revenue was 6.", importance=4),
        VerifiedFact(
            fact_id="F003",
            statement="Revenue grew.",
            importance=4,
            citations=[Citation(chunk_id="c", doc_id="D1", page_no=1)],
        ),
        VerifiedFact(fact_id="F004", statement="Revenue top.", importance=5),
        VerifiedFact(fact_id="F005", statement="Revenue low.", importance=4),
        VerifiedFact(fact_id="F006", statement="Margin.", importance=4, category="profitability"),
    ]
    return Report(run_id="r", facts={f.fact_id: f for f in facts}, **extra)


def test_scope_is_derived_from_the_statement() -> None:
    report = _capped_report()
    assert report.facts["F001"].scope == FactScope.standalone
    assert report.facts["F002"].scope == FactScope.consolidated
    assert report.facts["F003"].scope is None


def test_cap_ranks_importance_then_consolidated_then_citations() -> None:
    main, rest = split_facts_by_importance(_capped_report(), 4, 3)
    assert list(main) == ["F002", "F003", "F004", "F006"]
    assert list(rest) == ["F001", "F005"]


def test_referenced_facts_survive_the_cap() -> None:
    report = _capped_report(
        inferences=[Inference(inference_id="I001", opinion="o", fact_ids=["F001", "F005"])]
    )
    main, rest = split_facts_by_importance(report, 4, 1)
    assert set(main) == {"F001", "F005", "F006"}
    assert set(rest) == {"F002", "F003", "F004"}
    assert split_facts_by_importance(_capped_report(), 4, 0)[1] == {}


def test_cap_default_and_env() -> None:
    assert build_run_config(".", "b", "out", env={}).report_max_facts_per_category == 10
    cfg = build_run_config(".", "b", "out", env={"BUSYBEE_REPORT_MAX_PER_CATEGORY": "2"})
    assert cfg.report_max_facts_per_category == 2


def test_shown_fact_ids_split_main_and_appendix() -> None:
    from busybee.render.sections import shown_fact_ids

    shown = shown_fact_ids(_report(), 4, 6)
    assert shown["main"] == ["F001"]
    assert shown["appendix"] == [f"F00{n}" for n in (2, 3, 4, 5, 6, 7, 8)]


def test_rating_rationale_facts_rank_first_and_qualify_one_point_lower() -> None:
    cite = Citation(chunk_id="D2:p1:c0", doc_id="D2", page_no=1)
    rated = _fact("F101", 3).model_copy(update={"citations": [cite]})
    plain = [_fact(f"F{i}", 4) for i in range(102, 105)]
    report = Report(
        run_id="r",
        facts={f.fact_id: f for f in (*plain, rated)},
        documents=[Document(doc_id="D2", title="ICRA", kind=DocumentKind.rating_rationale)],
    )
    main, rest = split_facts_by_importance(report, 4, 2)
    assert set(main) == {"F101", "F102"} and set(rest) == {"F103", "F104"}
