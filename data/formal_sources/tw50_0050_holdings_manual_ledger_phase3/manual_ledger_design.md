# TW50/0050 Holdings Proxy Manual Ledger Phase 3

Task ID: `TASK-RADAR-TW50-0050-MANUAL-LEDGER-PHASE3-001`

Date: 2026-06-21

## Purpose

The user accepted manual download of historical Yuanta monthly / quarterly PDFs
and manual ledger gap filling.

This Phase 3 package designs the manual evidence ledger route. It does not
create historical holdings data, and it does not make the proxy source formal
ready.

Required flags for every ledger row:

- `source_mode`: `yuanta_0050_holdings_proxy`
- `is_proxy`: `true`
- `exact_tw50_official_constituents`: `false`

## Data Boundary

This route is for Yuanta 0050 ETF/fund holdings proxy snapshots.

It is not:

- exact TW50 official point-in-time index constituents
- a current-holdings backfill to earlier dates
- a Core model change
- a formal three-pool replay input until proxy readiness is separately accepted

## Target Coverage

Target period:

- start: `2022-01`
- end: current completed report month

Preferred source cadence:

1. Monthly 0050 fund report if a dated PDF can be obtained.
2. Quarterly domestic fund holdings PDF if it contains dated 0050 / 卓越50 data
   for the target quarter.
3. Official TW50 review notices only as cross-check evidence for entry/exit
   differences, not as primary holdings snapshots.

## Ledger States

Use these states consistently:

- `source_pending`: expected report not yet obtained.
- `downloaded`: PDF file obtained and filename follows the rule.
- `auto_parsed`: parser extracted rows from the source file.
- `manual_entered`: human entered rows from the PDF.
- `manual_reviewed`: second pass checked source file vs ledger rows.
- `accepted`: row can be used by proxy-specific readiness, still not exact TW50.
- `rejected`: row/source cannot be used; explain why in `notes`.

Accepted rows must have:

- dated source file
- source report date
- source file path
- proxy flags
- review status
- no future-data backfill

## Directory Layout

Recommended local working structure:

```text
data/formal_sources/tw50_0050_holdings_manual_ledger_phase3/
  source_pdfs/
    monthly_0050/
    quarterly_domestic_holdings/
  manual_ledger_template.csv
  source_acquisition_checklist.csv
  parser_manual_review_sop.md
  phase3_readiness.json
```

PDF files are intentionally not committed unless licensing and repository size
rules are explicitly approved. Commit the ledger, checklist, parser evidence, and
review metadata first.

## Filename Rules

Use stable ASCII filenames:

Monthly 0050 report:

```text
yuanta_0050_monthly_YYYYMM.pdf
```

Quarterly domestic fund holdings:

```text
yuanta_domestic_holdings_YYYYQn.pdf
```

If the source date is visible only inside the PDF, use the visible report date.
If the file was downloaded manually but source date is not verified, put it in
`source_pending` and do not parse it into accepted rows.

## Manual Workflow

1. Pick the next `source_pending` period from `source_acquisition_checklist.csv`.
2. Download the PDF manually from Yuanta website or another traceable official
   source.
3. Save the file using the filename rule above.
4. Record `download_method`, `source_url_or_manual_note`, `source_report_date`,
   and `source_file`.
5. Run parser if available.
6. If parser extracts only top-10 rows, set `parser_status=auto_parsed_top10_only`.
7. If the PDF has full holdings but parser cannot extract it, enter rows manually
   and set `parser_status=manual_entered`.
8. A second review pass compares ledger rows to the source PDF and sets
   `review_status=manual_reviewed` or `accepted`.
9. Never use a later source file to fill an earlier `snapshot_date`.

## Review Rules

Reject or keep pending if:

- source date is missing
- source is not a PDF/report from a traceable official source
- file date conflicts with the claimed snapshot date
- rows are copied from current holdings into historical dates
- the source only has top-10 holdings but downstream expects full holdings
- license/reuse status is unclear and the output would be redistributed

## Core Handoff

Core may implement a proxy-specific readiness path that checks this ledger.

Core must not:

- pass exact TW50 validator with these rows
- treat `accepted` proxy rows as official index constituents
- run formal three-pool diagnosis as final unless proxy-specific coverage and
  limitations are explicitly accepted

Recommended Core readiness dimensions:

- monthly/quarterly snapshot coverage ratio
- row scope: `top10_only`, `full_holdings`, or `quarterly_table`
- source review status
- manual vs auto parsed row count
- future-data violation count
- exact TW50 validator allowed: always `false`
