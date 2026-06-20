# BACKTEST_LAB Factor Input Data Package 2024-2026

- package_status: backtest_factor_package_partial
- ready: false
- decision_layer: data_readiness
- active_in_trade_decision: false
- period: 2024-01-02 to 2026-05-26
- expected_stock_tickers: 2308.TW, 2317.TW, 2330.TW, 2382.TW, 2454.TW, 3231.TW, 6669.TW

## Core Validator Source Paths
- institutional_flows: `data/formal_sources/backtest_factor_2024_2026/institutional_flows_daily_20240102_20260526.csv`
- margin_short: `data/formal_sources/backtest_factor_2024_2026/margin_short_daily_20240102_20260526.csv`
- day_trading: `data/formal_sources/backtest_factor_2024_2026/day_trading_daily_20240102_20260526.csv`

## Readiness
- institutional_flows: status=ready, source_start=2024-01-02, source_end=2026-05-26, fresh_coverage_ratio=0.998019, coverage_threshold_met=true, source_validator_ready=true, future_data_violation_count=0
- margin_short: status=ready, source_start=2024-01-02, source_end=2026-05-26, fresh_coverage_ratio=1.000000, coverage_threshold_met=true, source_validator_ready=true, future_data_violation_count=0
- day_trading: status=ready, source_start=2024-01-02, source_end=2026-05-26, fresh_coverage_ratio=0.994058, coverage_threshold_met=true, source_validator_ready=true, future_data_violation_count=0
- valuation: status=blocked, source_start=n/a, source_end=n/a, fresh_coverage_ratio=0.000000, coverage_threshold_met=false, source_validator_ready=false, future_data_violation_count=0

## Guardrails
- This package is not a trade signal and is not active in the formal trade decision layer.
- Valuation remains blocked because a point-in-time official source has not been ingested.
- Do not use later manual snapshots to backfill historical valuation factors.
