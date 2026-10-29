"""Tests for source hashing, theorem extraction, artifacts, and project paths."""

import re
import shutil

from busybee.lean.artifact import make_artifact, theorem_names
from busybee.lean.hash import sha256_text
from busybee.lean.project import camel_bank_id, project_dir, runs_dir
from busybee.schema.lean import CompileResult, LeanArtifactKind


def test_sha256_text_matches_a_known_digest() -> None:
    assert sha256_text("abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_theorem_names_are_unique_and_in_order() -> None:
    source = """theorem first : True := by trivial
lemma second : True := by trivial
theorem first : True := by trivial
def not_a_theorem : Int := 1
"""
    assert theorem_names(source) == ["first", "second"]


def test_make_artifact_fills_hash_kind_and_theorems() -> None:
    source = "theorem leverage_limit : 2 ≤ 3 := by decide\n"
    compile_result = CompileResult(ok=True, stdout="", stderr="")
    artifact = make_artifact(
        "run-1:leverage",
        "scores",
        "lean/Runs/run-1/Scores.lean",
        source,
        compile_result,
    )
    assert artifact.kind == LeanArtifactKind.scores
    assert artifact.sha256 == sha256_text(source)
    assert artifact.theorems == ["leverage_limit"]
    assert artifact.compile is compile_result


def test_project_dir_contains_the_pinned_toolchain() -> None:
    root = project_dir()
    assert (root / "lakefile.toml").is_file()
    pin = (root / "lean-toolchain").read_text(encoding="utf-8").strip()
    assert re.fullmatch(r"leanprover/lean4:v4\.\d+\.\d+", pin)


def test_runs_dir_is_created_under_the_project() -> None:
    target = runs_dir("test-run")
    try:
        assert target.is_dir()
        assert target.parent == project_dir() / "Runs"
    finally:
        shutil.rmtree(target, ignore_errors=True)


def test_camel_bank_id_produces_a_lean_identifier() -> None:
    assert camel_bank_id("demo_bank") == "DemoBank"
    assert camel_bank_id("tata-capital") == "TataCapital"
    assert camel_bank_id("123_bank") == "Bank123Bank"
