"""A fresh-context LLM compares policy.lean against the policy text and lists discrepancies.

The checker sees only the policy text, the score specs and the Lean source, never the
writer's conversation, so it cannot be anchored by the writer's reasoning.
"""

from pydantic import BaseModel, Field

from busybee.llm import Message, Provider, Role, complete_as
from busybee.policy.formalize.writer import score_description
from busybee.schema.policy import BankPolicy

CHECK_TASK = "policy.formalize_check"

_SYSTEM = (
    "You audit a Lean 4 formalisation of a bank credit policy against the policy text. "
    "Compare every threshold, band, point value, edge case (zero or negative denominators), "
    "grade label and rule. List each concrete discrepancy or missing rule as one short issue. "
    "Set ok to true only when you find no discrepancy."
)


class CheckOutput(BaseModel):
    """The checker's verdict and the discrepancies it found."""

    ok: bool
    issues: list[str] = Field(default_factory=list)


def checker_messages(bank: BankPolicy, source: str) -> list[Message]:
    """Build the checker prompt from policy text, score specs and the Lean source."""
    content = (
        f"Policy text:\n{bank.policy_md}\n\nScore specs:\n"
        + "\n".join(score_description(spec) for spec in bank.scores)
        + f"\n\nLean source:\n{source}\n\n"
        'Return JSON {"ok": <bool>, "issues": [<strings>]}.'
    )
    return [Message(role=Role.system, content=_SYSTEM), Message(role=Role.user, content=content)]


async def check_formalisation(provider: Provider, bank: BankPolicy, source: str) -> CheckOutput:
    """Return the checker's verdict; ok with listed issues is treated as not ok."""
    output = await complete_as(
        provider, checker_messages(bank, source), CheckOutput, task=CHECK_TASK
    )
    return CheckOutput(ok=output.ok and not output.issues, issues=output.issues)
