# 0050 歷史成分股來源 Phase 6：session-aware SITCA replay + exact request extraction

## 結論

本批完成 Phase 6 的兩條精準可程式化嘗試：

1. SITCA `IN2421.aspx` session-aware ASP.NET postback replay。
2. Phase 5 Nuxt chunks 的 exact request body/header/param static extraction 與 exact API probe。

四個 target periods 都有 session-aware SITCA 或 exact API probe evidence，但仍沒有取得任一 target period 的 0050 historical holdings rows。

目前答案仍是：尚未取得 2014Q4、2016Q1、2021Q4、2023Q4 任一段的 0050 成分股清單。

## Output

- Output: `outputs/radar_tw50_0050_session_replay_phase6_201411_202312_20260629`
- Previous output read: `outputs/radar_tw50_0050_endpoint_post_probe_phase5_201411_202312_20260629`
- SITCA form state inventory rows: 6
- SITCA postback attempts: 16
- Nuxt request extraction rows: 6
- Exact API probe attempts: 48
- Raw source candidates: 49 local files
- Parsed holdings sample rows: 0
- Accepted historical rows: 0

Raw response files are retained locally under `raw_sources/` for audit, but excluded from git.

## SITCA Replay Findings

GET `https://www.sitca.org.tw/ROC/Industry/IN2421.aspx` succeeded and returned an ASP.NET form state. Parsed controls:

- `__VIEWSTATE`
- `__VIEWSTATEGENERATOR`
- `__EVENTVALIDATION`
- `ctl00$ContentPlaceHolder1$BtnQuery`
- `ctl00$ContentPlaceHolder1$ddlQ_YEAR`
- `ctl00$ContentPlaceHolder1$ddlQ_MONTH`

The replay preserved session cookies, hidden fields, year/month dropdowns, `__EVENTTARGET`, `__EVENTARGUMENT`, and image-submit coordinates `BtnQuery.x/y`.

Blocker: all 16 SITCA postback attempts returned HTTP 404 and no holdings rows. This means GET form discovery works, but the server rejected the replayed POST route/state. The next step must capture the exact browser POST, including any additional headers/session behavior or anti-bot routing not visible from static form parsing.

## Nuxt/API Exact Extraction Findings

Static extraction from downloaded Nuxt chunks found the real request shape:

- `$getAPI("ETFAPI", "PCF/Daily", {ticker, ndate}, "/api/bridge")`
- `$getAPI("ETFBackstage", "ETFPCF", {stk_cd}, "/api/trans")`
- common request parameters include `APIType`, `CompanyName`, `PageName`, `DeviceId`, `FuncId`, plus function-specific params.

Exact API probes were attempted for all target periods. Blocker: probes returned HTML/offline shell or non-row responses, not JSON holdings rows with target `holdings_date/source_date`.

## Period Status

| period | target date | SITCA postback attempts | exact API attempts | parsed sample rows | accepted rows |
|---|---:|---:|---:|---:|---:|
| 2014Q4 | 2014-12-31 | 4 | 12 | 0 | 0 |
| 2016Q1 | 2016-03-31 | 4 | 12 | 0 | 0 |
| 2021Q4 | 2021-12-31 | 4 | 12 | 0 | 0 |
| 2023Q4 | 2023-12-31 | 4 | 12 | 0 | 0 |

## Acceptance Decision

- `accepted_historical_rows.csv` remains header-only.
- `parsed_holdings_sample.csv` remains header-only.
- ASP.NET 404/error pages are not accepted.
- HTML/offline shell API responses are not accepted.
- Current/rolling/date-mismatched responses are not accepted.

## Source Quality

- `formal_exact=false`
- `current_snapshot_used_as_historical=false`
- `aspnet_error_page_accepted=false`
- `future_data_violation_count=0`
- `formal_model_changed=false`
- `trade_decision_changed=false`

## Next Programmatic Route

Do not stop at manual download. The next bounded route should use browser automation/devtools rather than static replay:

1. Use Playwright/Chrome devtools network capture on the live SITCA page to record the exact POST that succeeds in the browser, including headers, cookies, event target, and any anti-bot/session fields.
2. Use Playwright/Chrome devtools network capture on `yuantaetfs.com/product/detail/0050/ratio` and `/tradeInfo/pcf/0050` to capture actual `api/bridge` and `api/trans` requests, then replay those exact URLs through Wayback timestamps or direct API with `ndate`.
3. If browser capture is unavailable, beautify the relevant Nuxt chunks and trace `$getAPI` base URL/store getters for `getBaseUrl` and `getCommonParameters`; static endpoint names alone are not enough.
4. Keep TWSE/Taiwan Index routes proxy-only unless source decision clearly ties them to 0050 ETF holdings.
