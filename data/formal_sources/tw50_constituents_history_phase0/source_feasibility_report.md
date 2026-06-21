# TW50 / 0050 Point-in-Time Constituents History Phase 0

Status: `partial_blocked`

This package evaluates how to obtain point-in-time Taiwan 50 / 0050
constituents for BACKTEST_LAB pool 2 historical replay. It does not provide
ready historical constituents and must not be used as formal replay input.

## Contract Read

Core contract read from BACKTEST_LAB:

- `docs/tw50_constituents_data_contract.md`
- default target file: `data/tw50_constituents.csv`
- required columns: `effective_date,ticker`
- recommended columns: `effective_date,end_date,ticker,name,source,source_updated_at`
- ready rule: every tested signal date must have at least 45 active
  constituents, and each target period must reach coverage ratio >= 0.95.

Current Core limitation:

- existing seed starts at `2025-06-23`
- 2022 coverage: 0%
- 2023 coverage: 0%
- 2024-2026 coverage: partial

## Source Feasibility

### 1. FTSE Russell current constituents PDF

- Candidate URL:
  `https://research.ftserussell.com/analytics/factsheets/Home/DownloadConstituentsWeights/?indexdetails=TW50`
- Existing Core updater can parse this style of PDF for a current snapshot.
- Feasibility: good for latest/current snapshot only.
- Blocker: no verified public historical archive endpoint was confirmed in this
  pass for 2022-01-03 to 2026-06-18.
- Decision: do not use latest PDF to backfill historical dates.

### 2. Taiwan Index / official index company notices

- Candidate type: dated index review / constituent change announcements.
- Feasibility: potentially formal if historical notices can be obtained with
  exact effective dates.
- Blocker: needs a baseline constituent list before 2022 plus every add/delete
  event through 2026-06-18. Search in this pass did not confirm a complete,
  machine-readable, public archive.
- Decision: keep as preferred official route, but not ready.

### 3. Yuanta 0050 fund reports / holdings disclosures

- Candidate type: dated ETF holdings or monthly/periodic reports.
- Feasibility: potentially useful as a point-in-time proxy for 0050 holdings.
- Blocker: must verify whether reports contain full holdings, exact report
  dates, and redistribution rights. ETF holdings may differ from index
  constituents around rebalance/cash events.
- Decision: acceptable only after user confirms this proxy is allowed and
  license/use boundary is acceptable.

### 4. Public secondary pages / community-maintained change lists

- Candidate type: public pages that list TW50 changes.
- Feasibility: useful for research hints and cross-checking.
- Blocker: not official, license unclear, and not enough for formal replay.
- Decision: may guide manual review, but cannot be accepted as formal source.

## Recommended Data Model

Use an event/snapshot hybrid, not a current-list backfill.

Minimum accepted row:

```text
effective_date,end_date,ticker,name,source,source_url,source_published_date,source_updated_at,review_status,usable_for_formal_replay,notes
```

Rules:

- `effective_date` must be the first valid date for that ticker in TW50 / 0050.
- `end_date` should be filled when a constituent leaves.
- `source_url` and `source_published_date` are required before a row can be
  reviewed as formal.
- `review_status=accepted` is required before Core may treat the row as formal.
- `usable_for_formal_replay=false` unless accepted.

## Current Phase 0 Output

Files in this package:

- `tw50_constituents_source_candidates.csv`
- `tw50_constituents_source_pending.csv`
- `tw50_constituents_history_readiness.json`
- `source_feasibility_report.md`

`tw50_constituents_source_pending.csv` is schema-only. It intentionally has no
constituent rows, because no source in this pass met the formal point-in-time
acceptance bar.

## Blockers

1. No complete official historical snapshot set for 2022-01-03 to 2026-06-18
   has been verified.
2. No official baseline list as of 2022-01-03 has been accepted.
3. No complete dated add/delete ledger through 2026-06-18 has been accepted.
4. Yuanta ETF holdings may be usable only if the user accepts it as a proxy and
   the license boundary is clear.
5. Secondary-source change lists are not formal enough for replay.

## User Decision Needed

Choose one route:

1. Official-only route: find/download official historical Taiwan 50 review
   notices and reconstruct a ledger. Slowest, strongest formal quality.
2. Fund-report proxy route: use dated 0050 holdings/monthly reports if
   licensing and proxy assumptions are acceptable. Faster, but must be labeled
   as ETF holdings proxy, not pure index constituents.
3. Manual evidence ledger route: manually build baseline + change events from
   official PDFs/notices, one event at a time, with review status.

Until one route is chosen and accepted rows cover the target periods, Core
validator must remain `partial_blocked` or `blocked_no_historical_coverage`.

