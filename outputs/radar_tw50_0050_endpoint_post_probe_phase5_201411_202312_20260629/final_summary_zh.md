# 0050 歷史成分股來源 Phase 5：Nuxt/API endpoint reverse + SITCA/MOPS POST probe

## 結論

本批完成 Phase 5，範圍收斂為兩條可程式化路線：

1. 從 Phase 3/4 raw HTML 反推元大 Nuxt chunks、API base URL、endpoint name 與 fund/date params。
2. Probe SITCA / MOPS form action、hidden fields 與 POST parameters。

四個 target periods 都有 endpoint/post probe evidence，但仍沒有取得任一 target period 的 0050 historical holdings rows。

目前答案很明確：尚未取得 2014Q4、2016Q1、2021Q4、2023Q4 任一段的 0050 成分股清單。

## Output

- Output: `outputs/radar_tw50_0050_endpoint_post_probe_phase5_201411_202312_20260629`
- Previous output read: `outputs/radar_tw50_0050_dated_api_disclosure_phase4_201411_202312_20260629`
- Nuxt chunk candidates: 24
- API endpoint candidates: 12
- API probe attempts: 120
- SITCA/MOPS form candidates: 3
- POST probe attempts: 12
- Raw source candidates: 125 local files
- Parsed holdings sample rows: 0
- Accepted historical rows: 0

Raw payload/chunk files are retained locally under `raw_sources/` for audit, but excluded from git.

## Nuxt/API Route Findings

Nuxt chunks were downloaded from both direct current routes and Wayback timestamp routes. Endpoint extraction found candidate API routes including:

- `https://etfapi.yuantaetfs.com/api/ETF/GetETFInfo`
- `https://etfapi.yuantaetfs.com/api/ETF/GetETFList`
- `https://etfapi.yuantaetfs.com/api/ETF/GetFileDownload`
- `https://etfapi.yuantaetfs.com/api/ETF/GetHoldStock`
- `https://etfapi.yuantaetfs.com/api/ETF/GetPCF`
- `https://api.yuantafunds.com/ECAPI/api/ETF/GetHoldStock`
- `https://api.yuantafunds.com/ECAPI/api/ETF/GetPCF`
- `https://api.yuantafunds.com/ECAPI/api/ETF/GetFileDownload`

Parameter combinations were attempted with `fundid/fundId/FundID/code` and `0050/1066`, plus target date/month variants.

Blocker: endpoint candidates either returned landing/current/non-row payloads, unavailable responses, or Wayback metadata. No response exposed target-period `holdings_date/source_date` plus valid holdings rows.

## SITCA/MOPS POST Findings

The probe found:

- `sitca_in2421_form_1`
  - page: `https://www.sitca.org.tw/ROC/Industry/IN2421.aspx`
  - method: POST
  - action: same page
  - hidden fields detected: 3, including ASP.NET `__VIEWSTATE`
- `sitca_etf_root_no_form`
  - page returned no usable form in this bounded probe
- `mops_index_no_form`
  - landing page returned no usable fund monthly portfolio form in this bounded probe

Bounded POST attempts used fund identities `0050`, `1066`, and target months. SITCA `IN2421.aspx` responded HTTP 200 but did not return holdings table rows. The likely blocker is ASP.NET postback state: exact dropdown/control names, `__EVENTTARGET`, `__EVENTARGUMENT`, updated `__VIEWSTATE`, and session cookies must be replayed.

## Period Status

| period | target date | Nuxt/API attempts | POST attempts | parsed sample rows | accepted rows |
|---|---:|---:|---:|---:|---:|
| 2014Q4 | 2014-12-31 | 48 | 3 | 0 | 0 |
| 2016Q1 | 2016-03-31 | 48 | 3 | 0 | 0 |
| 2021Q4 | 2021-12-31 | 48 | 3 | 0 | 0 |
| 2023Q4 | 2023-12-31 | 48 | 3 | 0 | 0 |

## Acceptance Decision

- `accepted_historical_rows.csv` remains header-only.
- `parsed_holdings_sample.csv` remains header-only.
- Wayback availability timestamp was not accepted as holdings/source date.
- No current, rolling, date-mismatched, wrapper HTML, or PDF-object garbage rows were accepted.

## Source Quality

- `formal_exact=false`
- `current_snapshot_used_as_historical=false`
- `wayback_metadata_accepted_as_source_date=false`
- `future_data_violation_count=0`
- `formal_model_changed=false`
- `trade_decision_changed=false`

## Next Programmatic Route

Do not stop at manual download. The next bounded route should be one of:

1. Use a browser/devtools or static JS beautifier pass over the downloaded Nuxt chunks to identify exact function names, request bodies, headers, and endpoint params for `GetHoldStock` / `GetPCF`.
2. Replay SITCA `IN2421.aspx` as a real ASP.NET postback:
   - preserve cookies,
   - parse all hidden fields,
   - discover dropdown names for year/month/fund,
   - submit `__EVENTTARGET` / `__EVENTARGUMENT`,
   - then parse returned tables.
3. Search SITCA downloadable static files or backend endpoints behind `IN2421.aspx`, instead of only the rendered ASP.NET page.
4. If TWSE/Taiwan Index constituents are used later, keep them proxy-only unless source decision clearly ties them to 0050 holdings.
