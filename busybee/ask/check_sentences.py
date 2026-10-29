"""Verify each answer sentence against the chunks it cites, reusing the verify components.

A sentence is supported when every number in it occurs in the cited text
(`verify.number_match.statement_numbers_supported`) and the entailment judge
(`verify.entailment.judge_entailment_batch`) marks at least one cited chunk as supported.
"""

import asyncio

from busybee.ask.compose_answer import AskSentence
from busybee.ask.model import CheckedSentence, Citation
from busybee.llm.provider import Provider
from busybee.render.links import report_pdf_href
from busybee.schema.documents import Chunk, Document
from busybee.verify.entailment import Verdict, judge_entailment_batch
from busybee.verify.number_match import statement_numbers_supported


def citation_for(chunk: Chunk, documents: dict[str, Document]) -> Citation:
    """Build a citation with the original-PDF link when the document is a PDF."""
    return Citation(
        chunk_id=chunk.chunk_id,
        doc_id=chunk.doc_id,
        page_no=chunk.page_no,
        pdf_href=report_pdf_href(documents.get(chunk.doc_id), chunk.page_no),
    )


async def check_sentence(
    sentence: AskSentence,
    chunks: dict[str, Chunk],
    documents: dict[str, Document],
    provider: Provider,
) -> CheckedSentence:
    """Return the sentence with its citations and a supported verdict."""
    cited = [chunks[cid] for cid in sentence.chunk_ids if cid in chunks]
    citations = [citation_for(chunk, documents) for chunk in cited]
    if not cited:
        return CheckedSentence(text=sentence.text, note="cites no retrieved chunk")
    numbers_ok, missing = statement_numbers_supported(
        sentence.text, "\n".join(chunk.text for chunk in cited)
    )
    if not numbers_ok:
        return CheckedSentence(
            text=sentence.text,
            citations=citations,
            note="numbers not found in cited text: " + ", ".join(missing),
        )
    verdicts = await judge_entailment_batch(
        sentence.text, [(chunk.chunk_id, chunk.text) for chunk in cited], provider
    )
    supported = any(verdict.verdict is Verdict.supported for verdict in verdicts)
    return CheckedSentence(
        text=sentence.text,
        citations=citations,
        supported=supported,
        note="" if supported else "cited text does not support the sentence",
    )


async def check_sentences(
    sentences: list[AskSentence],
    chunks: dict[str, Chunk],
    documents: dict[str, Document],
    provider: Provider,
) -> list[CheckedSentence]:
    """Check every sentence concurrently, preserving order."""
    return list(
        await asyncio.gather(
            *(check_sentence(sentence, chunks, documents, provider) for sentence in sentences)
        )
    )
