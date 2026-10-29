"""Tests for splitting policy.md into stably numbered, citable sections."""

from pathlib import Path

from busybee.policy.policy_sections import load_policy_sections, split_policy_sections

POLICY = """# Bank — Policy

Version 1.0.

## 1. Purpose

Sets the standard.

```
# not a heading
```

### 1.1 Detail

More text.
"""


def test_sections_are_split_at_headings_with_sequential_ids() -> None:
    sections = split_policy_sections(POLICY)

    assert [s.section_id for s in sections] == ["P1", "P2", "P3"]
    assert [s.heading for s in sections] == ["Bank — Policy", "1. Purpose", "1.1 Detail"]
    assert sections[0].text == "Version 1.0."
    assert "# not a heading" in sections[1].text


def test_text_before_first_heading_becomes_a_preamble() -> None:
    sections = split_policy_sections("Intro line.\n\n## A\n\nBody.")

    assert [s.heading for s in sections] == ["Preamble", "A"]


def test_load_policy_sections_reads_the_bank_and_tolerates_absence(tmp_path: Path) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "policy.md").write_text(POLICY, encoding="utf-8")

    assert len(load_policy_sections(tmp_path, "b")) == 3
    assert load_policy_sections(tmp_path, "missing") == []
