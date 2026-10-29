"""Truncated replies: top-level parsing, truncation signals, no re-prompt, server clamp."""

# ruff: noqa: E501

import json
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from busybee.extract.prompts import WindowOutput
from busybee.llm.audit_log import configure
from busybee.llm.messages import Completion, Message, Role, Usage
from busybee.llm.mock import MockProvider
from busybee.llm.openai_compatible import OpenAICompatibleProvider, server_token_limit
from busybee.llm.structured import StructuredOutputError, complete_as, extract_json_value

# Reply text of workspace/indoco-v3/llm_log.jsonl line 13: stopped at 4096 output tokens.
TRUNCATED_ICRA_REPLY = """{
  "entries": [
    {
      "statement": "ICRA reaffirmed the long-term fund-based term loan rating at [ICRA]A (Negative) for an amount of Rs. 400.00 crore on September 30, 2026.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "ratings",
      "kind": "fact",
      "importance": 5
    },
    {
      "statement": "ICRA reaffirmed the long-term fund-based cash credit limit rating at [ICRA]A (Negative) for an amount of Rs. 94.40 crore on September 30, 2026.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "ratings",
      "kind": "fact",
      "importance": 5
    },
    {
      "statement": "ICRA reaffirmed the short-term fund-based limit rating at [ICRA]A2+ for an amount of Rs. 335.00 crore on September 30, 2026.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "ratings",
      "kind": "fact",
      "importance": 5
    },
    {
      "statement": "ICRA reaffirmed the short-term non-fund based limit rating at [ICRA]A2+ for an amount of Rs. 20.25 crore on September 30, 2026.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "ratings",
      "kind": "fact",
      "importance": 5
    },
    {
      "statement": "The total rated amount for Indoco Remedies Limited is Rs. 1,019.65 crore.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "debt_leverage",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "The Negative outlook on the long-term rating reflects elevated debt levels, weak debt-protection metrics, and moderately high working capital intensity, despite a recovery in operating performance in FY2026.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "ratings",
      "kind": "fact",
      "importance": 4
    },
    {
      "statement": "Ratings remain constrained by the continued regulatory overhang at the Goa Plant II and uncertainty regarding the pace and sustainability of improvement in profitability, cash accruals, and leverage.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "ratings",
      "kind": "concern",
      "importance": 4
    },
    {
      "statement": "Continued investments in the over-the-counter (OTC) oral care business under Warren Remedies Private Limited constrained the company's consolidated profitability in FY2026.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "profitability",
      "kind": "concern",
      "importance": 3
    },
    {
      "statement": "Revenue grew by 10.8% to Rs. 1,845.3 crore in FY2026.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "revenue",
      "kind": "number",
      "importance": 5
    },
    {
      "statement": "Export formulation revenues grew by 28.7% in FY2026, with growth of 14.4% in regulated markets and 65.5% in non-regulated markets.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "revenue",
      "kind": "number",
      "importance": 4
    },
    {
      "statement": "The USFDA permitted the company to restart production on two of its four production lines at Goa Plant II by July 2025.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "litigation_regulatory",
      "kind": "fact",
      "importance": 4
    },
    {
      "statement": "IRL's margins and earnings remain far below previous levels.",
      "chunk_ids": [
        "D3:p1:c0"
      ],
      "category": "profitability",
      "kind": "concern",
      "importance": 4
    },
    {
      "statement": "Warren Remedies Private Limited's revenues increased by around 34% to Rs. 120.6 crore in FY2026 from Rs. 90.0 crore in FY2025.",
      "chunk_ids": [
        "D3:p1:c1"
      ],
      "category": "revenue",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "Operating income rose by 6.0% YoY to Rs. 467.5 crore in Q1 FY2027.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "revenue",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "The operating margin improved to 7.7% in FY2026 from 6.0% in FY2025.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "profitability",
      "kind": "number",
      "importance": 5
    },
    {
      "statement": "The operating margin grew to 8.8% in Q1 FY2027 from 4.0% in Q1 FY2026.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "profitability",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "Workforce rationalisation and other efficiencies under the Master Manufacturing Plan (MMP) are expected to generate annual savings of Rs. 14-15 crore.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "profitability",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "IRL received around Rs. 100 crore from the monetisation of its ophthalmic business in H1 FY2027.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "liquidity",
      "kind": "number",
      "importance": 4
    },
    {
      "statement": "IRL received a cash inflow of around Rs. 64 crore from the sale of a land parcel in Mumbai in H1 FY2027.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "liquidity",
      "kind": "number",
      "importance": 4
    },
    {
      "statement": "Total debt stood at Rs. 1,084.2 crore as on March 31, 2026.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "debt_leverage",
      "kind": "number",
      "importance": 5
    },
    {
      "statement": "Total debt/OPBDITA remained high at 7.6 times in FY2026.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "debt_leverage",
      "kind": "number",
      "importance": 5
    },
    {
      "statement": "Interest coverage was weak at 1.2 times in FY2026.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "debt_leverage",
      "kind": "number",
      "importance": 5
    },
    {
      "statement": "Debt Service Coverage Ratio (DSCR) was weak at 0.7 times in FY2026.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "debt_leverage",
      "kind": "number",
      "importance": 5
    },
    {
      "statement": "Working capital intensity remained moderately high at 34.6% in FY2026.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "liquidity",
      "kind": "number",
      "importance": 4
    },
    {
      "statement": "A USFDA inspection conducted during August 27–September 4, 2026, resulted in seven Form 483 observations for Goa Plant II.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "litigation_regulatory",
      "kind": "concern",
      "importance": 5
    },
    {
      "statement": "The receipt of the USFDA Establishment Inspection Report (EIR) for IRL’s Patalganga API facility in December 2025 is expected to support its operating profile.",
      "chunk_ids": [
        "D3:p2:c0"
      ],
      "category": "litigation_regulatory",
      "kind": "fact",
      "importance": 3
    },
    {
      "statement": "The company's operations are managed by Ms. Aditi Kare Panandikar and Mr. Sundeep Bambolkar, both of whom have over 30 years of experience in the pharmaceutical industry.",
      "chunk_ids": [
        "D3:p2:c1"
      ],
      "category": "ownership_governance",
      "kind": "fact",
      "importance": 3
    },
    {
      "statement": "In FY2026, domestic and export formulations contributed 46.6% and 36.8%, respectively, to the overall revenues.",
      "chunk_ids": [
        "D3:p3:c0"
      ],
      "category": "revenue",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "IRL's Goa Plants II and III received Operating Agency Inspection (OAI) status in June 2023 following a USFDA inspection in February 2023.",
      "chunk_ids": [
        "D3:p3:c0"
      ],
      "category": "litigation_regulatory",
      "kind": "fact",
      "importance": 4
    },
    {
      "statement": "A USFDA warning letter was issued to Goa Plant II in February 2024, leading to the shutdown of all four production lines in April 2024.",
      "chunk_ids": [
        "D3:p3:c0"
      ],
      "category": "litigation_regulatory",
      "kind": "fact",
      "importance": 4
    },
    {
      "statement": "About 11%-13% of the domestic formulations business is subject to Government mandated pricing controls under the National List of Essential Medicines (NLEM).",
      "chunk_ids": [
        "D3:p3:c1"
      ],
      "category": "industry_market",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "Working capital intensity moderated to 34.6% in FY2026 from 37.7% in FY2025.",
      "chunk_ids": [
        "D3:p4:c0"
      ],
      "category": "liquidity",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "Inventory days declined to 124 days in FY2026 from 139 days in FY2025.",
      "chunk_ids": [
        "D3:p4:c0"
      ],
      "category": "liquidity",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "Creditor days increased to 198 days in FY2026 from 141 days in FY2025.",
      "chunk_ids": [
        "D3:p4:c0"
      ],
      "category": "liquidity",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "The company's net loss widened to Rs. 98.7 crore in FY2026 from Rs. 78.0 crore in FY2025.",
      "chunk_ids": [
        "D3:p4:c0"
      ],
      "category": "profitability",
      "kind": "number",
      "importance": 5
    },
    {
      "statement": "Warren Remedies reported a higher loss before tax of Rs. 64.3 crore in FY2026 over Rs. 36.0 crore in FY2025.",
      "chunk_ids": [
        "D3:p4:c0"
      ],
      "category": "profitability",
      "kind": "number",
      "importance": 4
    },
    {
      "statement": "The company does not envisage any significant capex over the near term, with proposed expenditure restricted primarily to essential maintenance, energy saving initiatives, and boiler installations.",
      "chunk_ids": [
        "D3:p4:c0"
      ],
      "category": "cash_flow",
      "kind": "fact",
      "importance": 3
    },
    {
      "statement": "The company's liquidity position is rated as Adequate, with free cash and liquid investments of Rs. 26.2 crore as on March 31, 2026.",
      "chunk_ids": [
        "D3:p4:c1"
      ],
      "category": "liquidity",
      "kind": "number",
      "importance": 4
    },
    {
      "statement": "The average working capital utilisation was 90.7% against its drawing power during the 12-month period ending in July 2026.",
      "chunk_ids": [
        "D3:p4:c1"
      ],
      "category": "liquidity",
      "kind": "number",
      "importance": 4
    },
    {
      "statement": "Debt servicing obligations are Rs. 145.8 crore for FY2027 and Rs. 145.3 crore for FY2028.",
      "chunk_ids": [
        "D3:p4:c1"
      ],
      "category": "debt_leverage",
      "kind": "number",
      "importance": 4
    },
    {
      "statement": "The outlook may be revised to Stable if the company demonstrates significant improvement in margins, leading to sustained improvement in debt metrics, return indicators, and liquidity position.",
      "chunk_ids": [
        "D3:p5:c0"
      ],
      "category": "ratings",
      "kind": "fact",
      "importance": 4
    },
    {
      "statement": "The rating may be downgraded if the company is unable to improve revenues and margins materially by scaling additional capacities, or if there are delays in resolving regulatory non-compliance.",
      "chunk_ids": [
        "D3:p5:c0"
      ],
      "category": "ratings",
      "kind": "fact",
      "importance": 4
    },
    {
      "statement": "ICRA has considered the consolidated financials of IRL for arriving at the ratings.",
      "chunk_ids": [
        "D3:p5:c0"
      ],
      "category": "other",
      "kind": "fact",
      "importance": 2
    },
    {
      "statement": "Indoco Remedies Limited was established in 1947 and the current Chairman, Mr. Suresh G. Kare, took over in 1963.",
      "chunk_ids": [
        "D3:p5:c0"
      ],
      "category": "ownership_governance",
      "kind": "fact",
      "importance": 2
    },
    {
      "statement": "Domestic formulations contributed to around 44.3% of total revenues in FY2026 (consolidated).",
      "chunk_ids": [
        "D3:p5:c0"
      ],
      "category": "revenue",
      "kind": "number",
      "importance": 3
    },
    {
      "statement": "Export formulations comprised 39% of IRL's revenues in FY2026, while APIs accounted for 9%.",
      "chunk_ids": [
        "D3:p5:c0"
      ],
      "category": "revenue",
      "kind":"""


