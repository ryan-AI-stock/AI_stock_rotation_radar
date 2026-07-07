# Layer1 t164 TPEx phase_1 50x2 bounded proof runner

Status: phase1_tpex_50x2_bounded_proof_executed_not_full_universe

結論：
- phase_1 已依 Core contract 執行 50 TPEx tickers x 2 periods bounded proof runner。
- statement_success_rows=100/100。
- official_asof_matched_rows=85/100。
- cache_manifest_rows=779，actual_cache_rows_per_materialized_row=7.79。
- raw_cache files are kept local with raw_cache/.gitignore; response hashes and paths are recorded in raw_cache_hash_manifest.csv。
- baseline_cache_rows_per_materialized_row=42.075。
- route_reduction_vs_baseline=0.8149。
- route_error_count=0。
- future_data_violation_count=0。

Readiness:
- ready_for_core_t164_tpex_phase1_proof_review=true
- ready_for_core_t164_tpex_all_stock_proof_readiness_update=false
- ready_for_core_t164_broader_ingest_contract=false
- ready_for_core_t164_broader_materialization=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true

仍非 full universe：
- current-or-carried TPEx universe 只作 sampling；不可宣稱 historical PIT all-stock universe。
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
