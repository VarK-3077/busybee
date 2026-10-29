"""Fresh-context critique: what would a sceptical senior credit officer still want to know?

The model sees only the markdown draft (never the notebook or the corpus) and returns up to
12 questions, each with why it matters, a severity (high, medium or low), the fact ids it
relates to and a short search query for the document index. Fact ids the model invents are
removed in code, and a high severity without any remaining related fact id is lowered to
medium. `rank_questions` orders questions by severity, then by number of related facts. An unusable
reply yields no questions rather than failing the stage.
Task tag: `adversary_questions`; response model: `QuestionsOutput`.
"""

from typing import Literal

from pydantic import BaseModel, Field

from busybee.llm import Message, Role, StructuredOutputError, complete_as
from busybee.llm.provider import Provider

QUESTIONS_TASK = "adversary_questions"
MAX_QUESTIONS = 12

_SYSTEM = (
    "You are a sceptical senior credit officer reviewing a draft credit assessment. List what "
    f"you would still want to know and what looks weak or under-evidenced (at most "
    f"{MAX_QUESTIONS} items, most important first). For each item give: 'question', 'why' it "
    "matters for the credit decision, 'severity' ('high' only for gaps that could change the "
    "credit decision, otherwise 'medium' or 'low'), 'related_fact_ids' (ids such as F001 taken "
    "from the draft; must be non-empty for high severity), and 'search_query', a short keyword "
    "query likely to find the answer in the "
    "company's documents."
)


class Question(BaseModel):
    """One open question raised by the critic."""

    question: str
    why: str = ""
    severity: Literal["high", "medium", "low"] = "medium"
    related_fact_ids: list[str] = Field(default_factory=list)
    search_query: str = ""


class QuestionsOutput(BaseModel):
    """The critic's list of questions."""

    items: list[Question] = Field(default_factory=list)


SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def rank_key(question: Question) -> tuple[int, int]:
    """Sort key: most severe first, then the most related facts first."""
    return SEVERITY_ORDER[question.severity], -len(question.related_fact_ids)


def rank_questions(questions: list[Question]) -> list[Question]:
    """Return questions ordered by severity then related-fact count (stable on ties)."""
    return sorted(questions, key=rank_key)


def _clean(question: Question, known_fact_ids: set[str]) -> Question:
    related = [i for i in question.related_fact_ids if i in known_fact_ids]
    return question.model_copy(
        update={
            "related_fact_ids": related,
            "severity": "medium"
            if question.severity == "high" and not related
            else question.severity,
            "search_query": question.search_query.strip() or question.question,
        }
    )


async def ask_questions(draft: str, provider: Provider, known_fact_ids: set[str]) -> list[Question]:
    """Return the critic's questions about the draft, capped at MAX_QUESTIONS."""
    messages = [
        Message(role=Role.system, content=_SYSTEM),
        Message(role=Role.user, content=f"Draft:\n\n{draft}"),
    ]
    try:
        output = await complete_as(provider, messages, QuestionsOutput, task=QUESTIONS_TASK)
    except StructuredOutputError:
        return []
    items = [item for item in output.items if item.question.strip()]
    return [_clean(item, known_fact_ids) for item in items[:MAX_QUESTIONS]]