class Reply(BaseModel):
    answer: int = 0
    items: list[int] = []


def prompt() -> list[Message]:
    return [Message(role=Role.user, content="go")]


class ScriptedProvider:
    """Returns scripted completions with a chosen finish_reason and output token count."""

    name = "scripted"
    model = "scripted"

    def __init__(
        self, completions: list[Completion], default_max_tokens: int | None = None
    ) -> None:
        self.completions = completions
        self.calls = 0
        if default_max_tokens is not None:
            self.default_max_tokens = default_max_tokens

    async def complete(self, messages: list[Message], **kwargs: Any) -> Completion:
        self.calls += 1
        return self.completions[min(self.calls, len(self.completions)) - 1]


def completion(text: str, tokens: int, finish: str | None = None) -> Completion:
    return Completion(text=text, usage=Usage(output_tokens=tokens), finish_reason=finish)


def test_real_truncated_reply_is_not_rescued_from_a_nested_object() -> None:
    with pytest.raises(ValueError, match="top-level"):
        extract_json_value(TRUNCATED_ICRA_REPLY)


async def test_real_truncated_reply_raises_truncated_and_is_not_an_empty_window() -> None:
    provider = MockProvider({"extract": [TRUNCATED_ICRA_REPLY]})

    with pytest.raises(StructuredOutputError) as captured:
        await complete_as(provider, prompt(), WindowOutput, task="extract", max_tokens=9000)

    assert captured.value.truncated
    assert len(provider.calls) == 1


