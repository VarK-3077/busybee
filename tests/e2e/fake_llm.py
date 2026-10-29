"""A deterministic stand-in LLM that answers every pipeline task tag from the prompt text.

`fake_llm(messages, task)` is the callable a `MockProvider` delegates to. It reads the real
prompt of each stage and builds schema-valid, id-valid JSON: extract entries are verbatim
sentences with numbers from the window (cited with the chunk ids shown), relevance keeps
everything, entailment quotes a verbatim sentence of the chunk when the statement overlaps
it, bindings pick, per slot, the fact whose statement matches that slot's phrase and take the
number it captures, and inferences, adversary
questions and the recommendation cite only ids found in their prompt. Select it with
`BUSYBEE_LLM_PROVIDER=mock BUSYBEE_LLM_MOCK_CALLABLE=fake_llm:fake_llm` (tests/e2e on
PYTHONPATH).
"""

import json
import re
from collections.abc import Callable

from busybee.llm.messages import Message, Role

_CHUNK_ID = r"D\d+:p\d+:c\d+"
_CHUNK_BLOCK = re.compile(rf"^\[({_CHUNK_ID})\]\n(.*?)(?=\n\n\[{_CHUNK_ID}\]\n|\Z)", re.S | re.M)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_WORDS = re.compile(r"[a-z][a-z0-9]{2,}")
_STOP = frozenset(
    "the and for with that this from what are was were has have any there their which into "
    "does did how who why when about over under than its our not but all can".split()
)
_CATEGORY_WORDS = (
    ("revenue", ("revenue", "sales", "turnover")),
    ("profitability", ("ebitda", "profit", "margin")),
    ("debt_leverage", ("debt", "borrowing", "leverage", "net worth", "equity")),
    ("liquidity", ("liquidity", "current ratio", "cash", "current assets")),
    ("cash_flow", ("cash flow", "operations", "dscr", "coverage")),
    ("ratings", ("rating", "outlook")),
    ("credit_history", ("covenant", "repayment", "overdraft", "default")),
    ("litigation_regulatory", ("litigation", "tax", "regulatory", "court")),
    ("ownership_governance", ("promoter", "director", "shareholding")),
)


def _user_text(messages: list[Message]) -> str:
    return next((m.content for m in messages if m.role == Role.user), "")


def _words(text: str) -> set[str]:
    return {word for word in _WORDS.findall(text.lower()) if word not in _STOP}


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text) if len(part.strip()) > 25]


def _category(sentence: str) -> str:
    lowered = sentence.lower()
    for category, words in _CATEGORY_WORDS:
        if any(word in lowered for word in words):
            return category
    return "other"


_TABLE_HEADER = re.compile(r"^\[TABLE: (.*)\]$", re.M)
_ROW = re.compile(r"^(?P<label>[^|\n]+?) \| (?P<cells>.+)$")
_CELL = re.compile(r"^(?P<period>[^:|]+): (?P<value>-?[\d,]+(?:\.\d+)?)$")


def _table_records(chunk_id: str, chunk_text: str) -> list[dict]:
    if _TABLE_HEADER.search(chunk_text) is None:
        return []
    unit = "crore" if re.search(r"\(Rs crore\)", chunk_text) else ""
    records = []
    for line in chunk_text.splitlines():
        row = _ROW.match(line.strip())
        if row is None or line.startswith("[TABLE"):
            continue
        cells = [_CELL.match(cell.strip()) for cell in row.group("cells").split(" | ")]
        if not cells or any(cell is None for cell in cells):
            continue
        current, previous = cells[0], cells[1] if len(cells) > 1 else None
        records.append(
            {
                "m": row.group("label"),
                "v": current.group("value"),
                "u": unit,
                "p": current.group("period"),
                "pv": previous.group("value") if previous else None,
                "pp": previous.group("period") if previous else None,
                "c": [chunk_id],
                "i": 3,
            }
        )
    return records


def _extract(text: str) -> dict:
    body = text.split("New chunks for window", 1)[-1]
    body = body.split("\n", 1)[-1].split("\n\nExtract the new entries", 1)[0]
    entries = []
    records = []
    for chunk_id, chunk_text in _CHUNK_BLOCK.findall(body):
        records.extend(_table_records(chunk_id, chunk_text))
        numeric = [
            s
            for s in _sentences(chunk_text)
            if re.search(r"\d", s)
            and len(s.split()) >= 5
            and not s.startswith(("#", "Particulars"))
        ]
        for sentence in numeric[:3]:
            entries.append(
                {
                    "s": sentence,
                    "c": [chunk_id],
                    "cat": _category(sentence),
                    "k": "number",
                    "i": 3,
                }
            )
    return {"entries": entries, "records": records}


