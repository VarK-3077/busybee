import BusyBee.Common

/-!
# Demo Bank of India — Lean formalisation of the bank-defined scores

Formalises policy.md section 10 (Financial Strength Score, Internal Risk Grade, Maximum
Exposure test) exactly as listed in scores.yaml. Money is INR crore × 100 (12.34 crore is
`1234`); ratios are never divided, every band is a cross-multiplied inequality (for example
`net debt / EBITDA ≤ 2.5` is `2 * net_debt ≤ 5 * ebitda`). Each score has a value function
named in scores.yaml (arguments follow the order of the input slots, result is an `Int`)
and a `_grade` function returning the grade label exactly as written in scores.yaml.
-/

namespace BusyBee.Policy.DemoBank

open BusyBee

-- SECTION: Financial Strength Score components (policy 10.1)

/-- Net debt / EBITDA band, max 25 points; zero when EBITDA is not positive.
`net_debt` is total borrowings (including current maturities and leases) minus cash and bank
balances minus liquid investments (policy section 4); the binder derives it from signed fact terms. -/
def leverage_points (net_debt ebitda : Int) : Int :=
  if ebitda ≤ 0 then 0
  else if 2 * net_debt ≤ 3 * ebitda then 25
  else if 2 * net_debt ≤ 5 * ebitda then 20
  else if 2 * net_debt ≤ 7 * ebitda then 14
  else if 2 * net_debt ≤ 9 * ebitda then 7
  else 0

/-- Interest coverage (EBITDA / interest) band, max 20 points; non-positive interest meets every band. -/
def interest_cover_points (ebitda interest_expense : Int) : Int :=
  if interest_expense ≤ 0 then 20
  else if 6 * interest_expense ≤ ebitda then 20
  else if 4 * interest_expense ≤ ebitda then 15
  else if 5 * interest_expense ≤ 2 * ebitda then 10
  else if 3 * interest_expense ≤ 2 * ebitda then 5
  else 0

/-- DSCR (CFADS / debt service) band, max 20 points; zero debt service meets every band.
`cfads` is EBITDA minus cash taxes paid; `debt_service` is interest paid plus scheduled principal
repayments in the year (policy section 4); the binder derives both from signed fact terms. -/
def dscr_points (cfads debt_service : Int) : Int :=
  if debt_service ≤ 0 then 20
  else if 2 * debt_service ≤ cfads then 20
  else if 3 * debt_service ≤ 2 * cfads then 15
  else if 5 * debt_service ≤ 4 * cfads then 10
  else if debt_service ≤ cfads then 4
  else 0

/-- Current ratio band, max 15 points; a non-positive denominator earns nothing (conservative). -/
def current_ratio_points (current_assets current_liabilities : Int) : Int :=
  if current_liabilities ≤ 0 then 0
  else if 3 * current_liabilities ≤ 2 * current_assets then 15
  else if 5 * current_liabilities ≤ 4 * current_assets then 11
  else if current_liabilities ≤ current_assets then 6
  else 0

/-- Total debt / equity band, max 10 points; zero when equity is not positive. -/
def debt_equity_points (total_debt total_equity : Int) : Int :=
  if total_equity ≤ 0 then 0
  else if total_debt ≤ total_equity then 10
  else if total_debt ≤ 2 * total_equity then 7
  else if total_debt ≤ 3 * total_equity then 3
  else 0

/-- Revenue growth band, max 10 points; zero when previous revenue is not positive (conservative). -/
def revenue_growth_points (revenue_current revenue_previous : Int) : Int :=
  if revenue_previous ≤ 0 then 0
  else if 11 * revenue_previous ≤ 10 * revenue_current then 10
  else if revenue_previous ≤ revenue_current then 6
  else if 9 * revenue_previous ≤ 10 * revenue_current then 2
  else 0

/-- The six component maxima add up to 100. -/
theorem component_maxima_sum_to_100 : (25 : Int) + 20 + 20 + 15 + 10 + 10 = 100 := by decide

-- SECTION: Financial Strength Score

