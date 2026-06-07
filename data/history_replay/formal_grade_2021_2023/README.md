# Formal Grade Historical Radar Audit

This folder is a formal-grade readiness audit, not a formal-grade replay dataset.

- ready_for_formal_strategy_conclusion: false
- readiness_status: blocked_source_data_unavailable
- source_snapshot_count: 507
- formal_universe_symbol_count: 69
- excluded_missing_ohlcv_symbol_count: 91

Blocking items:
- point_in_time_fundamentals: Only baseline/carry-forward stock metrics are available in this repo; there is no historical financial announcement or acquisition-date table.
- date_aware_theme_membership: theme_map.csv has no effective_start/effective_end/source_date fields, so current classifications cannot be safely replayed as historical membership.
- official_exchange_turnover: The historical cache used by the replay contains OHLCV only; turnover_value was computed as close * volume, not official TWSE/TPEx turnover amount.

Conclusion:

目前資料只能支援研究草稿，不能支援正式雷達個股輪動策略結論。
