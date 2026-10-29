"""Compact reply formats: minified-JSON instruction, short extract keys, and token savings.

`old_format_replies.json` holds replies recorded in the old verbose format (trimmed copies of
workspace/indoco-v3/llm_log.jsonl). Each is re-rendered in the new format and both are counted
with `count_tokens`; the new one must be clearly smaller and parse to the same model.
"""

import json
from pathlib import Path
from typing import Any

from busybee.extract.prompts import SYSTEM_PROMPT, WindowOutput
from busybee.llm import Message, Role, count_tokens
from busybee.llm.provider import messages_with_schema, schema_instruction
from busybee.verify.conflicts import ConflictJudgement
from busybee.verify.entailment import EntailmentReply
from busybee.verify.relevance import DROP_REASONS, RelevanceReply

OLD = json.loads((Path(__file__).parent / "old_format_replies.json").read_text())


def minified(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def verbose(value: Any) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False)


def compact_extract(old: dict[str, Any]) -> str:
    entries = []
    for entry in old["entries"]:
        item: dict[str, Any] = {"s": entry["statement"], "c": entry["chunk_ids"]}
        if entry.get("category", "other") != "other":
            item["cat"] = entry["category"]
        if entry.get("kind", "fact") != "fact":
            item["k"] = entry["kind"]
        if entry.get("importance", 3) != 3:
            item["i"] = entry["importance"]
        entries.append(item)
    return minified({"entries": entries})


def compact_entailment(old: dict[str, Any]) -> str:
    return minified({"v": old["verdict"], "q": old["quote"][:160]})


def compact_relevance(old: dict[str, Any]) -> str:
    drops = [[d["entry_id"], "trivia"] for d in old["decisions"] if not d["keep"]]
    return minified({"drop": drops})


def compact_conflict(old: dict[str, Any]) -> str:
    rows = [
        {"id": r["pair"], "conflict": r["conflict"], "metric": r["metric"]} for r in old["results"]
    ]
    return minified({"r": rows})


def test_schema_instruction_demands_minified_single_line_json() -> None:
    text = schema_instruction({"type": "object"})
    assert "minified" in text and "single line" in text and "no indentation" in text
    assert "Markdown code fences" in text


def test_instruction_is_appended_to_every_structured_call() -> None:
    prepared = messages_with_schema([Message(role=Role.user, content="hi")], {"type": "object"})
    assert prepared[0].role == Role.system and "minified" in prepared[0].content


def test_extract_schema_uses_short_keys_and_parses_both_spellings() -> None:
    schema = json.dumps(WindowOutput.model_json_schema())
    for key in ('"s"', '"c"', '"cat"', '"k"', '"i"', '"sup"', '"m"', '"pv"', '"pp"', '"sc"'):
        assert key in schema
    assert '"statement"' not in schema and '"chunk_ids"' not in schema
    short = WindowOutput.model_validate_json(
        '{"entries":[{"s":"A.","c":["D1:p1:c0"],"cat":"revenue","k":"number","i":4,"sup":"E1"}],'
        '"records":[{"m":"Revenue","v":"1,845.3","u":"crore","p":"FY25","sc":"consolidated",'
        '"q":"restated","pv":"1,700","pp":"FY24","c":["D1:p1:c0"],"i":5}]}'
    )
    full = WindowOutput.model_validate(
        {
            "entries": [
                {
                    "statement": "A.",
                    "chunk_ids": ["D1:p1:c0"],
                    "category": "revenue",
                    "kind": "number",
                    "importance": 4,
                    "supersedes": "E1",
                }
            ],
            "records": [
                {
                    "metric": "Revenue",
                    "value": "1,845.3",
                    "unit": "crore",
                    "period": "FY25",
                    "scope": "consolidated",
                    "qualifier": "restated",
                    "previous_value": "1,700",
                    "previous_period": "FY24",
                    "chunk_ids": ["D1:p1:c0"],
                    "importance": 5,
                }
            ],
        }
    )
    assert short == full
    assert short.entries[0].statement == "A." and short.records[0].previous_period == "FY24"


def test_extract_prompt_shows_one_compact_example_line() -> None:
    example = next(line for line in SYSTEM_PROMPT.splitlines() if line.startswith('{"entries"'))
    parsed = WindowOutput.model_validate_json(example)
    assert parsed.entries[0].chunk_ids == ["D1:p12:c3"]
    assert ", " not in example and ": " not in example


def test_recorded_old_extract_reply_still_parses() -> None:
    parsed = WindowOutput.model_validate(OLD["extract"])
    again = WindowOutput.model_validate_json(compact_extract(OLD["extract"]))
    assert [e.statement for e in parsed.entries] == [e.statement for e in again.entries]
    assert [e.importance for e in parsed.entries] == [e.importance for e in again.entries]


def test_new_formats_parse_to_the_internal_models() -> None:
    assert EntailmentReply.model_validate_json(compact_entailment(OLD["verify_entailment"]))
    drop = RelevanceReply.model_validate_json(compact_relevance(OLD["verify_relevance"]))
    assert all(code in DROP_REASONS for _, code in drop.drop)
    judged = ConflictJudgement.model_validate_json(compact_conflict(OLD["verify_conflict"]))
    assert [r.pair for r in judged.results] == [1, 2, 3, 4, 5]


def test_new_formats_are_much_smaller_than_the_recorded_old_ones(capsys: Any) -> None:
    pairs = {
        "extract": (verbose(OLD["extract"]), compact_extract(OLD["extract"])),
        "entailment": (
            minified(OLD["verify_entailment"]),
            compact_entailment(OLD["verify_entailment"]),
        ),
        "relevance": (verbose(OLD["verify_relevance"]), compact_relevance(OLD["verify_relevance"])),
        "conflict": (verbose(OLD["verify_conflict"]), compact_conflict(OLD["verify_conflict"])),
    }
    ratios = {}
    with capsys.disabled():
        for name, (old, new) in pairs.items():
            before, after = count_tokens(old), count_tokens(new)
            ratios[name] = after / before
            print(f"\n{name}: {before} -> {after} tokens ({after / before:.0%})", end="")
    assert ratios["extract"] < 0.8
    assert ratios["entailment"] < 0.6
    assert ratios["relevance"] < 0.25
    assert ratios["conflict"] < 0.3
    assert count_tokens(schema_instruction(WindowOutput.model_json_schema())) > 0
