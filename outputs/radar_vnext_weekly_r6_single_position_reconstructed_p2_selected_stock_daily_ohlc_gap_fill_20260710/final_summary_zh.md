# Reconstructed weekly R6 P2 selected-stock daily OHLC gap fill

## 結論

- input gap rows: 32
- filled rows: 32
- blocked rows: 0
- unique tickers: 7
- unique price dates: 32
- unadjusted OHLC points: 32
- official_unadjusted_ohlc_ready_share=1.000000
- adjusted_close_ready=false
- ready_for_core_reconstructed_weekly_r6_p2_daily_ohlc_absorption=true
- ready_for_experiments=false
- ready_for_formal=false
- future_data_violation_count=0

## Source policy

- 只補 Core ledger 內 reconstructed single-position weekly R6 P2 selected ticker/date。
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

交 Core/Data absorption / readiness refresh；Radar/Data 不直接交 Experiments。完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。不要完成後停住不回報。
