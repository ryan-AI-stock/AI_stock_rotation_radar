# P1 C2 weighted pool80 top5 selected-ticker OHLC source fill

任務：TASK-RADAR-DATA-VNEXT-P1-C2-WEIGHTED-POOL80-TOP5-SELECTED-TICKER-OHLC-SOURCE-FILL-001

## 結論

以 Core blocked proxy audit 為 source of truth，只補 official_unadjusted_ohlc_path blocked rows。Core blocked rows 未帶 entry/exit date，因此沿用同一 P1 C2 timing 的 previous top5 OHLC package signal_date -> entry_date/exit_date mapping。未做 full-market mass download，未使用 00631L/excess reconstruction，未偽造 adjusted_close。

## Coverage

- input blocked rows：601
- path ready rows：601
- path blocked rows：0
- unique tickers：81
- additional ticker-month routes：188
- selected OHLC rows：371
- source manifest rows：478
- future_data_violation_count：0

## Readiness

ready_for_core_p1_c2_weighted_pool80_top5_ohlc_absorption=true
ready_for_p1_c2_weighted_pool80_top5_multi_stock_diagnostic=false
ready_for_experiments=false
ready_for_formal=false
ready_for_strategy_replay=false

## Referer patch

Some TWSE selected ticker-month requests returned 307/empty without the historical-stock-day Referer. A bounded referer patch was applied only to still-blocked ticker-months. referer_patch_routes=129.

## Midmonth patch

Some older TWSE month queries returned invalid date errors with YYYYMM01. A bounded midmonth-date patch used official rwd STOCK_DAY with YYYYMM15 only for still-blocked ticker-months. midmonth_patch_routes=14.

## Bounded TWSE MI_INDEX fallback

The final 9 blocked contract rows were concentrated in 2454 2015-02 and 2881 2016-03. A bounded official TWSE MI_INDEX day fallback was used only for 4 required trading dates, and extracted the target ticker rows from official daily market files. bounded_twse_mi_index_day_fallback_routes=4.

## Boundaries

formal_model_changed=false
trade_decision_changed=false
active_in_trade_decision=false
report_changed=false
portfolio_replay_executed=false
ready_for_strategy_replay=false
ready_for_formal=false
not_live_rule=true
forward_returns_live_rule_usage=false
