"""Critique the draft with fresh context, search for gaps, and record concerns."""

from .draft_markdown import draft_markdown
from .questions import Question, QuestionsOutput, ask_questions
from .run_adversary import run_adversary
from .search_gaps import AnswerOutput, GapResult, answer_question

__all__ = [
    "AnswerOutput",
    "GapResult",
    "Question",
    "QuestionsOutput",
    "answer_question",
    "ask_questions",
    "draft_markdown",
    "run_adversary",
]
