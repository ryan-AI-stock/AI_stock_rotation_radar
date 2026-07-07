# Layer1 t164 6187 114Q4 official-asof disambiguation

Status: accepted_unique_official_public_timestamp

結論：
- 只針對 6187 TPEx 114Q4 做 final bounded disambiguation。
- accepted official timestamp rows: 1。
- accepted market_available_at: 115/02/10 18:16:38。
- source: MOPS t05st01/t05st01_detail official public material-information route。
- future_data_violation_count=0。

Readiness:
- ready_for_core_t164_asof_patch_refresh=true
- ready_for_core_t164_full_or_broader_ingest_contract=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true

Policy:
- premeeting notice excluded。
- non-target-period announcements excluded。
- quarter_end_date prohibited。
- query_response_datetime prohibited。
- conservative deadline proxy separate only。
- forward_return_as_rule=false。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
