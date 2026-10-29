"""Binding validation: real fact, real number, exact scale; LLM claims are never trusted."""

import json
from decimal import Decimal

from policy_helpers import BANKS_DIR, binding_json, example_facts

from busybee.llm import MockProvider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import (
    BindingOutput,
    bind_inputs,
    candidate_facts,
    derive_deterministically,
    validate_bindings,
)
from busybee.schema.facts import NumericValue, VerifiedFact
from busybee.schema.policy import InputSlot, ScoreSpec


def _specs():
    return load_bank(BANKS_DIR, "demo_bank").scores


async def test_perfect_bindings_scale_and_skip_score_slots() -> None:
    facts = example_facts()
    provider = MockProvider({"policy.bind_inputs": [binding_json(facts)]})
    result = await bind_inputs(provider, _specs(), facts)
    assert result.rejected == []
    fss = {item.slot: item for item in result.bound["financial_strength_score"]}
    assert fss["net_debt"].value_scaled == 125000
    assert fss["net_debt"].fact_id == "F001"
    irg_slots = {item.slot for item in result.bound["internal_risk_grade"]}
    assert "financial_strength_score" not in irg_slots
    assert {item.slot for item in result.bound["maximum_exposure"]} == {
        "proposed_exposure",
        "projected_turnover",
        "revenue_current",
        "tangible_net_worth",
    }
    prompt = provider.calls[0]["messages"][-1].content
    assert "score_id=internal_risk_grade slot=financial_strength_score" not in prompt


def test_invalid_bindings_are_rejected_with_reasons() -> None:
    facts = {fact.fact_id: fact for fact in example_facts()}
    output = BindingOutput.model_validate(
        {
            "bindings": [
                {
                    "score_id": "financial_strength_score",
                    "slot": "ebitda",
                    "fact_id": "F999",
                    "value": "420.00",
                    "unit": "INR crore",
                },
                {
                    "score_id": "financial_strength_score",
                    "slot": "cfads",
                    "fact_id": "F004",
                    "value": "999",
                    "unit": "INR crore",
                },
                {
                    "score_id": "financial_strength_score",
                    "slot": "net_debt",
                    "fact_id": None,
                    "value": None,
                },
                {
                    "score_id": "financial_strength_score",
                    "slot": "nonsense",
                    "fact_id": "F001",
                    "value": "1250.00",
                },
                {
                    "score_id": "internal_risk_grade",
                    "slot": "financial_strength_score",
                    "fact_id": "F001",
                    "value": "1250.00",
                },
                {
                    "score_id": "financial_strength_score",
                    "slot": "total_debt",
                    "fact_id": "F006",
                    "value": "1500.00",
                    "unit": "INR crore",
                },
            ]
        }
    )
    result = validate_bindings(output, _specs(), facts)
    reasons = " | ".join(result.rejected)
    assert "unknown fact F999" in reasons
    assert "not a number of F004" in reasons
    assert "no fact chosen" in reasons
    assert "unknown or non-fact slot" in reasons
    assert len(result.rejected) == 5
    assert [item.slot for item in result.bound["financial_strength_score"]] == ["total_debt"]


async def test_unit_comes_from_the_fact_not_the_llm() -> None:
    facts = example_facts()
    reply = json.loads(binding_json(facts))
    for binding in reply["bindings"]:
        binding["unit"] = "lakh"
    provider = MockProvider({"policy.bind_inputs": [json.dumps(reply)]})
    result = await bind_inputs(provider, _specs(), facts)
    fss = {item.slot: item for item in result.bound["financial_strength_score"]}
    assert fss["ebitda"].value_scaled == 42000


def _fact(fact_id: str, statement: str, value: str, unit: str = "INR crore") -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        numbers=[NumericValue(label="n", value=Decimal(value), unit=unit)],
    )


