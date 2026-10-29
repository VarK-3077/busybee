"""Helpers: a hand-computed borrower, its verified facts, and the matching binder reply."""

import json
from decimal import Decimal
from pathlib import Path

from busybee.schema.facts import Citation, NumericValue, VerifiedFact

REPO = Path(__file__).resolve().parents[2]
BANKS_DIR = REPO / "banks"

CRORE = "INR crore"
EXAMPLE: dict[str, tuple[str, str, str]] = {
    "net_debt": ("1250.00", CRORE, "Net debt"),
    "ebitda": ("420.00", CRORE, "EBITDA"),
    "interest_expense": ("150.00", CRORE, "Finance cost"),
    "cfads": ("300.00", CRORE, "CFADS"),
    "debt_service": ("200.00", CRORE, "Debt service"),
    "total_debt": ("1500.00", CRORE, "Total borrowings"),
    "total_equity": ("1000.00", CRORE, "Net worth"),
    "current_assets": ("1800.00", CRORE, "Current assets"),
    "current_liabilities": ("1300.00", CRORE, "Current liabilities"),
    "revenue_current": ("5000.00", CRORE, "Revenue FY26"),
    "revenue_previous": ("4600.00", CRORE, "Revenue FY25"),
    "external_rating_index": ("9", "index", "Rating index"),
    "major_red_flag_count": ("1", "count", "Red flags"),
    "default_flag": ("0", "flag", "Default flag"),
    "proposed_exposure": ("400.00", CRORE, "Proposed exposure"),
    "projected_turnover": ("6000.00", CRORE, "Projected turnover"),
    "tangible_net_worth": ("1000.00", CRORE, "Tangible net worth"),
}


SPECIAL_STATEMENTS = {
    "external_rating_index": "The borrower's long-term credit rating is BBB (Stable) per ICRA",
    "major_red_flag_count": (
        "An unprovided litigation claim above 10 percent of net worth is pending"
    ),
    "default_flag": (
        "The company reports no NPA, wilful default or one-time settlement in 36 months"
    ),
}


def example_facts(omit: set[str] | None = None) -> list[VerifiedFact]:
    """One verified fact per example slot, F001 onward, each citing its own chunk."""
    facts = []
    for number, (slot, (value, unit, label)) in enumerate(EXAMPLE.items(), start=1):
        if omit and slot in omit:
            continue
        facts.append(
            VerifiedFact(
                fact_id=f"F{number:03d}",
                statement=SPECIAL_STATEMENTS.get(slot, f"{label} was {value} {unit}"),
                citations=[
                    Citation(chunk_id=f"D1:p{number}:c1", doc_id="D1", page_no=number, quote=label)
                ],
                numbers=[NumericValue(label=label, value=Decimal(value), unit=unit, period="FY26")],
            )
        )
    return facts


def slot_owners() -> dict[str, list[str]]:
    """The score ids that take each fact-backed slot."""
    return {
        **dict.fromkeys(list(EXAMPLE)[:9], ["financial_strength_score"]),
        "revenue_current": ["financial_strength_score", "maximum_exposure"],
        "revenue_previous": ["financial_strength_score"],
        **dict.fromkeys(list(EXAMPLE)[11:14], ["internal_risk_grade"]),
        **dict.fromkeys(list(EXAMPLE)[14:], ["maximum_exposure"]),
    }


def binding_json(facts: list[VerifiedFact]) -> str:
    """The JSON a perfect binder would return for the example facts."""
    by_label = {fact.numbers[0].label: fact for fact in facts}
    bindings = []
    for slot, owners in slot_owners().items():
        if slot in SPECIAL_STATEMENTS:
            continue
        fact = by_label.get(EXAMPLE[slot][2])
        for score_id in owners:
            bindings.append(
                {
                    "score_id": score_id,
                    "slot": slot,
                    "fact_id": fact.fact_id if fact else None,
                    "value": str(fact.numbers[0].value) if fact else None,
                    "unit": fact.numbers[0].unit if fact else "",
                }
            )
    return json.dumps({"bindings": bindings})


def judge_replies(facts: list[VerifiedFact]) -> list[str]:
    """What a perfect judge returns, in score-spec order: red-flag count 1, then default flag 0."""
    by_text = {fact.statement: fact.fact_id for fact in facts}
    replies = []
    for slot, value in (("major_red_flag_count", 1), ("default_flag", 0)):
        fact_id = by_text.get(SPECIAL_STATEMENTS[slot])
        if fact_id:
            replies.append(
                json.dumps(
                    {
                        "value": value,
                        "fact_ids": [fact_id],
                        "justification": f"{slot} judged from {fact_id}",
                    }
                )
            )
    return replies


def write_facts(workspace: Path, facts: list[VerifiedFact]) -> None:
    payload = [fact.model_dump(mode="json") for fact in facts]
    (workspace / "verified_facts.json").write_text(json.dumps(payload), encoding="utf-8")
