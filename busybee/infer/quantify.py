"""Turn quantitative inferences into compilable Lean files and attach the artifact.

All numbers in one claim share a single integer scale, 10^(most decimals among them, at most
4), so values taken from different facts stay comparable; the scale is stated once in a
`-- scale: xN` comment. Money is normalised to crore and percent/basis points to percent,
and a claim mixing incompatible units (crore with percent, a ratio with a percentage) is
rejected with a message. A claim must also not map two variables to the same number of a
fact, nor chain comparisons (`a < b < c`) that Lean cannot parse.

A whole-side integer literal such as the 1 in `interest_coverage < 1` is read in real units
(crore, percent, times) and scaled with the variables; multipliers are left alone.

A claim maps Lean variable names to facts. A fact reference is `F012` (the fact's first
number) or `F012#3.0` (the fact's number whose value is 3.0), so a threshold such as a
covenant limit in a fact with several numbers can be picked precisely. The claim itself must
be integer arithmetic over those variables: a decimal literal is rejected with a message
saying to map the number to a variable instead, never silently rescaled. When Lean rejects a
file, the logged and stored failure message is Lean's own diagnostic (Lean writes it to stdout).
"""

import asyncio
import logging
import os
import re
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from busybee.infer.make_inferences import facts_index
from busybee.infer.prompts import LeanClaim
from busybee.lean import templates
from busybee.lean.artifact import make_artifact
from busybee.lean.compile import compile_file
from busybee.schema.facts import NumericValue, VerifiedFact
from busybee.schema.lean import CompileResult
from busybee.schema.report import Inference
from busybee.verify.numbers import canonical_amount

logger = logging.getLogger(__name__)

MAX_DECIMALS = 4

_LEAN_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_']*")
_UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_COMPARATOR = re.compile(r"<=|>=|==|!=|≤|≥|<|>")
_MULTIPLY = re.compile(r"[*/×÷]")
_STATEMENT_MONEY_WORD = re.compile(r"\b(lakhs?|lacs?|crores?|millions?|billions?)\b", re.IGNORECASE)
_DURATION_COUNT = r"\s*(?:months?|years?)\b"
_DECIMAL_LITERAL = re.compile(r"(?<![\w.])\d+\.\d+")


class QuantifyError(ValueError):
    """Raised when an inference cannot be rendered as a Lean source file."""


def _money_factor(unit: str) -> Decimal | None:
    """Crore per one of this money unit, or None when the unit is not money."""
    text = unit.strip().lower().replace(",", "")
    amount = canonical_amount(Decimal(1), text.replace("₹", "inr ").replace("rs.", "rs"))
    if amount is not None:
        return amount[1]
    if "thousand" in text or re.search(r"\bk\b", text):
        return Decimal("0.0001")
    if re.search(r"(?:₹|\binr\b|\brs\b|\brupees?\b)", text):
        return Decimal("0.0000001")
    return None


def unit_class_and_factor(unit: str) -> tuple[str, Decimal]:
    """Return a unit's comparability class and its multiplier to the class base unit.

    Every money unit (INR/Rs/rupee, optionally with thousand, lakh, crore, million or billion)
    is the class "money" in crore, using the conversion shared with the number verifier;
    percent and basis points are percent, and unit-less ratios ("times", "x", empty) form one
    class. Any other unit is its own class, so it can only be compared with itself.
    """
    text = unit.strip().lower().replace(",", "")
    if "bps" in text or "basis point" in text:
        return "percent", Decimal("0.01")
    if "%" in text or "percent" in text or "pct" in text:
        return "percent", Decimal(1)
    factor = _money_factor(text)
    if factor is not None:
        return "money", factor
    if text in {"", "x", "times", "time", "ratio"}:
        return "ratio", Decimal(1)
    return text, Decimal(1)


def _normalised(number: NumericValue) -> Decimal:
    """The number's value expressed in its unit class's base unit."""
    return number.value * unit_class_and_factor(number.unit)[1]


def common_scale(numbers: Sequence[NumericValue]) -> int:
    """Return 10^d for the most decimals d among the numbers, with d capped at MAX_DECIMALS."""
    decimals = 0
    for number in numbers:
        exponent = _normalised(number).normalize().as_tuple().exponent
        if isinstance(exponent, int) and exponent < 0:
            decimals = max(decimals, -exponent)
    return 10 ** min(decimals, MAX_DECIMALS)


def scaled_int(number: NumericValue, scale: int) -> int:
    """Convert a numeric fact value to an integer at the claim's common scale."""
    scaled = _normalised(number) * scale
    return int(scaled.to_integral_value(rounding=ROUND_HALF_UP))


