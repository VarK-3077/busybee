"""Generates data/synthetic/acme_textiles/financial_statements.pdf (3 pages: P&L, balance sheet, cash flow) with PyMuPDF.

Run: uv run --no-project --with pymupdf python data/tools/make_acme_financials_pdf.py
Figures must stay consistent with the other Acme Textiles documents and the gold file.
"""
import sys
from pathlib import Path

import fitz

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "data/synthetic/acme_textiles/financial_statements.pdf")

PAGES = [
    ("Statement of Profit and Loss for the year ended 31 March 2025", [
        ("Particulars (Rs crore)", "FY2024-25", "FY2023-24"),
        ("Revenue from operations", "931.2", "845.5"),
        ("Other income", "5.6", "5.0"),
        ("Total income", "936.8", "850.5"),
        ("Cost of materials consumed", "512.1", "466.0"),
        ("Employee benefit expense", "148.6", "136.2"),
        ("Other expenses", "140.1", "122.4"),
        ("EBITDA (excluding other income)", "130.4", "120.9"),
        ("Depreciation and amortisation", "46.0", "41.5"),
        ("Finance costs", "38.6", "34.9"),
        ("Profit before tax", "51.4", "49.5"),
        ("Tax expense", "12.9", "12.4"),
        ("Profit after tax", "38.5", "37.1"),
        ("Earnings per share (Rs)", "16.04", "15.46"),
    ]),
    ("Balance Sheet as at 31 March 2025", [
        ("Particulars (Rs crore)", "31 Mar 2025", "31 Mar 2024"),
        ("Share capital", "24.0", "24.0"),
        ("Reserves and surplus", "276.0", "239.9"),
        ("Net worth", "300.0", "263.9"),
        ("Long-term borrowings", "182.0", "181.0"),
        ("Other non-current liabilities", "30.0", "28.4"),
        ("Short-term borrowings", "168.0", "142.0"),
        ("Current maturities of long-term debt", "32.0", "28.0"),
        ("Trade payables", "96.0", "88.3"),
        ("Other current liabilities", "28.0", "25.1"),
        ("Total equity and liabilities", "836.0", "756.7"),
        ("Property, plant and equipment (net)", "372.0", "358.4"),
        ("Capital work in progress", "31.0", "27.0"),
        ("Intangibles, investments and other non-current assets", "20.0", "18.9"),
        ("Inventories", "212.0", "180.3"),
        ("Trade receivables", "148.5", "128.1"),
        ("Cash and bank balances", "21.4", "18.4"),
        ("Liquid investments", "8.6", "7.6"),
        ("Other current assets", "22.5", "18.0"),
        ("Total assets", "836.0", "756.7"),
        ("Total borrowings", "382.0", "351.0"),
    ]),
    ("Cash Flow Statement for the year ended 31 March 2025", [
        ("Particulars (Rs crore)", "FY2024-25", "FY2023-24"),
        ("Operating profit before working-capital changes", "130.4", "120.9"),
        ("Increase in working capital", "(48.0)", "(31.1)"),
        ("Income taxes paid", "(12.0)", "(15.2)"),
        ("Net cash from operating activities", "70.4", "74.6"),
        ("Purchase of property, plant and equipment", "(62.0)", "(71.0)"),
        ("Purchase of investments", "(1.0)", "(0.4)"),
        ("Other income received", "5.6", "5.2"),
        ("Net cash used in investing activities", "(57.4)", "(66.2)"),
        ("Net increase in borrowings", "31.0", "20.5"),
        ("Interest paid", "(38.6)", "(34.9)"),
        ("Dividend paid", "(2.4)", "(2.4)"),
        ("Net cash used in financing activities", "(10.0)", "(16.8)"),
        ("Net increase in cash and bank balances", "3.0", "(8.4)"),
        ("Cash and bank balances at end of year", "21.4", "18.4"),
    ]),
]


def build(out: Path) -> None:
    doc = fitz.open()
    for n, (title, rows) in enumerate(PAGES, start=1):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 60), "Acme Textiles Limited (synthetic)", fontsize=11, fontname="helv")
        page.insert_text((50, 85), title, fontsize=14, fontname="hebo")
        y = 125
        for i, (a, b, c) in enumerate(rows):
            font = "hebo" if i == 0 else "helv"
            page.insert_text((50, y), a, fontsize=10, fontname=font)
            page.insert_text((400, y), b, fontsize=10, fontname=font)
            page.insert_text((490, y), c, fontsize=10, fontname=font)
            y += 24
        page.insert_text((50, 800), f"Page {n} of {len(PAGES)}", fontsize=9, fontname="helv")
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


if __name__ == "__main__":
    build(OUT)
