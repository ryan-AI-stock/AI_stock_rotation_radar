# Layer1 t164 TPEx phase_1 official-asof alternate route/disambiguation

Status: alternate_asof_disambiguation_completed_partial_patch_ready

結論：
- input_blocked_rows=15
- resolved_rows=3
- still_blocked_rows=12
- route_error_count=0
- cache_manifest_rows=76
- future_data_violation_count=0

Readiness:
- ready_for_core_t164_tpex_phase1_asof_patch_review=true
- ready_for_core_t164_tpex_all_stock_proof_readiness_update=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- ready_for_full_universe=false

Policy:
- accepted official public t05st01/t05st01_detail timestamp only。
- unmatched/ambiguous remains blocked; no silent backfill。
- quarter_end_date / query_response_datetime / conservative deadline proxy prohibited as official available_at。
- current-or-carried TPEx universe remains sampling-only, not historical PIT all-stock universe。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
