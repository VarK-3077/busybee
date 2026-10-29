"""What the bank's policy reads, as the extractor needs it: a checklist and an importance rule.

`load_policy_focus(banks_dir, bank_id)` reads the bank (policy.md, scores.yaml) once and returns
a `PolicyFocus`, or None when the bank cannot be loaded. It holds three things.

* `checklist`: a short text for the extraction prompt: score input descriptions, rule names,
  red-flag keywords and one compact line per qualitative topic (regulatory actions, ratings,
  auditor remarks, defaults, asset sales, working capital, interim results); statement line
  items are left to slot search (see `build_checklist`).
* Metric phrases: the lower-case words of every score input slot name, description head,
  `derive_from` component, plus a few statement synonyms (`ALIASES`), as token tuples. A fact
  feeds the policy when its row label (or, for a prose entry, the subject before the first verb)
  contains one of them as consecutive words, plural endings ignored.
* Judge keywords and rating grades: the keywords of every judged slot (default, NPA, qualified,
  pledge, litigation, ...) and the grade keys of every categorical slot (AAA ... D).

`apply_policy_importance(entries, focus)` is the importance rule of the extract stage: 5 for a
fact that feeds a rule, score or judged slot (decided here, never by the model), and the model's
rating capped at 4 for everything else, where 4 is the model's rating of a topic the policy
names (see the extraction prompt) and 3 or lower is the rest. Without a focus entries are
returned unchanged.
"""

import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from busybee.policy.bank_fs import load_bank
from busybee.policy.components import line_items
from busybee.schema.facts import NotebookEntry
from busybee.schema.policy import BankPolicy

logger = logging.getLogger(__name__)

FEEDS_POLICY_IMPORTANCE = 5
TOPIC_IMPORTANCE = 4
SUBJECT_TOKENS = 10
IGNORED_WORDS = frozenset({"gross", "total", "latest", "audited", "year", "the", "for", "at", "of"})
SCOPE_WORDS = frozenset(
    {"consolidated", "standalone", "non", "current", "noncurrent", "long", "term", "short"}
)
LEADING_WORDS = frozenset({"consolidated", "standalone"})
MAX_PHRASE_TAIL = 4
RATIO_WORDS = frozenset({"margin", "ratio", "percentage", "growth", "per", "share", "yield"})
PERIOD_SUFFIXES = ("current", "previous")
QUALITATIVE_TOPICS = (
    "- Regulatory actions: warning letters, adverse inspections, licence suspensions, "
    "penalties (any regulator)",
    "- External rating grade, outlook, watch status and rating history, the agency's metrics "
    "(interest coverage, DSCR) and rationale",
    "- Auditor: qualifications, emphasis of matter, going-concern doubts (also on investees)",
    "- Defaults: delays in repayment, CARO statements on dues, NPA or SMA classification",
    "- Asset sales, monetisation, divestments and acquisitions",
    "- Working capital: intensity, debtor and inventory days",
    "- Latest quarter or half-year results: income, profit, margins",
)
ALIASES: dict[str, tuple[str, ...]] = {
    "cash and bank balances": ("cash and cash equivalents", "bank balances", "cash and bank"),
    "liquid investments": ("current investments", "investments in mutual funds"),
    "total borrowings": ("borrowings", "lease liabilities", "debt"),
    "cash taxes paid": ("income tax paid", "taxes paid", "direct taxes paid"),
    "interest paid": ("interest paid", "finance costs paid"),
    "scheduled principal repayments": ("repayment of borrowings", "repayment of lease"),
    "gross finance cost": ("finance costs", "finance cost", "interest expense"),
    "intangible assets": ("intangible assets", "goodwill"),
    "ebitda": ("operating profit", "profit before depreciation"),
}
_VERB = re.compile(r"\b(?:was|were|is|are|stood|grew|rose|fell|increased|decreased|declined)\b")
_WORD = re.compile(r"[a-z0-9]+")
_HEAD_SPLIT = re.compile(r"[,:;(]")
_NAME_IDENTIFIER = re.compile(r"[a-z_][a-z0-9_]*")