def _relevance(text: str) -> dict:
    return {"drop": []}


def _entailment(text: str) -> dict:
    statement = text.split("Statement:\n", 1)[-1].split("\n\nSource passage:\n", 1)[0]
    passage = text.split("\n\nSource passage:\n", 1)[-1]
    wanted = _words(statement)
    best, overlap = "", 0.0
    for sentence in _sentences(passage):
        score = len(wanted & _words(sentence)) / max(len(wanted), 1)
        if score > overlap:
            best, overlap = sentence, score
    if overlap >= 0.5:
        return {"v": "supported", "q": best}
    return {"v": "unsupported", "q": ""}


def _entailment_batch(text: str) -> dict:
    statement = text.split("Statement:\n", 1)[-1].split("\n\nSource passages:\n", 1)[0]
    blocks = text.split("\n\nSource passages:\n", 1)[-1]
    judgements = []
    for block in re.split(r"\n\n(?=\[[^\]\n]+\]\n)", blocks):
        found = re.fullmatch(r"\[([^\]\n]+)\]\n(.*)", block, re.S)
        if found is None:
            continue
        single = _entailment(f"Statement:\n{statement}\n\nSource passage:\n{found.group(2)}")
        judgements.append({"id": found.group(1), **single})
    return {"r": judgements}


def _numbers_of(numbers: str) -> list[tuple[str, str, str]]:
    parsed = []
    for part in numbers.split("; "):
        if "=" not in part:
            continue
        label, rest = part.split("=", 1)
        pieces = rest.split()
        if pieces:
            parsed.append((label.lower(), pieces[0], " ".join(pieces[1:])))
    return parsed


_NUM = r"([\d,]+(?:\.\d+)?)"
_SLOT_PATTERNS: dict[str, str | tuple[str, ...]] = {
    "net_debt": rf"net debt of Rs {_NUM} crore",
    "ebitda": rf"EBITDA was Rs {_NUM} crore in FY25",
    "interest_expense": rf"finance costs for FY25 were Rs {_NUM} crore",
    "cfads": rf"\(CFADS\) in FY25 was Rs {_NUM} crore",
    "debt_service": rf"Debt service in FY25 was Rs {_NUM} crore",
    "total_debt": rf"total borrowings at 31 March 2025 were Rs {_NUM} crore",
    "total_equity": rf"(?:\(net worth\) at 31 March 2025 was|being net worth of) Rs {_NUM} crore",
    "current_assets": rf"current assets at 31 March 2025 were Rs {_NUM} crore",
    "current_liabilities": rf"current liabilities at 31 March 2025 were Rs {_NUM} crore",
    "revenue_current": rf"Revenue from operations rose to Rs {_NUM} crore in FY25",
    "revenue_previous": rf"in FY25 from Rs {_NUM} crore in FY24",
    "external_rating_index": r"external rating index of (\d+)",
    "major_red_flag_count": r"red flag count of (\d+)",
    "default_flag": r"default flag is (\d+)",
    "proposed_exposure": (
        rf"Bank input: proposed exposure INR {_NUM} crore",
        rf"exposure including existing limits is Rs {_NUM} crore",
    ),
    "projected_turnover": (
        rf"Bank input: projected turnover INR {_NUM} crore",
        rf"projects FY26 turnover of Rs {_NUM} crore",
    ),
    "tangible_net_worth": rf"Tangible net worth at 31 March 2025 was Rs {_NUM} crore",
}


def _bind_slot(
    slot: str, facts: list[tuple[str, str, list[tuple[str, str, str]]]]
) -> tuple[str, str, str] | None:
    patterns = _SLOT_PATTERNS.get(slot, ())
    for pattern in (patterns,) if isinstance(patterns, str) else patterns:
        for fact_id, statement, numbers in facts:
            match = re.search(pattern, statement, re.I)
            if not match:
                continue
            wanted = match.group(1).replace(",", "")
            for _, value, unit in numbers:
                if value == wanted:
                    return fact_id, value, unit
    return None


def _bind(text: str) -> dict:
    slots = re.findall(r"^- score_id=(\S+) slot=(\S+) ", text, re.M)
    facts = []
    for line in text.split("Verified facts:\n", 1)[-1].splitlines():
        match = re.match(r"(F\d+): (.*) \| numbers: (.*)$", line)
        if match:
            facts.append((match.group(1), match.group(2), _numbers_of(match.group(3))))
    bindings = []
    for score_id, slot in slots:
        found = _bind_slot(slot, facts)
        if found:
            fact_id, value, unit = found
            bindings.append(
                {
                    "score_id": score_id,
                    "slot": slot,
                    "fact_id": fact_id,
                    "value": value,
                    "unit": unit,
                }
            )
    return {"bindings": bindings}


