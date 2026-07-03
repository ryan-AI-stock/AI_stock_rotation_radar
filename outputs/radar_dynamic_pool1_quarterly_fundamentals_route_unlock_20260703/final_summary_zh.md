# Dynamic Pool1 quarterly fundamentals route unlock

## 判定
- status: `completed_route_unlocked_sample_rows`
- quarterly_fundamentals_route_unlocked: `true`
- accepted sample rows: `320`
- observed full source rows in bounded probes: `320`
- tested periods: `2015Q4, 2024Q4`
- tested markets: `otc, sii`
- future_data_violation_count: `0`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`
- formal_model_changed: `false`
- trade_decision_changed: `false`
- active_in_trade_decision: `false`

## 本棒解開的 route
MOPS 新版 SPA 會把 `t163sb04` 導到 `mops/#/web/t163sb04`。靜態解析 `assets/index.js` 與 `assets/t163sb04.js` 後，確認彙總頁不是直接打舊 `ajax_t163sb04`，而是：

1. `POST https://mops.twse.com.tw/mops/api/redirectToOld`
2. body: `{"apiName":"ajax_t163sb04","parameters":{"TYPEK","year","season","encodeURIComponent":1,"firstin":1,"off":1,"step":1,"isQuery":"Y"}}`
3. response 會回短效 `https://mopsov.twse.com.tw/mops/web/ajax_t163sb04?parameters=...`
4. GET 該 data URL 可取得 period-specific 財報彙總 HTML 表格。

## PIT 邊界
本棒只把官方 quarterly fundamentals route 解鎖並產生 bounded sample rows。因 MOPS 表格頁只有申報期限註記，尚未取得逐公司 exact filing timestamp，所以 sample rows 標為 `source_candidate_no_exact_filing_date`、`formal_exact=false`。`available_date` 先採保守法定申報期限，不可當正式 exact filing date。

## 剩餘 blocker
- 需要逐公司 exact filing_date/release timestamp route 或公告 crawler。
- 需要 full 2015-latest quarterly sweep 與 coverage audit。
- 若 Dynamic Pool1 要用資產負債表、現金流量或 ROE/負債比，還要擴 `t163sb05/t163sb20/t163sb06` 等 route。
