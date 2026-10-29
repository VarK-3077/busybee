"""Check that rendered Lean fragments are well formed and compile in the project."""

import pytest

from busybee.lean import templates
from busybee.lean.compile import compile_file
from busybee.lean.toolchain import find_lake, find_lean

pytestmark = pytest.mark.skipif(
    find_lean() is None or find_lake() is None,
    reason="Lean toolchain is not installed",
)


def test_file_header_puts_imports_before_the_module_doc() -> None:
    header = templates.file_header(["BusyBee.Common"], "Generated file.")
    assert header.startswith("import BusyBee.Common")
    assert header.index("import BusyBee.Common") < header.index("/-!")


def test_fact_def_keeps_provenance_on_the_same_line() -> None:
    rendered = templates.fact_def("netDebt", 125000, "F012 D1:p214:c2", doc="Net debt.")
    assert "/-- Net debt. -/" in rendered
    assert "def netDebt : Int := 125000 -- F012 D1:p214:c2" in rendered


def test_join_drops_empty_fragments_and_ends_with_newline() -> None:
    assert templates.join(["a", "", "b"]) == "a\n\nb\n"


async def test_templates_produce_compilable_source(tmp_path) -> None:
    source = templates.join(
        [
            templates.file_header(["BusyBee.Common"], "Generated test file."),
            templates.section("Facts"),
            templates.fact_def("netDebt", 125000, "F012 D1:p214:c2", doc="Net debt."),
            templates.fact_def("ebitda", 42000, "F013 D1:p214:c2", doc="EBITDA."),
            templates.section("Checks"),
            templates.theorem(
                "leverage_within_limit",
                "2 * netDebt ≤ 7 * ebitda",
                "decide",
                doc="Within the leverage limit.",
            ),
            templates.eval_line("netDebt"),
        ]
    )
    path = tmp_path / "generated.lean"
    path.write_text(source, encoding="utf-8")
    result = await compile_file(path)
    assert result.ok, result.stderr
    assert result.errors == []
    assert "125000" in result.stdout