/-- Financial Strength Score, 0 to 100: the sum of the six band scores. -/
def financial_strength_score
    (net_debt ebitda interest_expense cfads debt_service total_debt total_equity
      current_assets current_liabilities revenue_current revenue_previous : Int) : Int :=
  leverage_points net_debt ebitda
    + interest_cover_points ebitda interest_expense
    + dscr_points cfads debt_service
    + current_ratio_points current_assets current_liabilities
    + debt_equity_points total_debt total_equity
    + revenue_growth_points revenue_current revenue_previous

/-- Grade label of the Financial Strength Score: Strong, Adequate, Moderate or Weak. -/
def financial_strength_score_grade
    (net_debt ebitda interest_expense cfads debt_service total_debt total_equity
      current_assets current_liabilities revenue_current revenue_previous : Int) : String :=
  let score := financial_strength_score net_debt ebitda interest_expense cfads debt_service
    total_debt total_equity current_assets current_liabilities revenue_current revenue_previous
  if 80 ≤ score then "Strong"
  else if 60 ≤ score then "Adequate"
  else if 40 ≤ score then "Moderate"
  else "Weak"

-- SECTION: Minimum standards (policy 4)

/-- Net debt / EBITDA: pass up to 3.5 times, watch up to 4.5 times, fail above or if EBITDA is not positive. -/
def leverage_standard (net_debt ebitda : Int) : Grade :=
  if ebitda ≤ 0 then Grade.fail
  else if 2 * net_debt ≤ 7 * ebitda then Grade.pass
  else if 2 * net_debt ≤ 9 * ebitda then Grade.watch
  else Grade.fail

/-- Interest coverage: pass from 4.0 times, watch from 2.5 times, fail below. -/
def interest_cover_standard (ebitda interest_expense : Int) : Grade :=
  if interest_expense ≤ 0 then Grade.pass
  else if 4 * interest_expense ≤ ebitda then Grade.pass
  else if 5 * interest_expense ≤ 2 * ebitda then Grade.watch
  else Grade.fail

/-- DSCR: pass from 1.50 times, watch from 1.25 times, fail below. -/
def dscr_standard (cfads debt_service : Int) : Grade :=
  if debt_service ≤ 0 then Grade.pass
  else if 3 * debt_service ≤ 2 * cfads then Grade.pass
  else if 5 * debt_service ≤ 4 * cfads then Grade.watch
  else Grade.fail

-- SECTION: Internal Risk Grade (policy 10.2)

/-- Step 1: base grade from the Financial Strength Score, 1 (best) to 8. -/
def base_grade (fss : Int) : Int :=
  if 85 ≤ fss then 1
  else if 75 ≤ fss then 2
  else if 65 ≤ fss then 3
  else if 55 ≤ fss then 4
  else if 45 ≤ fss then 5
  else if 35 ≤ fss then 6
  else if 25 ≤ fss then 7
  else 8

/-- Step 2: rating floor, the best grade obtainable for an external rating index. The index comes
from the `mapping` table in scores.yaml (policy section 5: AAA = 1 ... A = 6 ... BBB- = 10, BB+ = 11
... C = 17, D = 22), applied to the latest long-term rating grade a fact states. -/
def rating_floor (external_rating_index : Int) : Int :=
  if external_rating_index ≤ 3 then 1
  else if external_rating_index ≤ 6 then 2
  else if external_rating_index ≤ 8 then 3
  else if external_rating_index = 9 then 4
  else if external_rating_index = 10 then 5
  else if external_rating_index ≤ 13 then 6
  else if external_rating_index ≤ 16 then 7
  else 8

/-- Step 3: red-flag notches, one per major red flag, at most 3. -/
def red_flag_notches (major_red_flag_count : Int) : Int :=
  if major_red_flag_count ≤ 0 then 0
  else if major_red_flag_count ≤ 3 then major_red_flag_count
  else 3

