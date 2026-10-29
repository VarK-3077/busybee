# Public company data

Real public documents for five Indian companies, used to test and evaluate BusyBee on realistic packs. PDFs are gitignored
(`data/companies/**/*.pdf`); each folder has a `manifest.json` of the form `{file: {title, kind, url, fetched_at, pages}}`
that the ingest stage of `busybee run` can use as its kind override. HTML rating rationales are single-page documents. All downloads are
untrusted third-party content; news items are plain-text extracts (URL and date at top). Documents were fetched on
2026-10-25. Regenerate manifests with
`uv run --no-project --with pymupdf python data/tools/build_company_manifests.py` (it checks every PDF opens with
PyMuPDF and has more than 0 pages).

## Split

* **Dev set** (gold files in `data/gold/`, used to tune prompts): `indoco_remedies`, `craftsman_automation`.
* **Eval set** (held out, no tuning): `bikaji_foods`, `ashoka_buildcon`, `tata_capital`.

## What was fetched

| Company | Sector | Set | Documents | Size |
|---|---|---|---|---|
| Indoco Remedies Limited (`indoco_remedies`) | pharma | dev | 1 annual_report, 2 rating_rationale, 2 news | 12.2 MB |
| Craftsman Automation Limited (`craftsman_automation`) | manufacturing (auto components) | dev | 1 annual_report, 1 drhp, 1 rating_rationale, 2 news | 10.2 MB |
| Bikaji Foods International Limited (`bikaji_foods`) | consumer (packaged foods) | eval | 1 annual_report, 1 drhp, 1 rating_rationale, 2 news | 21.4 MB |
| Ashoka Buildcon Limited (`ashoka_buildcon`) | infrastructure (roads, EPC) | eval | 1 annual_report, 2 rating_rationale, 2 news | 12.9 MB |
| Tata Capital Limited (`tata_capital`) | NBFC | eval | 1 annual_report, 1 drhp, 2 rating_rationale, 2 news | 14.4 MB |

Per-company contents (pages in each manifest):

* `indoco_remedies`: Annual Report 2025-26 (349 pp), ICRA rationales of 30 Sep 2026 and 24 Sep 2025, 2 news items (USFDA
  Form 483 at Goa; Q1 FY27 call). No DRHP: Indoco is a long-listed company.
* `craftsman_automation`: Annual Report 2025-26, DRHP Dec 2020 (454 pp), CRISIL rationale 12 Dec 2025 (HTML), 2 news items.
* `bikaji_foods`: Annual Report 2025-26, DRHP Feb 2022, ICRA rationale 25 Aug 2025, 2 news items.
* `ashoka_buildcon`: Annual Report 2025-26, CRISIL rationale 12 Jun 2026 (HTML; ratings withdrawn after reaffirmation),
  CARE press release Jan 2026, 2 news items. No DRHP (listed 2016, offer documents not fetched).
* `tata_capital`: Annual Report 2025-26 (584 pp), RHP Sep 2025 (836 pp, from a lead manager's site), CRISIL rationale
  22 Jul 2026 (HTML), ICRA rationale 21 Jul 2026, 2 news items.

## Not fetched

* DRHP/RHP for Indoco Remedies and Ashoka Buildcon (decades-old listings; not attempted beyond one search).
* Further rationales from other agencies (e.g. CRISIL for Bikaji; none found).
* Largest PDFs (Tata Capital RHP and annual report) are big for a "moderate-size" pack; drop them if runs are too slow.
