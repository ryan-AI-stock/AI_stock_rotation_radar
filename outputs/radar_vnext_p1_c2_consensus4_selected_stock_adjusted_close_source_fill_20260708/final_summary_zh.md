# P1 C2 consensus4 selected-stock adjusted close source fill

任務：TASK-RADAR-DATA-VNEXT-P1-C2-CONSENSUS4-SELECTED-STOCK-ADJUSTED-CLOSE-SOURCE-FILL-001

## 結論

以 Core adjusted price coverage ledger 為 source of truth，只盤點 adjusted_close_interval_ready=false 的 16 筆 selected interval。未做 full-market mass download，未使用 00631L/excess reconstruction，未把 unadjusted OHLC comparator 包裝成 adjusted-close path。

## Source route result

- 本機 EP05 adjusted cache：只找到 2316/3090/3324 候選檔，但不覆蓋本任務要求的 P1 日期。
- Yahoo chart includeAdjustedClose：bounded probe 回 HTTP 429。
- Stooq daily CSV：bounded probe 回 JS verification page，非可解析 CSV。
- FinMind TaiwanStockPriceAdj：bounded probe 回 free level blocked / sponsor required。

## Readiness

- patched_interval_rows：0
- remaining_blocked_interval_rows：16
- adjusted_close_ready=false
- ready_for_core_p1_c2_consensus4_adjusted_state_machine_refresh=false
- ready_for_experiments=false
- ready_for_formal=false
- future_data_violation_count=0

## Blocked reason

缺口已縮小為：沒有可接受的 selected-stock adjusted close source route。若要繼續，需 Core/Strategy Center 指定可接受的第三方授權來源、或接受由官方除權息/減資事件自行建 adjusted-close contract 的較大工程。
