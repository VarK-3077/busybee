import BusyBee.Common
import BusyBee.Policy.DemoBank

/-!
# Scores for this run

Bound facts, the bank-defined score functions applied to them,
`#eval` lines whose stdout carries the values, and `decide` proofs of those values.
-/

-- SECTION: Facts

/-- financial_strength_score input cfads: Cash flow available for debt service: EBITDA less cash taxes paid (INR crore x 100). -/
def financial_strength_score_cfads : Int := 11850 -- F058 D2:p5:c0

/-- financial_strength_score input debt_service: Interest paid plus scheduled principal repayments in the year (INR crore x 100). -/
def financial_strength_score_debt_service : Int := 6660 -- F059 D2:p5:c0

/-- financial_strength_score input total_debt: Total borrowings (short and long term, including current maturities and leases) (INR crore x 100). -/
def financial_strength_score_total_debt : Int := 38200 -- F042 D1:p2:c0 D2:p3:c0

/-- financial_strength_score input total_equity: Shareholders' equity (net worth) at year end (INR crore x 100). -/
def financial_strength_score_total_equity : Int := 30000 -- F063 D2:p7:c0

/-- financial_strength_score input current_assets: Total current assets at year end (INR crore x 100). -/
def financial_strength_score_current_assets : Int := 41300 -- F060 D2:p6:c0

/-- financial_strength_score input current_liabilities: Total current liabilities at year end (INR crore x 100). -/
def financial_strength_score_current_liabilities : Int := 32400 -- F061 D2:p6:c0

/-- financial_strength_score input revenue_current: Revenue from operations, latest audited year (INR crore x 100). -/
def financial_strength_score_revenue_current : Int := 93120 -- F010 D1:p1:c0 D2:p2:c0

/-- financial_strength_score input revenue_previous: Revenue from operations, previous audited year (INR crore x 100). -/
def financial_strength_score_revenue_previous : Int := 84550 -- F010 D1:p1:c0 D2:p2:c0

/-- financial_strength_score input ebitda: Operating profit before depreciation, interest and tax, excluding other income (INR crore x 100). -/
def financial_strength_score_ebitda : Int := 13040 -- F043 D1:p3:c0 | note: chosen by code: the operating profit before row of the profit and loss statement (F043)

/-- financial_strength_score input interest_expense: Gross finance cost for the year (INR crore x 100). -/
def financial_strength_score_interest_expense : Int := 3860 -- F018 D1:p1:c0 | note: chosen by code: the finance cost row of the profit and loss statement (F018)

/-- financial_strength_score input net_debt: Total borrowings less cash, bank balances and liquid investments, latest audited year (INR crore x 100). -/
def financial_strength_score_net_debt : Int := 35200 -- F087 D2:p3:c0

/-- internal_risk_grade input external_rating_index: Bank numeric index of the latest long-term external rating: AAA=1, AA+=2, ... BBB-=10, BB+=11, ... D=22 (index). -/
def internal_risk_grade_external_rating_index : Int := 5 -- F074 D4:p2:c0 | note: rating A+ maps to index 5 in the policy table

/-- internal_risk_grade input major_red_flag_count: Number of major red flags present under policy section 6 (count). -/
def internal_risk_grade_major_red_flag_count : Int := 0 -- F076 D4:p2:c0 | note: No evidence of major_red_flag_count in the candidate facts.

/-- internal_risk_grade input default_flag: 1 if any NPA, wilful default or one-time settlement in the last 36 months, else 0 (flag). -/
def internal_risk_grade_default_flag : Int := 0 -- F076 D4:p2:c0 | note: No evidence of default_flag in the candidate facts.

/-- maximum_exposure input projected_turnover: Projected annual turnover for the next financial year (INR crore x 100). -/
def maximum_exposure_projected_turnover : Int := 102430 -- F062 D2:p7:c0

/-- maximum_exposure input revenue_current: Revenue from operations, latest audited year (the audited turnover; projected turnover counts for at most 125% of it, policy section 7) (INR crore x 100). -/
def maximum_exposure_revenue_current : Int := 93120 -- F010 D1:p1:c0 D2:p2:c0

/-- maximum_exposure input tangible_net_worth: Tangible net worth at year end (INR crore x 100). -/
def maximum_exposure_tangible_net_worth : Int := 29240 -- F063 D2:p7:c0

