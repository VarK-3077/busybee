"""Lean compilation results, artifacts, and the manual explanation structures."""

from enum import StrEnum

from pydantic import BaseModel, Field


class LeanArtifactKind(StrEnum):
    """The three kinds of Lean file the pipeline generates."""

    policy = "policy"
    scores = "scores"
    inference = "inference"


class LeanError(BaseModel):
    """One parsed Lean compiler error."""

    line: int
    col: int
    message: str


class CompileResult(BaseModel):
    """The outcome of compiling one Lean file."""

    ok: bool = False
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    toolchain: str = ""
    errors: list[LeanError] = Field(default_factory=list)


class LeanArtifact(BaseModel):
    """A generated Lean source file, its hash, and its compilation result."""

    artifact_id: str
    kind: LeanArtifactKind
    file_path: str = ""
    source: str = ""
    sha256: str = ""
    theorems: list[str] = Field(default_factory=list)
    compile: CompileResult | None = None


class ExplainItem(BaseModel):
    """One def or theorem rendered for the human-facing Lean page."""

    name: str
    kind: str = ""
    lean: str = ""
    english: str = ""
    doc: str = ""


class ExplainSection(BaseModel):
    """A titled group of explained Lean declarations."""

    title: str
    items: list[ExplainItem] = Field(default_factory=list)


class LeanExplanation(BaseModel):
    """The complete manual explanation of a Lean source file."""

    sections: list[ExplainSection] = Field(default_factory=list)
