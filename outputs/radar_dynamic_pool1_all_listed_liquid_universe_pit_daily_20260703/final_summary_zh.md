# Dynamic Pool1 all-listed liquid universe PIT daily source package

- Task: `TASK-RADAR-DATA-DYNAMIC-POOL1-ALL-LISTED-LIQUID-UNIVERSE-PIT-DAILY-20260703`
- Status: `completed_partial_sample_verified`
- Accepted liquidity rows: `20418`
- Blocked/rejected rows total: `75481`
- `blocked_rows.csv` mode: first 5,000 row sample plus `blocked_rows_summary.csv`
- Download attempts: `24`
- Successful official daily attempts: `24`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`
- dynamic_pool1_shadow_challenger_ready: `false`
- future_data_violation_count: `0`

## Accepted partial source

TWSE `MI_INDEX?type=ALLBUT0999` and TPEx `dailyQuotes` official daily endpoints were verified from 2015 sample dates through latest sample date. Accepted rows are common-stock rows present in that date's official daily table with parseable OHLCV/turnover fields; ETF/ETN/warrant-style codes such as `00xx` are excluded.

## Not yet formal-ready

This is not full-range ready. The package verifies the source route, parser, schema, and checkpointable runner, but the complete 2015-latest daily sweep has not been run in this batch.

Listing/delisting/suspension master metadata is still blocked. Current TWSE/TPEx company profile OpenAPI routes are listed as current-snapshot inventory only and were not used to infer historical PIT membership.

## Boundary

No current listed snapshot is used to backfill 2015. No strategy replay, formal model change, trade decision change, or daily report change was made.