/-- maximum_exposure input proposed_exposure: Proposed aggregate bank exposure including existing limits (INR crore x 100). -/
def maximum_exposure_proposed_exposure : Int := 43200 -- F086 REQ:p1:c1 | note: method: bank_input

-- SECTION: Scores

/-- Financial Strength Score, computed by the bank policy. -/
def financial_strength_score_value : Int := BusyBee.Policy.DemoBank.financial_strength_score financial_strength_score_net_debt financial_strength_score_ebitda financial_strength_score_interest_expense financial_strength_score_cfads financial_strength_score_debt_service financial_strength_score_total_debt financial_strength_score_total_equity financial_strength_score_current_assets financial_strength_score_current_liabilities financial_strength_score_revenue_current financial_strength_score_revenue_previous

/-- Grade label of Financial Strength Score. -/
def financial_strength_score_grade_label : String := BusyBee.Policy.DemoBank.financial_strength_score_grade financial_strength_score_net_debt financial_strength_score_ebitda financial_strength_score_interest_expense financial_strength_score_cfads financial_strength_score_debt_service financial_strength_score_total_debt financial_strength_score_total_equity financial_strength_score_current_assets financial_strength_score_current_liabilities financial_strength_score_revenue_current financial_strength_score_revenue_previous

#eval IO.println s!"financial_strength_score={financial_strength_score_value}"

#eval IO.println s!"financial_strength_score_grade={financial_strength_score_grade_label}"

/-- Internal Risk Grade, computed by the bank policy. -/
def internal_risk_grade_value : Int := BusyBee.Policy.DemoBank.internal_risk_grade financial_strength_score_value internal_risk_grade_external_rating_index internal_risk_grade_major_red_flag_count internal_risk_grade_default_flag

/-- Grade label of Internal Risk Grade. -/
def internal_risk_grade_grade_label : String := BusyBee.Policy.DemoBank.internal_risk_grade_grade financial_strength_score_value internal_risk_grade_external_rating_index internal_risk_grade_major_red_flag_count internal_risk_grade_default_flag

#eval IO.println s!"internal_risk_grade={internal_risk_grade_value}"

#eval IO.println s!"internal_risk_grade_grade={internal_risk_grade_grade_label}"

/-- Maximum Exposure test, computed by the bank policy. -/
def maximum_exposure_value : Int := BusyBee.Policy.DemoBank.maximum_exposure_test maximum_exposure_proposed_exposure maximum_exposure_projected_turnover maximum_exposure_revenue_current maximum_exposure_tangible_net_worth internal_risk_grade_value

/-- Grade label of Maximum Exposure test. -/
def maximum_exposure_grade_label : String := BusyBee.Policy.DemoBank.maximum_exposure_test_grade maximum_exposure_proposed_exposure maximum_exposure_projected_turnover maximum_exposure_revenue_current maximum_exposure_tangible_net_worth internal_risk_grade_value

#eval IO.println s!"maximum_exposure={maximum_exposure_value}"

#eval IO.println s!"maximum_exposure_grade={maximum_exposure_grade_label}"

-- SECTION: Checks

/-- Lean proves the Financial Strength Score equals 67. -/
theorem financial_strength_score_value_is : financial_strength_score_value = 67 := by
  decide

/-- Lean proves the Financial Strength Score grade is Adequate. -/
theorem financial_strength_score_grade_is : financial_strength_score_grade_label = "Adequate" := by
  decide

/-- Lean proves the Internal Risk Grade equals 3. -/
theorem internal_risk_grade_value_is : internal_risk_grade_value = 3 := by
  decide

/-- Lean proves the Internal Risk Grade grade is Low risk. -/
theorem internal_risk_grade_grade_is : internal_risk_grade_grade_label = "Low risk" := by
  decide

/-- Lean proves the Maximum Exposure test equals 15364. -/
theorem maximum_exposure_value_is : maximum_exposure_value = 15364 := by
  decide

/-- Lean proves the Maximum Exposure test grade is Exceeds limit. -/
theorem maximum_exposure_grade_is : maximum_exposure_grade_label = "Exceeds limit" := by
  decide

-- SECTION: Policy rules

/-- Rule net_debt_to_ebitda_max (Net debt / EBITDA at most 4.5x), policy section 4: Net debt / EBITDA exceeds the 4.5x minimum standard (or EBITDA is not positive); caution zone is above 3.5x. -/
def rule_net_debt_to_ebitda_max_holds : Bool := decide (financial_strength_score_ebitda > 0 ∧ 2 * financial_strength_score_net_debt ≤ 9 * financial_strength_score_ebitda)