/-- Internal Risk Grade, 1 to 8: worse of base and floor, plus notches, capped at 8; a default flag forces 8. -/
def internal_risk_grade
    (financial_strength_score external_rating_index major_red_flag_count default_flag : Int) :
    Int :=
  let stepped := max (base_grade financial_strength_score) (rating_floor external_rating_index)
  let notched := stepped + red_flag_notches major_red_flag_count
  if 0 < default_flag then 8
  else if 8 ≤ notched then 8
  else notched

/-- Grade label of the Internal Risk Grade: Low risk, Acceptable risk, High risk or Decline. -/
def internal_risk_grade_grade
    (financial_strength_score external_rating_index major_red_flag_count default_flag : Int) :
    String :=
  let g := internal_risk_grade financial_strength_score external_rating_index
    major_red_flag_count default_flag
  if g ≤ 3 then "Low risk"
  else if g ≤ 5 then "Acceptable risk"
  else if g ≤ 7 then "High risk"
  else "Decline"

-- SECTION: Maximum Exposure test (policy 10.3)

/-- Exposure percentage P set by the Internal Risk Grade. -/
def exposure_percentage (internal_risk_grade : Int) : Int :=
  if internal_risk_grade ≤ 2 then 100
  else if internal_risk_grade ≤ 4 then 75
  else if internal_risk_grade = 5 then 50
  else if internal_risk_grade = 6 then 25
  else 0

/-- Turnover the cap is based on, scaled by 4: the smaller of 4 times the projected turnover and 5
times the latest audited turnover, so the projection counts for at most 125 percent of audited
turnover (policy section 7). -/
def capped_turnover_x4 (projected_turnover audited_turnover : Int) : Int :=
  min (4 * projected_turnover) (5 * audited_turnover)

/-- Both caps hold: `2000 * proposed ≤ P * capped turnover x4` (that is `P% × 20%` of the smaller of
projected turnover and 125 percent of audited turnover) and `100 * proposed ≤ P * net worth`.
`proposed_exposure` and `projected_turnover` are bank inputs from the credit request;
`audited_turnover` is the latest audited revenue from operations; tangible net worth is
shareholders' equity minus intangible assets (derived from signed fact terms). -/
def within_exposure_limit
    (proposed_exposure projected_turnover audited_turnover tangible_net_worth
      internal_risk_grade : Int) : Bool :=
  let p := exposure_percentage internal_risk_grade
  decide (2000 * proposed_exposure ≤ p * capped_turnover_x4 projected_turnover audited_turnover)
    && decide (100 * proposed_exposure ≤ p * tangible_net_worth)

/-- Maximum permissible exposure in INR crore × 100: the smaller of the turnover cap
(`P% × 20% ×` the smaller of projected turnover and 125 percent of audited turnover, that is
`P × capped turnover x4 / 2000`) and the net-worth cap (`P% × tangible net worth`, that is
`P × net worth / 100`); integer division rounds down. -/
def maximum_exposure_test
    (_proposed_exposure projected_turnover audited_turnover tangible_net_worth
      internal_risk_grade : Int) : Int :=
  let p := exposure_percentage internal_risk_grade
  min (p * capped_turnover_x4 projected_turnover audited_turnover / 2000)
    (p * tangible_net_worth / 100)

/-- Grade label of the Maximum Exposure test: Within limit or Exceeds limit, decided by the exact
cross-multiplied comparison of the proposed exposure against both caps. -/
def maximum_exposure_test_grade
    (proposed_exposure projected_turnover audited_turnover tangible_net_worth
      internal_risk_grade : Int) : String :=
  if within_exposure_limit proposed_exposure projected_turnover audited_turnover
      tangible_net_worth internal_risk_grade then "Within limit" else "Exceeds limit"

-- SECTION: Guarantees for every borrower

/-- A default flag always forces grade 8, whatever the score, rating or red flags. -/
theorem default_flag_forces_grade_8 (fss rating flags flag : Int) (h : 0 < flag) :
    internal_risk_grade fss rating flags flag = 8 := by
  unfold internal_risk_grade
  simp only [h, ite_true]