def _spec(*slots: str) -> list[ScoreSpec]:
    descriptions = {
        "net_debt": "Total borrowings less cash, bank balances and liquid investments",
        "ebitda": "Operating profit before depreciation, interest and tax",
    }
    return [
        ScoreSpec(
            score_id="s",
            name="S",
            inputs=[
                InputSlot(slot=s, description=descriptions[s], unit="INR crore x 100", scale=100)
                for s in slots
            ],
        )
    ]


def test_loose_value_strings_are_parsed() -> None:
    reply = BindingOutput.model_validate_json(
        '{"bindings": [{"score_id": "s", "slot": "ebitda", "fact_id": "F1",'
        ' "value": "Rs 1,130.40 crore"}]}'
    )
    assert reply.bindings[0].value == Decimal("1130.40")
    facts = {"F1": _fact("F1", "EBITDA was INR 1,130.4 crore", "1130.4")}
    result = validate_bindings(reply, _spec("ebitda"), facts)
    assert result.rejected == []
    assert result.bound["s"][0].value_scaled == 113040


def test_derived_slot_sums_signed_terms_exactly() -> None:
    facts = {
        "F1": _fact("F1", "Total borrowings were INR 382.0 crore", "382.0"),
        "F2": _fact("F2", "Cash and bank balances were INR 21.4 crore", "21.4"),
        "F3": _fact("F3", "Liquid investments were INR 8.6 crore", "8.6", "Rs crore"),
    }
    terms = [
        {"fact_id": "F1", "value": 382.0, "unit": "INR crore", "sign": 1},
        {"fact_id": "F2", "value": "21.4", "sign": -1},
        {"fact_id": "F3", "value": 8.6, "sign": -1},
    ]
    output = BindingOutput.model_validate(
        {"bindings": [{"score_id": "s", "slot": "net_debt", "terms": terms}]}
    )
    result = validate_bindings(output, _spec("net_debt"), facts)
    assert result.rejected == []
    bound = result.bound["s"][0]
    assert bound.value_scaled == 35200
    assert bound.value == Decimal("352")
    assert bound.derived_from == ["F1", "F2", "F3"]


def test_derived_slot_rejects_a_term_that_is_not_a_fact_number() -> None:
    facts = {"F1": _fact("F1", "Total borrowings were INR 382.0 crore", "382.0")}
    output = BindingOutput.model_validate(
        {
            "bindings": [
                {
                    "score_id": "s",
                    "slot": "net_debt",
                    "terms": [{"fact_id": "F1", "value": 100, "sign": 1}],
                }
            ]
        }
    )
    result = validate_bindings(output, _spec("net_debt"), facts)
    assert result.bound["s"] == []
    assert "term value 100 is not a number of F1" in result.rejected[0]


async def test_unbound_slot_gets_one_retry_with_candidate_facts() -> None:
    facts = [
        _fact(
            "F1",
            "Operating profit before depreciation, interest and tax was INR 130.4 crore",
            "130.4",
        ),
        _fact("F2", "Cars sold were 10", "10", ""),
    ]
    miss = {"bindings": [{"score_id": "s", "slot": "ebitda", "fact_id": "F2", "value": 10}]}
    hit = {"bindings": [{"score_id": "s", "slot": "ebitda", "fact_id": "F1", "value": 130.4}]}
    provider = MockProvider({"policy.bind_inputs": [json.dumps(miss), json.dumps(hit)]})
    result = await bind_inputs(provider, _spec("ebitda"), facts)
    assert len(provider.calls) == 2
    retry_prompt = provider.calls[1]["messages"][-1].content
    assert "candidates: F1" in retry_prompt
    assert "F2:" not in retry_prompt.split("Candidate facts:")[1]
    assert [item.fact_id for item in result.bound["s"]] == ["F1"]
    assert result.rejected == []


async def test_slot_without_candidates_is_not_retried() -> None:
    facts = [_fact("F2", "Cars sold were 10", "10", "")]
    provider = MockProvider({"policy.bind_inputs": [json.dumps({"bindings": []})]})
    result = await bind_inputs(provider, _spec("ebitda"), facts)
    assert provider.calls == []
    assert result.bound["s"] == []
    assert result.unbound[("s", "ebitda")] == "no verified fact shares key words with this slot"