def _has_other_meaning(fact: VerifiedFact, number: NumericValue) -> bool:
    """True when the statement prints the number as a ratio, day count or percentage."""
    text = fact.statement.replace(",", "")
    plain = format(number.value.normalize(), "f")
    pattern = rf"(?<![\d.]){re.escape(plain)}\s*(?:times|x\b|days?|%|per ?cent|percent)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def with_inherited_unit(fact: VerifiedFact, number: NumericValue) -> NumericValue:
    """Give a unit-less number the money unit of its fact when the fact carries one.

    A table row such as "loss of 5,547.27" printed in a lakh table has no unit of its own; the
    fact's record unit, else the money unit of another number in the same statement, else the
    first lakh/crore/million word the statement itself prints, is used. A number the
    statement prints as "times", days or a percentage stays plain.
    """
    if number.unit.strip() or _has_other_meaning(fact, number):
        return number
    candidates = [fact.record.unit] if fact.record is not None else []
    candidates += [other.unit for other in fact.numbers if other is not number]
    candidates += [match.group(1) for match in _STATEMENT_MONEY_WORD.finditer(fact.statement)][:1]
    for unit in candidates:
        if unit_class_and_factor(unit)[0] == "money":
            return number.model_copy(update={"unit": unit})
    return number


def _is_cross_multiplication(
    statement: str, classes: Mapping[str, list[str]], names: Mapping[str, str]
) -> bool:
    """True for `ebitda * 100 >= 250 * finance_cost`: money times or over money vs a ratio."""
    if "money" not in classes or not _MULTIPLY.search(statement):
        return False
    if any(group not in {"money", "ratio", "days", "percent", "day"} for group in classes):
        return False
    money_names = [name for name in names if names[name] == "money"]
    used = [name for name in money_names if _used_in(statement, name)]
    return len(used) >= 2


def _used_in(statement: str, name: str) -> bool:
    """True when the claim text mentions the variable name as a whole word."""
    return re.search(rf"(?<![\w']){re.escape(name)}(?![\w'])", statement) is not None


def check_comparable(
    selected: Mapping[str, tuple[VerifiedFact, NumericValue]], statement: str = ""
) -> None:
    """Reject claims whose variables mix incompatible units (e.g. crore with percent).

    Only variables the claim text actually uses are compared; a mapped but unused variable
    is context and cannot make the claim ill-typed.

    Lakh, crore, million and the like are all money and never mismatch. A ratio, percent or
    day count beside money is allowed only when the claim multiplies or divides two money
    variables (cross-multiplying a ratio), as in `ebitda * 100 >= 250 * finance_cost`.
    """
    classes: dict[str, list[str]] = {}
    class_of: dict[str, str] = {}
    for name, (_, number) in selected.items():
        if statement and not _used_in(statement, name):
            continue
        label = number.unit.strip() or "plain number"
        group = unit_class_and_factor(number.unit)[0]
        class_of[name] = group
        classes.setdefault(group, []).append(f"{name} ({label})")
    if len(classes) > 1 and not _is_cross_multiplication(statement, classes, class_of):
        groups = "; ".join(", ".join(members) for members in classes.values())
        raise QuantifyError(
            f"claim mixes incompatible units: {groups}; money (any lakh/crore/million) can only "
            "be compared with money, unless the claim multiplies or divides two money variables "
            "to compare against a ratio; select a number with a matching unit using a fact "
            "reference such as F012#3.5"
        )


def check_distinct_numbers(selected: Mapping[str, tuple[VerifiedFact, NumericValue]]) -> None:
    """Reject two variables that resolve to the very same number of the same fact."""
    seen: dict[tuple[str, int], str] = {}
    for name, (fact, number) in selected.items():
        key = (fact.fact_id, next(i for i, n in enumerate(fact.numbers) if n is number))
        if key in seen:
            raise QuantifyError(
                f"variables {seen[key]} and {name} are the same number of {fact.fact_id}; "
                "use a reference such as F012#1.25 to pick the other number"
            )
        seen[key] = name


def check_no_chained_comparison(statement: str) -> None:
    """Reject `a < b < c`, which Lean cannot parse; the model must join comparisons with &&."""
    for part in re.split(r"&&|\|\||∧|∨", statement):
        if len(_COMPARATOR.findall(part)) > 1:
            raise QuantifyError(
                f"chained comparison in {part.strip()!r}; write each comparison separately "
                "and join them with &&"
            )


