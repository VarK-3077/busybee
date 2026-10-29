"""Compile a good and a bad Lean file and check error parsing and #eval output."""

import pytest

from busybee.lean.compile import compile_file
from busybee.lean.toolchain import find_lake, find_lean

pytestmark = pytest.mark.skipif(
    find_lean() is None or find_lake() is None,
    reason="Lean toolchain is not installed",
)


async def test_good_file_compiles_and_eval_output_is_captured(tmp_path) -> None:
    path = tmp_path / "good.lean"
    path.write_text(
        "import BusyBee.Common\n\ndef answer : Int := 40 + 2\n\n#eval answer\n",
        encoding="utf-8",
    )
    result = await compile_file(path)
    assert result.ok
    assert result.errors == []
    assert "42" in result.stdout
    assert result.duration_s >= 0
    assert result.toolchain.startswith("Lean (version ")


async def test_bad_file_reports_line_and_column(tmp_path) -> None:
    path = tmp_path / "bad.lean"
    path.write_text("def broken : Int := missingThing\n", encoding="utf-8")
    result = await compile_file(path)
    assert not result.ok
    assert result.errors
    first = result.errors[0]
    assert first.line == 1
    assert first.col > 0
    assert "missingThing" in first.message


async def test_missing_file_fails_cleanly(tmp_path) -> None:
    result = await compile_file(tmp_path / "absent.lean")
    assert not result.ok
    assert "not found" in result.stderr
