"""cited_passages sends full chunks up to 6000 chars and an evidence-centred window beyond."""

from busybee.eval.metrics.common import cited_passages
from busybee.eval.metrics.precision import compute_precision
from busybee.llm import Message, MockProvider
from busybee.schema.documents import Chunk
from busybee.schema.facts import Citation, VerifiedFact


def chunk_of(text: str) -> Chunk:
    return Chunk(chunk_id="D1:p1:c0", doc_id="D1", page_no=1, index_in_page=0, text=text)


def fact_citing(statement: str, quote: str = "") -> VerifiedFact:
    return VerifiedFact(
        fact_id="F1",
        statement=statement,
        citations=[Citation(chunk_id="D1:p1:c0", doc_id="D1", page_no=1, quote=quote)],
    )


def test_three_thousand_char_chunk_with_evidence_at_the_end_is_intact() -> None:
    text = "x" * 2950 + " Revenue was Rs 931.2 crore in FY25."
    passage = cited_passages(
        fact_citing("Revenue was Rs 931.2 crore"), {"D1:p1:c0": chunk_of(text)}
    )
    assert passage == text


def test_long_chunk_is_windowed_around_the_quote() -> None:
    text = "a" * 8000 + " KEY EVIDENCE " + "b" * 8000
    passage = cited_passages(fact_citing("s", "KEY EVIDENCE"), {"D1:p1:c0": chunk_of(text)})
    assert "KEY EVIDENCE" in passage and 2500 <= len(passage) <= 6000


def test_long_chunk_without_quote_is_windowed_around_first_number() -> None:
    text = "a" * 9000 + " total 4567 here " + "b" * 9000
    passage = cited_passages(fact_citing("Total was 4567"), {"D1:p1:c0": chunk_of(text)})
    assert "4567" in passage and len(passage) >= 2500


async def test_precision_prompt_carries_quote_and_full_text() -> None:
    text = "y" * 3000 + " END-MARK"
    seen: list[str] = []

    def respond(messages: list[Message], task: str) -> str:
        seen.append(messages[-1].content)
        return '{"verdicts": [{"fact_id": "F1", "important": true, "correct": true}]}'

    await compute_precision(
        [fact_citing("s", "END-MARK")], {"D1:p1:c0": chunk_of(text)}, MockProvider(respond)
    )
    assert "QUOTE: END-MARK" in seen[0] and text in seen[0]
