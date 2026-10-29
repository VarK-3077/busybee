"""Give verified facts their stable ids F001, F002, ... in notebook order.

`added_by` and every other field are carried over untouched; only `fact_id` changes. Pass
`start` to continue numbering after existing facts (for example facts added later by the
adversary stage).
"""

from collections.abc import Sequence

from busybee.schema.facts import VerifiedFact


def fact_id_for(number: int) -> str:
    """Format a 1-based sequence number as a fact id."""
    return f"F{number:03d}"


def assign_fact_ids(facts: Sequence[VerifiedFact], start: int = 1) -> list[VerifiedFact]:
    """Return copies of facts numbered consecutively from start, preserving order."""
    return [
        fact.model_copy(update={"fact_id": fact_id_for(start + offset)})
        for offset, fact in enumerate(facts)
    ]
