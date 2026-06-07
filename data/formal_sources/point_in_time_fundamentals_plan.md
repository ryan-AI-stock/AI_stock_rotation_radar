# Point-In-Time Fundamentals Plan

## Goal

Upgrade from `fundamental_mode=limited_baseline_seed_carry_forward` to either:

- `fundamental_mode=point_in_time`
- `fundamental_mode=point_in_time_limited`

## Required Schema

```csv
symbol,name,metric_name,metric_value,period,announcement_date,available_date,source_type,source_url,ingested_at
```

## Candidate Sources

1. MOPS monthly revenue
   - Use for monthly revenue YoY/MoM.
   - Must preserve announcement or market-available date.
   - Useful for revenue trend and basic growth filters.
   - Source entry: https://mops.twse.com.tw/mops/web/ezsearch

2. MOPS financial statements
   - Use quarterly or annual statements.
   - Must preserve financial report announcement date.
   - Useful for EPS, margin, book value, debt ratio, or other accounting fields if needed.
   - Source entry: https://mops.twse.com.tw/mops/web/ezsearch

3. MOPS major announcements
   - Use when a company self-announces unaudited monthly or quarterly profit/loss.
   - Must treat announcement timestamp/date as availability boundary.
   - Source entry: https://mops.twse.com.tw/mops/web/ezsearch

## Current Gap

The repo currently has `data/stock_metrics.csv` and dated `fundamental_snapshot_*.csv`, but these are not historical point-in-time datasets. The historical replay seeded a baseline file and carried it forward. That is correct for fail-closed research, but not formal-grade.

## Feasibility

Status: `partially_feasible_needs_new_ingestion`.

Reason:

- MOPS has the needed categories, but this repo does not yet normalize those records into a point-in-time table.
- Historical announcement dates and source URLs must be captured before using fundamentals in a formal replay.
- If only monthly revenue can be reliably fetched first, the mode should be `point_in_time_limited`, not full `point_in_time`.

## Validation Rules

1. `available_date <= snapshot_date` for every joined metric.
2. No row may use a metric announced after the replay date.
3. Missing fundamentals must fail closed or explicitly downgrade the candidate bucket.
4. Coverage must be reported by symbol, date, metric, and theme.

## Minimum Acceptable First Version

Build `point_in_time_fundamentals.csv` using monthly revenue only:

- Coverage target: formal universe 69 symbols.
- Date range: 2021-12-01 to 2023-12-31.
- Mode if incomplete: `point_in_time_limited`.
- Missing symbols must be listed in `point_in_time_fundamentals_gap.csv`.

## Can This Make Formal Ready Now?

No. The source table does not exist yet.
