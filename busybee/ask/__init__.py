"""Chat with the documents of a finished run: retrieve, answer with citations, verify each sentence.

Public entry points: `answer_question` for one question and `chat_loop` for a REPL. Components:
`retrieve` (vector search of the run's index), `compose_answer` (one structured LLM call that may
cite only retrieved chunk ids), `check_sentences` (number match + entailment, reusing verify),
`render_answer` (text with supported / not supported marks and PDF links).
"""

from busybee.ask.compose_answer import AskReply, AskSentence, compose_answer
from busybee.ask.model import Answer, CheckedSentence, Citation
from busybee.ask.run_ask import answer_question, chat_loop

__all__ = [
    "Answer",
    "AskReply",
    "AskSentence",
    "CheckedSentence",
    "Citation",
    "answer_question",
    "chat_loop",
    "compose_answer",
]
