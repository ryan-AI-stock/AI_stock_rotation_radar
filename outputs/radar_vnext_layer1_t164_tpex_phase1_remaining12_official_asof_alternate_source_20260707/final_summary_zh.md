# Layer1 t164 TPEx phase_1 remaining 12 official-asof alternate source

Status: remaining12_higher_cost_alternate_source_completed_partial_patch_ready

結論：
- input_rows=12
- resolved_rows=10
- still_blocked_rows=2
- route_error_count=0
- cache_manifest_rows=351
- future_data_violation_count=0

Readiness:
- ready_for_core_t164_tpex_remaining12_asof_patch_review=true
- ready_for_core_t164_tpex_all_stock_proof_readiness_update=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- ready_for_full_universe=false

6114 policy:
- market_available_at must map to the t164 statement version actually used.
- If two official financial-report announcements remain and t164 current values cannot be mapped to one version, row remains version_match_blocked.

Governance:
- quarter_end_date / query_response_datetime / conservative deadline proxy prohibited as official available_at。
- unmatched/ambiguous rows remain blocked; no silent backfill。
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
