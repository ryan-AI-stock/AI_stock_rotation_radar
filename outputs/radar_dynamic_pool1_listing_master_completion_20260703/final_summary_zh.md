# Dynamic Pool1 listing master completion

- Task: `TASK-RADAR-DATA-DYNAMIC-POOL1-LISTING-MASTER-COMPLETION-20260703`
- Status: `completed_partial_improved_twse_status_coverage_but_master_ready_false`
- Previous accepted event rows: `557`
- Current accepted event rows total: `5994`
- Delta vs previous: `5437`
- Listing/delisting rows: `379`
- Suspension/status rows: `5582`
- Code/name change rows: `33`
- Transfer listing rows: `0`
- Source probe attempts: `425`
- future_data_violation_count: `0`
- listing_delisting_suspension_metadata_ready: `false`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`

## Improvements

- Added TWSE `TWTAWU` 2015-01 to 2026-07 monthly range sweep for suspended/resumed securities.
- Added TWSE `TWT85U` first/last trading-day monthly status snapshots from 2015-01 to 2026-07.
- Added current official disposition/status probes and MOPS date-query security-block evidence.

## Remaining blockers

- TPEx complete historical listing/delisting/removal master is still blocked.
- TPEx 2015-2025 historical suspension/resumption archive is still blocked; OpenAPI ignored historical parameters.
- Code/name change and transfer listing full history remains blocked; MOPS date query returned security block page.
- TWSE altered-trading status is only monthly anchor sampled in this package; full daily TWT85U sweep remains a next step.

No strategy replay, formal model change, trade decision change, or report change was made.
