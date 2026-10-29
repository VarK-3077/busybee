"""Parse Lean compiler diagnostics into structured errors."""

import re

from busybee.schema.lean import LeanError

_DIAGNOSTIC = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<col>\d+):\s*"
    r"(?P<severity>error|warning|info)(?:\([^)]*\))?:\s*(?P<message>.*)$"
)


def parse_errors(text: str) -> list[LeanError]:
    """Return every `path:line:col: error: message` diagnostic, including continuations."""
    errors: list[LeanError] = []
    current: LeanError | None = None
    for raw_line in text.splitlines():
        match = _DIAGNOSTIC.match(raw_line)
        if match is not None:
            if match.group("severity") == "error":
                current = LeanError(
                    line=int(match.group("line")),
                    col=int(match.group("col")),
                    message=match.group("message").strip(),
                )
                errors.append(current)
            else:
                current = None
            continue
        if current is not None and raw_line.strip():
            current.message = f"{current.message}\n{raw_line.strip()}".strip()
    return errors
