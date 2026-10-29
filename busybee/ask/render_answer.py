"""Format an Answer as terminal text: each sentence marked supported or not supported."""

from busybee.ask.model import Answer, Citation


def citation_label(citation: Citation) -> str:
    """Return "D1 p.157" plus the original-PDF link when there is one."""
    label = f"{citation.doc_id} p.{citation.page_no}"
    return f"{label} ({citation.pdf_href})" if citation.pdf_href else label


def render_answer(answer: Answer) -> str:
    """Return the printable answer."""
    if not answer.answered:
        return answer.message
    lines: list[str] = []
    for sentence in answer.sentences:
        mark = "supported" if sentence.supported else "not supported"
        lines.append(f"[{mark}] {sentence.text}")
        lines.extend(f"    - {citation_label(citation)}" for citation in sentence.citations)
        if sentence.note:
            lines.append(f"    ! {sentence.note}")
    return "\n".join(lines)
