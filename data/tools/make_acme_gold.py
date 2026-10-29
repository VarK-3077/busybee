"""Writes data/gold/acme_textiles.json: material facts and planted errors for the synthetic Acme Textiles pack.

Run: python3 data/tools/make_acme_gold.py
"""
import json
from pathlib import Path

AR, FS, RR, CV, N1, N2, BS = ("annual_report.md", "financial_statements.pdf", "rating_rationale.md",
                              "covenant_sheet.md", "news_1.md", "news_2.md", "bank_statement_summary.md")

FACTS = [
    ("Revenue from operations was Rs 931.2 crore in FY25, up 10.1% from Rs 845.5 crore in FY24.", "revenue", AR, 2),
    ("Revenue was Rs 742.0 crore in FY23 and grew 13.9% in FY24.", "revenue", AR, 2),
    ("Exports contributed 34% of FY25 revenue, up from 31% in FY24.", "revenue", AR, 1),
    ("The top five customers accounted for 41% of FY25 revenue; the largest single customer 14%.", "industry_market", AR, 1),
    ("EBITDA was Rs 130.4 crore in FY25, a margin of 14.0% (FY24: Rs 120.9 crore, 14.3%).", "profitability", AR, 2),
    ("Profit after tax was Rs 38.5 crore in FY25 against Rs 37.1 crore in FY24 and Rs 29.5 crore in FY23.", "profitability", AR, 2),
    ("Finance costs rose to Rs 38.6 crore in FY25 from Rs 34.9 crore in FY24.", "debt_leverage", FS, 1),
    ("Total borrowings were Rs 382.0 crore at 31 March 2025 (Rs 351.0 crore a year earlier).", "debt_leverage", AR, 3),
    ("Net debt was Rs 352.0 crore at March 2025, equal to 2.7 times EBITDA.", "debt_leverage", AR, 3),
    ("Net worth was Rs 300.0 crore and total debt to equity was 1.27 times at March 2025.", "debt_leverage", AR, 3),
    ("Interest coverage (EBITDA to finance costs) was 3.4 times in FY25.", "debt_leverage", AR, 3),
    ("The debt service coverage ratio was 1.78 times in FY25.", "debt_leverage", AR, 3),
    ("The current ratio was 1.27 times, with current assets Rs 413.0 crore and current liabilities Rs 324.0 crore.", "liquidity", AR, 3),
    ("Cash and bank balances were Rs 21.4 crore and liquid investments Rs 8.6 crore at March 2025.", "liquidity", FS, 2),
    ("Cash flow from operations was Rs 70.4 crore in FY25 after a working-capital build-up of Rs 48.0 crore.", "cash_flow", FS, 3),
    ("Capital expenditure was Rs 62.0 crore in FY25, leaving free cash flow of about Rs 8.4 crore.", "cash_flow", RR, 2),
    ("The board approved a Rs 120 crore capex programme for FY26-27 to add 60,000 spindles, funded by a Rs 78 crore term loan and Rs 42 crore internal accruals.", "debt_leverage", AR, 3),
    ("Management expects net debt to EBITDA to peak at about 3.0 times in FY27.", "debt_leverage", AR, 3),
    ("Meridian Ratings reaffirmed Acme's long-term rating at MR A+ with Stable outlook and short-term rating MR A1 on Rs 432.0 crore of bank facilities (12 June 2025).", "ratings", RR, 1),
    ("Rating downside triggers include net debt to EBITDA above 3.5 times, interest coverage below 2.5 times and promoter pledge above 25%.", "ratings", RR, 2),
    ("Promoters held 58.4% of equity, of which 12.0% of their holding was pledged.", "ownership_governance", AR, 3),
    ("The statutory auditors issued an unmodified opinion with an Emphasis of Matter on an unprovided GST demand of Rs 14.2 crore.", "litigation_regulatory", AR, 4),
    ("Contingent liabilities not provided for totalled Rs 21.6 crore at March 2025.", "litigation_regulatory", AR, 4),
    ("There were no defaults in repayment of loans or interest during the year.", "credit_history", AR, 4),
    ("Average utilisation of fund-based working-capital limits (Rs 190.0 crore) was 84%, peaking at 97% in October 2024.", "liquidity", BS, 1),
    ("Two instances of overdrawing beyond the limit for more than 5 days occurred in October and November 2024; no cheque returns.", "credit_history", BS, 1),
    ("All financial covenants were complied with in FY25, including net debt/EBITDA 2.7 times against a 3.5 times cap.", "debt_leverage", CV, 1),
    ("Lenders consented to the Rs 120 crore expansion subject to net debt/EBITDA staying at or below 3.5 times.", "debt_leverage", CV, 1),
    ("Key risks include cotton price volatility, customer concentration, working-capital intensity and expansion execution.", "industry_market", AR, 4),
    ("Q1 FY26 revenue was Rs 238.4 crore, up 9% year on year, with operating margin of 13.6%.", "news", N2, 1),
]

ERRORS = [
    ("Acme Textiles closed FY25 with revenue of Rs 1,018 crore.",
     "Annual report and financial statements show FY25 revenue of Rs 931.2 crore; the news item in news_2.md is wrong."),
    ("The statutory auditors issued a qualified opinion on the FY25 financial statements.",
     "The opinion was unmodified, with only an Emphasis of Matter paragraph on the GST dispute."),
    ("Net debt to EBITDA was 1.9 times at March 2025.",
     "Net debt of Rs 352.0 crore over EBITDA of Rs 130.4 crore is 2.7 times."),
    ("Acme's long-term rating is MR AA with a Positive outlook.",
     "The rating is MR A+ with a Stable outlook."),
    ("Promoters have pledged 35% of their holding.",
     "The pledge is 12.0% of promoter holding."),
    ("Total borrowings were Rs 282 crore at 31 March 2025.",
     "Total borrowings were Rs 382.0 crore."),
]

gold = {
    "company": "Acme Textiles Limited",
    "slug": "acme_textiles",
    "material_facts": [
        {"statement": s, "category": c, "doc_hint": d, "page_hint": p, "must_have": True} for s, c, d, p in FACTS
    ],
    "planted_errors": [{"statement": s, "why_wrong": w} for s, w in ERRORS],
}
out = Path("data/gold/acme_textiles.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(gold, indent=2) + "\n")
print(len(FACTS), len(ERRORS))
