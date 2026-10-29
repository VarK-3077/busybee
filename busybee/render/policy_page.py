"""Render the policy page: approval record, the policy text by section, and the Lean explanation.

Every `PolicySection` becomes a `section.bb-chunk` whose id is the section id (`P3`), so a
recommendation chip can open `policy.html#P3` and the shared JS highlights the cited clause.
Section text is plain markdown; paragraphs, bullet lists and pipe tables are rendered, nothing
else is interpreted.
"""

from __future__ import annotations

from collections.abc import Sequence

from jinja2 import Environment
from markupsafe import Markup, escape

from busybee.policy.policy_sections import PolicySection
from busybee.render.lean_pages import explanation_html
from busybee.schema.lean import LeanExplanation
from busybee.schema.policy import Approval


def _table_html(lines: Sequence[str]) -> str:
    """Render a markdown pipe table, dropping the separator row."""
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    rows = [row for row in rows if not all(set(cell) <= set("-: ") for cell in row)]
    if not rows:
        return ""
    head = "".join(f"<th>{escape(cell)}</th>" for cell in rows[0])
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>" for row in rows[1:]
    )
    return (
        '<div class="bb-table-wrap"><table class="bb-table">'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _list_html(lines: Sequence[str]) -> str:
    """Render consecutive bullet or numbered lines as a list, joining wrapped lines."""
    items: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped[:2] in ("* ", "- ") or stripped.split(".", 1)[0].isdigit():
            items.append(stripped.split(maxsplit=1)[1] if " " in stripped else "")
        elif items:
            items[-1] += " " + stripped
    return "<ul>" + "".join(f"<li>{escape(item)}</li>" for item in items) + "</ul>"


def _block_html(block: str) -> str:
    """Render one blank-line separated block as a table, list or paragraph."""
    lines = block.splitlines()
    first = lines[0].strip()
    if all(line.strip().startswith("|") for line in lines):
        return _table_html(lines)
    if first[:2] in ("* ", "- ") or first.split(".", 1)[0].isdigit():
        return _list_html(lines)
    return f"<p>{escape(' '.join(line.strip() for line in lines))}</p>"


def policy_sections_html(sections: Sequence[PolicySection]) -> Markup:
    """Return the policy text as anchored sections, or a note when it is unavailable."""
    if not sections:
        return Markup(
            '<p class="bb-small bb-muted">The policy text is not available in the bank '
            "filesystem.</p>"
        )
    parts = []
    for section in sections:
        blocks = [block for block in section.text.split("\n\n") if block.strip()]
        body = "".join(_block_html(block) for block in blocks)
        section_id = escape(section.section_id)
        parts.append(
            f'<section class="bb-chunk" id="{section_id}">'
            f'<a class="bb-chunk-id" href="#{section_id}">{section_id}</a>'
            f'<h3 class="bb-h3">{escape(section.heading)}</h3>{body}</section>'
        )
    return Markup("".join(parts))


def render_policy_page(
    environment: Environment,
    *,
    bank_id: str,
    policy_label: str,
    approval: Approval,
    notice: Markup,
    explanation: LeanExplanation | None,
    policy_source: str | None,
    sections: Sequence[PolicySection] = (),
) -> str:
    """Render policy.html with the approval record, policy sections and Lean explanation."""
    return environment.get_template("policy.html").render(
        root="",
        bank_id=bank_id,
        policy_label=policy_label,
        approval=approval,
        notice=notice,
        explanation=explanation_html(explanation),
        policy_source=policy_source,
        policy_text=policy_sections_html(sections),
    )
