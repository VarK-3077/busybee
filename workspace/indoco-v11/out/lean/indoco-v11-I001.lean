import BusyBee.Common

/-!
Generated Lean check for inference I001. Every number is scaled by x10 (money in crore, percent in percent).
-/

namespace BusyBee.Inference.I001

-- scale: x10

-- SECTION: Scaled facts

/-- Consolidated net debt to equity ratio was 113.4% as at March 31, 2026 (March 31, 2025: 95.9%). -/
def net_debt_equity : Int := 1134 -- F145 D1:p326:c0

/-- The group's net debt to equity ratio was 113.4% as at March 31, 2026, exceeding the group's strategy to maintain a gearing ratio within 50%. -/
def gearing_target : Int := 500 -- F141 D1:p326:c0

-- SECTION: Claim

/-- Quantified claim for inference I001 (all values scaled x10): The consolidated group is in a severe financial distress position, with a net loss that widened significantly year-on-year and a net debt-to-equity ratio that has breached the company's own 50% gearing strategy. -/
theorem claim : net_debt_equity > gearing_target := by
  decide

end BusyBee.Inference.I001
