# Layer1 t164 t05st01 unmatched alternate route capture

Status: alternate_t05st01_route_capture_partial_unlocked_remaining_blocked

結論：
- 針對 6 筆 prior unmatched rows 做 bounded t05st01 broader query / subject policy capture。
- accepted official timestamp rows: 5/6。
- remaining blocked rows: 1/6。
- relaxed candidate rows: 15。
- route_error_count=0。
- 沒有使用 quarter_end_date 或 query_response_datetime 當 available_at。

Readiness:
- ready_for_core_t164_asof_join_contract_refresh=false
- ready_for_core_t164_full_or_broader_ingest_contract=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- future_data_violation_count=0
- not_live_rule=true

Policy:
- no silent backfill。
- conservative filing deadline proxy must remain separate proxy candidate。
- exact internal upload timestamp remains distinct from official public announcement timestamp。
- relaxed subject candidates require human review and are not accepted official asof rows。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
