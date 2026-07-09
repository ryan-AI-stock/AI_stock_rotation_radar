# P1 risk-adjusted RS20 selected-stock OHLC gap fill

任務：TASK-RADAR-DATA-VNEXT-P1-RISK-ADJUSTED-RS20-SELECTED-STOCK-OHLC-GAP-FILL-001

## 結論

已依 Core missing ledger 做 bounded selected-ticker-only official OHLC source fill。未做 full-market download，未計算策略績效，未偽造 adjusted_close。

## Coverage

- input missing rows：357
- path ready rows：351
- path blocked rows：6
- unique tickers：199
- ticker-month official routes：395
- bounded exact-day fallback routes：23
- selected OHLC rows：677
- future_data_violation_count：0

## Readiness

ready_for_core_p1_risk_adjusted_rs20_selected_ohlc_absorption=false
ready_for_experiments=false
ready_for_formal=false
ready_for_strategy_replay=false
adjusted_close_ready=false

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

## Blocked rows

- 6121 新普 TPEx signal_date=2015-07-09 entry=2015-07-10 exit=2015-07-17：official selected-month and exact-day fallback target missing
- 3231 緯創 TWSE signal_date=2015-09-18 entry=2015-09-21 exit=2015-09-29：official selected-month and exact-day fallback target missing
- 5490 同亨 TPEx signal_date=2015-09-25 entry=2015-09-29 exit=2015-10-06：official selected-month and exact-day fallback target missing
- 2231 為升 TWSE signal_date=2016-07-07 entry=2016-07-08 exit=2016-07-15：official selected-month and exact-day fallback target missing
- 2340 台亞 TWSE signal_date=2017-09-15 entry=2017-09-18 exit=2017-09-25：official selected-month and exact-day fallback target missing
- 2912 統一超 TWSE signal_date=2019-05-17 entry=2019-05-20 exit=2019-05-27：official selected-month and exact-day fallback target missing
