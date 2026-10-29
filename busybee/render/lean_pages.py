"""Render one Lean artifact page with source, compiler output, and explanation."""

from __future__ import annotations

from jinja2 import Environment
from markupsafe import Markup, escape

from busybee.render.links import artifact_slug, lean_anchor_id
from busybee.schema.lean import LeanArtifact, LeanExplanation


def compile_status(artifact: LeanArtifact) -> tuple[str, str]:
    """Return the badge status and label for an artifact's compiler result."""
    compile_result = artifact.compile
    if compile_result is None:
        return "unchecked", "Not compiled"
    if compile_result.ok:
        return "proved", "Proved"
    return "failed", "Lean failed"


def source_line_spans(artifact: LeanArtifact) -> Markup:
    """Return one escaped .bb-line span per source line, marking compiler errors."""
    error_lines = (
        {error.line for error in artifact.compile.errors} if artifact.compile is not None else set()
    )
    lines = artifact.source.splitlines() or [""]
    spans = []
    for number, line in enumerate(lines, start=1):
        class_name = "bb-line bb-line--error" if number in error_lines else "bb-line"
        spans.append(f'<span class="{class_name}">{escape(line)}</span>')
    return Markup("".join(spans))


def compile_head(artifact: LeanArtifact) -> str:
    """Return the one-line compiler summary shown above its output."""
    result = artifact.compile
    if result is None:
        return "Not compiled"
    parts = ["Compiled without errors" if result.ok else "Compilation failed"]
    parts.append(f"{result.duration_s:.2f} s")
    if result.toolchain:
        parts.append(result.toolchain)
    return " · ".join(parts)


def compile_output(artifact: LeanArtifact) -> str:
    """Return stdout followed by stderr, or a calm placeholder when empty."""
    result = artifact.compile
    if result is None:
        return "(not compiled)"
    output = (result.stdout or "") + (result.stderr or "")
    return output.rstrip() or "(no messages)"


def explanation_html(explanation: LeanExplanation | None) -> Markup:
    """Render a LeanExplanation as the two-column Lean-beside-English list."""
    if explanation is None or not explanation.sections:
        return Markup("")
    sections = []
    for section in explanation.sections:
        items = []
        for item in section.items:
            doc = f'<p class="bb-explain-doc">{escape(item.doc)}</p>' if item.doc else ""
            items.append(
                f'<div class="bb-explain-item" id="explain-{escape(item.name)}">'
                '<div class="bb-explain-name">'
                f'{escape(item.name)} <span class="bb-explain-kind">{escape(item.kind)}</span>'
                "</div>"
                f'<pre class="bb-explain-lean">{escape(item.lean)}</pre>'
                '<div class="bb-explain-english">'
                f'{doc}<p class="bb-explain-mech">{escape(item.english)}</p></div></div>'
            )
        sections.append(
            '<section class="bb-explain-section">'
            f'<h3 class="bb-h3">{escape(section.title)}</h3>'
            '<div class="bb-explain-cols bb-caps"><span>Lean</span><span>In English</span></div>'
            f"{''.join(items)}</section>"
        )
    return Markup(f'<div class="bb-explain">{"".join(sections)}</div>')


def render_lean_page(
    environment: Environment,
    artifact: LeanArtifact,
    *,
    title: str,
    explanation: LeanExplanation | None = None,
) -> str:
    """Render one Lean artifact as a standalone HTML page."""
    status, status_label = compile_status(artifact)
    short_hash = f"{artifact.sha256[:12]}…" if len(artifact.sha256) > 12 else artifact.sha256
    return environment.get_template("lean.html").render(
        root="../",
        title=title,
        artifact=artifact,
        anchor_id=lean_anchor_id(artifact.artifact_id),
        status=status,
        status_label=status_label,
        line_spans=source_line_spans(artifact),
        compile_ok=bool(artifact.compile is not None and artifact.compile.ok),
        compile_head=compile_head(artifact),
        compile_output=compile_output(artifact),
        short_hash=short_hash,
        source_name=f"{artifact_slug(artifact.artifact_id)}.lean",
        explanation=explanation_html(explanation),
    )