/-- No external rating can rescue weak financials: a Financial Strength Score below 25 always gives grade 8. -/
theorem weak_financials_get_grade_8 (fss rating flags flag : Int) (h : fss < 25) :
    internal_risk_grade fss rating flags flag = 8 := by
  unfold internal_risk_grade red_flag_notches base_grade rating_floor
  dsimp only
  repeat' split <;> omega

/-- The grade is never better than the financial base grade: a lower number is a better grade, and
the final grade is at least the grade the Financial Strength Score alone would give. -/
theorem grade_not_better_than_base (fss rating flags flag : Int) :
    base_grade fss ≤ internal_risk_grade fss rating flags flag := by
  unfold internal_risk_grade red_flag_notches base_grade rating_floor
  dsimp only
  repeat' split <;> omega

/-- The grade is never better than the floor set by the external rating. -/
theorem grade_not_better_than_rating_floor (fss rating flags flag : Int) :
    rating_floor rating ≤ internal_risk_grade fss rating flags flag := by
  unfold internal_risk_grade red_flag_notches base_grade rating_floor
  dsimp only
  repeat' split <;> omega

/-- Grades 7 and 8 permit no exposure: any proposed exposure above zero is outside the limit,
whatever the turnover and tangible net worth. -/
theorem grades_7_and_8_permit_no_exposure
    (proposed turnover audited net_worth grade : Int) (hg : 7 ≤ grade) (hp : 0 < proposed) :
    within_exposure_limit proposed turnover audited net_worth grade = false := by
  have h0 : exposure_percentage grade = 0 := by
    unfold exposure_percentage
    repeat' split <;> omega
  unfold within_exposure_limit
  simp only [h0]
  simp only [Int.zero_mul, Bool.and_eq_false_iff, decide_eq_false_iff_not]
  omega

/-- A loan is never more than 25 percent of the latest audited turnover: whenever a positive
proposed exposure is within the limit, four times the proposed exposure is at most the audited
turnover, however high the projected turnover is. -/
theorem limit_bounded_by_audited_turnover
    (proposed turnover audited net_worth grade : Int) (hp : 0 < proposed)
    (h : within_exposure_limit proposed turnover audited net_worth grade = true) :
    4 * proposed ≤ audited := by
  have hp100 : exposure_percentage grade ≤ 100 := by
    unfold exposure_percentage
    repeat' split <;> omega
  have hp0 : 0 ≤ exposure_percentage grade := by
    unfold exposure_percentage
    repeat' split <;> omega
  unfold within_exposure_limit capped_turnover_x4 at h
  simp only [Bool.and_eq_true, decide_eq_true_eq] at h
  obtain ⟨h1, _⟩ := h
  generalize exposure_percentage grade = p at hp100 hp0 h1
  have h2 : p * min (4 * turnover) (5 * audited) ≤ p * (5 * audited) :=
    Int.mul_le_mul_of_nonneg_left (Int.min_le_right _ _) hp0
  by_cases ha : 0 ≤ audited
  · have h3 : 0 ≤ (100 - p) * (5 * audited) := Int.mul_nonneg (by omega) (by omega)
    have h4 : (100 - p) * (5 * audited) = 100 * (5 * audited) - p * (5 * audited) := by
      rw [Int.sub_mul]
    omega
  · have h3 : p * (5 * audited) ≤ 0 :=
      Int.mul_nonpos_of_nonneg_of_nonpos hp0 (by omega)
    omega

/-- More net debt never earns more leverage points, for any EBITDA. -/
theorem more_debt_never_earns_more_leverage_points (d1 d2 e : Int) (h : d1 ≤ d2) :
    leverage_points d2 e ≤ leverage_points d1 e := by
  unfold leverage_points
  repeat' split <;> omega

/-- More interest expense never earns more interest-cover points, for any EBITDA. -/
theorem more_interest_never_earns_more_cover_points (e i1 i2 : Int) (h : i1 ≤ i2) :
    interest_cover_points e i2 ≤ interest_cover_points e i1 := by
  unfold interest_cover_points
  repeat' split <;> omega

/-- The leverage points always lie between 0 and 25. -/
theorem leverage_points_between (a b : Int) :
    0 ≤ leverage_points a b ∧ leverage_points a b ≤ 25 := by
  unfold leverage_points
  repeat' split <;> omega

