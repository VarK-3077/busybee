"""The extraction prompt carries the policy checklist and the relevance instruction."""

import json
from pathlib import Path

from busybee.extract.aids import ReadingAids
from busybee.extract.policy_focus import build_checklist, load_policy_focus
from busybee.extract.prompts import SYSTEM_PROMPT, system_prompt
from busybee.extract.segmented import extract_segmented
from busybee.llm import MockProvider, Role
from busybee.policy.bank_fs import load_bank
from busybee.schema.documents import Chunk, Document, DocumentKind
from busybee.schema.run import RunConfig

BANKS = Path(__file__).parents[2] / "banks"


def test_checklist_lists_inputs_rules_rating_and_red_flags() -> None:
    text = build_checklist(load_bank(BANKS, "demo_bank"))
    for phrase in (
        "Gross finance cost",
        "Revenue from operations",
        "cash and bank balances",
        "Net debt / EBITDA at most 4.5x",
        "External rating grade, outlook",
        "Red-flag and default evidence",
        "wilful",
    ):
        assert phrase in text
    assert len(text) < 4000


def test_system_prompt_appends_the_checklist_and_tells_the_model_what_to_skip() -> None:
    assert system_prompt() == SYSTEM_PROMPT
    assert system_prompt("Checklist: X").endswith("Checklist: X")
    for phrase in ("Write only facts that bear on the credit decision", "CSR", "governance trivia"):
        assert phrase in SYSTEM_PROMPT


async def test_every_window_call_carries_the_checklist(tmp_path: Path) -> None:
    focus = load_policy_focus(BANKS, "demo_bank")
    assert focus is not None
    chunks = [
        Chunk(chunk_id=f"D1:p{n}:c0", doc_id="D1", page_no=n, index_in_page=0, text=f"Page {n}.")
        for n in (1, 2, 3, 4)
    ]
    provider = MockProvider({"extract": [json.dumps({"entries": []})] * 8})
    cfg = RunConfig(
        run_id="t",
        docs_dir=tmp_path,
        bank_id="demo_bank",
        out_dir=tmp_path,
        workspace_dir=tmp_path,
        window_tokens=3,
        segment_min_windows=2,
        concurrency=2,
    )
    docs = [Document(doc_id="D1", title="AR", kind=DocumentKind.annual_report)]
    await extract_segmented(docs, {"D1": chunks}, cfg, provider, aids=ReadingAids(focus=focus))
    systems = [
        next(m.content for m in call.messages if m.role is Role.system)
        for call in provider.calls
        if call.task == "extract"
    ]
    assert len(systems) >= 2 and all(focus.checklist in system for system in systems)
    plain = MockProvider({"extract": [json.dumps({"entries": []})] * 8})
    await extract_segmented(docs, {"D1": chunks}, cfg, plain)
    assert plain.calls and all(
        "Credit-policy checklist" not in call.messages[0].content
        for call in plain.calls
        if call.task == "extract"
    )


def test_checklist_names_qualitative_topics_and_has_no_must_extract_block() -> None:
    text = build_checklist(load_bank(BANKS, "demo_bank"))
    assert "MUST EXTRACT" not in text
    for phrase in (
        "warning letters",
        "DSCR",
        "emphasis of matter",
        "CARO",
        "monetisation",
        "Working capital",
        "Latest quarter",
    ):
        assert phrase in text
