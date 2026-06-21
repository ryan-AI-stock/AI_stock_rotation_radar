# TW50/0050 Holdings Proxy Phase 2 Manifest

Task ID: `TASK-RADAR-TW50-0050-HOLDINGS-PROXY-PHASE2-001`

Status: `Phase 2 parser/archive feasibility / partial_blocked`

Files:

- `phase2_feasibility_report.md`
- `parser_feasibility.csv`
- `archive_pattern_checks.csv`
- `yuanta_0050_current_top10_sample_rows.csv`
- `yuanta_0050_holdings_proxy_phase2_readiness.json`

Verification performed:

- Downloaded current Yuanta 0050 monthly report from official Yuanta URL.
- Downloaded current Yuanta domestic fund quarterly holdings PDF from official
  Yuanta URL.
- Confirmed bundled runtime has `pdfplumber` and `pypdf`.
- Parsed current Yuanta 0050 monthly report top-10 holdings with `pdfplumber`.
- Mapped extracted names to local `data/market_universe.generated.csv` tickers.
- Tested sampled 2022/2023/2024/2025 historical URL patterns and rejected them
  because the downloaded content was HTML, not PDF.

This package is not formal-ready, contains no accepted 2022-2026 historical
snapshot coverage, and must not be used as exact TW50 official constituent
history.
