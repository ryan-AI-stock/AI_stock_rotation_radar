# Revenue anomaly soft-penalty rerank selected OHLC gap fill

## 結論

- input gap rows: 92
- filled rows: 92
- blocked rows: 0
- unadjusted OHLC points: 64
- ready_for_core_revenue_anomaly_soft_penalty_rerank_ohlc_absorption=true
- future_data_violation_count=0

## Source policy

- 只補 selected_ticker_after 的 selected-only official unadjusted OHLC。
- 優先重用本機既有 official selected OHLC source package。
- 剩餘缺口使用 TWSE STOCK_DAY / TPEx tradingStock selected-ticker month official route。
- adjusted_close 仍 blocked，不 fabricated。
- 沒有使用 00631L + excess reconstruction。

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

交 Core/Data absorption / readiness refresh；不要直接交 Experiments。完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。不要完成後停住不回報。
