import BusyBee.Common

/-!
# Worked example

Demonstrates the conventions every generated Lean file follows: scaled `Int` facts with
provenance comments, thresholds written as cross-multiplied inequalities, and proofs by
`decide` or `omega`.
-/

namespace BusyBee.Example

-- SECTION: Scaled facts

/-- Net debt for FY26, in INR crore × 100. -/
def netDebt : Int := 125000 -- F012 D1:p214:c2

/-- EBITDA for FY26, in INR crore × 100. -/
def ebitda : Int := 42000 -- F013 D1:p214:c2

-- SECTION: Threshold checks

/-- Net debt is at most 3.5 times EBITDA, proved by cross-multiplication. -/
theorem leverage_within_limit : 2 * netDebt ≤ 7 * ebitda := by decide

/-- Interest expense for FY26, in INR crore × 100. -/
def interest : Int := 15000 -- F014 D1:p215:c1

/-- EBITDA covers interest at least twice. -/
theorem interest_cover_at_least_two : 2 * interest ≤ ebitda := by decide

-- SECTION: Arithmetic

/-- A linear fact closed by `omega` from a positivity hypothesis. -/
theorem headroom_positive (h : 0 < ebitda) : 0 < ebitda + 1000 := by omega

/-- The leverage grade for this borrower. -/
def leverageGrade : Grade := gradeAtMost (2 * netDebt) (7 * ebitda)

end BusyBee.Example
