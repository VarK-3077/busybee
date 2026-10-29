"""Check the independent-check downgrade and the end-to-end run_infer flow."""

import json
from decimal import Decimal

from busybee.infer import independent_check as check_module
from busybee.infer import prompts
from busybee.infer.independent_check import independent_check
from busybee.infer.run_infer import run_infer
from busybee.llm import MockProvider
from busybee.schema.facts import Citation, FactCategory, NumericValue, VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.report import Inference


def _fact(fact_id: str) -> VerifiedFact:
    return VerifiedFact(
        fact_id=fact_id,
        statement="Revenue was 100 crore.",
        category=FactCategory.revenue,
        citations=[Citation(chunk_id="D1:p1:c1", doc_id="D1", page_no=1)],
        numbers=[NumericValue(label="Revenue", value=Decimal("100"), unit="crore")],
    )


def _inference(inference_id: str) -> Inference:
    return Inference(
        inference_id=inference_id,
        opinion="Revenue is solid.",
        fact_ids=["F001"],
        reasoning="F001 shows revenue.",
        confidence=0.9,
        quantitative=False,
    )


async def test_failed_check_downgrades_confidence_and_appends_problem() -> None:
    provider = MockProvider(
        {
            check_module.TASK: [
                json.dumps({"ok": False, "problems": ["assumes market growth"]}),
                json.dumps({"ok": True, "problems": []}),
            ]
        }
    )
    result = await independent_check(
        [_inference("I001"), _inference("I002")], [_fact("F001")], provider
    )
    bad, good = result
    assert bad.confidence < 0.9
    assert "[Independent check: assumes market growth]" in bad.reasoning
    assert good.confidence == 0.9
    assert good.reasoning == "F001 shows revenue."


async def test_run_infer_writes_inferences_json(tmp_path) -> None:
    write_models_atomic(tmp_path / "verified_facts.json", [_fact("F001")])
    provider = MockProvider(
        {
            prompts.TASK: [
                json.dumps(
                    {
                        "inferences": [
                            {
                                "opinion": "Revenue is solid.",
                                "fact_ids": ["F001", "F404"],
                                "reasoning": "F001 shows revenue.",
                                "confidence": 0.7,
                            }
                        ]
                    }
                )
            ],
            check_module.TASK: [json.dumps({"ok": True, "problems": []})],
        }
    )
    result = await run_infer(tmp_path, {"run_id": "r1"}, provider)
    saved = read_models(tmp_path / "inferences.json", Inference)
    assert len(result) == 1
    assert saved[0].fact_ids == ["F001"]


async def test_run_infer_without_facts_writes_empty_list(tmp_path) -> None:
    result = await run_infer(tmp_path, {}, MockProvider({}))
    assert result == []
    assert read_models(tmp_path / "inferences.json", Inference) == []
