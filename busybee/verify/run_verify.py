"""Run the verify stage over a workspace.

Reads `notebook.json` (and the corpus and vector index written by ingest and index), verifies
every entry with `verify_entries`, merges duplicate facts (`dedupe_facts`), numbers the
surviving facts F001... in notebook order, and writes `verified_facts.json`. Entries that were
dropped are appended to any existing `dropped.json` (the extract stage may already have
written some), skipping exact repeats so that a resumed run does not duplicate records.
Each entry's outcome is checkpointed in `verify_progress.jsonl` as it completes (see
progress.py), so a re-run after a crash skips the finished entries; the file is deleted once the
outputs are written. Finally
`detect_and_resolve_conflicts` marks cross-document conflicts (the lower-authority fact becomes
`conflicted`, kept in verified_facts.json) and writes the open concerns to `conflicts.json`.
"""

import re
from pathlib import Path

from busybee.index import embedder_from_env
from busybee.index.store import VectorStore
from busybee.ingest.corpus_store import load_corpus
from busybee.llm.provider import Provider
from busybee.policy.bank_fs import load_bank
from busybee.policy.bind_inputs import score_input_slots
from busybee.schema.facts import DroppedEntry, NotebookEntry, VerifiedFact
from busybee.schema.io import read_models, write_models_atomic
from busybee.schema.run import RunConfig

from .assign_ids import assign_fact_ids
from .conflicts import detect_and_resolve_conflicts
from .dedupe import dedupe_facts
from .progress import PROGRESS_FILE
from .verify_entries import VerifyContext, verify_entries

CONFLICTS_FILE = "conflicts.json"


def _load_store(workspace: Path) -> VectorStore | None:
    index_dir = workspace / "index"
    if not (index_dir / "vectors.npy").exists():
        return None
    return VectorStore.load(index_dir)


def _merge_dropped(existing: list[DroppedEntry], new: list[DroppedEntry]) -> list[DroppedEntry]:
    seen = {(item.entry.entry_id, item.stage) for item in existing}
    return [*existing, *(item for item in new if (item.entry.entry_id, item.stage) not in seen)]


def policy_inputs_text(banks_dir: str | Path | None, bank_id: str) -> str:
    """One line per fact-backed score input of the bank, or "" when the bank cannot be loaded."""
    if banks_dir is None:
        return ""
    try:
        bank = load_bank(banks_dir, bank_id)
    except (OSError, ValueError):
        return ""
    return "\n".join(
        f"- {slot.slot}: {slot.description}" for spec, slot in score_input_slots(bank.scores)
    )


def policy_input_keywords(banks_dir: str | Path | None, bank_id: str) -> tuple[str, ...]:
    """Lower-case phrases naming the bank's score-input slots: slot names and description heads."""
    if banks_dir is None:
        return ()
    try:
        bank = load_bank(banks_dir, bank_id)
    except (OSError, ValueError):
        return ()
    phrases: set[str] = set()
    for _, slot in score_input_slots(bank.scores):
        phrases.add(slot.slot.replace("_", " ").casefold())
        head = re.split(r"[,:;(]", slot.description, maxsplit=1)[0].casefold().strip()
        if 0 < len(head.split()) <= 4:
            phrases.add(head)
    return tuple(sorted(phrases))


async def run_verify(
    workspace_dir: str | Path,
    cfg: RunConfig,
    provider: Provider,
    banks_dir: str | Path | None = None,
) -> list[VerifiedFact]:
    """Verify the notebook, write verified_facts.json and dropped.json, return the facts.

    With banks_dir the bank's score input descriptions are shown to the relevance filter so
    entries that feed a score are never dropped as minor.
    """
    workspace = Path(workspace_dir)
    entries = read_models(workspace / "notebook.json", NotebookEntry)
    corpus = load_corpus(workspace)
    store = _load_store(workspace)
    ctx = VerifyContext(
        provider=provider,
        chunks_by_id=corpus.chunks_by_id,
        store=store,
        embedder=embedder_from_env() if store is not None else None,
        doc_titles={document.doc_id: document.title for document in corpus.documents},
        required_inputs=policy_inputs_text(banks_dir, cfg.bank_id),
        doc_kinds={document.doc_id: document.kind for document in corpus.documents},
        score_keywords=policy_input_keywords(banks_dir, cfg.bank_id),
    )
    facts, dropped = await verify_entries(entries, ctx, progress_path=workspace / PROGRESS_FILE)
    numbered = assign_fact_ids(dedupe_facts(facts))
    outcome = await detect_and_resolve_conflicts(numbered, corpus.documents, provider)
    numbered = outcome.facts
    dropped_path = workspace / "dropped.json"
    existing = read_models(dropped_path, DroppedEntry) if dropped_path.exists() else []
    write_models_atomic(workspace / "verified_facts.json", numbered)
    write_models_atomic(workspace / CONFLICTS_FILE, outcome.concerns)
    write_models_atomic(dropped_path, _merge_dropped(existing, dropped))
    (workspace / PROGRESS_FILE).unlink(missing_ok=True)
    return numbered