def _default_number(fact: VerifiedFact) -> NumericValue:
    """The fact's first number, skipping a bare count that the statement says is months/years."""
    text = fact.statement.replace(",", "")
    for number in fact.numbers:
        plain = format(number.value.normalize(), "f")
        counted = re.search(rf"(?<![\d.]){re.escape(plain)}{_DURATION_COUNT}", text)
        if number.unit.strip() or counted is None:
            return number
    return fact.numbers[0]


def scale_bare_literals(statement: str, scale: int) -> str:
    """Scale an integer literal that is a whole side of a comparison to the claim's scale.

    `interest_coverage < 1` compares a value stored x10 with 1, so the 1 must become 10; a
    multiplier such as the 2 in `2 * a <= 7 * b` is not a whole side and stays as written.
    """
    if scale == 1:
        return statement
    parts = re.split(r"(&&|\|\||∧|∨)", statement)
    for position, part in enumerate(parts):
        match = _COMPARATOR.search(part)
        if match is None:
            continue
        left, operator, right = part[: match.start()], match.group(0), part[match.end() :]
        parts[position] = f"{_scale_side(left, scale)}{operator}{_scale_side(right, scale)}"
    return "".join(parts)


def _scale_side(side: str, scale: int) -> str:
    """Multiply the side by the scale when it is nothing but an integer literal."""
    bare = re.fullmatch(r"\(?\s*(\d+)\s*\)?", side.strip())
    if bare is None:
        return side
    lead = side[: len(side) - len(side.lstrip())]
    trail = side[len(side.rstrip()) :]
    return f"{lead}{int(bare.group(1)) * scale}{trail}"


def pick_number(fact: VerifiedFact, reference: str) -> NumericValue:
    """Return the number a fact reference selects: `#value` picks by value, else the first."""
    _, _, wanted = reference.partition("#")
    if not wanted.strip():
        return _default_number(fact)
    try:
        target = Decimal(wanted.strip().replace(",", ""))
    except ArithmeticError as error:
        raise QuantifyError(f"bad number selector in {reference!r}") from error
    for number in fact.numbers:
        if number.value == target:
            return number
    listed = ", ".join(str(number.value) for number in fact.numbers)
    raise QuantifyError(f"{fact.fact_id} has no number {wanted.strip()} (it has: {listed})")


def lean_failure_message(result: CompileResult) -> str:
    """Lean's own diagnostics for a failed compile, wherever it printed them."""
    if result.errors:
        return "; ".join(
            f"line {error.line}: {' '.join(error.message.split())}" for error in result.errors
        )
    return " ".join((result.stderr or result.stdout).split()) or "unknown error"


def _provenance(fact: VerifiedFact) -> str:
    """Return `F012 D1:p214:c2` or just the fact id when there is no citation."""
    if fact.citations:
        return f"{fact.fact_id} {fact.citations[0].chunk_id}"
    return fact.fact_id


def _doc(text: str) -> str:
    """Make arbitrary fact text safe for a one-line Lean doc comment."""
    return " ".join(str(text).replace("-/", "- /").split())


def _namespace(inference_id: str) -> str:
    """Return a safe Lean namespace for one inference artifact."""
    name = _UNSAFE_NAME.sub("_", inference_id).strip("_") or "inference"
    if name[0].isdigit():
        name = f"I_{name}"
    return f"BusyBee.Inference.{name}"


def _file_name(inference_id: str) -> str:
    """Return the artifact file name for one inference."""
    safe = _UNSAFE_NAME.sub("-", inference_id).strip("-") or "inference"
    return f"Inference_{safe}.lean"


