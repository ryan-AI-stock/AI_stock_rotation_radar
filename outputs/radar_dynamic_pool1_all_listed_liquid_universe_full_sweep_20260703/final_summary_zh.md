# Dynamic Pool1 all-listed liquid universe full daily sweep

- Task: `TASK-RADAR-DATA-DYNAMIC-POOL1-ALL-LISTED-LIQUID-UNIVERSE-FULL-SWEEP-20260703`
- Status: `completed_full_sweep_candidate`
- Requested range: `2015-01-01` to `2026-07-02`
- Covered row range: `2015-01-05` to `2026-07-02`
- Expected market-date attempts: `6002`
- Completed attempts: `6002`
- Failed attempts: `0`
- Missing attempts: `0`
- Accepted liquidity rows: `4769784`
- Accepted shard count: `139`
- all_listed_liquid_universe_pit_daily_full_range_ready: `true`
- listing_delisting_suspension_metadata_ready: `false`
- future_data_violation_count: `0`

## Storage

Large normalized accepted rows are stored locally under `shards/` and are intentionally not git-tracked. Git-tracked handoff files include shard manifest, download attempts, progress, coverage, audit, readiness, and summary.

## Boundary

No current listed snapshot is used to backfill 2015. No strategy replay, formal model change, trade decision change, or daily report change was made.