async def test_value_in_statement_but_missing_from_numbers_is_accepted() -> None:
    fact = VerifiedFact(
        fact_id="F1",
        statement="Operating profit before depreciation, interest and tax was INR 15,716.21 lakhs.",
        numbers=[],
    )
    reply = {"bindings": [{"score_id": "s", "slot": "ebitda", "fact_id": "F1", "value": 15716.21}]}
    provider = MockProvider({"policy.bind_inputs": [json.dumps(reply)]})
    result = await bind_inputs(provider, _spec("ebitda"), [fact])
    assert [(i.fact_id, i.value_scaled) for i in result.bound["s"]] == [("F1", 15716)]


async def test_each_slot_sees_at_most_fifteen_candidates() -> None:
    facts = [
        _fact(f"F{n}", f"Operating profit before depreciation was INR {n}.5 crore in year {n}", "1")
        for n in range(1, 41)
    ]
    provider = MockProvider({"policy.bind_inputs": [json.dumps({"bindings": []})] * 3})
    result = await bind_inputs(provider, _spec("ebitda"), facts)
    first_prompt = provider.calls[0]["messages"][-1].content
    line = next(x for x in first_prompt.splitlines() if x.startswith("- s.ebitda:"))
    assert len(line.split(": ", 1)[1].split(", ")) == 15
    assert len(provider.calls) == 3
    assert "the model found no fitting fact among 30 candidates (including a retry)" in str(
        result.unbound[("s", "ebitda")]
    )


async def test_rejected_proposal_reason_is_recorded_per_slot() -> None:
    facts = [_fact("F1", "Operating income before depreciation was INR 130.4 crore", "130.4")]
    bad = {"bindings": [{"score_id": "s", "slot": "ebitda", "fact_id": "F1", "value": 999}]}
    provider = MockProvider({"policy.bind_inputs": [json.dumps(bad)] * 2})
    result = await bind_inputs(provider, _spec("ebitda"), facts)
    assert "not a number of F1" in result.unbound[("s", "ebitda")]


def _cfads_spec() -> list[ScoreSpec]:
    slot = InputSlot(
        slot="cfads",
        description="Cash flow available for debt service",
        unit="INR crore x 100",
        scale=100,
        definition="EBITDA minus cash taxes paid for the latest audited year",
        derive_from=["ebitda", "cash taxes paid"],
    )
    return [ScoreSpec(score_id="s", name="S", inputs=[slot])]


async def test_definition_and_hints_reach_the_prompt_and_terms_derive_the_slot() -> None:
    facts = [
        _fact("F1", "Cash flow available for debt service is not reported", "0"),
        _fact("F2", "EBITDA was INR 420.00 crore in FY26", "420.00"),
        _fact("F3", "Income taxes paid were INR 36.50 crore in FY26", "36.50"),
        _fact("F4", "Cash taxes paid were INR 36.50 crore in FY26", "36.50"),
    ]
    terms = [
        {"fact_id": "F2", "component": "ebitda", "value": 420.0, "unit": "INR crore", "sign": 1},
        {
            "fact_id": "F4",
            "component": "cash taxes paid",
            "value": 36.5,
            "unit": "INR crore",
            "sign": -1,
        },
    ]
    reply = {"bindings": [{"score_id": "s", "slot": "cfads", "terms": terms}]}
    provider = MockProvider({"policy.bind_inputs": [json.dumps(reply)]})
    result = await bind_inputs(provider, _cfads_spec(), facts)
    messages = provider.calls[0]["messages"]
    prompt = messages[-1].content
    assert "definition: EBITDA minus cash taxes paid" in prompt
    assert "derive_from: ebitda; cash taxes paid" in prompt
    line = next(x for x in prompt.splitlines() if x.startswith("- s.cfads:"))
    assert "F2" in line and "F4" in line
    assert '"terms"' in messages[0].content and "Worked example" in messages[0].content
    item = result.bound["s"][0]
    assert (item.value_scaled, item.derived_from) == (38350, ["F2", "F4"])


