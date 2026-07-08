# P1 C2 selected-stock corporate action source package

任務：TASK-RADAR-DATA-VNEXT-P1-C2-CONSENSUS4-SELECTED-STOCK-CORPORATE-ACTION-SOURCE-PACKAGE-001

## 結論

針對 P1 C2 consensus4 仍缺 adjusted close 的 16 筆 selected interval，完成 bounded 官方 corporate-action source probe。Radar/Data 只做官方 source package，不計算 adjusted close、不建立 Core formula contract、不跑 Experiments。

## Source routes

- MOPS official `t05st01` / `t05st01_detail`：依 ticker 與 entry/exit date 前後一個月查詢重大訊息，擷取除權息、股利、減資、股本變動等候選事件。
- TWSE `TWT48U/TWT49U`：官方除權息 route 可連線，但 date probe 回 current 115 年資料，列為 current-route probe，不用於 P1 historical backfill。

## Coverage

- target_blocked_interval_rows：16
- source_manifest_rows：52
- corporate_action_event_candidate_rows：0
- adjustment_factor_source_candidate_rows：0
- blocked_no_candidate_rows：16
- future_data_violation_count：0

## Readiness

ready_for_core_p1_c2_corporate_action_adjustment_contract=false

這代表 Core 可以檢查候選事件是否足以設計 bounded adjustment contract；不是 adjusted close 已補齊，也不是 Experiments-ready。
