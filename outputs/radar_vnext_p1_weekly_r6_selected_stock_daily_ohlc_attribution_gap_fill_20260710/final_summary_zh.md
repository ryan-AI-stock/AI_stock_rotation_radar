# P1 weekly R6 selected-stock daily OHLC attribution gap fill

## 結論

- input gap rows: 125
- filled rows: 125
- blocked rows: 0
- unique tickers: 20
- unique price dates: 124
- unadjusted OHLC points: 125
- official_unadjusted_ohlc_ready_share=1.000000
- adjusted_close_ready=false
- ready_for_core_p1_weekly_r6_daily_ohlc_absorption=true
- ready_for_experiments=false
- ready_for_formal=false
- future_data_violation_count=0

## Source policy

- 只補 Core ledger 內 P1 weekly R6 selected ticker/date。
- 優先重用本機既有 official selected-ticker rows。
- 剩餘缺口使用 TWSE STOCK_DAY / TPEx tradingStock selected-ticker month official route。
- 不使用 00631L + excess reconstruction。
- adjusted_close 仍 blocked，未 fabricated。

## Flags

formal_model_changed=false
trade_decision_changed=false
active_in_trade_decision=false
report_changed=false
portfolio_replay_executed=false
ready_for_strategy_replay=false
ready_for_formal=false
not_live_rule=true
forward_returns_live_rule_usage=false

## 下一棒

交 Core/Data absorption / readiness refresh；Radar/Data 不直接交 Experiments。完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。
