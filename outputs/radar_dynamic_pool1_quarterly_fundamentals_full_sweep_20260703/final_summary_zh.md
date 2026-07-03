# Dynamic Pool1 quarterly fundamentals full sweep

## 判定
- status: `completed_full_sweep_source_candidate`
- quarterly_fundamentals_full_sweep_ready: `true`
- covered period: `2015Q1` to `2026Q1`
- accepted rows: `79046`
- symbols: `1970`
- failed/missing period-markets: `0`
- route_request_attempts: `180`
- source_type: `source_candidate_no_exact_filing_date`
- formal_exact: `false`
- filing_date_available: `false`
- future_data_violation_count: `0`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`

## Source Contract
使用上一棒解鎖的 MOPS SPA route：
1. `POST https://mops.twse.com.tw/mops/api/redirectToOld`
2. body: `apiName=ajax_t163sb04` + `TYPEK/year/season/encodeURIComponent/firstin/off/step/isQuery`
3. response 回短效 `mopsov.twse.com.tw/mops/web/ajax_t163sb04?parameters=...`
4. GET 該 URL 解析 period-specific HTML 財報彙總表。

## PIT 邊界
本 package 是 `source_candidate_no_exact_filing_date`。`available_date` 採保守法定申報期限，不是逐公司 exact filing timestamp，因此不可標 formal exact。

## 下一步
交 Core 重跑 Dynamic Pool1 readiness；後續若要更高 exactness，需補逐公司 filing_date/release timestamp crawler，並視策略需求擴資產負債表、現金流量或比率欄位。
