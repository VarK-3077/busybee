"""End to end score stage: real Lean on the demo bank and a hand-computed borrower.

Example: net debt 1250 on EBITDA 420 earns 14, EBITDA 420 on interest 150 earns 10, CFADS 300
on debt service 200 earns 15, current ratio 1800/1300 earns 11, debt/equity 1.5 earns 7 and
revenue growth 8.7 percent earns 6: FSS 63 (Adequate). Base grade 4, rating index 9 floor 4,
one red flag adds a notch: IRG 5 (Acceptable risk), P = 50. Exposure 400 against turnover 6000
and net worth 1000 passes both caps: Within limit.
"""

import json
import shutil
import uuid

import pytest
from policy_helpers import BANKS_DIR, binding_json, example_facts, judge_replies, write_facts

from busybee.lean.compile import compile_file
from busybee.lean.project import camel_bank_id, project_dir
from busybee.lean.toolchain import find_lake, find_lean
from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.generate import build_scores_lean
from busybee.policy.run_scores import run_scores
from busybee.schema.policy import ScoreStatus

pytestmark = pytest.mark.skipif(
    find_lean() is None or find_lake() is None, reason="Lean toolchain is not installed"
)


@pytest.fixture(autouse=True)
def clean_run_dir(run_config):
    yield
    shutil.rmtree(project_dir() / "Runs" / run_config.run_id, ignore_errors=True)


async def test_generated_source_has_sections_and_provenance(example_provider) -> None:
    from busybee.policy.bind_inputs import bind_inputs
    from busybee.policy.policy_sections import split_policy_sections

    facts = example_facts()
    bank = load_bank(BANKS_DIR, "demo_bank")
    sections = split_policy_sections(bank.policy_md)
    bound = (await bind_inputs(example_provider, bank.scores, facts, sections)).bound
    source = build_scores_lean(
        "BusyBee.Policy.DemoBank", bank.scores, bound, {f.fact_id: f for f in facts}
    )
    assert "import BusyBee.Policy.DemoBank" in source
    for title in ("Facts", "Scores", "Checks"):
        assert f"-- SECTION: {title}" in source
    assert "def financial_strength_score_net_debt : Int := 125000 -- F001 D1:p1:c1" in source
    assert 'IO.println s!"internal_risk_grade_grade={internal_risk_grade_grade_label}"' in source
    assert "def maximum_exposure_internal_risk_grade" not in source
    assert "BusyBee.Policy.DemoBank.maximum_exposure_test " in source


async def test_all_scores_computed_by_lean(tmp_path, run_config, example_provider) -> None:
    write_facts(tmp_path, example_facts())
    results = await run_scores(tmp_path, run_config, example_provider, BANKS_DIR)
    got = {r.score_id: (r.status, r.value_display, r.grade) for r in results}
    assert got == {
        "financial_strength_score": (ScoreStatus.computed, "63", "Adequate"),
        "internal_risk_grade": (ScoreStatus.computed, "5", "Acceptable risk"),
        "maximum_exposure": (ScoreStatus.computed, "500 crore", "Within limit"),
    }
    artifact = results[0].lean
    assert artifact is not None and artifact.compile is not None and artifact.compile.ok
    assert "financial_strength_score_value_is" in artifact.theorems
    assert artifact.sha256
    saved = json.loads((tmp_path / "scores.json").read_text())
    assert [item["score_id"] for item in saved] == [r.score_id for r in results]
    assert saved[0]["inputs"][0]["fact_id"] == "F001"


async def test_bank_inputs_become_facts_and_feed_the_exposure_test(tmp_path, run_config) -> None:
    from decimal import Decimal

    facts = example_facts(omit={"proposed_exposure", "projected_turnover"})
    write_facts(tmp_path, facts)
    reply = json.loads(binding_json(facts))
    reply["bindings"] = [
        b for b in reply["bindings"] if b["slot"] not in ("proposed_exposure", "projected_turnover")
    ] + [
        {
            "score_id": "maximum_exposure",
            "slot": "proposed_exposure",
            "fact_id": "F018",
            "value": 400,
            "unit": "INR crore",
        },
        {
            "score_id": "maximum_exposure",
            "slot": "projected_turnover",
            "fact_id": "F019",
            "value": 6000,
            "unit": "INR crore",
        },
    ]
    provider = MockProvider(
        {"policy.bind_inputs": [json.dumps(reply)], "policy.judge_slot": judge_replies(facts)}
    )
    config = run_config.model_copy(
        update={"proposed_exposure": Decimal("400"), "projected_turnover": Decimal("6000")}
    )
    results = await run_scores(tmp_path, config, provider, BANKS_DIR)
    assert {r.score_id: r.value_display for r in results}["maximum_exposure"] == "500 crore"
    assert results[2].grade == "Within limit"
    saved = json.loads((tmp_path / "verified_facts.json").read_text())
    assert [f["fact_id"] for f in saved[-2:]] == ["F018", "F019"]
    assert saved[-1]["citations"][0]["source"] == "bank_input"
    source = results[1].lean.source
    assert "| note: major_red_flag_count judged from" in source