/-- Caution zone of rule net_debt_to_ebitda_max. -/
def rule_net_debt_to_ebitda_max_in_zone : Bool := decide (2 * financial_strength_score_net_debt > 7 * financial_strength_score_ebitda)

/-- Status of rule net_debt_to_ebitda_max: pass, caution or fail. -/
def rule_net_debt_to_ebitda_max_status : String :=
  if rule_net_debt_to_ebitda_max_holds then (if rule_net_debt_to_ebitda_max_in_zone then "caution" else "pass") else "fail"

#eval IO.println s!"rule_net_debt_to_ebitda_max={rule_net_debt_to_ebitda_max_status}"

/-- Lean proves rule net_debt_to_ebitda_max (Net debt / EBITDA at most 4.5x) has status pass. -/
theorem rule_net_debt_to_ebitda_max_status_is : rule_net_debt_to_ebitda_max_status = "pass" := by
  decide

/-- Lean proves the condition of rule net_debt_to_ebitda_max holds. -/
theorem rule_net_debt_to_ebitda_max_met : financial_strength_score_ebitda > 0 ∧ 2 * financial_strength_score_net_debt ≤ 9 * financial_strength_score_ebitda := by
  decide

/-- Rule interest_coverage_min (Interest coverage at least 2.5x), policy section 4: Interest coverage (EBITDA / interest) is below the 2.5x minimum standard (or EBITDA is not positive); caution zone is below 4.0x. -/
def rule_interest_coverage_min_holds : Bool := decide (financial_strength_score_ebitda > 0 ∧ 2 * financial_strength_score_ebitda ≥ 5 * financial_strength_score_interest_expense)

/-- Caution zone of rule interest_coverage_min. -/
def rule_interest_coverage_min_in_zone : Bool := decide (financial_strength_score_ebitda < 4 * financial_strength_score_interest_expense)

/-- Status of rule interest_coverage_min: pass, caution or fail. -/
def rule_interest_coverage_min_status : String :=
  if rule_interest_coverage_min_holds then (if rule_interest_coverage_min_in_zone then "caution" else "pass") else "fail"

#eval IO.println s!"rule_interest_coverage_min={rule_interest_coverage_min_status}"

/-- Lean proves rule interest_coverage_min (Interest coverage at least 2.5x) has status caution. -/
theorem rule_interest_coverage_min_status_is : rule_interest_coverage_min_status = "caution" := by
  decide

/-- Lean proves the condition of rule interest_coverage_min holds. -/
theorem rule_interest_coverage_min_met : financial_strength_score_ebitda > 0 ∧ 2 * financial_strength_score_ebitda ≥ 5 * financial_strength_score_interest_expense := by
  decide

/-- Lean proves the borrower is inside the caution zone of rule interest_coverage_min. -/
theorem rule_interest_coverage_min_in_caution_zone : financial_strength_score_ebitda < 4 * financial_strength_score_interest_expense := by
  decide

/-- Rule dscr_min (DSCR at least 1.25x), policy section 4: DSCR (CFADS / debt service) is below the 1.25x minimum standard; caution zone is below 1.50x. -/
def rule_dscr_min_holds : Bool := decide ((financial_strength_score_debt_service ≤ 0) ∨ (100 * financial_strength_score_cfads ≥ 125 * financial_strength_score_debt_service))

/-- Caution zone of rule dscr_min. -/
def rule_dscr_min_in_zone : Bool := decide (financial_strength_score_debt_service > 0 ∧ 100 * financial_strength_score_cfads < 150 * financial_strength_score_debt_service)

/-- Status of rule dscr_min: pass, caution or fail. -/
def rule_dscr_min_status : String :=
  if rule_dscr_min_holds then (if rule_dscr_min_in_zone then "caution" else "pass") else "fail"

#eval IO.println s!"rule_dscr_min={rule_dscr_min_status}"

/-- Lean proves rule dscr_min (DSCR at least 1.25x) has status pass. -/
theorem rule_dscr_min_status_is : rule_dscr_min_status = "pass" := by
  decide

/-- Lean proves the condition of rule dscr_min holds. -/
theorem rule_dscr_min_met : (financial_strength_score_debt_service ≤ 0) ∨ (100 * financial_strength_score_cfads ≥ 125 * financial_strength_score_debt_service) := by
  decide

