"""Build Lean artifact records and extract the theorem names a source declares."""

import re
from pathlib import Path

from busybee.lean.hash import sha256_text
from busybee.schema.lean import CompileResult, LeanArtifact, LeanArtifactKind

_THEOREM = re.compile(
    r"^\s*(?:theorem|lemma)\s+([A-Za-z_][A-Za-z0-9_'.]*)",
    re.MULTILINE,
)


def theorem_names(source: str) -> list[str]:
    """Return theorem and lemma names in source order, without duplicates."""
    return list(dict.fromkeys(_THEOREM.findall(source)))


def make_artifact(
    artifact_id: str,
    kind: str | LeanArtifactKind,
    path: str | Path,
    source: str,
    compile: CompileResult | None,
) -> LeanArtifact:
    """Assemble a LeanArtifact with its hash, theorem names, and compile result."""
    return LeanArtifact(
        artifact_id=artifact_id,
        kind=LeanArtifactKind(kind),
        file_path=str(path),
        source=source,
        sha256=sha256_text(source),
        theorems=theorem_names(source),
        compile=compile,
    )
