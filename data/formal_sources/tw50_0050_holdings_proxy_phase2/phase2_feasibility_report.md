# TW50/0050 Holdings Proxy Phase 2 Feasibility Report

Task ID: `TASK-RADAR-TW50-0050-HOLDINGS-PROXY-PHASE2-001`

Date: 2026-06-21

## Scope

This package continues Phase 1. It checks whether Yuanta 0050 holdings proxy can
move from "current PDF downloadable" to a practical historical snapshot source.

This package does not replace exact TW50 official point-in-time constituent
history.

Required flags:

- `source_mode`: `yuanta_0050_holdings_proxy`
- `is_proxy`: `true`
- `exact_tw50_official_constituents`: `false`
- `formal_ready`: `false`

## Short Answer

1. Can the current PDF be parsed into holdings data?
   - Partially yes. The current Yuanta 0050 monthly report can be parsed with
     `pdfplumber`, but it exposes the top 10 holdings, not a full 50-stock
     historical constituent table.
   - The current `元大國內基金季持股.pdf` can be parsed as tables, but the file
     downloaded on 2026-06-21 is dated `2018/09/30`, so it is not a valid
     2022-2026 current/history coverage source without a dated archive route.

2. Is there a stable historical archive route for 2022-01 to current?
   - Not confirmed. The official page exposes current/latest direct download
     URLs, but no verified date parameter, archive endpoint, or month-specific
     PDF URL pattern was found in this pass.
   - Sampled historical URL patterns returned HTML documents, not PDFs.

3. Can this enter Core proxy-specific readiness design?
   - Schema-only design can proceed.
   - Data ingestion/readiness cannot proceed as ready yet. Core must keep this
     source as `partial_blocked` until historical archive coverage and full or
     accepted holdings coverage are available.

## Parser Feasibility

Environment checked:

- Bundled Python: available
- `pdfplumber`: available
- `pypdf`: available
- `pdftotext`: not found in system PATH in the earlier Phase 1 check

Current Yuanta 0050 monthly report:

- URL: `https://www.yuantafunds.com/fund/download/1066元大台灣卓越50基金月報.pdf`
- File signature: `%PDF-1.7`
- Source date extracted: `2026年05月31日`
- Parser result: `partial_parse_current_top10`
- Extracted evidence: 10 rows of top holdings with name and weight percentage.
- Ticker source: local `data/market_universe.generated.csv` name mapping.

Current Yuanta domestic fund quarterly holdings PDF:

- URL: `https://www.yuantafunds.com/fund/download/元大國內基金季持股.pdf`
- Parser result: table extraction works.
- Extracted source date: `2018/09/30`
- Readiness impact: blocked for 2022-2026 until a historical/current archive
  route is found and dated files can be checked.

## Archive Feasibility

The official Yuanta overview HTML contains current/latest download links such as:

- `https://www.yuantafunds.com/fund/download/1066元大台灣卓越50基金月報.pdf`
- `https://www.yuantafunds.com/fund/download/元大國內基金季持股.pdf`

It did not expose a verified date parameter or stable historical archive endpoint
for month-specific 0050 holdings PDFs.

Sampled URL patterns for 2022/2023/2024/2025/2026 returned 302 on HEAD, but GET
downloaded HTML pages rather than PDF files. This is treated as `pattern_failed`,
not as historical coverage.

## Status

Phase 2 status: `parser_partial_archive_blocked`

This package has 10 current top-10 sample rows from the latest monthly report.
It has zero accepted historical snapshot rows for 2022-01 through current.

It must not be used to replay the 2022-2026 TW50/0050 pool, and it must not be
used to mark Core exact TW50 readiness as passed.

## Blockers

1. No stable historical monthly/quarterly archive route was verified.
2. Current monthly report provides top 10 holdings, not a full 50-stock table.
3. The downloaded domestic quarterly holdings PDF is parseable but dated
   `2018/09/30`, outside the target period.
4. Redistribution/license constraints still need review before publishing a
   historical derived dataset.

## User Decision Needed

If no official historical archive can be found, the next practical path needs a
user decision:

1. Accept manual download of historical Yuanta monthly/quarterly PDFs and track
   them through a manual evidence ledger.
2. Keep the proxy route blocked and wait for a stable official archive/API.
3. Ask Core to proceed only with proxy-specific schema/readiness design, without
   ingesting historical rows yet.

Manual download should remain fallback, not the main automated source, unless
the user explicitly accepts it.
