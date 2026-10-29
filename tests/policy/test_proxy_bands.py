"""A band that reads a proxy or incomplete input awards 0 points (Indoco v8: DSCR from a proxy).

The hand example scores FSS 63 (Adequate) with 15 DSCR points. When debt service is bound from an
interest-expense proxy (a profit and loss finance cost as the interest paid term, which code flags
as a proxy whatever the model's note says) the DSCR band is not evaluable: Lean computes
63 - 15 = 48 (Moderate), the score carries a caution naming the band and the report shows
"DSCR band: not evaluable (proxy)".
"""

import json
import shutil
from decimal import Decimal

import pytest
from policy_helpers import BANKS_DIR, binding_json, example_facts, judge_replies, write_facts

from busybee.lean.project import project_dir
from busybee.lean.toolchain import find_lake, find_lean
from busybee.llm import MockProvider
from busybee.policy.bands import BAND_NOT_EVALUABLE, excluded_bands, grade_steps, score_bands
from busybee.policy.bank_fs import load_bank
from busybee.policy.generate import build_scores_lean
from busybee.policy.run_scores import run_scores, score_adjustments
from busybee.render.statements import band_text, score_statement_html
from busybee.schema.policy import BoundInput

FSS = "financial_strength_score"
PROXY = "Interest expense used as a proxy for interest paid"
needs_lean = pytest.mark.skipif(
    find_lean() is None or find_lake() is None, reason="Lean toolchain is not installed"
)


def _policy() -> str:
    return (BANKS_DIR / "demo_bank" / "policy.lean").read_text()


def _fss():
    return next(s for s in load_bank(BANKS_DIR, "demo_bank").scores if s.score_id == FSS)


def _item(slot: str, caution: str = "") -> BoundInput:
    return BoundInput(
        slot=slot, fact_id="F001", value=Decimal(1), value_scaled=100, caution=caution
    )


def test_bands_and_grade_ladder_are_read_from_the_policy() -> None:
    bands = score_bands(_policy(), "financial_strength_score")
    assert [b.label for b in bands] == [
        "leverage",
        "interest_cover",
        "dscr",
        "current_ratio",
        "debt_equity",
        "revenue_growth",
    ]
    assert grade_steps(_policy(), "financial_strength_score") == (
        [(80, "Strong"), (60, "Adequate"), (40, "Moderate")],
        "Weak",
    )


def test_only_the_band_reading_the_cautioned_input_is_excluded() -> None:
    spec = _fss()
    bound = [_item(slot.slot) for slot in spec.inputs if slot.slot != "debt_service"]
    bound.append(_item("debt_service", f"proxy used: {PROXY}"))
    adjustment = excluded_bands(spec, bound, _policy())
    assert adjustment is not None
    assert [b.label for b in adjustment.bands] == ["dscr"]
    assert "debt_service" in adjustment.reasons["dscr"]
    assert excluded_bands(spec, [_item(s.slot) for s in spec.inputs], _policy()) is None


def test_generated_lean_subtracts_the_band_and_grades_the_adjusted_value() -> None:
    facts = example_facts()
    bank = load_bank(BANKS_DIR, "demo_bank")
    spec = _fss()
    bound = {FSS: [_item(slot.slot) for slot in spec.inputs if slot.slot != "debt_service"]}
    bound[FSS].append(_item("debt_service", f"proxy used: {PROXY}"))
    adjustments = score_adjustments([spec], bound, _policy())
    source = build_scores_lean(
        "BusyBee.Policy.DemoBank",
        [spec],
        bound,
        {f.fact_id: f for f in facts},
        adjustments=adjustments,
    )
    assert (
        "- (BusyBee.Policy.DemoBank.dscr_points financial_strength_score_cfads "
        "financial_strength_score_debt_service)" in source
    )
    assert 'if 80 ≤ financial_strength_score_value then "Strong"' in source
    assert bank.scores


@pytest.fixture
def clean_run_dir(run_config):
    yield
    shutil.rmtree(project_dir() / "Runs" / run_config.run_id, ignore_errors=True)


@needs_lean
async def test_a_proxy_debt_service_earns_no_dscr_points(
    tmp_path, run_config, clean_run_dir
) -> None:
    facts = example_facts()
    reply = json.loads(binding_json(facts))
    for item in reply["bindings"]:
        if item["slot"] == "debt_service":
            item.update(
                fact_id=None,
                value=None,
                note=PROXY,
                missing=["scheduled principal repayments"],
                terms=[
                    {
                        "fact_id": "F003",
                        "value": "150.00",
                        "unit": "INR crore",
                        "component": "interest paid",
                    }
                ],
            )
    provider = MockProvider(
        {"policy.bind_inputs": [json.dumps(reply)], "policy.judge_slot": judge_replies(facts)}
    )
    write_facts(tmp_path, facts)
    results = {r.score_id: r for r in await run_scores(tmp_path, run_config, provider, BANKS_DIR)}
    fss = results[FSS]
    assert fss.value_display == "48" and fss.grade == "Moderate"
    assert fss.bands == {"dscr": BAND_NOT_EVALUABLE}
    assert "dscr" in fss.caution and fss.caution in fss.warnings
    html = str(score_statement_html(fss))
    assert band_text("dscr", BAND_NOT_EVALUABLE) == "DSCR band: not evaluable (proxy)"
    assert "DSCR " in html and "0 pts (proxy input)" in html