def _judge(text: str) -> dict:
    slot = re.search(r"Input: (\w+)", text).group(1)
    candidates = re.findall(r"^(F\d+): ", text.split("Candidate facts:\n", 1)[-1], re.M)
    value = "A+" if slot == "external_rating_index" else 0
    return {
        "value": value,
        "fact_ids": candidates[:1],
        "justification": f"No evidence of {slot} in the candidate facts.",
    }


def _slot_extract(text: str) -> dict:
    phrase = re.search(r"^Component: (.+)$", text, re.M).group(1).strip().lower()
    passage = text.split("Passage [", 1)[-1].split("]:\n", 1)[-1]
    for line in passage.splitlines():
        if phrase in line.lower() and re.search(r"\d", line):
            return {
                "found": True,
                "statement": line.strip(),
                "value": re.search(r"[\d,]+(?:\.\d+)?", line).group(0),
                "unit": "",
                "period": "",
                "quote": line.strip(),
            }
    return {"found": False}


def _infer(text: str) -> dict:
    facts = re.findall(r"^(F\d+) \| (\w+) \| (.*?)(?: \||$)", text, re.M)
    by_category: dict[str, list[str]] = {}
    for fact_id, category, _ in facts:
        by_category.setdefault(category, []).append(fact_id)
    topics = [
        ("revenue", "Revenue growth supports debt service capacity."),
        ("debt_leverage", "Leverage looks manageable relative to earnings."),
        ("liquidity", "Liquidity is adequate for near-term obligations."),
        ("ratings", "The external rating supports a stable credit view."),
    ]
    drafts = []
    for category, opinion in topics:
        ids = by_category.get(category, [])[:2]
        if ids:
            drafts.append(
                {
                    "opinion": opinion,
                    "fact_ids": ids,
                    "reasoning": f"The cited facts {', '.join(ids)} describe {category}.",
                    "confidence": 0.7,
                    "quantitative": False,
                }
            )
    if not drafts and facts:
        drafts.append(
            {
                "opinion": "The borrower shows a documented operating record.",
                "fact_ids": [facts[0][0]],
                "reasoning": f"Fact {facts[0][0]} documents the borrower.",
                "confidence": 0.5,
                "quantitative": False,
            }
        )
    return {"inferences": drafts}


_QUESTIONS = (
    ("What share of revenue comes from the largest customers?", "top five customers revenue share"),
    ("Is there any covenant breach or waiver?", "covenant breach waiver DSCR"),
    ("How will the capacity expansion be funded?", "expansion capex funding term loan"),
    ("Are there pending litigation matters against the directors?", "litigation directors"),
)


def _questions(text: str) -> dict:
    ids = list(dict.fromkeys(re.findall(r"\bF\d{3}\b", text)))
    return {
        "items": [
            {
                "question": question,
                "why": "A credit officer needs this to size the line.",
                "related_fact_ids": ids[:1],
                "search_query": query,
            }
            for question, query in _QUESTIONS
        ]
    }


def _answer(text: str) -> dict:
    question = text.split("Question: ", 1)[-1].split("\n\nPassages:\n", 1)[0]
    passages = text.split("\n\nPassages:\n", 1)[-1]
    wanted = _words(question)
    best, hits = "", 0
    for sentence in _sentences(re.sub(rf"^\[{_CHUNK_ID}\]$", "", passages, flags=re.M)):
        count = len(wanted & _words(sentence))
        if count > hits and re.search(r"\d", sentence):
            best, hits = sentence, count
    if hits >= 2:
        return {"answered": True, "statement": best, "category": _category(best)}
    return {"answered": False, "statement": "", "category": "other"}


def _section_ids(text: str, title: str, pattern: str) -> list[str]:
    block = text.split(f"{title}\n", 1)[-1].split("\n\n", 1)[0] if f"{title}\n" in text else ""
    return re.findall(pattern, block, re.M)


def _policy_section_ids(text: str) -> list[str]:
    block = text.split("Policy sections\n", 1)[-1].split("\n\nFacts\n", 1)[0]
    return re.findall(r"^\[(P\d+)\] ", block, re.M)


_STRICTNESS = ("approve", "approve_with_conditions", "refer", "decline")