/-- Rule current_ratio_min (Current ratio at least 1.10x), policy section 4: Current ratio is below the 1.10x minimum standard; caution zone is below 1.33x. -/
def rule_current_ratio_min_holds : Bool := decide (100 * financial_strength_score_current_assets ≥ 110 * financial_strength_score_current_liabilities)

/-- Caution zone of rule current_ratio_min. -/
def rule_current_ratio_min_in_zone : Bool := decide (100 * financial_strength_score_current_assets < 133 * financial_strength_score_current_liabilities)

/-- Status of rule current_ratio_min: pass, caution or fail. -/
def rule_current_ratio_min_status : String :=
  if rule_current_ratio_min_holds then (if rule_current_ratio_min_in_zone then "caution" else "pass") else "fail"

#eval IO.println s!"rule_current_ratio_min={rule_current_ratio_min_status}"

/-- Lean proves rule current_ratio_min (Current ratio at least 1.10x) has status caution. -/
theorem rule_current_ratio_min_status_is : rule_current_ratio_min_status = "caution" := by
  decide

/-- Lean proves the condition of rule current_ratio_min holds. -/
theorem rule_current_ratio_min_met : 100 * financial_strength_score_current_assets ≥ 110 * financial_strength_score_current_liabilities := by
  decide

/-- Lean proves the borrower is inside the caution zone of rule current_ratio_min. -/
theorem rule_current_ratio_min_in_caution_zone : 100 * financial_strength_score_current_assets < 133 * financial_strength_score_current_liabilities := by
  decide

/-- Rule debt_to_equity_max (Total debt / equity at most 3.0x), policy section 4: Total debt / equity exceeds the 3.0x minimum standard (or equity is not positive); caution zone is above 2.0x. -/
def rule_debt_to_equity_max_holds : Bool := decide (financial_strength_score_total_equity > 0 ∧ financial_strength_score_total_debt ≤ 3 * financial_strength_score_total_equity)

/-- Caution zone of rule debt_to_equity_max. -/
def rule_debt_to_equity_max_in_zone : Bool := decide (financial_strength_score_total_debt > 2 * financial_strength_score_total_equity)

/-- Status of rule debt_to_equity_max: pass, caution or fail. -/
def rule_debt_to_equity_max_status : String :=
  if rule_debt_to_equity_max_holds then (if rule_debt_to_equity_max_in_zone then "caution" else "pass") else "fail"

#eval IO.println s!"rule_debt_to_equity_max={rule_debt_to_equity_max_status}"

/-- Lean proves rule debt_to_equity_max (Total debt / equity at most 3.0x) has status pass. -/
theorem rule_debt_to_equity_max_status_is : rule_debt_to_equity_max_status = "pass" := by
  decide

/-- Lean proves the condition of rule debt_to_equity_max holds. -/
theorem rule_debt_to_equity_max_met : financial_strength_score_total_equity > 0 ∧ financial_strength_score_total_debt ≤ 3 * financial_strength_score_total_equity := by
  decide

/-- Rule revenue_trend_min (Revenue trend not below -10%), policy section 4: Year-on-year revenue fell by more than 10%, below the minimum standard; caution zone is any decline. -/
def rule_revenue_trend_min_holds : Bool := decide (financial_strength_score_revenue_previous > 0 ∧ 10 * financial_strength_score_revenue_current ≥ 9 * financial_strength_score_revenue_previous)

/-- Caution zone of rule revenue_trend_min. -/
def rule_revenue_trend_min_in_zone : Bool := decide (financial_strength_score_revenue_current < financial_strength_score_revenue_previous)

/-- Status of rule revenue_trend_min: pass, caution or fail. -/
def rule_revenue_trend_min_status : String :=
  if rule_revenue_trend_min_holds then (if rule_revenue_trend_min_in_zone then "caution" else "pass") else "fail"

#eval IO.println s!"rule_revenue_trend_min={rule_revenue_trend_min_status}"

/-- Lean proves rule revenue_trend_min (Revenue trend not below -10%) has status pass. -/
theorem rule_revenue_trend_min_status_is : rule_revenue_trend_min_status = "pass" := by
  decide

/-- Lean proves the condition of rule revenue_trend_min holds. -/
theorem rule_revenue_trend_min_met : financial_strength_score_revenue_previous > 0 ∧ 10 * financial_strength_score_revenue_current ≥ 9 * financial_strength_score_revenue_previous := by
  decide

