"""Tests for locating the elan toolchain and reading its version."""

import re

from busybee.lean.toolchain import find_lake, find_lean, toolchain_version


def test_find_lean_and_lake_are_available() -> None:
    assert find_lean() is not None
    assert find_lake() is not None


def test_toolchain_version_reports_the_pinned_release() -> None:
    version = toolchain_version()
    assert version.startswith("Lean (version ")
    assert re.search(r"\b4\.\d+\.\d+\b", version)
