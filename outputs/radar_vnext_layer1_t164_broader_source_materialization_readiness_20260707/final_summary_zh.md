# vNext Layer1 t164 broader source materialization readiness

Status: bounded_broader_materialization_sample_ready_not_full_ingest

結論：
- 這是 bounded broader materialization readiness，不是 full ingest，不交 Experiments。
- payload replay 已實際擴到 4 檔、2 個市場、2 個期間：1101/2308 TWSE、6488/8299 TPEx；115Q1、114Q4。
- t164sb05/t164sb03 statement sample success rows: 8/8。
- t05st01 official announcement timestamp matched rows: 8/8。
- `market_available_at` 使用 t05st01/t05st01_detail public material-information timestamp；沒有使用 quarter_end_date 或 query_response_datetime。
- after-close next-trading-day eligibility policy 已保留為 Core calendar join requirement。

Readiness:
- ready_for_core_t164_broader_interim_official_asof_join=true
- ready_for_core_full_ingest_readiness=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0
- not_live_rule=true

仍非 full ingest 的原因：
- 這仍是 bounded sample，不是 full-universe runner。
- TPEx 只有 bounded samples，不是 universal ready。
- capex_proxy 與 receivables_basket 仍需 human-review label policy。
- exact upload timestamp 仍不是 t05st01 public announcement timestamp；這裡只做 official announcement asof。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
