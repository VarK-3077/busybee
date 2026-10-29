"""Planted-error catch rate: inject known-wrong statements and count how many verify drops.

Each gold planted error becomes a `NotebookEntry` citing the corpus chunk whose numbers best
match the wrong statement (a plausible but wrong citation; ties fall back to shared content
words, then to the first chunk). The entries run through `verify_entries` with the relevance
filter off, so only citation checking can catch them. A planted error counts as caught by
either of two paths: `verify_entries` drops the injected entry, or, when the final report
facts are supplied, no report fact carries its statement. Presence is judge-free: a report
fact carries the statement when it contains every amount of the statement (numbers with a
unit, % or currency, else all non-fiscal numbers; a statement without numbers needs a near-
identical wording). Facts marked `conflicted` by verify's conflict step are not report facts:
an error whose statement appears only as a conflicted fact counts as caught (absent from the
report) and is also tallied in `conflicted`. Errors that were neither dropped nor absent
survived into the report and are listed in `missed`.
"""

from collections.abc import Mapping, Sequence

from pydantic import BaseModel, Field

from busybee.eval.gold import PlantedError
from busybee.schema.documents import Chunk
from busybee.schema.facts import Citation, EntryKind, NotebookEntry, VerifiedFact
from busybee.verify.conflicts import is_conflicted
from busybee.verify.dedupe import jaccard, statement_tokens
from busybee.verify.number_match import extract_numbers, find_numbers
from busybee.verify.verify_entries import VerifyContext, verify_entries

from .common import ratio

PLANTED_PREFIX = "PLANTED"
NO_NUMBER_JACCARD = 0.8


class PlantedErrorResult(BaseModel):
    """Catch rate and the planted statements that slipped through."""

    catch_rate: float | None = None
    caught: int = 0
    total: int = 0
    dropped_by_verify: int = 0
    absent_from_report: int = 0
    conflicted: int = 0
    missed: list[str] = Field(default_factory=list)


def _tokens(text: str) -> set[str]:
    return {word for word in "".join(c if c.isalnum() else " " for c in text.lower()).split()}


def best_matching_chunk(statement: str, chunks: Sequence[Chunk]) -> Chunk | None:
    """Pick the chunk sharing the most numbers (then content words) with the statement."""
    if not chunks:
        return None
    wanted = {abs(v) for v in extract_numbers(statement)}
    words = _tokens(statement)

    def score(chunk: Chunk) -> tuple[int, int]:
        have = {abs(v) for v in extract_numbers(chunk.text)}
        return len(wanted & have), len(words & _tokens(chunk.text))

    return max(chunks, key=score)


def planted_entries(errors: Sequence[PlantedError], chunks: Sequence[Chunk]) -> list[NotebookEntry]:
    """Build one notebook entry per planted error, citing its best-matching chunk."""
    entries: list[NotebookEntry] = []
    for index, error in enumerate(errors):
        chunk = best_matching_chunk(error.statement, chunks)
        citations = (
            [Citation(chunk_id=chunk.chunk_id, doc_id=chunk.doc_id, page_no=chunk.page_no)]
            if chunk
            else []
        )
        entries.append(
            NotebookEntry(
                entry_id=f"{PLANTED_PREFIX}{index + 1:03d}",
                statement=error.statement,
                citations=citations,
                kind=EntryKind.fact,
                doc_id=chunk.doc_id if chunk else "",
                added_by="eval.planted_errors",
            )
        )
    return entries


def statement_in_report(statement: str, report_facts: Sequence[VerifiedFact]) -> bool:
    """Judge-free check that some report fact carries the statement's numbers (or wording)."""
    mentions = [m for m in find_numbers(statement) if not m.fiscal]
    needed = [m for m in mentions if m.unit or m.percent or m.currency] or mentions
    wanted = statement_tokens(statement)
    for fact in report_facts:
        if needed:
            have = {abs(v) for v in extract_numbers(fact.statement)}
            if all(any(abs(v) in have for v in m.alternatives) for m in needed):
                return True
        elif jaccard(wanted, statement_tokens(fact.statement)) >= NO_NUMBER_JACCARD:
            return True
    return False


async def compute_planted_error_catch(
    errors: Sequence[PlantedError],
    ctx: VerifyContext,
    report_facts: Sequence[VerifiedFact] | None = None,
) -> PlantedErrorResult:
    """Inject planted errors, run verification; count those dropped or absent from the report."""
    chunks = list(ctx.chunks_by_id.values())
    entries = planted_entries(errors, chunks)
    facts, dropped = await verify_entries(entries, ctx, check_relevance=False)
    accepted = {fact.source_entry_id for fact in facts}
    statements: Mapping[str, str] = {e.entry_id: e.statement for e in entries}
    live = None if report_facts is None else [f for f in report_facts if not is_conflicted(f)]
    held_back = [f for f in report_facts or [] if is_conflicted(f)]
    survived = [
        statement
        for entry_id, statement in statements.items()
        if entry_id in accepted and (live is None or statement_in_report(statement, live))
    ]
    conflicted = len(
        [
            entry_id
            for entry_id, statement in statements.items()
            if entry_id in accepted
            and statement not in survived
            and live is not None
            and statement_in_report(statement, held_back)
        ]
    )
    absent = len([entry_id for entry_id in accepted if entry_id in statements]) - len(survived)
    caught = len(dropped) + absent
    return PlantedErrorResult(
        catch_rate=ratio(caught, len(entries)),
        caught=caught,
        total=len(entries),
        dropped_by_verify=len(dropped),
        absent_from_report=absent,
        conflicted=conflicted,
        missed=survived,
    )
