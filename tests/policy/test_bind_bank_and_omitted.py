"""Bank inputs bind in code without a model call; slots a reply omits are asked again."""

import json
from decimal import Decimal

from policy_helpers import BANKS_DIR, binding_json, example_facts

from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bank_inputs import bank_input_facts
from busybee.policy.bind_inputs import bind_inputs
from busybee.schema.run import RunConfig


def _specs():
    return load_bank(BANKS_DIR, "demo_bank").scores


def _with_bank_inputs(tmp_path):
    cfg = RunConfig(
        run_id="r",
        docs_dir=tmp_path,
        bank_id="demo_bank",
        out_dir=tmp_path / "out",
        workspace_dir=tmp_path,
        proposed_exposure=Decimal("400"),
        projected_turnover=Decimal("6000"),
    )
    return bank_input_facts(cfg, example_facts())


def _prompts(provider: MockProvider) -> str:
    return "\n".join(call["messages"][-1].content for call in provider.calls)


async def test_bank_input_slots_bind_without_asking_the_model(tmp_path) -> None:
    facts = _with_bank_inputs(tmp_path)
    reply = json.loads(binding_json(facts))
    reply["bindings"] = [
        b for b in reply["bindings"] if b["slot"] not in {"proposed_exposure", "projected_turnover"}
    ]
    provider = MockProvider({"policy.bind_inputs": [json.dumps(reply)]})
    result = await bind_inputs(provider, _specs(), facts)
    bound = {item.slot: item for item in result.bound["maximum_exposure"]}
    bank_ids = {f.fact_id for f in facts if f.added_by == "bank_input"}
    assert bound["proposed_exposure"].fact_id in bank_ids
    assert bound["proposed_exposure"].value_scaled == 40000
    assert "bank_input" in bound["proposed_exposure"].note
    assert "slot=proposed_exposure" not in _prompts(provider)
    assert "slot=projected_turnover" not in _prompts(provider)


async def test_omitted_slots_are_asked_again_one_batch_at_a_time() -> None:
    facts = example_facts()
    full = json.loads(binding_json(facts))
    omitted = {"total_equity", "revenue_previous", "ebitda"}
    first = {"bindings": [b for b in full["bindings"] if b["slot"] not in omitted]}
    follow_up = {"bindings": [b for b in full["bindings"] if b["slot"] in omitted]}
    provider = MockProvider({"policy.bind_inputs": [json.dumps(first), json.dumps(follow_up)]})
    result = await bind_inputs(provider, _specs(), facts)
    bound = {item.slot for item in result.bound["financial_strength_score"]}
    assert omitted <= bound
    bind_calls = [c for c in provider.calls if c["task"] == "policy.bind_inputs"]
    assert len(bind_calls) == 2
    second = bind_calls[1]["messages"][-1].content
    assert "slot=total_equity" in second and "slot=net_debt" not in second
