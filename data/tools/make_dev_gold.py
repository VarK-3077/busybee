"""Writes data/gold/indoco_remedies.json and data/gold/craftsman_automation.json: ~30 analyst-style material facts each.

Facts are drawn from the latest rating rationale and the annual report summary pages. page_hint is the 1-based page of the
PDF file as stored in data/companies/<slug>/ (HTML documents count as page 1).
Run: python3 data/tools/make_dev_gold.py
"""
import json
from pathlib import Path

I_RR, I_AR = "icra_rationale_2026-09-30.pdf", "annual_report_fy2025_26.pdf"
INDOCO = [
    ("ICRA reaffirmed Indoco's long-term ratings at [ICRA]A with a Negative outlook and short-term ratings at [ICRA]A2+ on Rs 1,019.65 crore of facilities (30 September 2026).", "ratings", I_RR, 1),
    ("Rated facilities comprise Rs 400.00 crore term loans, Rs 94.40 crore cash credit and Rs 335.00 crore short-term fund-based limits among others.", "debt_leverage", I_RR, 1),
    ("The Negative outlook reflects elevated debt, weak debt-protection metrics and moderately high working capital intensity despite recovery in FY2026 operations.", "ratings", I_RR, 1),
    ("Consolidated revenue grew 10.8% to Rs 1,845.3 crore in FY2026.", "revenue", I_RR, 1),
    ("Export formulation revenues grew 28.7% in FY2026, with regulated markets up 14.4% and non-regulated markets up 65.5%.", "revenue", I_RR, 1),
    ("USFDA permitted restart of two of four production lines at Goa Plant II by July 2025 after the lines were shut in April 2024.", "litigation_regulatory", I_RR, 3),
    ("Goa Plants II and III received OAI status in June 2023 and a USFDA warning letter followed the February 2024 re-audit.", "litigation_regulatory", I_RR, 3),
    ("A USFDA reinspection of Goa Plant II on 27 August to 4 September 2026 resulted in seven Form 483 observations.", "litigation_regulatory", I_RR, 2),
    ("Operating margin improved to 7.7% in FY2026 from 6.0% in FY2025 and to 8.8% in Q1 FY2027 from 4.0%.", "profitability", I_RR, 2),
    ("Q1 FY2027 operating income rose 6.0% year on year to Rs 467.5 crore.", "revenue", I_RR, 2),
    ("Net loss widened to Rs 98.7 crore in FY2026 from Rs 78.0 crore in FY2025 because of higher depreciation and finance costs.", "profitability", I_RR, 4),
    ("Total debt was Rs 1,084.2 crore at 31 March 2026 and total debt to OPBDITA was 7.6 times.", "debt_leverage", I_RR, 2),
    ("Interest coverage was 1.2 times and DSCR 0.7 times in FY2026.", "debt_leverage", I_RR, 2),
    ("Working capital intensity was 34.6% in FY2026 against 37.7% in FY2025.", "liquidity", I_RR, 4),
    ("Inventory days fell to 124 from 139, while creditor days rose to 198 from 141 amid cash-flow pressure.", "liquidity", I_RR, 4),
    ("Liquidity is adequate: free cash and liquid investments were Rs 26.2 crore and average working capital utilisation was 90.7% over 12 months to July 2026.", "liquidity", I_RR, 4),
    ("Debt servicing obligations are Rs 145.8 crore for FY2027 and Rs 145.3 crore for FY2028.", "debt_leverage", I_RR, 4),
    ("Indoco received about Rs 100 crore from monetising its ophthalmic business and about Rs 64 crore from a Mumbai land sale in H1 FY2027.", "liquidity", I_RR, 2),
    ("Warren Remedies (OTC oral care subsidiary) revenue rose about 34% to Rs 120.6 crore in FY2026 but its loss before tax widened to Rs 64.3 crore from Rs 36.0 crore.", "profitability", I_RR, 4),
    ("Domestic and export formulations contributed 46.6% and 36.8% of FY2026 revenues respectively.", "revenue", I_RR, 3),
    ("About 11% to 13% of domestic formulations are under NLEM price controls.", "litigation_regulatory", I_RR, 3),
    ("Rating downgrade triggers include inability to scale additional capacities and delays in resolving regulatory non-compliance.", "ratings", I_RR, 5),
    ("The rating history shows downgrades from AA- (Negative) to A (Negative) between January and August 2025.", "ratings", "icra_rationale_2025-09-24.pdf", 1),
    ("Consolidated income from operations was Rs 1,845.32 crore in FY2026 against Rs 1,664.92 crore in FY2025.", "revenue", I_AR, 58),
    ("Consolidated net profit after tax was a loss of Rs 98.67 crore in FY2026 against a loss of Rs 77.95 crore in FY2025.", "profitability", I_AR, 58),
    ("Consolidated finance cost rose to Rs 122.25 crore from Rs 66.23 crore, and depreciation to Rs 126.45 crore from Rs 113.84 crore.", "debt_leverage", I_AR, 58),
    ("Consolidated EBITDA (profit before finance cost, depreciation and tax) was Rs 145.16 crore against Rs 104.71 crore.", "profitability", I_AR, 58),
    ("The board recommended a dividend of Rs 0.20 per equity share of Rs 2, the same as the previous year.", "stock", I_AR, 59),
    ("The auditors' report includes an Emphasis of Matter on going-concern uncertainty at an investee (FPP Holding LLC) with a net loss of Rs 2,365.21 lakh and negative net worth of Rs 4,225.11 lakh; the opinion is not modified.", "litigation_regulatory", I_AR, 173),
    ("The company reports it has not defaulted in repayment of dues or other borrowings or interest to any lender (CARO statement).", "credit_history", I_AR, 182),
]

