"""Render a parsed Lean declaration as a best-effort English sentence."""

import re

from busybee.lean.explain.parse import ParsedDeclaration

_OPERATORS = (
    ("≤", "is at most"),
    ("≥", "is at least"),
    ("<", "is less than"),
    (">", "is greater than"),
    ("*", "times"),
    ("+", "plus"),
    ("-", "minus"),
    ("=", "equals"),
    ("∧", "and"),
    ("∨", "or"),
    ("¬", "not"),
    ("→", "implies"),
)
_KEYWORDS = {"if", "then", "else", "by", "Int", "Prop", "Bool", "true", "false", "where"}


def _space_identifier(name: str) -> str:
    """Turn snake_case and camelCase identifiers into spaced lowercase words."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    words = spaced.replace("_", " ").replace("'", "").split()
    rendered = [
        word
        if word.isupper() or not any(character.islower() for character in word)
        else word[:1].lower() + word[1:]
        for word in words
    ]
    return " ".join(rendered)


def _space_identifiers(text: str) -> str:
    """Space out every identifier in text while leaving Lean keywords alone."""

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        return word if word in _KEYWORDS else _space_identifier(word)

    return re.sub(r"[A-Za-z_][A-Za-z0-9_']*", replace, text)


def _render(text: str) -> str:
    """Replace Lean operators with words and normalise whitespace."""
    without_comments = re.sub(r"--.*$", "", text, flags=re.MULTILINE)
    rendered = without_comments
    for symbol, words in _OPERATORS:
        rendered = rendered.replace(symbol, f" {words} ")
    rendered = _space_identifiers(rendered)
    return re.sub(r"\s+", " ", rendered).strip()


def _conclusion(signature: str) -> str:
    """Return the type or statement after the last top-level colon."""
    depth = 0
    last_colon = -1
    for index, character in enumerate(signature):
        if character in "([{":
            depth += 1
        elif character in ")]}":
            depth = max(0, depth - 1)
        elif character == ":" and depth == 0:
            if index + 1 < len(signature) and signature[index + 1] == ":":
                continue
            last_colon = index
    return signature[last_colon + 1 :].strip() if last_colon >= 0 else signature.strip()


def _constructors(body: str) -> list[str]:
    """Return the constructor names from an inductive declaration body."""
    names = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            rest = stripped[1:].strip()
            if rest:
                names.append(_space_identifier(rest.split()[0]))
    return names


def _fields(body: str) -> list[str]:
    """Return the field names from a structure declaration body."""
    names = []
    for line in body.splitlines():
        stripped = line.strip()
        if stripped and ":" in stripped and not stripped.startswith("|"):
            name = stripped.split(":", 1)[0].strip()
            if name:
                names.append(_space_identifier(name))
    return names


_FACT_COMMENT = re.compile(r"--\s*(F\d+\b.*)$", re.MULTILINE)
_SCALED_LITERAL = re.compile(r"-?\d+")


def _provenance(text: str) -> str:
    """Return ', from fact F007 (D1:p2:c0)' for a `-- F### chunk…` comment, else ''."""
    match = _FACT_COMMENT.search(text)
    if match is None:
        return ""
    facts: list[str] = []
    for token in match.group(1).split(" | ", 1)[0].split():
        if re.fullmatch(r"F\d+", token):
            facts.append(f"{token} (")
        elif facts:
            facts[-1] += (", " if not facts[-1].endswith("(") else "") + token
    if not facts:
        return ""
    rendered = [f"{fact})" for fact in facts]
    noun = "fact" if len(rendered) == 1 else "facts"
    joined = (
        rendered[0] if len(rendered) == 1 else ", ".join(rendered[:-1]) + " and " + rendered[-1]
    )
    return f", from {noun} {joined}"


def english_for(declaration: ParsedDeclaration) -> str:
    """Return the mechanical reading of a declaration (the doc comment is shown separately)."""
    name = _space_identifier(declaration.name)
    kind = declaration.kind
    if kind in {"theorem", "lemma"}:
        return f"{name}: {_render(_conclusion(declaration.signature))}"
    if kind in {"def", "abbrev"}:
        body = _render(declaration.body) or _render(_conclusion(declaration.signature))
        scaled = " (scaled)" if _SCALED_LITERAL.fullmatch(body) else ""
        return f"{name} is defined as {body}{scaled}{_provenance(declaration.body)}"
    if kind == "inductive":
        constructors = _constructors(declaration.body)
        if constructors:
            return f"{name} is a type with constructors {', '.join(constructors)}"
    if kind == "structure":
        fields = _fields(declaration.body)
        if fields:
            return f"{name} is a structure with fields {', '.join(fields)}"
    return f"{name} is declared as {_render(declaration.signature)}"
