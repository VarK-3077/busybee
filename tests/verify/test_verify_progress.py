"""Verify checkpointing: a crash mid-stage keeps finished entries, and the re-run skips them."""

import re
from pathlib import Path
from typing import Any

import pytest

from busybee.ingest.corpus_store import write_corpus
from busybee.llm import Completion, Message
from busybee.schema.documents import Document, DocumentKind, Page
from busybee.schema.facts import NotebookEntry, VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.run import RunConfig
from busybee.verify.progress import PROGRESS_FILE, load_progress
from busybee.verify.run_verify import run_verify

from .helpers import judge_provider, make_chunk, make_entry

CHUNK = make_chunk("D1:p1:c0", "Revenue for FY24 was Rs 1,200 crore.")
NAMES = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta"]


class FlakyProvider:
    """Delegates to a scripted judge but raises on entailment calls after `allow` succeed."""

    name = "flaky"
    model = "flaky"

    def __init__(self, allow: int | None) -> None:
        self.inner = judge_provider(supports=lambda statement, passage: True)
        self.allow = allow
        self.entailed: list[str] = []

    async def complete(self, messages: list[Message], **kwargs: Any) -> Completion:
        if kwargs.get("task") == "verify_entailment":
            statement = re.search(r"Statement:\n(.*)\n\nSource passage", messages[-1].content)
            assert statement is not None
            if self.allow is not None and len(self.entailed) >= self.allow:
                raise ConnectionError("server down")
            self.entailed.append(statement.group(1))
        return await self.inner.complete(messages, **kwargs)


def read_models_entries(tmp_path: Path) -> list[NotebookEntry]:
    return read_models(tmp_path / "notebook.json", NotebookEntry)


def prepare(tmp_path: Path) -> RunConfig:
    document = Document(
        doc_id="D1",
        title="AR",
        kind=DocumentKind.annual_report,
        source_path="x",
        sha256="0",
        num_pages=1,
    )
    write_corpus(
        tmp_path, [document], {"D1": [Page(doc_id="D1", page_no=1, text=CHUNK.text)]}, [CHUNK]
    )
    entries = [
        make_entry(f"E{i}", f"Revenue for FY24 was Rs 1,200 crore ({name})")
        for i, name in enumerate(NAMES)
    ]
    write_models_atomic(tmp_path / "notebook.json", entries)
    return RunConfig(
        run_id="r", docs_dir=tmp_path, bank_id="b", out_dir=tmp_path, workspace_dir=tmp_path
    )


async def test_rerun_after_a_crash_skips_finished_entries(tmp_path: Path) -> None:
    cfg = prepare(tmp_path)
    first = FlakyProvider(allow=3)

    with pytest.raises(ConnectionError):
        await run_verify(tmp_path, cfg, first)

    progress = tmp_path / PROGRESS_FILE
    assert len(first.entailed) == 3
    assert len(load_progress(progress, read_models_entries(tmp_path))) == 3
    assert not (tmp_path / "verified_facts.json").exists()

    second = FlakyProvider(allow=None)
    facts = await run_verify(tmp_path, cfg, second)

    assert len(second.entailed) == 3
    assert set(first.entailed).isdisjoint(second.entailed)
    assert len(facts) == 1
    assert facts[0].verification.notes.count("merged duplicate") == 5
    assert len(read_models(tmp_path / "verified_facts.json", VerifiedFact)) == 1
    assert not progress.exists()


async def test_truncated_last_line_and_changed_entries_are_ignored(tmp_path: Path) -> None:
    cfg = prepare(tmp_path)
    with pytest.raises(ConnectionError):
        await run_verify(tmp_path, cfg, FlakyProvider(allow=2))
    progress = tmp_path / PROGRESS_FILE
    with progress.open("a", encoding="utf-8") as handle:
        handle.write('{"entry_id": "E5", "finger')
    entries = read_models_entries(tmp_path)
    entries[0] = make_entry("E0", "Revenue for FY24 was Rs 1,200 crore (changed)")

    assert len(load_progress(progress, read_models_entries(tmp_path))) == 2
    assert "E0" not in load_progress(progress, entries)
