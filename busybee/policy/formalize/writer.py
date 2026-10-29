"""Ask an LLM to write a bank's `policy.lean` from policy.md and scores.yaml.

The prompt carries the Lean conventions of docs/ARCHITECTURE.md section 4 verbatim, the shared
`BusyBee.Common` module, and `Example.lean` as a style example. It fixes the interface the
score generator relies on: the file's namespace is the policy module name, each score has a
function named by `lean_function` taking the input slots in order as `Int`s and returning
`Int`, plus `<lean_function>_grade` with the same arguments returning the grade label `String`
exactly as written in scores.yaml.
"""

from pydantic import BaseModel

from busybee.lean.project import camel_bank_id, project_dir
from busybee.llm import Message, Provider, Role, complete_as
from busybee.schema.policy import BankPolicy, ScoreSpec

WRITE_TASK = "policy.formalize_write"

LEAN_CONVENTIONS = """\
* **Lean 4 core only, no Mathlib** (keeps the toolchain small and builds reliable). Toolchain
  pinned in `lean/lean-toolchain`.
* All quantities are `Int` in a declared integer scale (e.g. INR crore × 100 for two
  decimals, percentages in basis points). The scale is in `scores.yaml` and in a comment.
* Ratios never appear as division. A threshold `net_debt / ebitda ≤ 3.5` is written as
  `2 * net_debt ≤ 7 * ebitda` under the hypothesis `0 < ebitda`.
* Proof tactics allowed: `decide`, `omega`, `simp`, `rfl`. `native_decide` only as a last
  resort and flagged in the artifact.
* Every fact `def` carries its provenance comment on the same line: `-- F012 D1:p214:c2`.
* Policy files are organised with `-- SECTION: <title>` markers and `/-- doc comments -/`
  on every `def`/`theorem`, because the manual explainer renders those for humans."""

_SYSTEM = (
    "You are an expert Lean 4 engineer formalising a bank's credit policy. Follow these Lean "
    "conventions exactly:\n" + LEAN_CONVENTIONS
)


class WriterOutput(BaseModel):
    """The complete text of the proposed policy.lean."""

    lean_source: str


def strip_fences(text: str) -> str:
    """Remove a surrounding Markdown code fence from model-written source."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip() + "\n"


def score_description(spec: ScoreSpec) -> str:
    slots = ", ".join(f"{slot.slot} (scale {slot.scale}, {slot.unit})" for slot in spec.inputs)
    grades = "; ".join(f"{grade.label}: {grade.condition_text}" for grade in spec.grades)
    return (
        f"- score_id {spec.score_id}: {spec.name}. {spec.description}\n"
        f"  lean_function `{spec.lean_function}` taking Int arguments in this order: {slots}\n"
        f"  grade function `{spec.lean_function}_grade` (same arguments, returns String): {grades}"
    )


def writer_messages(
    bank: BankPolicy, previous: str | None = None, feedback: list[str] | None = None
) -> list[Message]:
    """Build the writer prompt, adding the previous attempt and its problems when repairing."""
    module = f"BusyBee.Policy.{camel_bank_id(bank.bank_id)}"
    lean_root = project_dir() / "BusyBee"
    common = (lean_root / "Common.lean").read_text(encoding="utf-8")
    example = (lean_root / "Example.lean").read_text(encoding="utf-8")
    content = (
        f"Write `policy.lean` for bank `{bank.bank_id}`.\n\n"
        f"Requirements:\n- Start with `import BusyBee.Common`, then a `/-! ... -/` doc block.\n"
        f"- Put everything inside `namespace {module}` ... `end {module}`.\n"
        "- Define exactly the functions below; every `def` and `theorem` has a `/-- doc -/`.\n"
        "- No division and no Mathlib; the grade function returns the label string exactly.\n"
        "- Add a few `decide`-proved sanity theorems.\n\n"
        f"Scores:\n" + "\n".join(score_description(spec) for spec in bank.scores) + "\n\n"
        f"Policy text:\n{bank.policy_md}\n\n"
        f"BusyBee/Common.lean (already available, import it):\n{common}\n\n"
        f"Style example (BusyBee/Example.lean):\n{example}\n"
    )
    if previous is not None:
        content += f"\nYour previous attempt:\n{previous}\n"
    if feedback:
        content += "\nFix all of these problems:\n" + "\n".join(f"- {item}" for item in feedback)
    content += '\nReturn JSON {"lean_source": "<the whole file>"}.'
    return [Message(role=Role.system, content=_SYSTEM), Message(role=Role.user, content=content)]


async def write_policy(
    provider: Provider,
    bank: BankPolicy,
    previous: str | None = None,
    feedback: list[str] | None = None,
) -> str:
    """Return a freshly written (or repaired) policy.lean source."""
    output = await complete_as(
        provider, writer_messages(bank, previous, feedback), WriterOutput, task=WRITE_TASK
    )
    return strip_fences(output.lean_source)
