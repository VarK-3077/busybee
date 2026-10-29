"""Tests for canonical fact grouping and adversary-last ordering within a group."""

from busybee.compose.fact_groups import group_facts
from busybee.schema.facts import FactCategory, VerifiedFact


def fact(fact_id: str, category: FactCategory, added_by: str) -> VerifiedFact:
    """Build a minimal verified fact for grouping tests."""
    return VerifiedFact(
        fact_id=fact_id,
        statement=f"Statement {fact_id}.",
        category=category,
        added_by=added_by,
    )


def test_groups_follow_canonical_category_order() -> None:
    facts = [
        fact("F010", FactCategory.profitability, "extract"),
        fact("F001", FactCategory.revenue, "extract"),
        fact("F020", FactCategory.debt_leverage, "extract"),
    ]

    groups = group_facts(facts)

    assert [group.category for group in groups] == [
        FactCategory.revenue,
        FactCategory.profitability,
        FactCategory.debt_leverage,
    ]


def test_adversary_additions_go_last_within_a_group() -> None:
    facts = [
        fact("F001", FactCategory.revenue, "extract"),
        fact("F002", FactCategory.revenue, "adversary"),
        fact("F003", FactCategory.revenue, "extract"),
        fact("F004", FactCategory.revenue, "adversary"),
    ]

    groups = group_facts({item.fact_id: item for item in facts})

    assert len(groups) == 1
    assert groups[0].fact_ids == ["F001", "F003", "F002", "F004"]


def test_empty_categories_are_omitted() -> None:
    groups = group_facts([fact("F001", FactCategory.other, "extract")])

    assert [group.category for group in groups] == [FactCategory.other]
    assert groups[0].fact_ids == ["F001"]