/-- Rule tangible_net_worth_positive (Tangible net worth positive), policy section 2: Tangible net worth is not positive, so the borrower is ineligible under the eligibility rules. -/
def rule_tangible_net_worth_positive_holds : Bool := decide (maximum_exposure_tangible_net_worth > 0)

/-- Status of rule tangible_net_worth_positive: pass, caution or fail. -/
def rule_tangible_net_worth_positive_status : String :=
  if rule_tangible_net_worth_positive_holds then "pass" else "fail"

#eval IO.println s!"rule_tangible_net_worth_positive={rule_tangible_net_worth_positive_status}"

/-- Lean proves rule tangible_net_worth_positive (Tangible net worth positive) has status pass. -/
theorem rule_tangible_net_worth_positive_status_is : rule_tangible_net_worth_positive_status = "pass" := by
  decide

/-- Lean proves the condition of rule tangible_net_worth_positive holds. -/
theorem rule_tangible_net_worth_positive_met : maximum_exposure_tangible_net_worth > 0 := by
  decide

/-- Rule external_rating_min (External rating at least BBB-), policy section 5: The external rating is below BBB- (index above 10), which is not acceptable (the secured SME exception below INR 25 crore needs a manual decision). -/
def rule_external_rating_min_holds : Bool := decide (internal_risk_grade_external_rating_index ≤ 10)

/-- Status of rule external_rating_min: pass, caution or fail. -/
def rule_external_rating_min_status : String :=
  if rule_external_rating_min_holds then "pass" else "fail"

#eval IO.println s!"rule_external_rating_min={rule_external_rating_min_status}"

/-- Lean proves rule external_rating_min (External rating at least BBB-) has status pass. -/
theorem rule_external_rating_min_status_is : rule_external_rating_min_status = "pass" := by
  decide

/-- Lean proves the condition of rule external_rating_min holds. -/
theorem rule_external_rating_min_met : internal_risk_grade_external_rating_index ≤ 10 := by
  decide

/-- Rule default_flag_clear (No default flag), policy section 6: A default flag is raised (NPA, wilful default or one-time settlement in the last 36 months), which forces the Internal Risk Grade to 8 and a decline. -/
def rule_default_flag_clear_holds : Bool := decide (internal_risk_grade_default_flag ≤ 0)

/-- Status of rule default_flag_clear: pass, caution or fail. -/
def rule_default_flag_clear_status : String :=
  if rule_default_flag_clear_holds then "pass" else "fail"

#eval IO.println s!"rule_default_flag_clear={rule_default_flag_clear_status}"

/-- Lean proves rule default_flag_clear (No default flag) has status pass. -/
theorem rule_default_flag_clear_status_is : rule_default_flag_clear_status = "pass" := by
  decide

/-- Lean proves the condition of rule default_flag_clear holds. -/
theorem rule_default_flag_clear_met : internal_risk_grade_default_flag ≤ 0 := by
  decide

/-- Rule major_red_flags_below_two (Fewer than two major red flags), policy section 6: Two or more major red flags are present, which is a mandatory referral to the credit committee. -/
def rule_major_red_flags_below_two_holds : Bool := decide (internal_risk_grade_major_red_flag_count ≤ 1)

/-- Status of rule major_red_flags_below_two: pass, caution or fail. -/
def rule_major_red_flags_below_two_status : String :=
  if rule_major_red_flags_below_two_holds then "pass" else "fail"

#eval IO.println s!"rule_major_red_flags_below_two={rule_major_red_flags_below_two_status}"

/-- Lean proves rule major_red_flags_below_two (Fewer than two major red flags) has status pass. -/
theorem rule_major_red_flags_below_two_status_is : rule_major_red_flags_below_two_status = "pass" := by
  decide

/-- Lean proves the condition of rule major_red_flags_below_two holds. -/
theorem rule_major_red_flags_below_two_met : internal_risk_grade_major_red_flag_count ≤ 1 := by
  decide

/-- Rule no_major_red_flag (No major red flag), policy section 11: One major red flag is present, which allows approval only with conditions. -/
def rule_no_major_red_flag_holds : Bool := decide (internal_risk_grade_major_red_flag_count ≤ 0)

/-- Status of rule no_major_red_flag: pass, caution or fail. -/
def rule_no_major_red_flag_status : String :=
  if rule_no_major_red_flag_holds then "pass" else "caution"