def _turnover_specs() -> list[ScoreSpec]:
    return [
        ScoreSpec(
            score_id="a",
            name="A",
            inputs=[
                InputSlot(
                    slot="revenue_current",
                    description="Revenue from operations, latest audited year",
                    unit="INR crore x 100",
                    scale=100,
                )
            ],
        ),
        ScoreSpec(
            score_id="b",
            name="B",
            inputs=[
                InputSlot(
                    slot="projected_turnover",
                    description="Projected annual turnover for the next financial year",
                    unit="INR crore x 100",
                    scale=100,
                    run_parameter="projected_turnover",
                    fallback_slot="revenue_current",
                    fallback_note="projection not provided; latest revenue used",
                )
            ],
        ),
    ]


async def test_projected_turnover_falls_back_to_latest_revenue_with_a_note() -> None:
    facts = [_fact("F1", "Revenue from operations was INR 931.20 crore in FY25", "931.20")]
    reply = {
        "bindings": [{"score_id": "a", "slot": "revenue_current", "fact_id": "F1", "value": 931.2}]
    }
    provider = MockProvider({"policy.bind_inputs": [json.dumps(reply)] * 2})
    result = await bind_inputs(provider, _turnover_specs(), facts)
    item = result.bound["b"][0]
    assert (item.slot, item.fact_id, item.value_scaled) == ("projected_turnover", "F1", 93120)
    assert item.note == "projection not provided; latest revenue used"
    assert ("b", "projected_turnover") not in result.unbound


async def test_a_bank_input_fact_is_an_ordinary_candidate_and_wins_over_the_fallback() -> None:
    facts = [
        _fact("F1", "Revenue from operations was INR 931.20 crore in FY25", "931.20"),
        _fact(
            "F2",
            "Bank input: projected turnover INR 1100 crore (from the credit request)",
            "1100",
        ),
    ]
    reply = {
        "bindings": [
            {"score_id": "a", "slot": "revenue_current", "fact_id": "F1", "value": 931.2},
            {"score_id": "b", "slot": "projected_turnover", "fact_id": "F2", "value": 1100},
        ]
    }
    provider = MockProvider({"policy.bind_inputs": [json.dumps(reply)]})
    result = await bind_inputs(provider, _turnover_specs(), facts)
    item = result.bound["b"][0]
    assert (item.fact_id, item.value_scaled, item.note) == ("F2", 110000, "")
    assert "Bank input: projected turnover" in provider.calls[0]["messages"][-1].content


async def test_unbound_bank_input_slot_says_how_to_supply_it() -> None:
    spec = [_turnover_specs()[1].model_copy()]
    spec[0].inputs[0] = spec[0].inputs[0].model_copy(update={"fallback_slot": ""})
    provider = MockProvider({"policy.bind_inputs": []})
    result = await bind_inputs(provider, spec, [])
    reason = result.unbound[("b", "projected_turnover")]
    assert "--projected-turnover" in reason and "BUSYBEE_PROJECTED_TURNOVER" in reason


def _debt_service_spec() -> list[ScoreSpec]:
    slot = InputSlot(
        slot="debt_service",
        description="Interest paid plus scheduled principal repayments in the year",
        unit="INR crore x 100",
        scale=100,
        definition="Interest paid plus scheduled principal repayments of borrowings",
        derive_from=["interest paid", "scheduled principal repayments"],
    )
    return [ScoreSpec(score_id="s", name="S", inputs=[slot])]


def _lakh(fact_id: str, statement: str, *values: str) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        numbers=[NumericValue(label="n", value=Decimal(v), unit="INR lakh") for v in values],
    )


