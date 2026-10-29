"""Writes data/companies/<slug>/manifest.json (file -> {title, kind, url, fetched_at, pages}) and data/companies/README.md.

PDFs are opened with PyMuPDF and must have more than 0 pages; HTML and markdown documents count as 1 page.
Run: uv run --no-project --with pymupdf python data/tools/build_company_manifests.py
"""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

ROOT = Path("data/companies")
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%d")
CRISIL = "https://www.crisil.com/mnt/winshare/Ratings/RatingList/RatingDocs/"
ICRA = "https://www.icra.in/Rating/ShowRationalReportFilePdfViewer/"

COMPANIES = {
    "indoco_remedies": ("Indoco Remedies Limited", "pharma", "dev", {
        "annual_report_fy2025_26.pdf": ("Indoco Remedies Annual Report 2025-26 (79th)", "annual_report", "https://www.indoco.com/annual-reports/79annualreport2025-2026.pdf"),
        "icra_rationale_2026-09-30.pdf": ("ICRA rating rationale, 30 Sep 2026 (ratings reaffirmed)", "rating_rationale", ICRA + "146083"),
        "icra_rationale_2025-09-24.pdf": ("ICRA rating rationale, 24 Sep 2025 (reaffirmed, enhanced amount)", "rating_rationale", ICRA + "137958"),
    }),
    "craftsman_automation": ("Craftsman Automation Limited", "manufacturing (auto components)", "dev", {
        "annual_report_fy2025_26.pdf": ("Craftsman Automation Annual Report 2025-26 (40th)", "annual_report", "https://www.craftsmanautomation.com/investors/wp-content/uploads/2026/06/Annual-Report-2026.pdf"),
        "drhp_2020-12.pdf": ("Craftsman Automation Draft Red Herring Prospectus, Dec 2020", "drhp", "https://listing.bseindia.com/download/349406/CraftsmanAutomationLimited_DraftRedHerringProspectus_20201215152058.pdf"),
        "crisil_rationale_2025-12-12.html": ("CRISIL rating rationale, 12 Dec 2025 (AA-/Stable reaffirmed)", "rating_rationale", CRISIL + "CraftsmanAutomationLimited_December%2012_%202025_RR_385207.html"),
    }),
    "bikaji_foods": ("Bikaji Foods International Limited", "consumer (packaged foods)", "eval", {
        "annual_report_fy2025_26.pdf": ("Bikaji Foods Annual Report 2025-26", "annual_report", "https://www.bikaji.com/pub/media/Bikaji-Annual-Report-2025-26.pdf"),
        "drhp_2022-02.pdf": ("Bikaji Foods Draft Red Herring Prospectus, 22 Feb 2022", "drhp", "https://investmentbank.kotak.com/downloads/bikaji-foods-international-limited-DRHP.pdf"),
        "icra_rationale_2025-08-25.pdf": ("ICRA rating rationale, 25 Aug 2025 (AA-/Stable reaffirmed)", "rating_rationale", ICRA + "137188"),
    }),
    "ashoka_buildcon": ("Ashoka Buildcon Limited", "infrastructure (roads, EPC)", "eval", {
        "annual_report_fy2025_26.pdf": ("Ashoka Buildcon Annual Report 2025-26", "annual_report", "https://www.ashokabuildcon.com/files/investors/financial-info/ABL_AR_FY_25-26.pdf"),
        "crisil_rationale_2026-06-12.html": ("CRISIL rating rationale, 12 Jun 2026 (AA-/Negative reaffirmed and withdrawn)", "rating_rationale", CRISIL + "AshokaBuildconLimited_June%2012_%202026_RR_397950.html"),
        "care_rationale_2026-01.pdf": ("CARE Ratings press release, Jan 2026 (AA- on Rating Watch with Positive Implications)", "rating_rationale", "https://www.careratings.com/upload/CompanyFiles/PR/202601150144_Ashoka_Buildcon_Limited.pdf"),
    }),
    "tata_capital": ("Tata Capital Limited", "NBFC", "eval", {
        "annual_report_fy2025_26.pdf": ("Tata Capital Annual Report 2025-26 (35th)", "annual_report", "https://www.tatacapital.com/content/dam/tata-capital/pdf/investors-and-financial-reports/annual-reports/25-26/tata-capital-limited-annual-report-fy-2025-26.pdf"),
        "rhp_2025.pdf": ("Tata Capital Red Herring Prospectus, 26 Sep 2025", "drhp", "https://www.bnpparibas.bank.in/app/uploads/sites/25/2025/09/tata-capital-limited-rhp-vf.pdf"),
        "crisil_rationale_2026-07-22.html": ("CRISIL rating rationale, 22 Jul 2026 (AAA/Stable)", "rating_rationale", CRISIL + "TataCapitalLimited_July%2022_%202026_RR_400616.html"),
        "icra_rationale_2026-07-21.pdf": ("ICRA rating rationale, 21 Jul 2026 (AAA/Stable)", "rating_rationale", ICRA + "144339"),
    }),
}


def pages_of(path: Path) -> int:
    if path.suffix == ".pdf":
        with pymupdf.open(path) as doc:
            return len(doc)
    return 1


def news_entry(path: Path) -> tuple[str, str]:
    text = path.read_text()
    title = text.splitlines()[0].lstrip("# ").strip()
    url = re.search(r"- URL: (\S+)", text).group(1)
    return title, url


def main() -> None:
    rows = []
    for slug, (name, sector, split, docs) in COMPANIES.items():
        folder = ROOT / slug
        manifest = {}
        for fname, (title, kind, url) in docs.items():
            p = folder / fname
            if not p.exists():
                continue
            n = pages_of(p)
            assert n > 0, p
            manifest[fname] = {"title": title, "kind": kind, "url": url, "fetched_at": NOW, "pages": n}
        for p in sorted(folder.glob("news_*.md")):
            title, url = news_entry(p)
            manifest[p.name] = {"title": title, "kind": "news", "url": url, "fetched_at": NOW, "pages": 1}
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
        size = sum((folder / f).stat().st_size for f in manifest) / 1e6
        kinds = ", ".join(f"{sum(1 for m in manifest.values() if m['kind'] == k)} {k}" for k in dict.fromkeys(m["kind"] for m in manifest.values()))
        rows.append(f"| {name} (`{slug}`) | {sector} | {split} | {kinds} | {size:.1f} MB |")
    table = "| Company | Sector | Set | Documents | Size |\n|---|---|---|---|---|\n" + "\n".join(rows) + "\n"
    (ROOT / "README.table.md").write_text(table)
    print(table)


main()
