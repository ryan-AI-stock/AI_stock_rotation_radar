# vNext ad-hoc 2026-07-08 EOD source fill

任務：TASK-RADAR-DATA-VNEXT-ADHOC-20260708-EOD-VNEXT-SIGNAL-SNAPSHOT-SOURCE-FILL-001

## 結論

已取得 2026-07-08 官方 EOD source：TWSE MI_INDEX ALLBUT0999 與 TPEx dailyQuotes。這是單日 source package，不是 full historical mass download；不使用 2026-06-29/06-30/07-02 冒充 2026-07-08。

## Coverage

- TWSE rows：1369
- TPEx rows：10039
- official_eod_ohlcv_rows：11408
- scoped common-stock / required ETF rows：1973
- required 0050/00631L found：0050, 00631L
- blocked rows：0
- future_data_violation_count：0

## Core Materialization Readiness

ready_for_core_vnext_adhoc_20260708_eod_materialization_refresh=true
ready_for_core_layer0_compact_active_universe_source_refresh=true
ready_for_core_layer4_primary80_snapshot_refresh=source_ready_core_contract_required
ready_for_core_0050_market_regime_refresh=source_ready_historical_window_join_required
ready_for_core_dynamic80_pool_regime_refresh=source_ready_core_pool_join_required
ready_for_experiments=false
ready_for_formal=false
ready_for_strategy_replay=false

## Notes

- DAILY_STOCK report artifact/cache was not used as source anchor; official exchange routes were used directly.
- adjusted_close remains blocked/not fabricated; package provides official unadjusted OHLCV and turnover.
- Retrieval time is recorded in manifest only, not used as market available date.

## Boundaries

formal_model_changed=false
trade_decision_changed=false
active_in_trade_decision=false
report_changed=true
portfolio_replay_executed=false
ready_for_strategy_replay=false
ready_for_formal=false
not_live_rule=true
forward_returns_live_rule_usage=false