def _rule_rows(text: str) -> tuple[list[tuple[str, str]], str]:
    block = text.split("Policy rule results\n", 1)[-1].split("\n\n", 1)[0]
    rows = re.findall(r"^- (\w+) \| [^|]* \| (\w+) \|", block, re.M)
    floor = re.search(r"Policy-implied minimum decision: (\w+)", block)
    return rows, floor.group(1) if floor else "approve"


def _compose(text: str) -> dict:
    facts = _section_ids(text, "Facts", r"^- (F\d+) ")
    scores = _section_ids(text, "Scores", r"^- (\w+): ")
    inferences = _section_ids(text, "Inferences", r"^- (I\d+): ")
    sections = _policy_section_ids(text)
    reasons = [
        {
            "text": "Net debt/EBITDA is within the policy cap.",
            "kind": "policy_rule",
            "policy_citations": [{"section_id": sections[0], "quote": ""}] if sections else [],
            "fact_ids": facts[2:4] or facts[:1],
            "score_ids": scores[:1],
        },
        {
            "text": "Revenue and earnings are documented and growing.",
            "kind": "hard_fact",
            "fact_ids": facts[:2],
        },
    ]
    if inferences:
        reasons.append(
            {
                "text": "The analyst inferences are supportive.",
                "kind": "inference",
                "inference_ids": inferences[:2],
            }
        )
    rows, floor = _rule_rows(text)
    for rule_id, status in rows:
        if status in ("fail", "caution"):
            reasons.append(
                {
                    "text": f"Policy rule {rule_id} is {status}.",
                    "kind": "policy_rule",
                    "policy_citations": [{"section_id": sections[0], "quote": ""}]
                    if sections
                    else [],
                    "rule_ids": [rule_id],
                }
            )
    decision = max("approve_with_conditions", floor, key=_STRICTNESS.index)
    return {
        "decision": decision,
        "headline": "Approve a working-capital limit with covenant monitoring.",
        "proposed_limit": None,
        "conditions": ["Maintain the existing financial covenants."],
        "key_reasons": reasons,
        "confidence_note": "Based on synthetic documents; open concerns remain.",
    }


def _verdict_check(text: str) -> dict:
    indexes = re.findall(r"^Reason (\d+) \[", text, re.M)
    return {"checks": [{"index": int(i), "verdict": "correct", "note": ""} for i in indexes]}


def _calibrate(text: str) -> dict:
    keep = int(re.search(r"Return the ids of the (\d+) most", text).group(1))
    ids = re.findall(r"^(D\d+:E\d+) \| ", text, re.M)
    return {"entry_ids": ids[:keep]}


def _conflict(text: str) -> dict:
    results = []
    for block in re.split(r"\n\n(?=Pair \d+)", text.split("Pairs\n\n", 1)[-1]):
        number = re.match(r"Pair (\d+)", block)
        statements = re.findall(r"^[AB] \[F\d+\] \(.*?\): (.*)$", block, re.M)
        if number is None or len(statements) != 2:
            continue
        periods = [set(re.findall(r"\bFY\d{2,4}(?:-\d{2})?\b|\bQ[1-4]\b", s)) for s in statements]
        numbers = [set(re.findall(r"\d[\d,]*\.?\d*", s)) for s in statements]
        conflict = bool(periods[0] & periods[1]) and numbers[0] != numbers[1]
        results.append(
            {
                "id": int(number.group(1)),
                "conflict": conflict,
                "metric": "reported figure" if conflict else "",
            }
        )
    return {"r": results}


_HANDLERS: dict[str, Callable[[str], dict]] = {
    "extract": _extract,
    "extract_calibrate": _calibrate,
    "verify_relevance": _relevance,
    "verify_entailment": _entailment,
    "verify_entailment_batch": _entailment_batch,
    "adversary_answer": _answer,
    "policy.bind_inputs": _bind,
    "policy.judge_slot": _judge,
    "policy.slot_extract": _slot_extract,
    "infer": _infer,
    "infer_check": lambda _text: {"ok": True, "problems": []},
    "adversary_questions": _questions,
    "compose": _compose,
    "compose_verdict_check": _verdict_check,
    "verify_conflict": _conflict,
}


def fake_llm(messages: list[Message], task: str) -> str:
    """Return the JSON reply for one task tag, raising on a tag it does not know."""
    handler = _HANDLERS.get(task)
    if handler is None:
        raise ValueError(f"fake_llm has no handler for task {task!r}")
    return json.dumps(handler(_user_text(messages)), separators=(",", ":"))
