"""Split a Lean source file into `-- SECTION:` groups and their declarations."""

import re
from dataclasses import dataclass, field

_DECLARATION = re.compile(
    r"^(?P<kind>def|theorem|lemma|inductive|structure|abbrev)\s+"
    r"(?P<name>[A-Za-z_][A-Za-z0-9_'.]*)",
)
_SECTION = re.compile(r"^\s*--\s*SECTION:\s*(?P<title>.*?)\s*$")
_COMMAND = ("end", "namespace", "open", "section", "variable", "set_option", "#")


@dataclass
class ParsedDeclaration:
    """One declaration found in a Lean section."""

    name: str
    kind: str
    doc: str
    signature: str
    body: str
    lean: str


@dataclass
class ParsedSection:
    """A `-- SECTION:` group and the declarations it contains."""

    title: str
    declarations: list[ParsedDeclaration] = field(default_factory=list)


def _doc_comment_before(lines: list[str], index: int) -> str:
    """Return the `/-- ... -/` doc comment immediately before a declaration, if any."""
    cursor = index - 1
    while cursor >= 0 and not lines[cursor].strip():
        cursor -= 1
    if cursor < 0 or not lines[cursor].rstrip().endswith("-/"):
        return ""
    end = cursor
    start = cursor
    while start >= 0 and "/--" not in lines[start]:
        start -= 1
    if start < 0 or "/-!" in lines[start]:
        return ""
    block = "\n".join(lines[start : end + 1])
    inner = block.split("/--", 1)[1].rsplit("-/", 1)[0]
    return " ".join(inner.split())


def _declaration_end(lines: list[str], start: int) -> int:
    """Return the line index where the declaration beginning at start ends."""
    for index in range(start + 1, len(lines)):
        line = lines[index]
        stripped = line.strip()
        if _SECTION.match(line) or _DECLARATION.match(line):
            return index
        if line.startswith(("/--", "/-!", "--")):
            return index
        if not line.startswith((" ", "\t")) and stripped.startswith(_COMMAND):
            return index
    return len(lines)


def _split_signature_body(text: str) -> tuple[str, str]:
    """Split a declaration at its first `:=` or `where` keyword."""
    match = re.search(r":=|\bwhere\b", text)
    if match is None:
        return text.strip(), ""
    return text[: match.start()].strip(), text[match.end() :].strip()


def parse_sections(source: str) -> list[ParsedSection]:
    """Parse source into sections and declarations, ignoring imports and commands."""
    lines = source.splitlines()
    sections: list[ParsedSection] = []
    current = ParsedSection(title="Overview")
    index = 0
    while index < len(lines):
        marker = _SECTION.match(lines[index])
        if marker is not None:
            if current.declarations:
                sections.append(current)
            current = ParsedSection(title=marker.group("title"))
            index += 1
            continue
        declaration = _DECLARATION.match(lines[index])
        if declaration is not None:
            end = _declaration_end(lines, index)
            text = "\n".join(lines[index:end]).rstrip()
            signature, body = _split_signature_body(text)
            current.declarations.append(
                ParsedDeclaration(
                    name=declaration.group("name"),
                    kind=declaration.group("kind"),
                    doc=_doc_comment_before(lines, index),
                    signature=signature,
                    body=body,
                    lean=text,
                )
            )
            index = end
            continue
        index += 1
    if current.declarations:
        sections.append(current)
    return sections
