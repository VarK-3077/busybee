"""Verify relevance and citations, re-cite where possible, and drop the rest."""

from .assign_ids import assign_fact_ids
from .conflicts import (
    detect_and_resolve_conflicts,
    find_conflict_candidates,
    is_conflicted,
    undo_conflicts_involving,
)
from .dedupe import dedupe_facts
from .number_match import extract_numbers, statement_numbers_supported
from .rescue import rescue_dropped
from .run_verify import run_verify
from .verify_entries import VerifyContext, verify_entries

__all__ = [
    "VerifyContext",
    "assign_fact_ids",
    "dedupe_facts",
    "detect_and_resolve_conflicts",
    "find_conflict_candidates",
    "is_conflicted",
    "undo_conflicts_involving",
    "extract_numbers",
    "rescue_dropped",
    "run_verify",
    "statement_numbers_supported",
    "verify_entries",
]
