"""A score with invariant warnings shows a warning badge and ships them in the popover record."""

from busybee.render.statements import score_lean_record, score_statement_html
from busybee.schema.policy import ScoreResult


def test_warning_badge_and_record() -> None:
    score = ScoreResult(score_id="fss", warnings=["Net debt cannot exceed total debt [F1, F2]"])
    html = str(score_statement_html(score))
    assert 'data-status="unchecked"' in html
    assert "1 warning" in html
    assert score_lean_record(score, {})["warnings"] == score.warnings
    assert "warning" not in str(score_statement_html(ScoreResult(score_id="fss")))