async def test_unbound_slot_makes_dependent_scores_not_computable(tmp_path, run_config) -> None:
    facts = example_facts(omit={"default_flag"})
    write_facts(tmp_path, facts)
    provider = MockProvider(
        {"policy.bind_inputs": [binding_json(facts)], "policy.judge_slot": judge_replies(facts)}
    )
    results = await run_scores(tmp_path, run_config, provider, BANKS_DIR)
    status = {r.score_id: r.status for r in results}
    assert status == {
        "financial_strength_score": ScoreStatus.computed,
        "internal_risk_grade": ScoreStatus.not_computable,
        "maximum_exposure": ScoreStatus.not_computable,
    }
    assert results[1].value_display is None and results[1].lean is None


async def test_lean_failure_keeps_the_artifact(tmp_path, run_config, example_provider) -> None:
    bank_id = f"tmp_{uuid.uuid4().hex[:6]}"
    banks = tmp_path / "banks"
    shutil.copytree(BANKS_DIR / "demo_bank", banks / bank_id)
    module_name = camel_bank_id(bank_id)
    policy = banks / bank_id / "policy.lean"
    policy.write_text(
        policy.read_text()
        .replace("BusyBee.Policy.DemoBank", f"BusyBee.Policy.{module_name}")
        .replace("maximum_exposure_test_grade", "renamed_grade")
    )
    module = project_dir() / "BusyBee" / "Policy" / f"{module_name}.lean"
    config = run_config.model_copy(update={"bank_id": bank_id})
    write_facts(tmp_path, example_facts())
    try:
        results = await run_scores(tmp_path, config, example_provider, banks)
    finally:
        module.unlink(missing_ok=True)
        for leftover in (project_dir() / ".lake" / "build").rglob(f"{module_name}.*"):
            leftover.unlink(missing_ok=True)
    assert {r.status for r in results} == {ScoreStatus.lean_failed}
    artifact = results[0].lean
    assert artifact is not None and artifact.compile is not None
    assert not artifact.compile.ok
    assert "maximum_exposure_test_grade" in artifact.compile.errors[0].message


async def test_maximum_exposure_value_is_the_cap_and_grade_compares_proposed(
    tmp_path, run_config, example_provider
) -> None:
    """Hand example: grade 3, turnover 1,024.3, net worth 292.4 -> cap 153.64; 432 exceeds."""
    source = (BANKS_DIR / "demo_bank" / "policy.lean").read_text()
    script = tmp_path / "Example.lean"
    script.write_text(
        source
        + "\nopen BusyBee.Policy.DemoBank in\n"
        + '#eval IO.println s!"{maximum_exposure_test 43200 102430 102430 29240 3} '
        + "{maximum_exposure_test_grade 43200 102430 102430 29240 3} "
        + '{maximum_exposure_test_grade 15000 102430 102430 29240 3}"\n'
    )
    result = await compile_file(script)
    assert result.ok, result.stderr
    assert result.stdout.split() == ["15364", "Exceeds", "limit", "Within", "limit"]


async def test_projection_above_125_percent_of_audited_turnover_is_capped(tmp_path) -> None:
    source = (BANKS_DIR / "demo_bank" / "policy.lean").read_text()
    script = tmp_path / "Capped.lean"
    script.write_text(
        source
        + "\nopen BusyBee.Policy.DemoBank in\n"
        + '#eval IO.println s!"{maximum_exposure_test 1 1000000 100000 10000000 1} '
        + "{maximum_exposure_test 1 125000 100000 10000000 1} "
        + '{maximum_exposure_test_grade 30000 1000000 100000 10000000 1}"\n'
    )
    result = await compile_file(script)
    assert result.ok, result.stderr
    assert result.stdout.split() == ["25000", "25000", "Exceeds", "limit"]
