# 0050 歷史成分股來源 Phase 4：dated API / disclosure route

## 結論

本批完成 dated API / disclosure route 的 bounded 自動嘗試。四個 target period 都有 source probe evidence，但沒有取得可對上 target period 的 0050 historical holdings rows。

目前仍沒有取得「2014Q4、2016Q1、2021Q4、2023Q4 各時間點的 0050 成分股清單」。本批沒有 accepted historical rows。

## 產出

- Output: `outputs/radar_tw50_0050_dated_api_disclosure_phase4_201411_202312_20260629`
- Previous output read: `outputs/radar_tw50_0050_archived_html_crawler_201411_202312_20260629`
- Source probe attempts: 112
- API payload candidates: 72
- Disclosure candidates: 40
- Raw source candidates: 93 local files
- Parsed holdings sample rows: 0
- Accepted historical rows: 0

Raw payload files are retained locally under `raw_sources/` for audit, but excluded from git. CSV ledgers keep the URL, status, content type, detected date field, holdings date, row count, retrieved path, and error.

## Period Status

| period | target date | probe attempts | api candidates | disclosure candidates | parsed sample rows | accepted rows |
|---|---:|---:|---:|---:|---:|---:|
| 2014Q4 | 2014-12-31 | 28 | 18 | 10 | 0 | 0 |
| 2016Q1 | 2016-03-31 | 28 | 18 | 10 | 0 | 0 |
| 2021Q4 | 2021-12-31 | 28 | 18 | 10 | 0 | 0 |
| 2023Q4 | 2023-12-31 | 28 | 18 | 10 | 0 | 0 |

## What Was Tried

- Yuanta current API/payload guess routes, including ETF info, holdings, PCF, file download, and product list route candidates.
- API URLs extracted from Phase 3 archived Yuanta HTML, including `etfapi.yuantaetfs.com` / `api.yuantafunds.com` candidates and Nuxt JS routes.
- Wayback availability probes around the four target dates for each dated API/disclosure route.
- SITCA, MOPS, TWSE ETF, and Taiwan Index proxy/disclosure landing routes.

## Acceptance Decision

- `accepted_historical_rows.csv` remains header-only.
- `parsed_holdings_sample.csv` remains header-only after sanitation.
- False-positive rows from PDF/object text were removed and not counted.
- No route produced valid `ticker/name/weight` or `ticker/name` rows with `holdings_date/source_date` equal to the requested target period.

## Source Quality Decision

- `formal_exact=false`
- `current_snapshot_used_as_historical=false`
- `date_mismatched_payload_accepted=false`
- `future_data_violation_count=0`
- `formal_model_changed=false`
- `trade_decision_changed=false`

## Main Blocker

The available API/disclosure probes either returned current/landing payloads, unavailable routes, Wayback availability metadata, or non-structured content. None exposed a target-period holdings date with valid 0050 constituent rows.

## Next Programmatic Sources

Do not stop at manual download. The next bounded route should be:

1. Reverse engineer the exact `etfapi.yuantaetfs.com` endpoint names and parameters from archived Nuxt JS chunks, then query those endpoint URLs through Wayback by timestamp.
2. Probe SITCA monthly portfolio/disclosure forms with POST parameters, using fund identity `1066` / `0050` / `元大台灣卓越50基金`.
3. Probe MOPS or fund public disclosure endpoints by company/fund code and month, not just landing pages.
4. If Taiwan Index/TWSE constituents are used, keep them as proxy unless a source decision clearly ties them to 0050 holdings and the holdings date.
