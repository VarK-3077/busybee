"""Merge duplicate notebook entries over the token budget; a truncated reply keeps them as is."""

from collections.abc import Iterable, Sequence

from pydantic import BaseModel, Field

from busybee.llm import Message, Role, StructuredOutputError, complete_as, count_tokens
from busybee.llm.provider import Provider
from busybee.schema.facts import Citation, NotebookEntry

from .condensed import condense_notebook

CONDENSE_MAX_TOKENS = 16000

MERGE_SYSTEM_PROMPT = """You are a credit analyst editing a compact notebook of facts for \
a credit decision. You receive one line per notebook entry. Some entries duplicate or \
restate the same fact, often because it appeared in more than one document.

Group only entries that state the same fact with the same period and meaning. Do not merge \
entries that merely share a category or a number. Every entry id you put in a group must \
appear in the notebook. Reply with JSON matching MergeOutput, where each group is a list of \
entry ids and a group has at least two ids."""


class MergeOutput(BaseModel):
    """Groups of notebook entry ids that should be merged into one entry."""

    groups: list[list[str]] = Field(default_factory=list)


def build_merge_prompt(entries: Sequence[NotebookEntry]) -> str:
    """Build the user turn that asks the model to group duplicate entries."""
    return (
        "Notebook entries:\n"
        f"{condense_notebook(entries)}\n\n"
        "Return the groups of duplicate entry ids as JSON matching MergeOutput."
    )


def _union_citations(members: Sequence[NotebookEntry]) -> list[Citation]:
    """Union citations in member order, keeping the first occurrence of each chunk."""
    seen: set[str] = set()
    citations: list[Citation] = []
    for member in members:
        for citation in member.citations:
            if citation.chunk_id in seen:
                continue
            seen.add(citation.chunk_id)
            citations.append(citation)
    return citations


def merge_groups(
    entries: Iterable[NotebookEntry],
    groups: Iterable[Sequence[str]],
) -> list[NotebookEntry]:
    """Merge each valid group into its earliest entry and preserve notebook order."""
    ordered = list(entries)
    positions = {entry.entry_id: index for index, entry in enumerate(ordered)}
    group_members: list[list[NotebookEntry]] = []
    grouped_ids: set[str] = set()
    for group in groups:
        member_ids = [entry_id for entry_id in dict.fromkeys(group) if entry_id in positions]
        if len(member_ids) < 2 or grouped_ids.intersection(member_ids):
            continue
        members = sorted(
            (ordered[positions[entry_id]] for entry_id in member_ids),
            key=lambda member: positions[member.entry_id],
        )
        group_members.append(members)
        grouped_ids.update(entry.entry_id for entry in members)

    if not group_members:
        return ordered

    merged_at = {positions[members[0].entry_id]: members for members in group_members}
    merged: list[NotebookEntry] = []
    for index, entry in enumerate(ordered):
        members = merged_at.get(index)
        if members is not None:
            base = members[0]
            merged.append(
                base.model_copy(
                    update={
                        "citations": _union_citations(members),
                        "importance": max(member.importance for member in members),
                    }
                )
            )
            continue
        if entry.entry_id in grouped_ids:
            continue
        merged.append(entry)
    return merged


def should_condense(entries: Iterable[NotebookEntry], budget_tokens: int) -> bool:
    """Return True when the condensed notebook is over its token budget."""
    return count_tokens(condense_notebook(entries)) > budget_tokens


async def condense_entries(
    entries: Iterable[NotebookEntry],
    provider: Provider,
    *,
    budget_tokens: int,
) -> list[NotebookEntry]:
    """Merge duplicate entries with one LLM call when the notebook is over budget."""
    ordered = list(entries)
    if not should_condense(ordered, budget_tokens):
        return ordered
    messages = [
        Message(role=Role.system, content=MERGE_SYSTEM_PROMPT),
        Message(role=Role.user, content=build_merge_prompt(ordered)),
    ]
    try:
        output = await complete_as(
            provider, messages, MergeOutput, task="condense", max_tokens=CONDENSE_MAX_TOKENS
        )
    except StructuredOutputError as error:
        if not error.truncated:
            raise
        return ordered
    return merge_groups(ordered, output.groups)


async def condense_if_needed(
    entries: Iterable[NotebookEntry],
    budget_tokens: int,
    provider: Provider,
) -> list[NotebookEntry]:
    """Convenience wrapper with the budget before the provider."""
    return await condense_entries(entries, provider, budget_tokens=budget_tokens)
