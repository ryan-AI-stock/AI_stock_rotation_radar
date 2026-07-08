# P1 C2 official historical ex-right / capital-change route unlock

任務：TASK-RADAR-DATA-VNEXT-P1-C2-OFFICIAL-HISTORICAL-EXRIGHT-CAPITAL-CHANGE-ROUTE-UNLOCK-001

## 結論

完成 bounded official route unlock。TWSE/TPEx `t187ap39/40` 可提供 selected tickers 的官方歷史股利分派候選資料，但仍缺 exact historical ex-right trading date 與完整減資/分割/合併/股本變動 route，因此不能宣告 ready for adjusted-close contract。

## Coverage

- target_blocked_interval_rows：16
- source_manifest_rows：6
- event_candidate_rows：51
- adjustment_factor_source_candidate_rows：51
- blocked_interval_rows：16
- future_data_violation_count：0

## Route status

- TWSE/TPEx official `t187ap39/40`：partial usable dividend distribution/resolution source。
- TWSE `TWT48U/TWT49U`：route reachable，但 historical date probe 回 current-table behavior，不能當 P1 historical ex-date source。
- MOPS t05st01 bounded windows upstream：無事件候選，但 Strategy Center 已裁決不能把這當 no adjustment needed proof。

ready_for_core_p1_c2_adjustment_contract=false
