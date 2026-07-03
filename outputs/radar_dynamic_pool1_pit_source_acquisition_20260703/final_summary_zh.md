# Dynamic Pool1 PIT source acquisition package

- Task: `TASK-RADAR-DATA-DYNAMIC-POOL1-PIT-SOURCE-ACQUISITION-20260703`
- Status: `completed_partial_sources_but_core_ready_false`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`
- dynamic_pool1_shadow_challenger_ready: `false`
- future_data_violation_count: `0`

## Partial-ready sources

- `monthly_revenue_pit`: existing MOPS monthly revenue PIT v1 has release/available-date pattern, but only covers the existing formal universe and 2021-12~2023-12.
- `all_listed_liquid_universe_pit_daily` component: official turnover v1 is a usable partial daily official turnover component for liquidity screening, but the full universe still needs listing/delisting/suspension PIT metadata.

## Still blocked

- all-listed liquid universe PIT daily
- quarterly fundamentals PIT
- historical market cap PIT
- sector/mainline PIT membership
- sector/mainline breadth daily

## Boundary

Current/generated/static sector maps, current AI theme lists, current market universe, and 0050/TW50-specific PIT candidates are not promoted to Dynamic Pool1 formal sources.
