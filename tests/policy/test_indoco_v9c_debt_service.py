"""Indoco v9c regression: debt service 48.67 crore, the negative repayment subtracted.

F250 states finance cost as "an outflow of INR 12,270.29 lakh" and F111 the repayment of
long-term borrowings as "-INR 7,403.04 lakh" (bracketed in the cash flow). Both are outflows, so
debt service is 122.70 + 74.03 = 196.73 crore, never 48.67, whether the model names the
components exactly or loosely, and whether it copies a figure negative or positive.
"""

import json

from policy_helpers import BANKS_DIR

from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import BindingOutput, validate_bindings
from busybee.schema.facts import FactScope, VerifiedFact

F250 = {
    "fact_id": "F250",
    "statement": (
        "Consolidated finance Cost (Other than Unrealised Foreign Exchange (Gain) / Loss) was an "
        "outflow of INR 12,270.29 lakh for the year ended March 31, 2026."
    ),
    "category": "cash_flow",
    "citations": [
        {
            "chunk_id": "D1:p274:c0",
            "doc_id": "D1",
            "page_no": 274,
            "quote": (
                "Finance Cost (Other than Unrealised Foreign | Year ended 31.03.2026: (12,270.29)"
            ),
        }
    ],
    "numbers": [{"label": "outflow", "value": "12270.29", "unit": "INR lakh", "period": "2026"}],
    "verification": {"status": "supported", "method": "llm_entailment", "notes": ""},
    "importance": 4,
    "source_entry_id": "SLOT:E001",
    "added_by": "slot_search",
    "scope": "consolidated",
}
F111 = {
    "fact_id": "F111",
    "statement": (
        "Consolidated repayment of Long Term Borrowings was -INR 7,403.04 lakh as at Year ended "
        "31.03.2026 (Year ended 31.03.2025: -INR 4,173.24 lakh)."
    ),
    "category": "debt_leverage",
    "citations": [
        {
            "chunk_id": "D1:p274:c0",
            "doc_id": "D1",
            "page_no": 274,
            "quote": "Repayment of Long Term Borrowings | Year ended 31.03.2026: (7,403.04)",
        }
    ],
    "numbers": [
        {
            "label": "Repayment of Long Term Borrowings",
            "value": "-7403.04",
            "unit": "INR lakh",
            "period": "Year ended 31.03.2026",
        },
        {
            "label": "Repayment of Long Term Borrowings",
            "value": "-4173.24",
            "unit": "INR lakh",
            "period": "Year ended 31.03.2025",
        },
    ],
    "verification": {"status": "supported", "method": "record_match", "notes": ""},
    "importance": 5,
    "source_entry_id": "D1:E326",
    "added_by": "extract",
    "scope": "consolidated",
}


def _reply(interest: str, repayment: str) -> str:
    terms = [
        {
            "fact_id": "F250",
            "value": 12270.29,
            "unit": "INR lakh",
            "sign": 1,
            "component": interest,
        },
        {
            "fact_id": "F111",
            "value": -7403.04,
            "unit": "INR lakh",
            "sign": 1,
            "component": repayment,
        },
    ]
    binding = {
        "score_id": "financial_strength_score",
        "slot": "debt_service",
        "fact_id": None,
        "value": None,
        "unit": "",
        "period": "",
        "terms": terms,
        "missing": [],
        "note": "finance cost outflow and repayment of long-term borrowings",
    }
    return json.dumps({"bindings": [binding]})


def _debt_service(reply: str) -> int:
    specs = load_bank(BANKS_DIR, "demo_bank").scores
    facts = {item["fact_id"]: VerifiedFact.model_validate(item) for item in (F250, F111)}
    output = BindingOutput.model_validate_json(reply)
    result = validate_bindings(output, specs, facts, FactScope.consolidated)
    assert result.rejected == []
    bound = {item.slot: item for item in result.bound["financial_strength_score"]}
    return bound["debt_service"].value_scaled


def test_logged_v9c_terms_add_the_negative_repayment() -> None:
    reply = _reply("interest paid", "scheduled principal repayments")
    assert _debt_service(reply) == 19673


def test_loosely_named_outflow_terms_still_enter_by_absolute_figure() -> None:
    assert _debt_service(_reply("interest", "principal repayments")) == 19673
