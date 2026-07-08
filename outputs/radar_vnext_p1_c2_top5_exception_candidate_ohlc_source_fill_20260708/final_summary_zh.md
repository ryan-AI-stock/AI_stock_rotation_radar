# P1 C2 top5 exception candidate OHLC source fill

任務：TASK-RADAR-DATA-VNEXT-P1-C2-TOP5-EXCEPTION-CANDIDATE-OHLC-SOURCE-FILL-001

## 結論

以 Core missing path ledger 為 source of truth，只對 blocked candidate rows 做 selected ticker-month 官方未還原 OHLC 補價。未做 full-market mass download，未使用 00631L/excess reconstruction，未偽造 adjusted_close。

## Coverage

- input blocked rows：959
- path ready rows：959
- path blocked rows：0
- unique tickers：297
- ticker-month routes：988
- selected OHLC rows：2021
- future_data_violation_count：0

## Readiness

ready_for_core_p1_c2_top5_exception_candidate_path_ingest=true
ready_for_p1_c2_top5_multi_stock_exception_count_diagnostic=false
ready_for_experiments=false
ready_for_formal=false

## Blocked

若仍有 blocked rows，原因保留於 `p1_c2_top5_exception_candidate_ohlc_blocked_ledger.csv`，不做 silent fill。


## RWD patch

TWSE legacy `exchangeReport/STOCK_DAY` returned invalid old-date errors for several P1 months. A bounded patch used official `rwd/zh/afterTrading/STOCK_DAY` only for still-blocked ticker-months. rwd_patch_routes=13.
