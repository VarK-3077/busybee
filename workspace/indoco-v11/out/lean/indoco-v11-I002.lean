import BusyBee.Common

/-!
Generated Lean check for inference I002. Every number is scaled by x10 (money in crore, percent in percent).
-/

namespace BusyBee.Inference.I002

-- scale: x10

-- SECTION: Scaled facts

/-- DSCR was weak at 0.7 times in FY2026. -/
def dscr : Int := 7 -- F228 D3:p2:c0

/-- Interest coverage was weak at 1.2 times in FY2026. -/
def interest_coverage : Int := 12 -- F227 D3:p2:c0

-- SECTION: Claim

/-- Quantified claim for inference I002 (all values scaled x10): Repayment capacity is critically weak, as evidenced by a company-reported DSCR of 0.7 times and an interest coverage ratio of 1.2 times, both of which are below the minimum threshold of 1.0 times required for adequate debt service. -/
theorem claim : dscr < 10 && interest_coverage < 20 := by
  decide

end BusyBee.Inference.I002