def build_lean_source(
    inference: Inference,
    lean_claim: LeanClaim,
    facts: Sequence[VerifiedFact] | Mapping[str, VerifiedFact],
) -> str:
    """Render scaled fact definitions and the claim theorem as Lean source."""
    index = facts_index(facts)
    selected: dict[str, tuple[VerifiedFact, NumericValue]] = {}
    for name, reference in lean_claim.facts.items():
        fact_id = reference.partition("#")[0].strip()
        if _LEAN_NAME.fullmatch(name) is None:
            raise QuantifyError(f"invalid Lean variable name: {name!r}")
        fact = index.get(fact_id)
        if fact is None:
            raise QuantifyError(f"unknown fact id in Lean claim: {fact_id}")
        if not fact.numbers:
            raise QuantifyError(f"fact {fact_id} has no numeric value to scale")
        selected[name] = (fact, pick_number(fact, reference))
    statement = lean_claim.claim.strip()
    if not statement:
        raise QuantifyError("Lean claim is empty")
    if not selected:
        raise QuantifyError("Lean claim has no facts")
    literal = _DECIMAL_LITERAL.search(statement)
    if literal is not None:
        raise QuantifyError(
            f"decimal literal {literal.group(0)} in the claim; map that number to a "
            "variable with a fact reference such as F012#1.25"
        )
    check_no_chained_comparison(statement)
    check_distinct_numbers(selected)
    selected = {
        name: (fact, with_inherited_unit(fact, number)) for name, (fact, number) in selected.items()
    }
    check_comparable(selected, statement)
    scale = common_scale([number for _, number in selected.values()])
    statement = scale_bare_literals(statement, scale)
    definitions = [
        templates.fact_def(
            name,
            scaled_int(number, scale),
            _provenance(fact),
            doc=_doc(fact.statement) or fact.fact_id,
        )
        for name, (fact, number) in selected.items()
    ]
    namespace = _namespace(inference.inference_id)
    theorem = templates.theorem(
        "claim",
        statement,
        "decide",
        doc=(
            f"Quantified claim for inference {inference.inference_id} "
            f"(all values scaled x{scale}): {_doc(inference.opinion)}"
        ),
    )
    return templates.join(
        [
            templates.file_header(
                ["BusyBee.Common"],
                f"Generated Lean check for inference {inference.inference_id}. "
                f"Every number is scaled by x{scale} (money in crore, percent in percent).",
            ),
            f"namespace {namespace}",
            f"-- scale: x{scale}",
            templates.section("Scaled facts"),
            *definitions,
            templates.section("Claim"),
            theorem,
            f"end {namespace}",
        ]
    )


def _write_text(path: Path, text: str) -> None:
    """Write text atomically, creating the parent directory when needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(text, encoding="utf-8")
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def _artifact_id(run_id: str, inference_id: str) -> str:
    """Return the artifact id for one inference in a run."""
    return f"{run_id}:{inference_id}" if run_id else inference_id


def _failed_artifact(
    inference: Inference,
    path: Path,
    source: str,
    message: str,
    run_id: str,
):
    """Build an inference artifact carrying a failed compile result."""
    artifact = make_artifact(
        _artifact_id(run_id, inference.inference_id),
        "inference",
        path,
        source,
        CompileResult(ok=False, stderr=message),
    )
    return inference.model_copy(update={"lean": artifact})


async def quantify_inference(
    inference: Inference,
    lean_claim: LeanClaim,
    facts: Sequence[VerifiedFact] | Mapping[str, VerifiedFact],
    *,
    output_dir: str | Path,
    run_id: str = "infer",
) -> Inference:
    """Build and compile one inference's Lean file, keeping failures as artifacts."""
    directory = Path(output_dir)
    path = directory / _file_name(inference.inference_id)
    try:
        source = build_lean_source(inference, lean_claim, facts)
    except QuantifyError as error:
        logger.warning("cannot quantify %s: %s", inference.inference_id, error)
        source = templates.file_header(
            [],
            f"Cannot quantify inference {inference.inference_id}: {error}",
        )
        try:
            _write_text(path, source)
        except OSError:
            logger.exception("could not write failed Lean source for %s", inference.inference_id)
        return _failed_artifact(inference, path, source, str(error), run_id)
    try:
        _write_text(path, source)
        compile_result = await compile_file(path)
    except Exception as error:
        logger.exception("Lean compile crashed for %s", inference.inference_id)
        return _failed_artifact(inference, path, source, str(error), run_id)
    if not compile_result.ok:
        logger.warning(
            "Lean check failed for %s: %s",
            inference.inference_id,
            lean_failure_message(compile_result),
        )
    artifact = make_artifact(
        _artifact_id(run_id, inference.inference_id),
        "inference",
        path,
        source,
        compile_result,
    )
    return inference.model_copy(update={"lean": artifact})


async def quantify_inferences(
    items: Sequence[tuple[Inference, LeanClaim]],
    facts: Sequence[VerifiedFact] | Mapping[str, VerifiedFact],
    *,
    output_dir: str | Path,
    run_id: str = "infer",
) -> list[Inference]:
    """Quantify independent inferences concurrently, preserving their order."""
    return list(
        await asyncio.gather(
            *(
                quantify_inference(
                    inference,
                    lean_claim,
                    facts,
                    output_dir=output_dir,
                    run_id=run_id,
                )
                for inference, lean_claim in items
            )
        )
    )


quantify = quantify_inference
