"""Group verified facts by canonical category, placing adversary additions last."""

from collections.abc import Iterable, Mapping

from busybee.schema.facts import FactCategory, VerifiedFact
from busybee.schema.report import FactGroup

CANONICAL_CATEGORIES: tuple[FactCategory, ...] = tuple(FactCategory)


def _ordered_facts(facts: Iterable[VerifiedFact]) -> list[VerifiedFact]:
    """Return ordinary facts first and adversary additions last, keeping input order."""
    ordered = list(facts)
    ordinary = [fact for fact in ordered if fact.added_by != "adversary"]
    adversary = [fact for fact in ordered if fact.added_by == "adversary"]
    return [*ordinary, *adversary]


def group_facts(
    facts: Iterable[VerifiedFact] | Mapping[str, VerifiedFact],
) -> list[FactGroup]:
    """Return one FactGroup per non-empty category in canonical category order."""
    values = facts.values() if isinstance(facts, Mapping) else facts
    ordered = _ordered_facts(values)
    groups: list[FactGroup] = []
    for category in CANONICAL_CATEGORIES:
        ids = [fact.fact_id for fact in ordered if fact.category == category]
        if ids:
            groups.append(FactGroup(category=category, fact_ids=ids))
    return groups
