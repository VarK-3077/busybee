"""Convert a fact's decimal value and unit into the scaled integer a score input slot expects.

Money slots (unit mentions crore) take lakh, million, billion, thousand, crore or rupee facts
and are stored as crore times the slot scale. Basis-point slots take percent or basis-point facts.
Every other slot is dimensionless (count, index, flag, points) and is multiplied by its scale.
A money value converted from another unit (lakh, million, ...) is rounded half-up to the
slot's scale (0.01 crore for scale 100: under half a lakh, immaterial to every ratio and
threshold), because a two-decimal lakh figure is never a whole multiple of 0.01 crore; a value
already in the slot's own unit must be exact. Anything ambiguous or not exactly
representable raises `ScalingError` instead of guessing,
so a bad binding leaves the slot unbound rather than silently wrong. `format_score_value`
goes the other way: it turns the integer Lean printed for a score into its display text,
dividing by the score's `value_scale` and appending its unit when the scale is above 1.
"""

from decimal import ROUND_HALF_UP, Decimal, localcontext

from busybee.schema.policy import InputSlot, ScoreSpec

_TO_CRORE: dict[str, Decimal] = {
    "crore": Decimal(1),
    "crores": Decimal(1),
    "cr": Decimal(1),
    "lakh": Decimal("0.01"),
    "lakhs": Decimal("0.01"),
    "lac": Decimal("0.01"),
    "million": Decimal("0.1"),
    "millions": Decimal("0.1"),
    "mn": Decimal("0.1"),
    "billion": Decimal(100),
    "billions": Decimal(100),
    "bn": Decimal(100),
    "thousand": Decimal("1e-4"),
    "thousands": Decimal("1e-4"),
    "rupee": Decimal("1e-7"),
    "rupees": Decimal("1e-7"),
    "inr": Decimal("1e-7"),
    "rs": Decimal("1e-7"),
}
_PERCENT = {"%", "percent", "pct", "per cent"}
_BASIS_POINTS = {"bps", "bp", "basis points", "basis point"}
_DIMENSIONLESS = {"", "x", "times", "count", "number", "points", "index", "flag", "grade"}


class ScalingError(ValueError):
    """Raised when a value cannot be converted exactly into a slot's integer scale."""


def _words(unit: str) -> list[str]:
    """Lowercase unit text split into words, keeping a lone percent sign as a word."""
    return unit.lower().replace("%", " % ").replace("₹", " inr ").replace("×", " x ").split()


def _crore_factor(unit: str) -> Decimal:
    """Return how many crore one unit of the fact's money unit equals."""
    words = [word for word in _words(unit) if word in _TO_CRORE]
    scale_words = [word for word in words if word not in {"inr", "rs", "rupee", "rupees"}]
    chosen = scale_words or words
    if not chosen:
        raise ScalingError(f"unit {unit!r} is not a money unit (crore, lakh, million, billion)")
    if len(set(chosen)) > 1 and len({_TO_CRORE[word] for word in chosen}) > 1:
        raise ScalingError(f"unit {unit!r} mixes several money scales")
    return _TO_CRORE[chosen[0]]


def _basis_point_factor(unit: str) -> Decimal:
    """Return how many basis points one unit of the fact's percentage unit equals."""
    text = " ".join(_words(unit))
    if text in _BASIS_POINTS or any(word in {"bps", "bp"} for word in _words(unit)):
        return Decimal(1)
    if any(word in _PERCENT for word in _words(unit)) or text in _PERCENT:
        return Decimal(100)
    raise ScalingError(f"unit {unit!r} is not a percentage or basis-point unit")


def _plain_factor(unit: str, slot: InputSlot) -> Decimal:
    """Accept only dimensionless facts (or the slot's own unit) for a plain slot."""
    wanted = {word for word in _words(slot.unit)}
    given = set(_words(unit))
    if given <= _DIMENSIONLESS or (given and given <= wanted):
        return Decimal(1)
    raise ScalingError(f"unit {unit!r} does not fit slot {slot.slot!r} ({slot.unit!r})")


def to_scaled_int(value: Decimal, unit: str, slot: InputSlot) -> int:
    """Convert value in unit to the integer stored for the slot, or raise ScalingError."""
    target = slot.unit.lower()
    with localcontext() as context:
        context.prec = 60
        if "crore" in target:
            factor = _crore_factor(unit)
        elif "basis" in target or "bps" in target:
            factor = _basis_point_factor(unit)
        else:
            factor = _plain_factor(unit, slot)
        scaled = Decimal(value) * factor * Decimal(slot.scale)
        converted_money = "crore" in target and factor != 1
        integral = scaled.to_integral_value(rounding=ROUND_HALF_UP if converted_money else None)
        if scaled != integral and not converted_money:
            raise ScalingError(
                f"{value} {unit} is not a whole number at scale {slot.scale} for {slot.slot!r}"
            )
        return int(integral)


def format_score_value(spec: ScoreSpec, printed: str) -> str:
    """Display text of a printed integer score value, e.g. 15364 at scale 100 -> '153.64 crore'."""
    if spec.value_scale <= 1:
        return printed
    shown = (Decimal(printed) / spec.value_scale).quantize(Decimal(1) / spec.value_scale)
    text = f"{shown:f}".rstrip("0").rstrip(".") if "." in f"{shown:f}" else f"{shown:f}"
    return f"{text} {spec.unit}".strip()