/-- The interest cover points always lie between 0 and 20. -/
theorem interest_cover_points_between (a b : Int) :
    0 ≤ interest_cover_points a b ∧ interest_cover_points a b ≤ 20 := by
  unfold interest_cover_points
  repeat' split <;> omega

/-- The dscr points always lie between 0 and 20. -/
theorem dscr_points_between (a b : Int) :
    0 ≤ dscr_points a b ∧ dscr_points a b ≤ 20 := by
  unfold dscr_points
  repeat' split <;> omega

/-- The current ratio points always lie between 0 and 15. -/
theorem current_ratio_points_between (a b : Int) :
    0 ≤ current_ratio_points a b ∧ current_ratio_points a b ≤ 15 := by
  unfold current_ratio_points
  repeat' split <;> omega

/-- The debt equity points always lie between 0 and 10. -/
theorem debt_equity_points_between (a b : Int) :
    0 ≤ debt_equity_points a b ∧ debt_equity_points a b ≤ 10 := by
  unfold debt_equity_points
  repeat' split <;> omega

/-- The revenue growth points always lie between 0 and 10. -/
theorem revenue_growth_points_between (a b : Int) :
    0 ≤ revenue_growth_points a b ∧ revenue_growth_points a b ≤ 10 := by
  unfold revenue_growth_points
  repeat' split <;> omega

/-- The Financial Strength Score is never negative. -/
theorem fss_at_least_0 (nd eb ie cf ds td te ca cl rc rp : Int) :
    0 ≤ financial_strength_score nd eb ie cf ds td te ca cl rc rp := by
  unfold financial_strength_score
  have h0 := leverage_points_between nd eb
  have h1 := interest_cover_points_between eb ie
  have h2 := dscr_points_between cf ds
  have h3 := current_ratio_points_between ca cl
  have h4 := debt_equity_points_between td te
  have h5 := revenue_growth_points_between rc rp
  omega

/-- The Financial Strength Score never exceeds 100. -/
theorem fss_at_most_100 (nd eb ie cf ds td te ca cl rc rp : Int) :
    financial_strength_score nd eb ie cf ds td te ca cl rc rp ≤ 100 := by
  unfold financial_strength_score
  have h0 := leverage_points_between nd eb
  have h1 := interest_cover_points_between eb ie
  have h2 := dscr_points_between cf ds
  have h3 := current_ratio_points_between ca cl
  have h4 := debt_equity_points_between td te
  have h5 := revenue_growth_points_between rc rp
  omega

-- SECTION: Sanity theorems

/-- Worked example: a default flag gives grade 8 even with a score of 100. -/
theorem default_flag_example : internal_risk_grade 100 1 0 1 = 8 := by decide

/-- Grade 3 (P = 75), turnover 1,024.3 crore, net worth 292.4 crore: the cap is 153.64 crore
(turnover cap 153.64, net-worth cap 219.3), so a proposed 432 crore exceeds it. -/
theorem exposure_cap_example : maximum_exposure_test 43200 102430 102430 29240 3 = 15364 := by decide

/-- The same example is graded "Exceeds limit". -/
theorem exposure_grade_example :
    maximum_exposure_test_grade 43200 102430 102430 29240 3 = "Exceeds limit" := by decide

/-- Grades 7 and 8 allow no exposure at all. -/
theorem no_exposure_for_grade_7 : exposure_percentage 7 = 0 := by decide

/-- A borrower that meets the net debt / EBITDA minimum standard (at most 4.5 times, policy section 4)
never earns fewer than 7 leverage points (section 10.1): the standard and the score bands agree,
including a borrower exactly at the 4.5 times limit. -/
theorem standard_met_earns_leverage_points (net_debt ebitda : Int) (h_pos : 0 < ebitda)
    (h_met : 2 * net_debt ≤ 9 * ebitda) : 7 ≤ leverage_points net_debt ebitda := by
  unfold leverage_points
  repeat' split <;> omega

end BusyBee.Policy.DemoBank