def test_complete_top_level_value_still_parses_with_trailing_text() -> None:
    assert extract_json_value('```json\n{"answer": 1, "items": [2]}\n``` ') == {
        "answer": 1,
        "items": [2],
    }
    assert extract_json_value('[{"a": 1}, {"b": 2}]\n') == [{"a": 1}, {"b": 2}]


def test_malformed_top_level_is_not_replaced_by_a_nested_object() -> None:
    with pytest.raises(ValueError):
        extract_json_value('{"outer": oops, "inner": {"answer": 3}}')


async def test_finish_reason_length_means_truncated_even_for_invalid_content() -> None:
    provider = ScriptedProvider([completion('{"answer": "x"}', 10, "length")])

    with pytest.raises(StructuredOutputError) as captured:
        await complete_as(provider, prompt(), Reply, task="t", max_tokens=9000)

    assert captured.value.truncated
    assert provider.calls == 1


@pytest.mark.parametrize(
    ("max_tokens", "default", "tokens"),
    [(1000, None, 990), (9000, 4096, 4050), (9000, 4096, 4096)],
)
async def test_output_tokens_near_requested_or_default_limit_mean_truncated(
    max_tokens: int, default: int | None, tokens: int
) -> None:
    provider = ScriptedProvider([completion('{"answer": "x"}', tokens)], default)

    with pytest.raises(StructuredOutputError) as captured:
        await complete_as(provider, prompt(), Reply, task="t", max_tokens=max_tokens)

    assert captured.value.truncated


