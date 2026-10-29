"""Pure functions that render the Lean source fragments used in generated artifacts."""

from collections.abc import Iterable


def _doc_comment(doc: str | None) -> str:
    """Render an optional `/-- ... -/` doc comment."""
    if not doc:
        return ""
    return f"/-- {doc.strip()} -/"


def file_header(imports: Iterable[str], doc: str) -> str:
    """Render a module doc block, after any imports as Lean requires."""
    header = f"/-!\n{doc.strip()}\n-/"
    import_lines = "\n".join(f"import {name}" for name in imports)
    return f"{import_lines}\n\n{header}" if import_lines else header


def section(title: str) -> str:
    """Render a `-- SECTION:` marker consumed by the manual explainer."""
    return f"-- SECTION: {title.strip()}"


def fact_def(name: str, value: int, comment: str, doc: str | None = None) -> str:
    """Render an `Int` fact with its provenance comment on the same line."""
    lines = []
    doc_comment = _doc_comment(doc)
    if doc_comment:
        lines.append(doc_comment)
    lines.append(f"def {name} : Int := {value} -- {comment.strip()}")
    return "\n".join(lines)


def theorem(
    name: str,
    statement: str,
    tactic: str = "decide",
    doc: str | None = None,
) -> str:
    """Render a theorem whose proof is a short tactic block."""
    lines = []
    doc_comment = _doc_comment(doc)
    if doc_comment:
        lines.append(doc_comment)
    lines.append(f"theorem {name} : {statement.strip()} := by")
    for tactic_line in tactic.strip().splitlines() or ["decide"]:
        lines.append(f"  {tactic_line.strip()}")
    return "\n".join(lines)


def eval_line(expr: str) -> str:
    """Render a `#eval` line whose output is parsed from the compiler stdout."""
    return f"#eval {expr.strip()}"


def join(parts: Iterable[str]) -> str:
    """Join non-empty source fragments with blank lines and a trailing newline."""
    rendered = [part.strip() for part in parts if part and part.strip()]
    return "\n\n".join(rendered) + "\n"
