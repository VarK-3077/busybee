"""Tolerant access to the optional fields of a fact, so reports from older runs still render.

Facts written before `record`, `scope`, `conflicts` and `importance` existed lack them (or a
loader may hand back a plain object without them). `fact_field` reads one such field with a
default; the render stage uses it instead of direct attribute access.
"""

from typing import Any

from busybee.schema.facts import FactScope

DEFAULTS: dict[str, Any] = {"record": None, "scope": None, "conflicts": (), "importance": 3}


def fact_field(fact: object, name: str) -> Any:
    """Return `fact.<name>`, or the documented default when the fact has no such field or None."""
    value = getattr(fact, name, None)
    return DEFAULTS[name] if value is None else value


def fact_scope(fact: object) -> FactScope | None:
    """The fact's scope, or None when unknown."""
    return fact_field(fact, "scope")
