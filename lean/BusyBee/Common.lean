/-!
# Shared conventions

Definitions and lemmas used by every BusyBee Lean file. All quantities are `Int` in a
declared integer scale: money is INR crore × 100 (two decimals), percentages are basis
points. Ratios are compared by cross-multiplication, never by division, so `decide` and
`omega` can close the generated goals.
-/

namespace BusyBee

/-- A credit grade, ordered from best to worst. -/
inductive Grade where
  | pass
  | watch
  | fail
  deriving DecidableEq, Repr, Inhabited

/-- A scaled two-decimal amount, kept as an `Int` in hundredths. -/
abbrev ScaledAmount := Int

/-- A percentage expressed in basis points (1% = 100 bps). -/
abbrev BasisPoints := Int

/-- The cross-multiplied form of `lhs / rhs ≤ threshold / scale` for positive denominators. -/
def ratioAtMost (lhs rhs threshold scale : Int) : Prop :=
  scale * lhs ≤ threshold * rhs

/-- `ratioAtMost` is monotone in its numerator when the scale is positive. -/
theorem ratioAtMost.mono_num {lhs lhs' rhs threshold scale : Int}
    (h : lhs' ≤ lhs) (hscale : 0 < scale) :
    ratioAtMost lhs rhs threshold scale → ratioAtMost lhs' rhs threshold scale := by
  intro hle
  unfold ratioAtMost at *
  exact Int.le_trans (Int.mul_le_mul_of_nonneg_left h (Int.le_of_lt hscale)) hle

/-- A non-positive numerator makes the cross-multiplied ratio at most zero. -/
theorem ratioAtMost_zero {lhs rhs : Int} (h : lhs ≤ 0) :
    ratioAtMost lhs rhs 0 1 := by
  unfold ratioAtMost
  omega

/-- Grade a value against a threshold: `pass` at or below it, `fail` above it. -/
def gradeAtMost (value threshold : Int) : Grade :=
  if value ≤ threshold then Grade.pass else Grade.fail

/-- Grade a basis-point value: `pass` at or below, `watch` up to twice it, `fail` beyond. -/
def gradeBps (value threshold : Int) : Grade :=
  if value ≤ threshold then Grade.pass
  else if value ≤ 2 * threshold then Grade.watch
  else Grade.fail

end BusyBee
