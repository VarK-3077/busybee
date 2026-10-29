"""Entailment replies are verdict+quote only; code makes quotes verbatim, never re-prompts."""

import json

from busybee.llm import MockProvider
from busybee.verify.entailment import (
    NOTE_NO_SUPPORTING_LINE,
    NOTE_QUOTE_BY_CODE,
    Verdict,
    judge_entailment,
    judge_entailment_batch,
    locate_quote,
)

CHUNK = "The company reported net debt of Rs 40 crore\nat 31 March 2024."


def reply(verdict: str, quote: str) -> MockProvider:
    return MockProvider(json.dumps({"v": verdict, "q": quote}, separators=(",", ":")))


async def test_verbatim_quote_keeps_verdict() -> None:
    out = await judge_entailment(
        "Net debt is Rs 40 crore", CHUNK, reply("supported", "net debt of Rs 40 crore")
    )
    assert out.verdict is Verdict.supported
    assert out.quote == "net debt of Rs 40 crore" and out.note == ""


async def test_full_field_names_still_parse() -> None:
    provider = MockProvider(json.dumps({"verdict": "supported", "quote": "net debt of Rs 40"}))
    out = await judge_entailment("Net debt is Rs 40 crore", CHUNK, provider)
    assert out.verdict is Verdict.supported and out.quote == "net debt of Rs 40"


async def test_whitespace_differences_are_resolved_to_the_exact_span() -> None:
    out = await judge_entailment("s", CHUNK, reply("supported", "Rs 40 crore at 31 March 2024"))
    assert out.verdict is Verdict.supported
    assert out.quote == "Rs 40 crore\nat 31 March 2024"


async def test_invented_quote_falls_back_to_deterministic_span_without_reprompt() -> None:
    provider = reply("supported", "net debt of Rs 400 crore")
    out = await judge_entailment("Net debt is Rs 40 crore", CHUNK, provider)
    assert out.verdict is Verdict.supported
    assert out.quote in CHUNK and "Rs 40" in out.quote
    assert out.note == NOTE_QUOTE_BY_CODE
    assert len(provider.calls) == 1


async def test_partial_without_quote_gets_deterministic_span() -> None:
    out = await judge_entailment("Net debt is Rs 40 crore", CHUNK, reply("partial", ""))
    assert out.verdict is Verdict.partial
    assert out.quote in CHUNK and out.note == NOTE_QUOTE_BY_CODE


async def test_unsupported_passes_through_without_quote() -> None:
    out = await judge_entailment("s", CHUNK, reply("unsupported", "net debt"))
    assert out.verdict is Verdict.unsupported and out.quote == ""


async def test_unparseable_reply_is_unsupported_after_reprompt() -> None:
    provider = MockProvider("not json")
    out = await judge_entailment("s", CHUNK, provider)
    assert out.verdict is Verdict.unsupported and "unusable" in out.note
    assert len(provider.calls) == 3


async def test_missing_verdict_is_reprompted_then_accepted() -> None:
    provider = MockProvider(
        {"verify_entailment": ['{"q":"x"}', '{"v":"supported","q":"net debt of Rs 40"}']}
    )
    out = await judge_entailment("Net debt is Rs 40 crore", CHUNK, provider)
    assert out.verdict is Verdict.supported and len(provider.calls) == 2


def test_locate_quote() -> None:
    assert locate_quote("a  b c", "a b") == "a  b"
    assert locate_quote("a b c", "") is None
    assert locate_quote("a b c", "c a") is None


async def test_prompt_asks_for_compact_verdict_quote_and_partial_for_inferred_values() -> None:
    provider = reply("supported", "net debt of Rs 40")
    await judge_entailment("Net debt is Rs 40 crore", CHUNK, provider)
    system = provider.calls[0].messages[0].content
    assert "literally" in system and "same period" in system and "unit" in system
    assert "never compute" in system.casefold() and "partial" in system
    assert '"v":"supported|partial|unsupported"' in system and "160" in system
    assert "note" not in system.casefold()
    assert "minified" in system


async def test_batch_reply_uses_short_keys_and_code_fallback_quotes() -> None:
    other = "Interest cover stood at 3.2 times."
    body = {
        "r": [
            {"id": "D1:c1", "v": "supported", "q": "net debt of Rs 40 crore"},
            {"id": "D1:c2", "v": "partial", "q": "invented words"},
        ]
    }
    provider = MockProvider(json.dumps(body, separators=(",", ":")))
    outs = await judge_entailment_batch(
        "Net debt is Rs 40 crore", [("D1:c1", CHUNK), ("D1:c2", other)], provider
    )
    assert [o.verdict for o in outs] == [Verdict.supported, Verdict.partial]
    assert outs[0].quote == "net debt of Rs 40 crore" and outs[0].note == ""
    assert outs[1].quote == other and outs[1].note == NOTE_QUOTE_BY_CODE
    assert len(provider.calls) == 1
    assert '"r":[{"id"' in provider.calls[0].messages[0].content


async def test_batch_forgotten_chunk_falls_back_to_single_judge() -> None:
    provider = MockProvider(
        {
            "verify_entailment_batch": ['{"r":[{"id":"D1:c1","v":"supported","q":"net debt"}]}'],
            "verify_entailment": ['{"v":"unsupported","q":""}'],
        }
    )
    outs = await judge_entailment_batch(
        "Net debt is Rs 40 crore", [("D1:c1", CHUNK), ("D1:c2", "Other text.")], provider
    )
    assert outs[0].verdict is Verdict.supported and outs[1].verdict is Verdict.unsupported


RATING = (
    "CRISIL has downgraded the rating of the bank facilities to BBB from A-.\nOutlook is stable."
)


async def test_numberless_supported_with_matching_line_is_accepted() -> None:
    statement = "CRISIL downgraded the bank facilities rating to BBB."
    out = await judge_entailment(statement, RATING, reply("supported", "made up words"))
    assert out.verdict is Verdict.supported
    assert out.quote == RATING.splitlines()[0] and out.note == NOTE_QUOTE_BY_CODE


async def test_numberless_supported_with_invented_quote_and_no_line_is_partial() -> None:
    statement = "The promoter pledged shares to a lender."
    out = await judge_entailment(statement, RATING, reply("supported", "pledged shares"))
    assert out.verdict is Verdict.partial
    assert out.note == NOTE_NO_SUPPORTING_LINE


async def test_numberless_verbatim_quote_stays_supported() -> None:
    statement = "The outlook is stable."
    out = await judge_entailment(statement, RATING, reply("supported", "Outlook is stable"))
    assert out.verdict is Verdict.supported and out.note == ""
