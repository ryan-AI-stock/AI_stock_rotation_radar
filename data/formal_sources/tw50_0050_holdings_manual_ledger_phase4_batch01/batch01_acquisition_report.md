# TW50/0050 Manual Ledger Phase 4 Batch 01 Acquisition Report

Task: continue `TASK-RADAR-TW50-0050-MANUAL-LEDGER-PHASE3-001`

Date: 2026-06-21

## Scope

User accepted the manual ledger route. This batch tries the first two high
priority source targets from Phase 3:

- `2022-01` monthly Yuanta 0050 report
- `2022-Q1` Yuanta domestic fund quarterly holdings report

This batch does not modify the daily radar report, workflow, Drive publishing,
or BACKTEST_LAB Core model.

## Result

Status: `batch01_source_pending`

No accepted PDF source was obtained in this batch.

The sources remain pending because:

1. Public web search did not return the target 2022-01 / 2022-Q1 PDFs.
2. Internet Archive CDX direct checks returned empty result arrays.
3. Internet Archive CDX wildcard checks returned empty result arrays.

No historical holdings rows were created.

## Searches Performed

Public search queries:

- `"元大台灣卓越50基金月報" "2022年01月31日" PDF`
- `"元大台灣卓越50基金" "2022年01月31日" "前十大持有標的"`
- `"元大投信國內基金持股明細表" "2022/03/31" "卓越50基金"`
- `"卓越50基金" "2022/03/31" "台積電" "元大投信國內基金持股明細表"`
- `"1066元大台灣卓越50基金月報" "202201"`
- `"元大國內基金季持股" "2022/03/31"`

Archive checks:

- direct CDX for `1066元大台灣卓越50基金月報.pdf`, 2022-01 to 2022-03: `[]`
- direct CDX for `元大國內基金季持股.pdf`, 2022-01 to 2022-04: `[]`
- wildcard CDX for `*卓越50*月報*.pdf`, 2022-01 to 2022-03: `[]`
- wildcard CDX for `*國內基金*持股*.pdf`, 2022-01 to 2022-04: `[]`

## Ledger Impact

Rows created: 0

`2022-01` and `2022-Q1` should stay:

- `source_status=source_pending`
- `download_method=manual_download_required`
- `parser_status=not_started`
- `review_status=source_pending`

## Next Manual Actions

The next human-assisted source acquisition options are:

1. Use Yuanta website UI manually to check whether older fund reports are
   accessible after selecting fund 0050 or report date filters.
2. Contact Yuanta or use investor/fund document archives to request historical
   0050 monthly reports and domestic holdings PDFs.
3. Search existing local/Drive archives if the user or previous workflows saved
   older Yuanta PDF files.
4. If historical PDFs are obtained, save them using Phase 3 filename rules:
   - `yuanta_0050_monthly_202201.pdf`
   - `yuanta_domestic_holdings_2022Q1.pdf`

After files are obtained, run parser/manual review SOP from Phase 3 and update
the ledger.

## Data Boundary

This remains a proxy source route:

- `source_mode=yuanta_0050_holdings_proxy`
- `is_proxy=true`
- `exact_tw50_official_constituents=false`

Do not use current holdings to backfill these 2022 dates.