C_RR, C_AR = "crisil_rationale_2025-12-12.html", "annual_report_fy2025_26.pdf"
CRAFTSMAN = [
    ("CRISIL reaffirmed Craftsman Automation at Crisil AA-/Stable for long-term and Crisil A1+ short-term on bank facilities enhanced to Rs 3,950 crore from Rs 2,300 crore (12 December 2025).", "ratings", C_RR, 1),
    ("Consolidated operating revenue was Rs 3,786 crore in H1 FY2026 against Rs 2,365 crore a year earlier.", "revenue", C_RR, 1),
    ("Consolidated revenue grew 28% to Rs 5,693 crore in fiscal 2025 from Rs 4,452 crore; the aluminium segment grew about 41%.", "revenue", C_RR, 1),
    ("Aluminium contributed over 60% of H1 FY2026 revenue, powertrain 27% and industrial and engineering 13%.", "revenue", C_RR, 1),
    ("Consolidated operating margin fell to 14.9% in fiscal 2025 from about 20% earlier, owing to consolidation of Sunbeam and lower standalone margins.", "profitability", C_RR, 1),
    ("Operating margin was about 15% in H1 FY2026 versus 16.5% a year earlier; CRISIL expects about 15% for the year.", "profitability", C_RR, 1),
    ("Gearing was about 0.78 times at 31 March 2025 against 0.91 times a year earlier.", "debt_leverage", C_RR, 1),
    ("Interest cover was 3.97 times and debt to EBITDA 2.53 times in fiscal 2025 versus 5.79 times and 1.70 times in fiscal 2023.", "debt_leverage", C_RR, 1),
    ("Debt was Rs 2,141 crore at 31 March 2025 and Rs 3,038 crore at 30 September 2025, expected near Rs 3,500 crore by March 2026.", "debt_leverage", C_RR, 1),
    ("Debt to EBITDA is expected at about 2.8 to 2.9 times in fiscal 2026 and below 2.5 times thereafter.", "debt_leverage", C_RR, 1),
    ("Capex of about Rs 1,200 crore is planned in fiscal 2026 for Sunbeam modernisation, phase II expansions and greenfield facilities.", "debt_leverage", C_RR, 1),
    ("The company raised Rs 1,200 crore through a QIP in June 2024 (net Rs 1,176.7 crore), repaying over Rs 650 crore of debt and buying the residual 24% of DR Axion for Rs 250 crore.", "debt_leverage", C_RR, 1),
    ("CRISIL rates subsidiary Sunbeam Lightweighting at BBB-/Positive/A3 and DR Axion at AA-/Stable/A1+.", "ratings", C_RR, 1),
    ("Gross current assets average 160 to 170 days, with inventory of close to 4 months and receivables near 2 months.", "liquidity", C_RR, 1),
    ("Liquidity is strong: annual accruals of about Rs 760 crore this fiscal against repayments of about Rs 180 crore, and average utilisation of the Rs 1,010 crore standalone bank limit was about 56%.", "liquidity", C_RR, 1),
    ("The auto segment will account for over 85% of revenues, making performance vulnerable to an auto sector slowdown.", "industry_market", C_RR, 1),
    ("Board is 67% independent directors and 33% women.", "ownership_governance", C_RR, 1),
    ("Consolidated operating revenue was Rs 8,069.27 crore in FY2026 against Rs 5,690.48 crore in FY2025.", "revenue", C_AR, 4),
    ("Standalone operating revenue was Rs 4,818.08 crore in FY2026 against Rs 3,847.95 crore.", "revenue", C_AR, 4),
    ("Consolidated EBITDA was Rs 1,300.07 crore in FY2026 against Rs 858.78 crore in FY2025.", "profitability", C_AR, 4),
    ("Consolidated finance cost was Rs 308.97 crore against Rs 216.64 crore; depreciation Rs 443.85 crore against Rs 347.02 crore.", "debt_leverage", C_AR, 4),
    ("Consolidated profit before tax was Rs 534.3 crore and profit after tax Rs 383.99 crore in FY2026 (FY2025: Rs 269.65 crore and Rs 200.87 crore).", "profitability", C_AR, 4),
    ("Standalone profit after tax was Rs 221.47 crore in FY2026 against Rs 93.69 crore.", "profitability", C_AR, 4),
    ("Consolidated other equity closed at Rs 3,252.13 crore at 31 March 2026.", "debt_leverage", C_AR, 4),
    ("Dividend paid in the year was Rs 11.93 crore against Rs 23.77 crore the previous year.", "stock", C_AR, 4),
    ("The board proposed a final dividend of Rs 11.25 per share of Rs 5 face value, a total of about Rs 26.84 crore.", "stock", C_AR, 139),
    ("Standalone long-term borrowings (including current portion) were Rs 2,202.75 crore at 31 March 2026 against Rs 1,509.56 crore a year earlier.", "debt_leverage", C_AR, 139),
    ("Standalone secured rupee term loans from banks stood at Rs 1,869.35 crore non-current and Rs 154.77 crore current at March 2026.", "debt_leverage", C_AR, 139),
    ("This is the 40th annual report of the company, for the year ended 31 March 2026.", "other", C_AR, 4),
]


def write(slug: str, company: str, facts: list) -> None:
    out = Path("data/gold") / f"{slug}.json"
    out.write_text(json.dumps({
        "company": company, "slug": slug,
        "material_facts": [{"statement": s, "category": c, "doc_hint": d, "page_hint": p, "must_have": True} for s, c, d, p in facts],
        "planted_errors": [],
    }, indent=2) + "\n")
    print(out, len(facts))


write("indoco_remedies", "Indoco Remedies Limited", INDOCO)
write("craftsman_automation", "Craftsman Automation Limited", CRAFTSMAN)
