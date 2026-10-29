"""Rule input formatting, table structure the paginator relies on, and a headless split check."""

import re
import shutil
import subprocess
from decimal import Decimal
from pathlib import Path

import pytest

from busybee.render.sections import rules_table_html
from busybee.render.statements import format_input, rule_lean_record, slot_index
from busybee.schema.policy import (
    BoundInput,
    InputSlot,
    RuleOutcome,
    RuleResult,
    RuleStatus,
    ScoreSpec,
)

FIXTURE = Path(__file__).parent / "fixtures" / "paginate_table.html"
SPECS = {
    "s": ScoreSpec(
        score_id="s",
        name="S",
        inputs=[
            InputSlot(slot="ebitda", unit="INR crore x 100", scale=100),
            InputSlot(slot="icr", unit="x", scale=100),
            InputSlot(slot="growth", unit="%", scale=100),
            InputSlot(slot="red_flags", unit="count", scale=1),
        ],
    )
}


def bound(slot: str, value: str, scaled: int, unit: str) -> BoundInput:
    return BoundInput(slot=slot, fact_id="F1", value=Decimal(value), unit=unit, value_scaled=scaled)


def test_inputs_use_label_and_display_unit() -> None:
    slots = slot_index(SPECS)
    assert (
        format_input(bound("ebitda", "14181.82", 14182, "INR lakh"), slots) == "EBITDA 141.82 crore"
    )
    assert format_input(bound("icr", "1.2", 125, ""), slots) == "ICR 1.25x"
    assert format_input(bound("growth", "9", 950, ""), slots) == "Growth 9.50%"
    assert format_input(bound("red_flags", "2", 2, "count"), slots) == "Red flags 2"
    assert format_input(bound("mystery", "3", 3, "u"), slots) == "Mystery 3 u"


def make_rule() -> RuleResult:
    return RuleResult(
        rule_id="r",
        name="R",
        status=RuleStatus.fail,
        outcome=RuleOutcome.refer,
        inputs=[bound("ebitda", "14181.82", 14182, "INR lakh")],
    )


def test_table_html_and_popover_show_display_values() -> None:
    slots = slot_index(SPECS)
    html = str(rules_table_html([make_rule()], slots))
    assert "EBITDA 141.82 crore" in html
    assert "lakh" not in html
    record = rule_lean_record(make_rule(), {}, slots)
    assert record["bindings"][0]["display"] == "141.82 crore"


def test_table_has_thead_and_tbody_for_the_paginator() -> None:
    html = str(rules_table_html([make_rule()] * 3))
    assert html.count("<thead>") == 1
    assert html.count("<tbody>") == 1
    assert html.index("<thead>") < html.index("<tbody>")
    assert len(re.findall(r"<tbody>.*</tbody>", html, re.S)) == 1
    assert html.count('class="bb-rule ') == 3


@pytest.mark.skipif(shutil.which("chromium") is None, reason="chromium not on PATH")
def test_rule_table_splits_across_two_sheets_with_repeated_head() -> None:
    dom = subprocess.run(
        [
            "chromium",
            "--headless=new",
            "--disable-gpu",
            "--no-sandbox",
            "--allow-file-access-from-files",
            "--virtual-time-budget=3000",
            "--dump-dom",
            FIXTURE.as_uri(),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=True,
    ).stdout
    sheets = re.findall(r'<section class="bb-page bb-sheet".*?</section>', dom, re.S)
    with_table = [sheet for sheet in sheets if "<table" in sheet]
    assert len(with_table) >= 2
    assert all("<thead" in sheet for sheet in with_table)
    assert dom.count('id="rules"') == 1
    assert sum(len(re.findall(r"<tr class=\"bb-rule[ \"]", sheet)) for sheet in with_table) == 12
