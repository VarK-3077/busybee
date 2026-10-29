"""Check inference generation, id scrubbing, dropping, and response parsing."""

import json
from decimal import Decimal

from busybee.infer.make_inferences import make_inference_drafts, make_inferences
from busybee.infer.prompts import TASK, InferenceDraft, InferenceOutput, LeanClaim
from busybee.llm import MockProvider
from busybee.schema.facts import (
    Citation,
    FactCategory,
    NumericValue,
    VerifiedFact,
)


def _fact(fact_id: str, statement: str = "Revenue was 100 crore.") -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        category=FactCategory.revenue,
        citations=[Citation(chunk_id="D1:p1:c1", doc_id="D1", page_no=1)],
        numbers=[NumericValue(label="Revenue", value=Decimal("100"), unit="crore")],
    )


def _reply(inferences: list[dict]) -> str:
    return json.dumps({"inferences": inferences})


async def test_unknown_fact_ids_are_dropped() -> None:
    provider = MockProvider(
        {
            TASK: [
                _reply(
                    [
                        {
                            "opinion": "Leverage is comfortable.",
                            "fact_ids": ["F001", "F999", "F001"],
                            "reasoning": "F001 shows low debt. F999 would be outside evidence.",
                            "confidence": 0.8,
                        }
                    ]
                )
            ]
        }
    )
    inferences = await make_inferences([_fact("F001")], [], provider)
    assert len(inferences) == 1
    assert inferences[0].fact_ids == ["F001"]
    assert inferences[0].inference_id == "I001"


async def test_inference_with_only_unknown_ids_is_dropped() -> None:
    provider = MockProvider(
        {
            TASK: [
                _reply(
                    [
                        {
                            "opinion": "Unsupported claim.",
                            "fact_ids": ["F999"],
                            "reasoning": "No real fact.",
                            "confidence": 0.9,
                        },
                        {
                            "opinion": "Supported claim.",
                            "fact_ids": ["F001"],
                            "reasoning": "F001 supports this.",
                            "confidence": 0.7,
                        },
                    ]
                )
            ]
        }
    )
    inferences = await make_inferences([_fact("F001")], [], provider)
    assert [inference.opinion for inference in inferences] == ["Supported claim."]
    assert inferences[0].inference_id == "I001"


async def test_list_is_capped_at_eight_valid_inferences() -> None:
    facts = [_fact(f"F{index:03d}") for index in range(1, 4)]
    items = [
        {
            "opinion": f"Opinion {index}.",
            "fact_ids": ["F001"],
            "reasoning": "F001 supports this.",
            "confidence": 0.5,
        }
        for index in range(10)
    ]
    provider = MockProvider({TASK: [_reply(items)]})
    inferences = await make_inferences(facts, [], provider)
    assert len(inferences) == 8
    assert [inference.inference_id for inference in inferences] == [
        f"I{index:03d}" for index in range(1, 9)
    ]


async def test_confidence_words_and_percentages_are_normalised() -> None:
    provider = MockProvider(
        {
            TASK: [
                _reply(
                    [
                        {
                            "opinion": "High case.",
                            "fact_ids": ["F001"],
                            "reasoning": "F001.",
                            "confidence": "high",
                        },
                        {
                            "opinion": "Percent case.",
                            "fact_ids": ["F001"],
                            "reasoning": "F001.",
                            "confidence": 75,
                        },
                    ]
                )
            ]
        }
    )
    inferences = await make_inferences([_fact("F001")], [], provider)
    assert inferences[0].confidence == 0.85
    assert inferences[1].confidence == 0.75


def test_lean_claim_mappings_to_unlisted_or_unknown_facts_are_removed() -> None:
    output = InferenceOutput(
        inferences=[
            InferenceDraft(
                opinion="Quantitative.",
                fact_ids=["F001", "F999"],
                reasoning="F001.",
                quantitative=True,
                lean_claim=LeanClaim(facts={"a": "F999"}, claim="a > 0"),
            )
        ]
    )
    from busybee.infer.make_inferences import validate_inference_drafts

    drafts = validate_inference_drafts(output, [_fact("F001")])
    assert drafts[0].fact_ids == ["F001"]
    assert drafts[0].quantitative is False
    assert drafts[0].lean_claim is None


async def test_valid_lean_claim_survives_draft_validation() -> None:
    provider = MockProvider(
        {
            TASK: [
                _reply(
                    [
                        {
                            "opinion": "Debt is at most three times revenue.",
                            "fact_ids": ["F001", "F002"],
                            "reasoning": "F001 and F002 support the comparison.",
                            "confidence": 0.8,
                            "quantitative": True,
                            "lean_claim": {
                                "facts": {"revenue": "F001", "debt": "F002"},
                                "claim": "debt <= 3 * revenue",
                            },
                        }
                    ]
                )
            ]
        }
    )
    drafts = await make_inference_drafts([_fact("F001"), _fact("F002")], [], provider)
    assert drafts[0].quantitative is True
    assert drafts[0].lean_claim is not None
    assert drafts[0].lean_claim.facts == {"revenue": "F001", "debt": "F002"}


def test_fact_reference_with_number_selector_is_kept() -> None:
    from busybee.infer.make_inferences import validate_inference_drafts

    output = InferenceOutput(
        inferences=[
            InferenceDraft(
                opinion="Quantitative.",
                fact_ids=["F001"],
                reasoning="F001.",
                quantitative=True,
                lean_claim=LeanClaim(facts={"a": "F001", "b": "F001#100"}, claim="a <= b"),
            )
        ]
    )
    drafts = validate_inference_drafts(output, [_fact("F001")])
    assert drafts[0].lean_claim is not None
    assert drafts[0].lean_claim.facts == {"a": "F001", "b": "F001#100"}
