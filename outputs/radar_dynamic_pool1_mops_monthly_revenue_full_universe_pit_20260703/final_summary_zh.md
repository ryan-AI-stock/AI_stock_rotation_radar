# Dynamic Pool1 MOPS monthly revenue full-universe PIT

## 結論

狀態：`completed_full_universe_candidate`。

本棒使用 MOPS official static monthly revenue route `t21sc03` 擴成 2015-01～2026-05 全市場候選資料包。accepted rows 以年度 shards 保存，`accepted_monthly_revenue_rows.csv` 是 shard index，避免單檔超過 GitHub 上限。

- accepted rows：244620
- symbol count：1971
- route attempts：548
- failed attempts：0
- month-market coverage：274/274
- `future_data_violation_count=0`

## PIT 邊界

每筆 row 具 `source_date/release_date/available_date`，但日期是保守可用日：次月 10 日，若遇週末順延到下一個 weekday。這避免 future-data leakage，但不是逐公司精確申報時間；因此 `formal_exact=false`。

## Readiness

- `monthly_revenue_pit_full_universe_ready=true`
- `monthly_revenue_pit_partial_ready=true`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`

## 下一步

交 Core 重跑 Dynamic Pool1 readiness。若 Core 要求 exact per-company filing timestamp，下一棒 Radar/Data 需走 MOPS material information / announcement crawler by company-month。
