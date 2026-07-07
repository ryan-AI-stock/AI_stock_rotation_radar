# Layer1 t164 full/broader source materialization runner package

Status: broader_seed_source_materialization_package_ready_not_full_universe

結論：
- 已建立可重跑的 broader seed materialization runner/source package。
- coverage: 20 tickers x 2 periods = 40 rows；TWSE + TPEx。
- statement_success_rows=40/40。
- official_asof_matched_rows=40/40。
- raw cache/hash manifest rows=1683。
- route_error_count=0。
- future_data_violation_count=0。

Readiness:
- ready_for_core_t164_broader_source_package_review=true
- ready_for_core_t164_broader_ingest_contract=false
- ready_for_core_t164_broader_materialization=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- not_live_rule=true

仍非 full universe：
- agreed full ticker universe 尚未由 Core/Strategy formally materialize。
- full period range 仍未全跑。
- TPEx 是 broader bounded seed evidence，不是 all-stock universal readiness。
- capex_proxy / receivables_basket 仍需 human-review label policy。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