DEBT_FACTS = [
    _lakh(
        "F1",
        "Interest Expense increased to INR 6,032.58 lakhs for the year ended March 31, 2026, "
        "from INR 5,344.74 lakhs for the year ended March 31, 2025.",
        "6032.58",
        "5344.74",
    ),
    _lakh(
        "F2",
        "Repayment of long-term borrowings was INR 7,403.04 lakhs for the year "
        "ended March 31, 2026, compared to INR 4,173.24 lakhs for the year ended March 31, 2025.",
        "7403.04",
        "4173.24",
    ),
    _lakh(
        "F3",
        "Term loan outstanding INR 2,237.50 lakhs, interest rate 8.20%, repayment 2029",
        "2237.50",
    ),
]


async def test_unbound_derived_slot_is_derived_deterministically_after_the_retry() -> None:
    empty = json.dumps({"bindings": []})
    provider = MockProvider({"policy.bind_inputs": [empty, empty]})
    result = await bind_inputs(provider, _debt_service_spec(), DEBT_FACTS)
    item = result.bound["s"][0]
    assert (item.slot, item.value_scaled) == ("debt_service", 13436)
    assert item.derived_from == ["F1", "F2"]
    assert item.note.startswith("derived deterministically from interest paid (F1)")
    assert result.unbound == {}


async def test_deterministic_derivation_needs_every_component() -> None:
    empty = json.dumps({"bindings": []})
    provider = MockProvider({"policy.bind_inputs": [empty, empty]})
    result = await bind_inputs(provider, _debt_service_spec(), [DEBT_FACTS[0], DEBT_FACTS[2]])
    assert result.bound["s"] == []
    assert ("s", "debt_service") in result.unbound


async def test_deterministic_derivation_signs_follow_the_definition_and_skip_ambiguity() -> None:
    slot = _cfads_spec()[0].inputs[0]
    facts = [
        _fact("F2", "EBITDA was INR 420.00 crore in FY26", "420.00"),
        _fact("F4", "Cash taxes paid were INR 36.50 crore in FY26", "36.50"),
    ]
    derived = derive_deterministically(slot, facts)
    assert derived is not None and derived.value_scaled == 38350
    rival = _fact("F5", "Cash taxes paid were INR 40.00 crore in FY26", "40.00")
    assert derive_deterministically(slot, [*facts, rival]) is None


async def test_retry_prompt_lists_component_candidates_and_insists_on_terms() -> None:
    empty = json.dumps({"bindings": []})
    provider = MockProvider({"policy.bind_inputs": [empty, empty, empty]})
    await bind_inputs(provider, _debt_service_spec(), DEBT_FACTS)
    retry = provider.calls[2]["messages"][-1].content
    assert "component 'interest paid': F1" in retry
    assert "component 'scheduled principal repayments': F2" in retry
    assert "answer with `terms`" in retry


def _record_fact(fact_id: str, metric: str, value: str, period: str = "FY2025-26") -> VerifiedFact:
    from busybee.extract.templates import record_numbers, statement_from_record
    from busybee.schema.facts import FactRecord

    record = FactRecord(metric=metric, value=Decimal(value), unit="crore", period=period)
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement_from_record(record),
        numbers=record_numbers(record),
        record=record,
    )


def test_record_facts_are_scored_on_their_metric_and_derive_from_record_values() -> None:
    slot = _cfads_spec()[0].inputs[0]
    facts = [
        _record_fact("F2", "EBITDA", "420.00"),
        _record_fact("F4", "Cash taxes paid", "36.50"),
        _record_fact("F5", "Cash taxes paid", "40.00", period="FY2023-24"),
        _record_fact("F6", "Other income", "5.00"),
    ]
    derived = derive_deterministically(slot, facts)
    assert derived is not None and derived.value_scaled == 38350
    assert derived.derived_from == ["F2", "F4"]
    ranked = candidate_facts(
        InputSlot(slot="ebitda", description="Earnings before interest, tax, depreciation"), facts
    )
    assert ranked[0].fact_id == "F2"
