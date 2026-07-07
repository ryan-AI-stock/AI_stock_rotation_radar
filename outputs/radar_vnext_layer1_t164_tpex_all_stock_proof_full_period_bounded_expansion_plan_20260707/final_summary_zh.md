# Radar/Data Layer1 t164 TPEx all-stock proof + full-period bounded expansion plan

## 結論
- status=bounded_expansion_plan_ready_tpex_all_stock_proof_not_complete。
- 既有 Core bounded materialization 的 TPEx seed：8 檔 x 2 期，16/16 statement rows 成功，official-asof 16/16 matched。
- 本機可用 TPEx current-or-carried universe candidate：891 檔；只能作抽樣母體與成本估算，不能回推歷史 PIT universe。
- 建議下一步是 Core/Data review runner contract，或 Radar/Data 先執行 phase_1_tpex_stratified_50x2 bounded proof runner。

## Readiness
- ready_for_core_t164_tpex_all_stock_proof_runner_contract=true
- ready_for_core_t164_full_period_bounded_expansion_contract=true
- ready_for_core_t164_broader_or_full_ingest_contract=false
- ready_for_core_t164_broader_or_full_materialization=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- ready_for_full_universe=false

## Cost / fan-out
- pruning v2 planning basis：8.0 routes / ticker-period row。
- Phase 1 建議：50 TPEx tickers x 2 periods = 100 ticker-period rows，約 800 routes。
- Full current-snapshot TPEx x full period candidate：891 tickers x 46 periods = 40986 ticker-period rows，約 327888 routes；必須 checkpoint/resume/budget guard。

## 保留 blocker
- TPEx all-stock universal readiness 仍未完成；目前只有 8 檔 x 2 期 seed positive。
- Full period range 尚未 materialized。
- TPEx historical membership 不能用 current snapshot 回推。
- capex_proxy / receivables_trade 只作 diagnostic proxy，human-review required，不作 formal fundamentals。

## Governance
- quarter_end_date 不得作 available_at。
- query_response_datetime 不得作 available_at。
- market_available_at 必須來自 official t05st01/t05st01_detail public timestamp。
- after-close announcement 僅可 next-trading-day eligible。
- future_data_violation_count=0。

## Flags
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
