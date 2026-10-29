"""Write, compile, check, and repair policy.lean until it compiles and the checker agrees.

Each round the writer drafts (or repairs) the file, the draft is compiled on its own against
`BusyBee.Common`, a cheap deterministic check confirms every score's functions exist, and only
then the fresh-context checker compares it with the policy text. Compiler errors and checker
issues are fed back to the writer, for at most `max_rounds` rounds. The best source seen
(compiles and checked ok, then compiles, then fewest problems) is returned with a log.
"""

from dataclasses import dataclass, field
from pathlib import Path

from busybee.lean.compile import compile_file
from busybee.llm import Provider
from busybee.policy.formalize.checker import check_formalisation
from busybee.policy.formalize.writer import write_policy
from busybee.schema.policy import BankPolicy

MAX_ROUNDS = 4


@dataclass
class FormalizeResult:
    """The best policy.lean found, whether it passed everything, and a per-round log."""

    source: str
    ok: bool
    log: list[str] = field(default_factory=list)


def missing_functions(bank: BankPolicy, source: str) -> list[str]:
    """Problems for score functions the source does not define."""
    problems = []
    for spec in bank.scores:
        for name in (spec.lean_function, f"{spec.lean_function}_grade"):
            if f"def {name}" not in source:
                problems.append(f"missing `def {name}` required for score {spec.score_id}")
    return problems


async def formalise(
    provider: Provider,
    bank: BankPolicy,
    work_dir: str | Path,
    max_rounds: int = MAX_ROUNDS,
) -> FormalizeResult:
    """Run the write-compile-check loop and return the best source with its log."""
    folder = Path(work_dir)
    folder.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    best: tuple[tuple[int, int, int], str] | None = None
    best_ok = False
    source: str | None = None
    feedback: list[str] = []
    for round_no in range(1, max_rounds + 1):
        source = await write_policy(provider, bank, source, feedback)
        path = folder / f"policy_round{round_no}.lean"
        path.write_text(source, encoding="utf-8")
        compiled = await compile_file(path)
        feedback = [f"line {e.line}: {e.message}" for e in compiled.errors]
        if not compiled.ok and not feedback:
            feedback = [compiled.stderr.strip() or "compilation failed"]
        feedback += missing_functions(bank, source)
        verdict_ok = False
        if compiled.ok and not feedback:
            verdict = await check_formalisation(provider, bank, source)
            verdict_ok = verdict.ok
            feedback = verdict.issues
        log.append(
            f"round {round_no}: compiled={compiled.ok} checker_ok={verdict_ok} "
            f"problems={len(feedback)}"
        )
        log.extend(f"  - {item}" for item in feedback)
        rank = (int(compiled.ok and verdict_ok), int(compiled.ok), -len(feedback))
        if best is None or rank > best[0]:
            best = (rank, source)
            best_ok = compiled.ok and verdict_ok
        if compiled.ok and verdict_ok:
            break
    assert best is not None
    return FormalizeResult(source=best[1], ok=best_ok, log=log)
