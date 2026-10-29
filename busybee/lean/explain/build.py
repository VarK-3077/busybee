"""Build the human-facing Lean explanation model from a source file."""

from busybee.lean.explain.english import english_for
from busybee.lean.explain.parse import parse_sections
from busybee.schema.lean import ExplainItem, ExplainSection, LeanExplanation


def explain_source(source: str) -> LeanExplanation:
    """Parse source into sections and render each declaration for the explanation page."""
    sections: list[ExplainSection] = []
    for parsed in parse_sections(source):
        items = [
            ExplainItem(
                name=declaration.name,
                kind=declaration.kind,
                lean=declaration.lean,
                english=english_for(declaration),
                doc=declaration.doc,
            )
            for declaration in parsed.declarations
        ]
        sections.append(ExplainSection(title=parsed.title, items=items))
    return LeanExplanation(sections=sections)