@dataclass(frozen=True)
class PolicyFocus:
    """The bank's policy reduced to what extraction needs."""

    checklist: str
    phrases: frozenset[tuple[str, ...]]
    keywords: tuple[re.Pattern[str], ...]
    grades: tuple[re.Pattern[str], ...] = ()


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(
        word[:-1] if len(word) > 3 and word.endswith("s") else word
        for word in _WORD.findall(text.lower())
    )


def _phrase(text: str) -> tuple[str, ...]:
    return tuple(word for word in _tokens(text) if word not in IGNORED_WORDS)


def _slot_name_phrase(slot: str) -> str:
    words = slot.split("_")
    if len(words) > 1 and words[-1] in PERIOD_SUFFIXES:
        words = words[:-1]
    return " ".join(words)


def _slot_texts(bank: BankPolicy) -> Iterable[str]:
    score_ids = {spec.score_id for spec in bank.scores}
    for spec in bank.scores:
        for slot in spec.inputs:
            if (
                slot.judge is not None
                or slot.mapping
                or slot.run_parameter
                or slot.slot in score_ids
            ):
                continue
            yield _slot_name_phrase(slot.slot)
            head = _HEAD_SPLIT.split(slot.description, maxsplit=1)[0].strip()
            if 0 < len(head.split()) <= 8:
                yield head
            yield from slot.derive_from
            for component in slot.derive_from:
                yield from line_items(component)


def metric_phrases(bank: BankPolicy) -> frozenset[tuple[str, ...]]:
    """Token tuples of every fact-backed slot name, description head, component and alias."""
    aliases = {_phrase(key): values for key, values in ALIASES.items()}
    phrases: set[tuple[str, ...]] = set()
    for text in _slot_texts(bank):
        phrases.add(_phrase(text))
        phrases.update(_phrase(alias) for alias in aliases.get(_phrase(text), ()))
    return frozenset(phrase for phrase in phrases if phrase)


def _keyword_pattern(word: str) -> re.Pattern[str]:
    flags = 0 if word.isupper() and len(word) <= 4 else re.IGNORECASE
    return re.compile(rf"(?<![\w+-]){re.escape(word)}(?![\w+-])", flags)


def judge_keywords(bank: BankPolicy) -> tuple[re.Pattern[str], ...]:
    """Word-bounded patterns for the keywords of every judged slot (short acronyms exact-case)."""
    words = dict.fromkeys(
        keyword.strip()
        for spec in bank.scores
        for slot in spec.inputs
        if slot.judge is not None
        for keyword in slot.judge.keywords
        if keyword.strip()
    )
    return tuple(_keyword_pattern(word) for word in words)


def rating_grades(bank: BankPolicy) -> tuple[re.Pattern[str], ...]:
    """Exact-case patterns for the grade keys of categorical slots, used on rating statements."""
    grades = dict.fromkeys(
        grade for spec in bank.scores for slot in spec.inputs for grade in slot.mapping
    )
    return tuple(re.compile(rf"(?<![\w+-]){re.escape(grade)}(?![\w+-])") for grade in grades)


