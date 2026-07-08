# Regime-switch selected-stock OHLC source package

任務：TASK-RADAR-DATA-VNEXT-REGIME-SWITCH-ROUTE-SELECTED-STOCK-OHLC-SOURCE-PACKAGE-001

## 結論

Radar/Data 使用本機 `radar_dynamic_pool1_all_listed_liquid_universe_full_sweep_20260703` shards，只補 Core regime-route selected path 的 entry/exit dates。沒有全市場下載，沒有讀 Google/Drive，沒有使用 00631L + excess 重建 selected-stock path。

## Coverage

- Core path rows audited：615
- ordinary stock path rows：615
- ordinary stock unadjusted OHLC ready rows：613
- ordinary stock blocked rows：2
- 00631L reference rows：0，已分開標 `path_bucket=00631L_reference`
- selected OHLC rows extracted：631

## Readiness

- ready_for_core_regime_switch_unadjusted_ohlc_path_refresh=false
- next_day_unadjusted_path_ready=false
- adjusted_close_ready=false
- ready_for_regime_switch_hybrid_route_diagnostic=false
- ready_for_experiments=false
- ready_for_formal=false
- future_data_violation_count=0

## 邊界

官方 daily rows 是未還原 OHLC；`adjusted_close` 不可偽造，因此 adjusted close path 保持 blocked。00631L reference rows 與 ordinary stock path 分開，不混成 ordinary stock。

## Corrected 00631L split

Core recommendation_type=00631L rows are separated as reference rows. Corrected ordinary stock rows=594, ordinary unadjusted ready rows=592, ordinary blocked rows=2, 00631L reference rows=21, 00631L ready rows=21.
