# Layer1 t164 candidate/detail pruning runner v2

Status: candidate_detail_pruning_runner_v2_ready_not_full_universe

結論：
- pruning v2 已在同一 40-row broader seed 驗證。
- statement_success_rows=40/40。
- official_asof_matched_rows=40/40。
- cache_manifest_rows=456，actual_cache_rows_per_materialized_row=11.4。
- baseline_cache_rows_per_materialized_row=42.075。
- route_reduction_vs_baseline=0.7291。
- route_error_count=0。
- future_data_violation_count=0。

Readiness:
- ready_for_core_t164_pruned_source_package_review=true
- ready_for_core_t164_broader_ingest_contract=false
- ready_for_core_t164_broader_materialization=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true

仍非 full universe：
- TPEx all-stock proof not complete。
- full period range not complete。
- capex_proxy / receivables_trade human_review_proxy_label_required。
- unmatched/ambiguous policy remains blocked/no silent fill。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
