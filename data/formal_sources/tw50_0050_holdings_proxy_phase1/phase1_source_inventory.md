# TW50/0050 Holdings Proxy Phase 1 Source Inventory

Task ID: `TASK-RADAR-TW50-0050-HOLDINGS-PROXY-PHASE1-001`

Date: 2026-06-21

## Decision Context

The selected Phase 1 route is to use Yuanta 0050 holdings as a stable proxy source.
This is not an exact point-in-time TW50 official constituent history source.

Source mode:

- `source_mode`: `yuanta_0050_holdings_proxy`
- `is_proxy`: `true`
- `exact_tw50_official_constituents`: `false`
- `formal_ready`: `false`

## Current Source Findings

Yuanta official fund pages expose direct PDF download URLs for current public reports.
The following URLs were checked from this workspace on 2026-06-21:

| Source | URL | File type | Check result |
| --- | --- | --- | --- |
| Yuanta 0050 monthly report | `https://www.yuantafunds.com/fund/download/1066元大台灣卓越50基金月報.pdf` | PDF | Download OK, 425671 bytes |
| Yuanta domestic fund quarterly holdings | `https://www.yuantafunds.com/fund/download/元大國內基金季持股.pdf` | PDF | Download OK, 542696 bytes |

The current/latest PDF route is therefore usable for scheduled source checks.
However, this pass did not confirm a stable month-specific historical URL pattern
for 2022-01 through current. The current monthly-report URL may point to the
latest overwritten report rather than a dated archive.

## Feasibility Judgment

Phase 1 status: `source_inventory_partial`

The Yuanta 0050 holdings proxy route is feasible as the main practical route if
the project accepts this data口徑:

- Use 0050 ETF/fund holdings disclosure as a proxy for TW50 large-cap pool history.
- Preserve source date and file date on every row.
- Never label these rows as exact TW50 official constituent history.
- Use official index review notices only as cross-check evidence for additions
  and deletions, not as the main maintenance path.

Open gaps:

1. Historical archive coverage from 2022-01 to current is not yet verified.
2. Current local environment does not have a PDF text extraction package/tool
   available in this repo session, so PDF table parsing is not yet validated here.
3. License and redistribution wording still needs review before publishing a
   redistributed historical dataset.

## Cross-Check Role For Official Notices

Official TW50 / Taiwan index review notices should be stored as event evidence:

- review_date
- effective_date
- added_tickers
- removed_tickers
- source_url
- source_file
- note

These events can validate whether the Yuanta holdings proxy reflects the same
major entry/exit changes around review dates. They should not replace monthly
or quarterly holdings snapshots for this Phase 1 route.

## Manual Fallback Role

Manual evidence ledger is fallback only. It should be used when:

- A historical Yuanta PDF cannot be downloaded automatically.
- A PDF table cannot be parsed reliably.
- A date has conflicting proxy and official review evidence.
- A source has license/status uncertainty and requires human approval.

Fallback fields should include:

- snapshot_date
- effective_date
- ticker
- name
- source_mode
- is_proxy
- source_url
- source_file
- parse_status
- review_status
- reviewer
- notes

## Core Contract Recommendation

Core should not feed this package into the existing exact TW50 constituent
validator as if it were official point-in-time index membership.

Recommended next Core change:

1. Add a proxy-specific readiness path, for example
   `tw50_holdings_proxy_readiness`.
2. Require `source_mode=yuanta_0050_holdings_proxy` and `is_proxy=true`.
3. Validate monthly or quarterly snapshot coverage separately from exact index
   effective-date coverage.
4. Keep exact TW50 validator fail-closed unless an official exact historical
   constituent source is provided.

## Next Step

Build the Phase 1 collector/parser in small steps:

1. Add a download checker for current Yuanta 0050 monthly report and domestic
   quarterly holdings PDF.
2. Add PDF extraction dependency or parsing workflow.
3. Create a first dated sample from one verified PDF.
4. Search for a stable historical archive route. If no archive exists, ask
   whether manual historical PDF download is acceptable for 2022-2026 backfill.