#eval IO.println s!"rule_no_major_red_flag={rule_no_major_red_flag_status}"

/-- Lean proves rule no_major_red_flag (No major red flag) has status pass. -/
theorem rule_no_major_red_flag_status_is : rule_no_major_red_flag_status = "pass" := by
  decide

/-- Lean proves the condition of rule no_major_red_flag holds. -/
theorem rule_no_major_red_flag_met : internal_risk_grade_major_red_flag_count ≤ 0 := by
  decide

/-- Rule exposure_within_cap (Proposed exposure within the maximum exposure), policy section 10.3: The proposed exposure is above the maximum permissible exposure; it must be reduced to the maximum exposure. -/
def rule_exposure_within_cap_holds : Bool := decide (maximum_exposure_proposed_exposure ≤ maximum_exposure_value)

/-- Status of rule exposure_within_cap: pass, caution or fail. -/
def rule_exposure_within_cap_status : String :=
  if rule_exposure_within_cap_holds then "pass" else "fail"

#eval IO.println s!"rule_exposure_within_cap={rule_exposure_within_cap_status}"

/-- Lean proves rule exposure_within_cap (Proposed exposure within the maximum exposure) has status fail. -/
theorem rule_exposure_within_cap_status_is : rule_exposure_within_cap_status = "fail" := by
  decide

/-- Lean proves the condition of rule exposure_within_cap is violated. -/
theorem rule_exposure_within_cap_violated : ¬ (maximum_exposure_proposed_exposure ≤ maximum_exposure_value) := by
  decide

/-- Rule irg_not_decline (Internal Risk Grade 1 to 7), policy section 11: Internal Risk Grade is 8, which the decision rules decline. -/
def rule_irg_not_decline_holds : Bool := decide (internal_risk_grade_value ≤ 7)

/-- Status of rule irg_not_decline: pass, caution or fail. -/
def rule_irg_not_decline_status : String :=
  if rule_irg_not_decline_holds then "pass" else "fail"

#eval IO.println s!"rule_irg_not_decline={rule_irg_not_decline_status}"

/-- Lean proves rule irg_not_decline (Internal Risk Grade 1 to 7) has status pass. -/
theorem rule_irg_not_decline_status_is : rule_irg_not_decline_status = "pass" := by
  decide

/-- Lean proves the condition of rule irg_not_decline holds. -/
theorem rule_irg_not_decline_met : internal_risk_grade_value ≤ 7 := by
  decide

/-- Rule irg_not_committee_only (Internal Risk Grade 1 to 5), policy section 11: Internal Risk Grade is 6 or 7 (high risk), which the decision rules refer to the credit committee. -/
def rule_irg_not_committee_only_holds : Bool := decide (internal_risk_grade_value ≤ 5)

/-- Status of rule irg_not_committee_only: pass, caution or fail. -/
def rule_irg_not_committee_only_status : String :=
  if rule_irg_not_committee_only_holds then "pass" else "fail"

#eval IO.println s!"rule_irg_not_committee_only={rule_irg_not_committee_only_status}"

/-- Lean proves rule irg_not_committee_only (Internal Risk Grade 1 to 5) has status pass. -/
theorem rule_irg_not_committee_only_status_is : rule_irg_not_committee_only_status = "pass" := by
  decide

/-- Lean proves the condition of rule irg_not_committee_only holds. -/
theorem rule_irg_not_committee_only_met : internal_risk_grade_value ≤ 5 := by
  decide

/-- Rule irg_low_risk (Internal Risk Grade 1 to 3), policy section 11: Internal Risk Grade is 4 or 5 (acceptable risk), which allows approval only with conditions. -/
def rule_irg_low_risk_holds : Bool := decide (internal_risk_grade_value ≤ 3)

/-- Status of rule irg_low_risk: pass, caution or fail. -/
def rule_irg_low_risk_status : String :=
  if rule_irg_low_risk_holds then "pass" else "caution"

#eval IO.println s!"rule_irg_low_risk={rule_irg_low_risk_status}"

/-- Lean proves rule irg_low_risk (Internal Risk Grade 1 to 3) has status pass. -/
theorem rule_irg_low_risk_status_is : rule_irg_low_risk_status = "pass" := by
  decide

/-- Lean proves the condition of rule irg_low_risk holds. -/
theorem rule_irg_low_risk_met : internal_risk_grade_value ≤ 3 := by
  decide
