"""Turn the bank's own run parameters into synthetic verified facts the binder can cite.

`busybee run --proposed-exposure 150 --projected-turnover 1100` (or the matching environment
variables) are figures the borrower's documents cannot contain: they come from the credit
request. This module writes each one into `verified_facts.json` as an ordinary fact, with id
continuing the F sequence, category other, `added_by = bank_input`, and one citation to the
synthetic document "Credit request" (`doc_id` REQ, chunk `REQ:p1:c1`, `source = bank_input`) so
ingest, compose and render need no special case beyond showing a "bank input" chip instead of a
document chip. The merge is idempotent: a fact for the same parameter keeps its id and is
rewritten, one whose parameter was dropped is removed, so re-running the scores stage never
duplicates anything. `bank_input_facts` is pure; `sync_bank_input_facts` does the file work.
"""

import json
from decimal import Decimal
from pathlib import Path

from busybee.schema.facts import (
    Citation,
    FactCategory,
    NumericValue,
    Verification,
    VerificationStatus,
    VerifiedFact,
)
from busybee.schema.ids import make_fact_id
from busybee.schema.io import write_models_atomic
from busybee.schema.run import RunConfig

BANK_INPUT = "bank_input"
REQUEST_DOC_ID = "REQ"
REQUEST_DOC_TITLE = "Credit request"
REQUEST_CHUNK_ID = f"{REQUEST_DOC_ID}:p1:c1"
_PARAMETERS = (
    ("proposed_exposure", "proposed exposure"),
    ("projected_turnover", "projected turnover"),
)


def _crore_text(amount: Decimal) -> str:
    return format(amount.normalize(), "f")


def is_bank_input(fact: VerifiedFact) -> bool:
    """True for a synthetic fact written from a run parameter."""
    return fact.added_by == BANK_INPUT


def _fact(fact_id: str, key: str, label: str, amount: Decimal) -> VerifiedFact:
    statement = f"Bank input: {label} INR {_crore_text(amount)} crore (from the credit request)"
    return VerifiedFact(
        fact_id=fact_id,
        statement=statement,
        category=FactCategory.other,
        citations=[
            Citation(
                chunk_id=REQUEST_CHUNK_ID,
                doc_id=REQUEST_DOC_ID,
                page_no=1,
                quote=statement,
                source=BANK_INPUT,
            )
        ],
        numbers=[NumericValue(label=label, value=amount, unit="INR crore")],
        verification=Verification(
            status=VerificationStatus.supported, method=BANK_INPUT, notes="supplied by the bank"
        ),
        importance=4,
        source_entry_id=f"{BANK_INPUT}:{key}",
        added_by=BANK_INPUT,
    )


def bank_input_facts(cfg: RunConfig, existing: list[VerifiedFact]) -> list[VerifiedFact]:
    """Return `existing` with the run parameters' facts added, updated in place or removed."""
    previous = {fact.source_entry_id: fact for fact in existing if is_bank_input(fact)}
    used = {int(fact.fact_id[1:]) for fact in existing if fact.fact_id[1:].isdigit()}
    next_number = max(used, default=0) + 1
    made: dict[str, VerifiedFact] = {}
    for key, label in _PARAMETERS:
        amount = getattr(cfg, key)
        if amount is None:
            continue
        entry_id = f"{BANK_INPUT}:{key}"
        old = previous.get(entry_id)
        if old is not None:
            fact_id = old.fact_id
        else:
            fact_id, next_number = make_fact_id(next_number), next_number + 1
        made[entry_id] = _fact(fact_id, key, label, amount)
    kept = [
        made.pop(fact.source_entry_id or "", fact) if is_bank_input(fact) else fact
        for fact in existing
        if not is_bank_input(fact) or (fact.source_entry_id or "") in made
    ]
    return [*kept, *made.values()]


def read_all_facts(workspace_dir: Path) -> list[VerifiedFact]:
    """Read verified_facts.json (list, dict, or {"facts": [...]}), conflicted facts included."""
    data = json.loads((Path(workspace_dir) / "verified_facts.json").read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("facts", data)
    items = list(data.values()) if isinstance(data, dict) else data
    return [VerifiedFact.model_validate(item) for item in items]


def sync_bank_input_facts(workspace_dir: Path, cfg: RunConfig) -> None:
    """Rewrite verified_facts.json with the bank input facts, only when something changes."""
    current = read_all_facts(workspace_dir)
    merged = bank_input_facts(cfg, current)
    if [f.model_dump(mode="json") for f in merged] != [f.model_dump(mode="json") for f in current]:
        write_models_atomic(Path(workspace_dir) / "verified_facts.json", merged)