async def test_invalid_reply_far_from_any_limit_is_reprompted_not_truncated() -> None:
    provider = ScriptedProvider(
        [completion('{"answer": "x"}', 50), completion('{"answer": 2}', 50)], 4096
    )

    reply = await complete_as(provider, prompt(), Reply, task="t", max_tokens=9000)

    assert reply.answer == 2
    assert provider.calls == 2


async def test_unclosed_reply_is_truncated_without_a_reprompt() -> None:
    provider = ScriptedProvider([completion('{"answer": 1, "items": [1, 2', 5)])

    with pytest.raises(StructuredOutputError) as captured:
        await complete_as(provider, prompt(), Reply, task="t")

    assert captured.value.truncated
    assert provider.calls == 1


def test_window_output_requires_entries() -> None:
    with pytest.raises(ValueError):
        WindowOutput.model_validate({"chunk_ids": ["D1:p1:c0"], "kind": "fact"})


def chat(text: str, finish: str = "stop", tokens: int = 4) -> dict[str, Any]:
    return {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": finish,
            }
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": tokens, "total_tokens": 7 + tokens},
    }


def make_provider(handler: Any) -> OpenAICompatibleProvider:
    return OpenAICompatibleProvider(
        "m", base_url="http://test/v1", api_key="k", http_client=httpx.MockTransport(handler)
    )


async def test_finish_reason_is_exposed_and_audited(tmp_path: Any) -> None:
    configure(tmp_path / "log.jsonl")
    try:
        provider = make_provider(lambda request: httpx.Response(200, json=chat("{", "length")))
        result = await provider.complete(prompt(), max_tokens=9000, task="t")
    finally:
        configure(None)

    assert result.finish_reason == "length"
    line = json.loads((tmp_path / "log.jsonl").read_text().splitlines()[0])
    assert line["finish_reason"] == "length"


async def test_max_tokens_is_passed_through_unchanged() -> None:
    seen: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["max_tokens"])
        return httpx.Response(200, json=chat("ok"))

    await make_provider(handler).complete(prompt(), max_tokens=9000)

    assert seen == [9000]


async def test_server_limit_in_400_is_clamped_once() -> None:
    seen: list[int] = []
    message = (
        "'max_tokens' is too large: 9000. This model's maximum context length is 8192 tokens "
        "and your request has 7243 input tokens (9000 > 8192 - 7243)."
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["max_tokens"])
        if len(seen) == 1:
            return httpx.Response(
                400, json={"error": {"message": message, "type": "BadRequestError", "code": 400}}
            )
        return httpx.Response(200, json=chat("ok"))

    result = await make_provider(handler).complete(prompt(), max_tokens=9000)

    assert result.text == "ok"
    assert seen == [9000, 949]


def test_server_token_limit_reads_common_messages() -> None:
    assert server_token_limit("(9000 > 8192 - 7243)", 9000) == 949
    assert server_token_limit("max_tokens must be less than or equal to 4096", 9000) == 4096
    assert server_token_limit("max_tokens must be less than or equal to 4096", 100) is None
    assert server_token_limit("something else", 9000) is None
