# TPEx historical listing/status master

- Task: `TASK-RADAR-DATA-DYNAMIC-POOL1-TPEX-HISTORICAL-LISTING-STATUS-MASTER-20260703`
- Status: `blocked_with_attempt_evidence`
- Accepted TPEx 2015-2025 historical rows: `0`
- Accepted listing metadata rows: `0`
- Accepted suspension event rows: `0`
- Accepted status snapshot rows: `0`
- Current/carried TPEx 2026 rows from previous package: `236`
- Source probe attempts recorded: `7`
- future_data_violation_count: `0`
- full_cross_market_listing_master_ready: `false`
- ready_for_core_rerun: `true`

## What was confirmed

- Core latest readiness still marks TPEx 2015-2025 as the leading blocker.
- Previous TPEx OpenAPI `tpex_spendi_history` ignores historical parameters and returns current ROC year 115 rows.
- TPEx old `/web/stock/aftertrading/` root is reachable but bounded link extraction did not expose a direct historical spendi/cmode/delist route.
- TPEx new `stock-pricing.html` is valid, but the guessed status/disposal/suspension/altered pages returned TPEx 404 HTML.
- MOPS material-information date query remains security-blocked.

## Decision

No current snapshot, current-year row, or proxy row was accepted as 2015-2025 TPEx historical metadata. This package is intentionally blocked/partial with evidence, not formal-ready.

## Next programmable routes

- Reverse TPEx frontend table URL construction in `/rsrc/js/tables.js` for concrete page ids.
- Locate TPEx official archived downloads for terminated listings/removals and transfer-to-TWSE events.
- Use browser/devtools exact request extraction for TPEx or MOPS only if approved.
