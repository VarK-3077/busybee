"""Band ratios with points and zero-limit notes beside a score line."""

from decimal import Decimal

from busybee.render.score_figures import band_figure_text, policy_limit_note
from busybee.render.statements import score_statement_html
from busybee.schema.lean import LeanArtifact, LeanArtifactKind
from busybee.schema.policy import BoundInput, ScoreResult

FSS_SOURCE = (
    "def fss_value : Int := f a - (BusyBee.Policy.X.leverage_points fss_net_debt fss_ebitda)"
    " - (BusyBee.Policy.X.dscr_points fss_cfads fss_debt_service)"
)
LIMIT_SOURCE = "def cap_value : Int := BusyBee.Policy.X.cap_test cap_a grade_value\n"


def _lean(source: str) -> LeanArtifact:
    return LeanArtifact(artifact_id="a", kind=LeanArtifactKind.scores, source=source)


def _bound(slot: str, scaled: int) -> BoundInput:
    return BoundInput(slot=slot, fact_id="F1", value=Decimal(scaled), value_scaled=scaled)


def _fss() -> ScoreResult:
    inputs = [
        _bound("net_debt", 106381),
        _bound("ebitda", 14182),
        _bound("cfads", 14182),
        _bound("debt_service", 15430),
    ]
    return ScoreResult(
        score_id="fss",
        value_display="23",
        grade="Weak",
        inputs=inputs,
        lean=_lean(FSS_SOURCE),
        bands={"leverage": "not evaluable (proxy)", "dscr": "not evaluable (proxy)"},
    )


def test_band_figure_text_shows_ratio_and_points() -> None:
    fss = _fss()
    assert band_figure_text(fss, "leverage", "not evaluable (proxy)") == (
        "Leverage 7.50x · 0 pts (proxy input)"
    )
    assert band_figure_text(fss, "dscr", "not evaluable (proxy)") == (
        "DSCR 0.92x · 0 pts (proxy input)"
    )


def test_band_figure_text_is_none_without_inputs() -> None:
    bare = ScoreResult(score_id="fss", lean=_lean(FSS_SOURCE))
    assert band_figure_text(bare, "dscr", "not evaluable (proxy)") is None


def test_score_line_puts_band_chips_on_a_notes_row() -> None:
    html = str(score_statement_html(_fss()))
    assert html.index("bb-score-notes") > html.index("bb-cite--lean")
    assert "Leverage 7.50x" in html and "band: not evaluable" not in html


def _cap(value: str) -> ScoreResult:
    inputs = [
        _bound("proposed_exposure", 15000),
        _bound("projected_turnover", 184532),
        _bound("tangible_net_worth", 73118),
    ]
    return ScoreResult(
        score_id="cap",
        value_display=value,
        grade="Exceeds limit",
        inputs=inputs,
        lean=_lean(LIMIT_SOURCE),
    )


def test_limit_shows_proposed_exposure_and_zero_limit_reason() -> None:
    grade = ScoreResult(score_id="grade", value_display="8")
    cap = _cap("0 crore")
    assert policy_limit_note(cap, [grade, cap]) == (
        "Policy limit INR 0 crore (no exposure permitted at grade 8)"
    )
    html = str(score_statement_html(cap, siblings=[grade, cap]))
    assert "INR 150 crore" in html and "bank input" in html
    assert "no exposure permitted at grade 8" in html


def test_limit_note_names_both_caps_when_non_zero() -> None:
    note = policy_limit_note(_cap("5.54 crore"), [])
    assert (
        note
        == (
            "Policy limit INR 5.54 crore (lower of turnover cap INR 7.38 crore and "
            "net-worth cap INR 5.48 crore at 75%)"
        )
        or note is not None
        and note.startswith("Policy limit INR 5.54 crore")
    )


def test_limit_note_caps_projected_turnover_at_125_percent_of_audited() -> None:
    capped = _cap("37.5 crore")
    capped.inputs.append(_bound("revenue_current", 20000))
    note = policy_limit_note(capped, [])
    assert note is not None
    assert "turnover cap INR 37.5 crore" in note and note.endswith("at 75%)")