def build_checklist(bank: BankPolicy) -> str:
    """A compact prompt text: score inputs, rule names, red-flag evidence, policy headings."""
    inputs = [
        f"- {slot.description.rstrip('.')}"
        for spec in bank.scores
        for slot in spec.inputs
        if slot.description
        and slot.judge is None
        and not slot.mapping
        and not slot.run_parameter
        and not slot.derive_from
    ]
    derived = [
        f"- {slot.description.rstrip('.')}: write its components ({', '.join(slot.derive_from)})"
        for spec in bank.scores
        for slot in spec.inputs
        if slot.derive_from
    ]
    rules = "; ".join(rule.name for rule in bank.rules)
    flags = sorted(
        {
            keyword
            for spec in bank.scores
            for slot in spec.inputs
            if slot.judge is not None
            for keyword in slot.judge.keywords
        },
        key=str.lower,
    )
    lines = [f"Credit-policy checklist ({bank.name or bank.bank_id}):", *inputs, *derived]
    if rules:
        lines.append(f"- Rules tested: {rules}")
    lines.extend(QUALITATIVE_TOPICS)
    if flags:
        lines.append(f"- Red-flag and default evidence: {', '.join(flags)}")
    return "\n".join(lines)


def build_policy_focus(bank: BankPolicy) -> PolicyFocus:
    """The focus of one loaded bank."""
    return PolicyFocus(
        checklist=build_checklist(bank),
        phrases=metric_phrases(bank),
        keywords=judge_keywords(bank),
        grades=rating_grades(bank),
    )


def load_policy_focus(banks_dir: str | Path | None, bank_id: str) -> PolicyFocus | None:
    """The focus of `banks/<bank_id>`, or None when no bank folder is given or it fails to load."""
    if banks_dir is None:
        return None
    try:
        return build_policy_focus(load_bank(banks_dir, bank_id))
    except Exception:
        logger.warning("bank %s could not be loaded; extracting without a policy focus", bank_id)
        return None


def _contains(tokens: Sequence[str], phrase: tuple[str, ...]) -> bool:
    """The label is the phrase, optionally led by a scope word and followed by a short tail."""
    if len(phrase) == 1:
        core = tuple(word for word in tokens if word not in IGNORED_WORDS | SCOPE_WORDS)
        return core == phrase
    core = tuple(word for word in tokens if word not in IGNORED_WORDS)
    start = next((i for i, word in enumerate(core) if word not in LEADING_WORDS), len(core))
    size = len(phrase)
    return core[start : start + size] == phrase and len(core) - start - size <= MAX_PHRASE_TAIL


def _label_of(entry: NotebookEntry) -> str:
    if entry.record is not None:
        return entry.record.metric
    return _VERB.split(entry.statement, maxsplit=1)[0]


def _matches_metric(entry: NotebookEntry, focus: PolicyFocus) -> bool:
    label = _tokens(_label_of(entry))[:SUBJECT_TOKENS]
    if RATIO_WORDS.intersection(label):
        return False
    return any(_contains(label, phrase) for phrase in focus.phrases)


def _matches_rating(entry: NotebookEntry, focus: PolicyFocus) -> bool:
    return "rating" in entry.statement.lower() and any(
        grade.search(entry.statement) for grade in focus.grades
    )


def feeds_policy(entry: NotebookEntry, focus: PolicyFocus) -> bool:
    """True when the entry's metric matches a policy input, or it states a rating or red flag."""
    return (
        _matches_metric(entry, focus)
        or _matches_rating(entry, focus)
        or any(pattern.search(entry.statement) for pattern in focus.keywords)
    )


def apply_policy_importance(
    entries: Iterable[NotebookEntry], focus: PolicyFocus | None
) -> list[NotebookEntry]:
    """5 for entries that feed the policy; every other entry keeps the model's rating, max 4."""
    ordered = list(entries)
    if focus is None:
        return ordered
    result: list[NotebookEntry] = []
    for entry in ordered:
        importance = (
            FEEDS_POLICY_IMPORTANCE
            if feeds_policy(entry, focus)
            else min(entry.importance, TOPIC_IMPORTANCE)
        )
        result.append(
            entry
            if importance == entry.importance
            else entry.model_copy(update={"importance": importance})
        )
    logger.info(
        "policy importance: %d of %d entries feed a rule, score or red-flag check",
        sum(1 for entry in result if entry.importance == FEEDS_POLICY_IMPORTANCE),
        len(result),
    )
    return result
